"""Walk detected entities, splice in same-length mocks, build a diff for the UI.

Char offsets are 1:1 with the original page text because every mock has the
same length as its source. That means downstream image redaction can use
the existing :func:`app.pii_v2.text_layout.char_to_bbox` resolver without
any offset arithmetic.
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.pii_v2.redaction.mock_generators import mock_for
from app.pii_v2.schema import PIIEntity
from app.pii_v2.text_layout import RegionSpan, char_to_bbox

logger = logging.getLogger(__name__)


@dataclass
class DiffSpan:
    """One redacted span — what the UI renders side-by-side."""

    start: int
    end: int
    original: str
    mock: str
    entity_type: str
    bbox_px: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "original": self.original,
            "mock": self.mock,
            "entity_type": self.entity_type,
            "bbox_px": self.bbox_px,
        }


@dataclass
class TextRedactionResult:
    redacted_text: str
    diff_spans: List[DiffSpan]
    # mock_to_original: cipher mapping the LLM output uses to restore.
    # original_to_mock: helper for the UI mapping table.
    mock_to_original: Dict[str, str] = field(default_factory=dict)
    original_to_mock: Dict[str, str] = field(default_factory=dict)
    entity_types: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "n_entities": len(self.diff_spans),
            "n_mocks": len(self.mock_to_original),
            "entity_types": dict(self.entity_types),
        }


def _seeded_rng(pii_run_id: str, original: str, entity_type: str) -> random.Random:
    """Per-run, per-value deterministic rng.

    Same (pii_run_id, value, entity_type) → same mock across every cell of
    the run. A fresh pii_run_id (re-run) gets fresh mocks.
    """
    seed_bytes = hashlib.sha256(
        f"{pii_run_id}::{entity_type}::{original}".encode("utf-8")
    ).digest()
    return random.Random(int.from_bytes(seed_bytes[:8], "big"))


def _resolve_overlaps(entities: Iterable[PIIEntity]) -> List[PIIEntity]:
    """Drop overlapping spans — keep the highest-score / earlier-start span.

    The merger upstream should have already done this, but redaction has
    to be defensive: splicing overlapping replacements at the same offset
    would corrupt the text.
    """
    sorted_ents = sorted(entities, key=lambda e: (e.start, -e.score))
    kept: List[PIIEntity] = []
    last_end = -1
    for e in sorted_ents:
        if e.start < last_end:
            continue
        kept.append(e)
        last_end = e.end
    return kept


def redact_text(
    *,
    pii_run_id: str,
    text: str,
    entities: Iterable[PIIEntity],
    region_index: Optional[List[RegionSpan]] = None,
) -> TextRedactionResult:
    """Produce ``TextRedactionResult`` for one page of joined OCR text.

    The mocks are stable within a pii_run — identical originals on
    different pages / different cells get the same mock — so the mapping
    table can be consolidated at the document level by the caller.
    """
    if not text or not entities:
        return TextRedactionResult(redacted_text=text or "", diff_spans=[])

    safe_entities = _resolve_overlaps(entities)
    mock_to_original: Dict[str, str] = {}
    original_to_mock: Dict[str, str] = {}
    entity_types: Dict[str, int] = {}
    diff_spans: List[DiffSpan] = []
    parts: List[str] = []
    cursor = 0

    for ent in safe_entities:
        if ent.start < cursor:
            # Shouldn't happen after _resolve_overlaps, but guard anyway.
            continue
        original = text[ent.start : ent.end]
        if not original:
            continue
        # Look up an existing mock for this (value, entity_type), else
        # generate a fresh one. Identical originals share a mock so the
        # diff + mapping table stays small.
        key = (original, ent.entity_type)
        mock = original_to_mock.get(_keystr(key))
        if mock is None:
            rng = _seeded_rng(pii_run_id, original, ent.entity_type)
            mock = mock_for(ent.entity_type, original, rng)
            original_to_mock[_keystr(key)] = mock
            mock_to_original[mock] = original
        entity_types[ent.entity_type] = entity_types.get(ent.entity_type, 0) + 1

        # Splice.
        parts.append(text[cursor : ent.start])
        parts.append(mock)
        cursor = ent.end

        bbox = (
            char_to_bbox(ent.start, ent.end, region_index)
            if region_index
            else None
        )
        diff_spans.append(DiffSpan(
            start=ent.start,
            end=ent.end,
            original=original,
            mock=mock,
            entity_type=ent.entity_type,
            bbox_px=bbox,
        ))

    parts.append(text[cursor:])
    redacted_text = "".join(parts)

    if len(redacted_text) != len(text):
        # The whole point of same-length mocks is that offsets are stable.
        # If anything diverges here it's a generator bug — log loudly.
        logger.error(
            "redaction length mismatch: original=%d redacted=%d — char-bbox alignment compromised",
            len(text), len(redacted_text),
        )

    return TextRedactionResult(
        redacted_text=redacted_text,
        diff_spans=diff_spans,
        mock_to_original=mock_to_original,
        original_to_mock={k.split("::", 1)[1]: v for k, v in original_to_mock.items()},
        entity_types=entity_types,
    )


def _keystr(key: Tuple[str, str]) -> str:
    """Tuple → str so the dict can be JSON-serialised later if needed."""
    return f"{key[1]}::{key[0]}"
