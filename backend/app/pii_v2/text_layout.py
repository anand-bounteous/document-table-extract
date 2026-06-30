"""Char-range → pixel bbox mapping for pii_v2.

When `pii_runner._join_pages_text` joins per-region OCR text into a single
page-level string, the original Region.bbox info is lost. Detectors emit
char-offset spans, so we need a parallel index that maps each char-range
back to its source region so the dashboard can draw bboxes on the page
image.

The bbox computation mirrors the heuristic used by the existing in-pipeline
PII path (`backend/app/stages/pii/presidio.py:_span_bbox`): uniform
``x_per_char`` density within a single source region.

When a span crosses multiple regions (rare for real PII) we return a union
bbox covering every overlapped region.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RegionSpan:
    """One entry of the per-page char-range → region index."""

    start: int        # inclusive char offset in joined page text
    end: int          # exclusive
    region_id: str
    bbox: Dict[str, Any]   # {x, y, w, h, page_index, coord_space}
    text_len: int          # original region text length (cached for char_to_bbox)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "region_id": self.region_id,
            "bbox": self.bbox,
            "text_len": self.text_len,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegionSpan":
        return cls(
            start=int(d["start"]),
            end=int(d["end"]),
            region_id=str(d["region_id"]),
            bbox=dict(d["bbox"]),
            text_len=int(d.get("text_len", d["end"] - d["start"])),
        )


def char_to_bbox(
    span_start: int,
    span_end: int,
    index: List[RegionSpan],
) -> Optional[Dict[str, Any]]:
    """Resolve a char-range to a pixel bbox via the region index.

    Returns the union bbox across every region the span overlaps, with the
    x-coordinate scaled by ``x_per_char`` *within* each source region. None
    when the span doesn't overlap any indexed region (e.g. detector emitted
    a span over inserted whitespace).
    """
    overlapping = [rs for rs in index if not (rs.end <= span_start or span_end <= rs.start)]
    if not overlapping:
        return None

    boxes: List[Dict[str, Any]] = []
    for rs in overlapping:
        text_len = rs.text_len or max(1, rs.end - rs.start)
        x_per_char = float(rs.bbox.get("w", 0)) / max(1, text_len)
        # Span offset within this region's text:
        local_start = max(0, span_start - rs.start)
        local_end = min(text_len, span_end - rs.start)
        if local_end <= local_start:
            continue
        x1 = float(rs.bbox.get("x", 0)) + x_per_char * local_start
        x2 = float(rs.bbox.get("x", 0)) + x_per_char * local_end
        boxes.append({
            "x": x1,
            "y": float(rs.bbox.get("y", 0)),
            "x2": x2,
            "y2": float(rs.bbox.get("y", 0)) + float(rs.bbox.get("h", 0)),
            "page_index": rs.bbox.get("page_index", 0),
            "coord_space": rs.bbox.get("coord_space", "image_px@300"),
        })

    if not boxes:
        return None

    x = min(b["x"] for b in boxes)
    y = min(b["y"] for b in boxes)
    x2 = max(b["x2"] for b in boxes)
    y2 = max(b["y2"] for b in boxes)
    return {
        "x": x,
        "y": y,
        "w": max(2.0, x2 - x),
        "h": max(2.0, y2 - y),
        "page_index": boxes[0]["page_index"],
        "coord_space": boxes[0]["coord_space"],
    }


def serialize_index(index: List[RegionSpan]) -> List[Dict[str, Any]]:
    return [rs.to_dict() for rs in index]


def deserialize_index(raw: List[Dict[str, Any]]) -> List[RegionSpan]:
    return [RegionSpan.from_dict(d) for d in raw]
