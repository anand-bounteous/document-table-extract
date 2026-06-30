"""Derive a single page-level "doc format" label from layout region distribution.

Buckets the regions emitted by any layout-emitting solution by area and maps
the resulting distribution to one of:

    tabular-heavy | form-like | narrative | image-heavy | mixed | unknown

Idempotent: if a stage upstream already populated ``page.doc_format`` (e.g.
Layout-Parser writes it authoritatively from its own labels), this stage is a
no-op for that page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from app.core.schemas import Region, RegionType
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.doc_format")


_TABLE_TYPES = {
    RegionType.TABLE.value,
    RegionType.TABLE_HEADER.value,
    RegionType.TABLE_ROW.value,
    RegionType.TABLE_CELL.value,
}


@dataclass
class DocFormatStage:
    name: str = "layout_doc_format"
    tool: str = "doc_format_heuristic"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        for idx, page in state.pages.items():
            if page.doc_format:  # already set authoritatively upstream
                continue
            label, scores = classify_page(page.regions)
            page.doc_format = label
            page.doc_format_scores = scores
        return state


def classify_page(regions: List[Region]) -> tuple[str, Dict[str, float]]:
    """Return (label, scores). ``scores`` is the area-weighted fraction per bucket."""
    if not regions:
        return "unknown", {}

    area_by_bucket: Dict[str, float] = {
        "tables": 0.0,
        "figures": 0.0,
        "text": 0.0,
        "headings": 0.0,
        "lists": 0.0,
        "other": 0.0,
    }
    n_headings = 0

    for r in regions:
        area = max(0.0, float(r.bbox.w) * float(r.bbox.h))
        if area <= 0:
            continue
        layout_label = str((r.attributes or {}).get("layout_label") or "").lower()
        rtype = r.type.value if hasattr(r.type, "value") else str(r.type)

        if rtype in _TABLE_TYPES:
            area_by_bucket["tables"] += area
        elif rtype == RegionType.IMAGE.value:
            area_by_bucket["figures"] += area
        elif rtype == RegionType.NORMAL_TEXT.value:
            if layout_label == "list":
                area_by_bucket["lists"] += area
            else:
                area_by_bucket["text"] += area
        elif rtype == RegionType.KV_PAIR.value:
            if layout_label in ("title", "header"):
                area_by_bucket["headings"] += area
                n_headings += 1
            else:
                area_by_bucket["other"] += area
        else:
            area_by_bucket["other"] += area

    total = sum(area_by_bucket.values())
    if total <= 0:
        return "unknown", {}

    scores = {k: v / total for k, v in area_by_bucket.items() if v > 0}
    tables_frac = scores.get("tables", 0.0)
    figures_frac = scores.get("figures", 0.0)
    text_frac = scores.get("text", 0.0)

    if tables_frac >= 0.35:
        return "tabular-heavy", scores
    if figures_frac >= 0.35:
        return "image-heavy", scores
    if n_headings >= 5 and tables_frac < 0.20:
        return "form-like", scores
    if text_frac >= 0.70:
        return "narrative", scores
    return "mixed", scores
