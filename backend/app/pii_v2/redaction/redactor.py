"""Cell-level redaction orchestrator — the single public entry point.

Writes five artifacts to disk per ``(pii_run × doc × page × ocr × detector)``:

  mapping.fernet         encrypted {mock: original}
  mapping.index.json     entity-type counts (plaintext-safe)
  redacted_text.txt      page text with mocks spliced in
  redacted_page.png      page image with PII bboxes whited + mock text drawn
  diff.json              [{start, end, original, mock, entity_type, bbox_px}]

The summary returned (small ``RedactionArtifacts`` dataclass) is stamped
into the cell summary by the caller so the dashboard can show a
"🛡 redacted: N" chip and link straight to the Redaction tab.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.pii_v2.redaction.image_redactor import redact_image
from app.pii_v2.redaction.mapping import RedactionMapping, save_encrypted, save_index
from app.pii_v2.redaction.text_redactor import redact_text
from app.pii_v2.schema import PIIEntity
from app.pii_v2.text_layout import RegionSpan

logger = logging.getLogger(__name__)


@dataclass
class RedactionArtifacts:
    n_entities: int
    n_mocks: int
    entity_types: Dict[str, int] = field(default_factory=dict)
    has_image: bool = False
    out_dir: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_entities": self.n_entities,
            "n_mocks": self.n_mocks,
            "entity_types": self.entity_types,
            "has_image": self.has_image,
            "out_dir": self.out_dir,
            "error": self.error,
        }


def redact_cell(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
    text: str,
    entities: Iterable[PIIEntity],
    region_index: Optional[List[RegionSpan]] = None,
    page_image_path: Optional[Path] = None,
    out_dir: Path,
) -> RedactionArtifacts:
    """Eager redaction of one cell. Failures are caught + logged — never raise."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        ents_list = list(entities)
        if not text or not ents_list:
            return RedactionArtifacts(
                n_entities=0, n_mocks=0,
                out_dir=str(out_dir),
            )

        result = redact_text(
            pii_run_id=pii_run_id,
            text=text,
            entities=ents_list,
            region_index=region_index,
        )

        # text + diff
        (out_dir / "redacted_text.txt").write_text(result.redacted_text)
        (out_dir / "diff.json").write_text(
            json.dumps([d.to_dict() for d in result.diff_spans], indent=2)
        )

        # mapping (encrypted) + plaintext index
        mapping = RedactionMapping(
            pii_run_id=pii_run_id,
            document_id=document_id,
            page_index=page_index,
            ocr=ocr,
            detector=detector,
            mock_to_original=result.mock_to_original,
            entity_types=result.entity_types,
        )
        save_encrypted(mapping, out_dir / "mapping.fernet")
        save_index(mapping, out_dir / "mapping.index.json")

        # image (best effort — text redaction must work even when the
        # page image isn't available, e.g. for non-paired pii_runs that
        # haven't rasterised yet). We produce two variants:
        #   redacted_page.png            — clean image, what you feed to LLM
        #   redacted_page_annotated.png  — same image + bbox outlines for the UI
        has_image = False
        if page_image_path is not None and page_image_path.exists():
            png_clean = redact_image(page_image_path, result.diff_spans, annotate=False)
            if png_clean is not None:
                (out_dir / "redacted_page.png").write_bytes(png_clean)
                has_image = True
            png_annot = redact_image(page_image_path, result.diff_spans, annotate=True)
            if png_annot is not None:
                (out_dir / "redacted_page_annotated.png").write_bytes(png_annot)

        return RedactionArtifacts(
            n_entities=len(result.diff_spans),
            n_mocks=len(result.mock_to_original),
            entity_types=dict(result.entity_types),
            has_image=has_image,
            out_dir=str(out_dir),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "redaction failed for %s/%s/%s/page-%d", pii_run_id, document_id, ocr, page_index,
        )
        return RedactionArtifacts(
            n_entities=0, n_mocks=0,
            out_dir=str(out_dir),
            error=f"{type(exc).__name__}: {exc}",
        )
