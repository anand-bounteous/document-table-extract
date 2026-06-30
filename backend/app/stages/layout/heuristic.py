"""Dependency-free layout helpers: cluster lines into table regions when ruled lines exist;
otherwise leave text regions as-is. This is the fallback when no ML layout model is loaded.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List

from app.core.geometry import iou, union_bbox
from app.core.schemas import BBox, Region, RegionType, TableCell, TableModel
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.layout")


@dataclass
class RuledTableFromOpenCV:
    """Pair the OpenCV ruled-cell grid with tesseract text Regions to build TableModels."""

    name: str = "layout_ruled_table"
    tool: str = "heuristic+opencv"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        grids: Dict[int, List[BBox]] = state.extras.get("ruled_cells", {})
        if not grids:
            return state
        for idx, page in state.pages.items():
            cells = grids.get(idx)
            if not cells:
                continue
            text_regions = [r for r in page.regions if r.type == RegionType.NORMAL_TEXT]
            if not text_regions:
                continue
            row_ys = sorted({round(c.y) for c in cells})
            col_xs = sorted({round(c.x) for c in cells})
            n_rows = max(0, len(row_ys) - 1)
            n_cols = max(0, len(col_xs) - 1)
            if n_rows == 0 or n_cols == 0:
                continue
            table_bbox = union_bbox(cells)
            if not table_bbox:
                continue
            table_region = Region(
                id=uuid.uuid4().hex[:10],
                type=RegionType.TABLE,
                bbox=table_bbox,
                source_tool=self.tool,
                attributes={"n_rows": n_rows, "n_cols": n_cols, "border_mode": "ruled"},
            )
            page.regions.append(table_region)

            table_cells: List[TableCell] = []
            for r_idx in range(n_rows):
                for c_idx in range(n_cols):
                    cy1, cy2 = row_ys[r_idx], row_ys[r_idx + 1]
                    cx1, cx2 = col_xs[c_idx], col_xs[c_idx + 1]
                    cell_box = BBox(
                        x=cx1, y=cy1, w=cx2 - cx1, h=cy2 - cy1,
                        page_index=idx, coord_space=table_bbox.coord_space,
                    )
                    inside = [t for t in text_regions if iou(t.bbox, cell_box) > 0.05]
                    text = " ".join(t.text for t in sorted(inside, key=lambda t: (t.bbox.y, t.bbox.x))).strip()
                    table_cells.append(
                        TableCell(
                            row=r_idx,
                            col=c_idx,
                            text=text,
                            bbox=cell_box,
                            multiline=len(inside) > 1,
                        )
                    )
            page.tables.append(
                TableModel(
                    region_id=table_region.id,
                    orientation="horizontal",
                    border_mode="ruled",
                    n_rows=n_rows,
                    n_cols=n_cols,
                    cells=table_cells,
                )
            )
        return state
