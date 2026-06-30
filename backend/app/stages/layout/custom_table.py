"""Pure-Python geometric table detection from already-extracted region bboxes.

Reads `page.regions` populated by upstream OCR/Vision stages and emits derived
`CustomTable` objects into `page.custom_tables`. No LLM is involved; this is
a deterministic heuristic over x-y coordinates.

Detects two orientations:
  - horizontal: rows aligned on a Y-band with consistent column x-centers
  - vertical_kv: pairs of regions forming key (left X cluster) + value (right X cluster)
    with monotonically increasing Y over >= 3 rows
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.geometry import union_bbox
from app.core.schemas import BBox, CustomTable, Region, TableCell
from app.pipeline.base import RunState
from app.pipeline.context import RunContext


MIN_ROW_REGIONS = 3       # row must have >= this many regions
MIN_TABLE_ROWS = 2        # horizontal table needs >= this many consecutive rows
MIN_KV_ROWS = 3           # vertical kv table needs >= this many rows
MIN_REGIONS = 4           # at least this many text regions on the page or we skip
ROW_GAP_FACTOR = 1.6      # adjacent rows must be within ROW_GAP_FACTOR * median_line_height


@dataclass
class CustomTableStage:
    name: str = "layout_custom_table"
    tool: str = "geometric_heuristic"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        for page in state.pages.values():
            text_regions = _candidate_regions(page.regions)
            if not text_regions:
                page.custom_table_status = "na_missing_bbox"
                page.custom_table_message = "x-y data missing — no regions had usable bbox"
                continue
            if len(text_regions) < MIN_REGIONS:
                page.custom_table_status = "not_found"
                page.custom_table_message = f"too few text regions ({len(text_regions)}) to form a table"
                continue

            heights = [r.bbox.h for r in text_regions if r.bbox.h > 0]
            widths = [r.bbox.w for r in text_regions if r.bbox.w > 0]
            if not heights or not widths:
                page.custom_table_status = "na_missing_bbox"
                page.custom_table_message = "x-y data missing — all regions had zero-area bbox"
                continue
            median_h = statistics.median(heights)
            median_w = statistics.median(widths)
            y_tol = max(1.0, 0.5 * median_h)
            x_tol = max(1.0, 0.6 * median_w)

            detected: List[CustomTable] = []
            detected.extend(_detect_horizontal(text_regions, y_tol=y_tol, x_tol=x_tol, row_gap=ROW_GAP_FACTOR * median_h, page_index=page.page_index, dpi=page.dpi))
            detected.extend(_detect_vertical_kv(text_regions, x_tol=x_tol, y_tol=y_tol, page_index=page.page_index, dpi=page.dpi))

            if detected:
                page.custom_tables = detected
                page.custom_table_status = "ok"
                page.custom_table_message = (
                    f"detected {len(detected)} table(s) via geometric heuristic "
                    f"(y_tol={y_tol:.1f}, x_tol={x_tol:.1f})"
                )
            else:
                page.custom_table_status = "not_found"
                page.custom_table_message = (
                    f"no table pattern in {len(text_regions)} regions "
                    f"(y_tol={y_tol:.1f}, x_tol={x_tol:.1f})"
                )
        return state


# ---------------------------------------------------------------------------
# candidate filtering
# ---------------------------------------------------------------------------


_TEXT_TYPES = {"normal_text", "kv_pair", "table_cell", "table_row", "table_header", "unknown"}


def _candidate_regions(regions: List[Region]) -> List[Region]:
    out: List[Region] = []
    for r in regions:
        if r.type.value not in _TEXT_TYPES:
            continue
        if not (r.text or "").strip():
            continue
        if r.bbox.w <= 0 or r.bbox.h <= 0:
            continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# horizontal-table heuristic
# ---------------------------------------------------------------------------


def _detect_horizontal(
    regions: List[Region], *, y_tol: float, x_tol: float, row_gap: float, page_index: int, dpi: int
) -> List[CustomTable]:
    # Group regions into Y-clusters (rows)
    sorted_regions = sorted(regions, key=lambda r: r.bbox.y + r.bbox.h / 2)
    rows: List[List[Region]] = []
    for r in sorted_regions:
        cy = r.bbox.y + r.bbox.h / 2
        if rows and abs(_row_cy(rows[-1]) - cy) <= y_tol:
            rows[-1].append(r)
        else:
            rows.append([r])

    # Keep only rows that have enough regions to be a row of a table
    candidate_rows = [row for row in rows if len(row) >= MIN_ROW_REGIONS]
    if len(candidate_rows) < MIN_TABLE_ROWS:
        return []

    # Group consecutive candidate rows into tables
    tables: List[List[List[Region]]] = []
    for row in candidate_rows:
        cy = _row_cy(row)
        if tables and abs(cy - _row_cy(tables[-1][-1])) <= row_gap:
            tables[-1].append(row)
        else:
            tables.append([row])

    out: List[CustomTable] = []
    coord = f"image_px@{dpi}"
    for tbl_rows in tables:
        if len(tbl_rows) < MIN_TABLE_ROWS:
            continue

        # Build column x-centers from the row with the most regions (most likely the header)
        anchor_row = max(tbl_rows, key=len)
        col_centers = sorted(r.bbox.x + r.bbox.w / 2 for r in anchor_row)
        n_cols = len(col_centers)
        if n_cols < MIN_ROW_REGIONS:
            continue

        # For each row, map regions to the nearest column
        cells: List[TableCell] = []
        for r_idx, row in enumerate(sorted(tbl_rows, key=_row_cy)):
            row_sorted = sorted(row, key=lambda x: x.bbox.x)
            for reg in row_sorted:
                cx = reg.bbox.x + reg.bbox.w / 2
                # find the column with closest center
                col_idx, dist = min(
                    ((i, abs(c - cx)) for i, c in enumerate(col_centers)),
                    key=lambda kv: kv[1],
                )
                if dist > x_tol * 2:
                    continue
                cells.append(TableCell(row=r_idx, col=col_idx, text=reg.text.strip(), bbox=reg.bbox))

        if not cells:
            continue

        table_bbox = union_bbox([reg.bbox for row in tbl_rows for reg in row])
        if table_bbox is None:
            continue
        region_id = uuid.uuid4().hex[:10]
        out.append(
            CustomTable(
                region_id=region_id,
                orientation="horizontal",
                border_mode="whitespace",
                n_rows=len(tbl_rows),
                n_cols=n_cols,
                cells=cells,
                detection={
                    "anchor_row_size": len(anchor_row),
                    "y_tol": y_tol,
                    "x_tol": x_tol,
                    "row_gap": row_gap,
                    "rows_clustered": [len(row) for row in tbl_rows],
                    "bbox": _bbox_dict(table_bbox),
                },
            )
        )
    return out


def _row_cy(row: List[Region]) -> float:
    return statistics.mean(r.bbox.y + r.bbox.h / 2 for r in row)


# ---------------------------------------------------------------------------
# vertical key-value heuristic
# ---------------------------------------------------------------------------


def _detect_vertical_kv(
    regions: List[Region], *, x_tol: float, y_tol: float, page_index: int, dpi: int
) -> List[CustomTable]:
    # Find pairs of regions on (approximately) the same Y-line with two distinct X clusters
    sorted_regions = sorted(regions, key=lambda r: r.bbox.y + r.bbox.h / 2)
    pairs: List[Tuple[Region, Region]] = []
    used = set()
    for i, left in enumerate(sorted_regions):
        if id(left) in used:
            continue
        cy_l = left.bbox.y + left.bbox.h / 2
        # find one region to the right on the same Y
        best: Optional[Region] = None
        for right in sorted_regions[i + 1 :]:
            cy_r = right.bbox.y + right.bbox.h / 2
            if cy_r - cy_l > y_tol * 4:
                break
            if abs(cy_r - cy_l) <= y_tol and right.bbox.x > left.bbox.x + left.bbox.w + x_tol * 0.2:
                if best is None or right.bbox.x < best.bbox.x:
                    best = right
        if best is not None:
            pairs.append((left, best))
            used.add(id(left))
            used.add(id(best))

    if len(pairs) < MIN_KV_ROWS:
        return []

    # Cluster key X-centers + value X-centers; require both to be tight
    key_cx = [p[0].bbox.x + p[0].bbox.w / 2 for p in pairs]
    val_cx = [p[1].bbox.x + p[1].bbox.w / 2 for p in pairs]
    key_med = statistics.median(key_cx)
    val_med = statistics.median(val_cx)

    consistent = [
        (k, v)
        for (k, v), kx, vx in zip(pairs, key_cx, val_cx)
        if abs(kx - key_med) <= x_tol * 1.5 and abs(vx - val_med) <= x_tol * 3
    ]
    if len(consistent) < MIN_KV_ROWS:
        return []

    # Sort by Y to form rows
    consistent.sort(key=lambda p: p[0].bbox.y + p[0].bbox.h / 2)
    cells: List[TableCell] = []
    for r_idx, (k, v) in enumerate(consistent):
        cells.append(TableCell(row=r_idx, col=0, text=k.text.strip(), bbox=k.bbox))
        cells.append(TableCell(row=r_idx, col=1, text=v.text.strip(), bbox=v.bbox))

    table_bbox = union_bbox([k.bbox for k, _ in consistent] + [v.bbox for _, v in consistent])
    if table_bbox is None:
        return []
    region_id = uuid.uuid4().hex[:10]
    return [
        CustomTable(
            region_id=region_id,
            orientation="vertical_kv",
            border_mode="whitespace",
            n_rows=len(consistent),
            n_cols=2,
            cells=cells,
            detection={
                "key_x_median": key_med,
                "value_x_median": val_med,
                "x_tol": x_tol,
                "y_tol": y_tol,
                "row_count": len(consistent),
                "bbox": _bbox_dict(table_bbox),
            },
        )
    ]


def _bbox_dict(b: BBox) -> Dict[str, Any]:
    return {"x": b.x, "y": b.y, "w": b.w, "h": b.h, "page_index": b.page_index, "coord_space": b.coord_space}
