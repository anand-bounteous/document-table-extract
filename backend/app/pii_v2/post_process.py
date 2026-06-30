"""Post-process steps run after every detector.

Pipeline (in order):

1. ``substring_search`` — connects shortname mentions (e.g. ``"John"``)
   to fullname detections (e.g. ``"John Smith"``) elsewhere in the doc.
2. ``fallback_search`` — for each unique entity text the detector
   returned across the doc, sweep every page's text and add any
   occurrences the detector missed (tagged ``discovery="search_only"``).
3. ``manual_overlay`` — merge the document's manual annotations
   (see ``app.pii_v2_manual_store``). Lib + manual matches are tagged
   ``"both"``; manual-only ones are tagged ``"manual_only"``.
4. ``occurrence_count`` — aggregate per ``(text, entity_type)`` →
   ``{page_count, doc_count, by_source}`` for the dashboard.

Inputs: ``per_page_entities`` = ``{page_index: [PIIEntity, ...]}`` and
``text_by_page`` = ``{page_index: str}``. Returns the (mutated) per-page
entity dict plus the occurrence stats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.pii_v2.audit import AuditCollector
from app.pii_v2.schema import PIIEntity


@dataclass
class OccurrenceEntry:
    text: str
    entity_type: str
    page_count: int
    doc_count: int
    by_source: Dict[str, int]   # {"lib", "search_only", "manual_only", "both"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "page_count": self.page_count,
            "doc_count": self.doc_count,
            "by_source": self.by_source,
        }


def _key(text: str, entity_type: str) -> str:
    return f"{text}::{entity_type}"


def _has_overlap(a: PIIEntity, others: List[PIIEntity]) -> bool:
    for o in others:
        if a.entity_type == o.entity_type and not (a.end <= o.start or o.end <= a.start):
            return True
    return False


SUBSTRING_PARENT_TYPES = {"PERSON", "UK_ADDRESS"}


def substring_search(
    per_page_entities: Dict[int, List[PIIEntity]],
    text_by_page: Dict[int, str],
) -> List[Tuple[int, PIIEntity]]:
    """For each PERSON / UK_ADDRESS detection, find shorter mentions in the doc."""
    parents: List[Tuple[int, PIIEntity]] = []
    for page_index, ents in per_page_entities.items():
        for e in ents:
            if e.entity_type in SUBSTRING_PARENT_TYPES and len(e.text.split()) >= 2:
                parents.append((page_index, e))

    added: List[Tuple[int, PIIEntity]] = []
    seen_keys: set[tuple[int, int, int]] = set()  # (page, start, end)
    for parent_page, parent in parents:
        # Tokens of length >= 3 to avoid matching tiny prepositions.
        tokens = [t for t in parent.text.split() if len(t) >= 3]
        for token in tokens + [parent.text]:
            if token == parent.text:
                # Skip the parent's own page-and-position
                continue
            pattern = re.compile(rf"\b{re.escape(token)}\b")
            for page_index, page_text in text_by_page.items():
                for match in pattern.finditer(page_text):
                    span = (page_index, match.start(), match.end())
                    if span in seen_keys:
                        continue
                    # Don't add if this overlaps an existing detection of the
                    # same entity type on this page (the lib found it already).
                    existing = per_page_entities.get(page_index, [])
                    candidate = PIIEntity(
                        entity_type=parent.entity_type,
                        text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        score=parent.score * 0.8,
                        source="substring",
                        detection_method="post_process",
                        jurisdiction=parent.jurisdiction,
                        risk_level=parent.risk_level,
                        sensitivity_category=parent.sensitivity_category,
                        metadata={
                            "discovery": "substring_of",
                            "parent_text": parent.text,
                            "parent_page": parent_page,
                        },
                    )
                    if _has_overlap(candidate, existing):
                        continue
                    seen_keys.add(span)
                    added.append((page_index, candidate))
    return added


def fallback_search(
    per_page_entities: Dict[int, List[PIIEntity]],
    text_by_page: Dict[int, str],
) -> List[Tuple[int, PIIEntity]]:
    """For each unique detected entity text, search every page for missed occurrences."""
    unique_texts: Dict[str, PIIEntity] = {}
    for ents in per_page_entities.values():
        for e in ents:
            key = _key(e.text, e.entity_type)
            unique_texts.setdefault(key, e)

    added: List[Tuple[int, PIIEntity]] = []
    seen_keys: set[tuple[int, int, int]] = set()
    for _, source_entity in unique_texts.items():
        text_value = source_entity.text.strip()
        if len(text_value) < 3:
            continue
        pattern = re.compile(rf"(?i)\b{re.escape(text_value)}\b")
        for page_index, page_text in text_by_page.items():
            for match in pattern.finditer(page_text):
                span = (page_index, match.start(), match.end())
                if span in seen_keys:
                    continue
                existing = per_page_entities.get(page_index, [])
                candidate = PIIEntity(
                    entity_type=source_entity.entity_type,
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    score=source_entity.score * 0.7,
                    source="fallback_search",
                    detection_method="post_process",
                    jurisdiction=source_entity.jurisdiction,
                    risk_level=source_entity.risk_level,
                    sensitivity_category=source_entity.sensitivity_category,
                    metadata={"discovery": "search_only", "source_value": text_value},
                )
                if _has_overlap(candidate, existing):
                    continue
                seen_keys.add(span)
                added.append((page_index, candidate))
    return added


def manual_overlay(
    per_page_entities: Dict[int, List[PIIEntity]],
    manual_annotations: List[Dict[str, Any]],
) -> List[Tuple[int, PIIEntity]]:
    """Merge manual annotations as virtual detections, tagging discovery accordingly.

    Each manual entry: {page_index, entity_type, text, bbox_px?}. We try to
    find the text on the matching page (case-insensitive substring); if found
    and the detector also returned a same-type overlapping span, the LIB span
    keeps but its metadata gets ``discovery: both``. Manual-only entries are
    added with ``discovery: manual_only``.
    """
    added: List[Tuple[int, PIIEntity]] = []
    for ann in manual_annotations:
        page_index = int(ann.get("page_index", -1))
        if page_index < 0:
            continue
        text_value = str(ann.get("text", "")).strip()
        entity_type = str(ann.get("entity_type", "MANUAL")).strip()
        if not text_value:
            continue
        existing = per_page_entities.get(page_index, [])
        matched_existing = False
        for e in existing:
            if e.entity_type == entity_type and e.text.casefold() == text_value.casefold():
                e.metadata.setdefault("discovery", "lib")
                if e.metadata["discovery"] == "lib":
                    e.metadata["discovery"] = "both"
                e.metadata["manual_annotation_id"] = ann.get("annotation_id")
                matched_existing = True
                break
        if matched_existing:
            continue
        added.append((page_index, PIIEntity(
            entity_type=entity_type,
            text=text_value,
            start=int(ann.get("start", -1)),
            end=int(ann.get("end", -1)),
            score=1.0,
            source="manual",
            detection_method="manual",
            jurisdiction=ann.get("jurisdiction"),
            metadata={
                "discovery": "manual_only",
                "annotation_id": ann.get("annotation_id"),
                "bbox_px": ann.get("bbox_px"),
            },
        )))
    return added


def occurrence_count(
    per_page_entities: Dict[int, List[PIIEntity]],
) -> Dict[str, OccurrenceEntry]:
    """Aggregate (text, entity_type) → per-page + per-doc counts split by discovery."""
    out: Dict[str, OccurrenceEntry] = {}
    per_page: Dict[str, Dict[int, int]] = {}
    for page_index, ents in per_page_entities.items():
        for e in ents:
            key = _key(e.text, e.entity_type)
            entry = out.get(key)
            if entry is None:
                entry = OccurrenceEntry(
                    text=e.text,
                    entity_type=e.entity_type,
                    page_count=0,
                    doc_count=0,
                    by_source={"lib": 0, "search_only": 0, "manual_only": 0, "both": 0},
                )
                out[key] = entry
                per_page[key] = {}
            entry.doc_count += 1
            per_page[key][page_index] = per_page[key].get(page_index, 0) + 1
            discovery = (e.metadata or {}).get("discovery", "lib")
            if discovery not in entry.by_source:
                entry.by_source[discovery] = 0
            entry.by_source[discovery] += 1
    for key, page_counts in per_page.items():
        out[key].page_count = len(page_counts)
    return out


def run_post_process(
    *,
    per_page_entities: Dict[int, List[PIIEntity]],
    text_by_page: Dict[int, str],
    manual_annotations: Optional[List[Dict[str, Any]]] = None,
    audit: Optional[AuditCollector] = None,
) -> Tuple[Dict[int, List[PIIEntity]], Dict[str, OccurrenceEntry]]:
    """Run the full post-process chain in order and return mutated entities + occurrences."""
    from contextlib import nullcontext

    n_in = sum(len(v) for v in per_page_entities.values())

    with audit.time("substring_search", "pii_v2.post_process.substring") if audit else nullcontext() as step:
        added = substring_search(per_page_entities, text_by_page)
        for page_index, e in added:
            per_page_entities.setdefault(page_index, []).append(e)
        if step is not None:
            step.outputs = [f"added:{len(added)}"]

    with audit.time("fallback_search", "pii_v2.post_process.fallback") if audit else nullcontext() as step:
        added = fallback_search(per_page_entities, text_by_page)
        for page_index, e in added:
            per_page_entities.setdefault(page_index, []).append(e)
        if step is not None:
            step.outputs = [f"added:{len(added)}"]

    if manual_annotations:
        with audit.time("manual_overlay", "pii_v2.post_process.manual") if audit else nullcontext() as step:
            added = manual_overlay(per_page_entities, manual_annotations)
            for page_index, e in added:
                per_page_entities.setdefault(page_index, []).append(e)
            if step is not None:
                step.outputs = [f"added:{len(added)}"]

    with audit.time("occurrence_count", "pii_v2.post_process.occurrences") if audit else nullcontext() as step:
        occurrences = occurrence_count(per_page_entities)
        if step is not None:
            n_out = sum(len(v) for v in per_page_entities.values())
            step.metadata["n_in"] = n_in
            step.metadata["n_out"] = n_out
            step.outputs = [f"unique_values:{len(occurrences)}"]

    return per_page_entities, occurrences
