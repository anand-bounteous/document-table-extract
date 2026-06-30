"""BBox geometry helpers and coordinate-space conversion."""

from __future__ import annotations

from typing import Iterable

from app.core.schemas import BBox


def bbox_from_xyxy(x1: float, y1: float, x2: float, y2: float, page_index: int, dpi: int) -> BBox:
    return BBox(
        x=min(x1, x2),
        y=min(y1, y2),
        w=abs(x2 - x1),
        h=abs(y2 - y1),
        page_index=page_index,
        coord_space=f"image_px@{dpi}",
    )


def pdf_points_to_image_px(
    x: float, y: float, *, page_height_pts: float, dpi: int
) -> tuple[float, float]:
    """Convert a PDF point (top-left or bottom-left handled here as bottom-left → top-left flip)."""
    scale = dpi / 72.0
    return x * scale, (page_height_pts - y) * scale


def iou(a: BBox, b: BBox) -> float:
    if a.page_index != b.page_index:
        return 0.0
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x2, b.x2), min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def union_bbox(boxes: Iterable[BBox]) -> BBox | None:
    boxes = list(boxes)
    if not boxes:
        return None
    page = boxes[0].page_index
    coord = boxes[0].coord_space
    x1 = min(b.x for b in boxes)
    y1 = min(b.y for b in boxes)
    x2 = max(b.x2 for b in boxes)
    y2 = max(b.y2 for b in boxes)
    return BBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1, page_index=page, coord_space=coord)
