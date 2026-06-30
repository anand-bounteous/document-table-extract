"""Camelot worker: vector-PDF tables (lattice + stream).

Camelot returns bboxes in PDF points, bottom-left origin. We convert to image
pixels at the run DPI, top-left origin, before emitting cells.

Requires Ghostscript on the system PATH (``brew install ghostscript``).
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import camelot  # type: ignore
    import fitz  # type: ignore

    pdf_path = payload["pdf_path"]
    pages_meta: Dict[str, Dict[str, Any]] = payload.get("pages", {}) or {}
    if not pages_meta:
        return {"pages": []}

    doc = fitz.open(pdf_path)
    try:
        page_heights_pts = {i: doc[i].rect.height for i in range(doc.page_count)}
    finally:
        doc.close()

    page_indices = sorted(int(k) for k in pages_meta.keys())
    pages_arg = ",".join(str(i + 1) for i in page_indices)

    # Camelot processes all pages in a single read_pdf call; we report a
    # coarse 1/total update at the start so the UI shows activity.
    from app.workers._io import write_progress
    _total = int(payload.get("__progress_total", len(page_indices)))
    _offset = int(payload.get("__progress_offset", 0))
    if page_indices:
        write_progress(_offset + 1, _total, "running", tool="camelot")

    params = payload.get("params", {})
    flavors = params.get("flavors", ["lattice", "stream"])
    # Per-flavor advanced kwargs (e.g. line_scale, copy_text for lattice; edge_tol for stream)
    flavor_kwargs: Dict[str, Dict[str, Any]] = params.get("flavor_kwargs", {})
    all_tables_by_flavor: Dict[str, Any] = {}
    for flavor in flavors:
        try:
            extra = flavor_kwargs.get(flavor, {})
            all_tables_by_flavor[flavor] = camelot.read_pdf(pdf_path, pages=pages_arg, flavor=flavor, **extra)
        except Exception as exc:  # noqa: BLE001
            print(f"camelot flavor={flavor} failed: {exc}", file=sys.stderr)
            all_tables_by_flavor[flavor] = []

    out_pages: Dict[int, Dict[str, Any]] = {i: {"page_index": i, "regions": [], "tables": []} for i in page_indices}
    for flavor, tlist in all_tables_by_flavor.items():
        for t in tlist:
            page_num = int(getattr(t, "page", 1)) - 1
            if page_num not in out_pages:
                continue
            meta = pages_meta[str(page_num)]
            dpi = int(meta["dpi"])
            page_h_pts = page_heights_pts.get(page_num, 0)
            coord = f"image_px@{dpi}"
            x1p, y1p, x2p, y2p = getattr(t, "_bbox", None) or _bbox_from_cells(t)
            tbox_px = _pdf_bbox_to_image_px(x1p, y1p, x2p, y2p, page_h_pts, dpi)
            region_id = uuid.uuid4().hex[:10]
            out_pages[page_num]["regions"].append({
                "id": region_id,
                "type": "table",
                "bbox": _bbox_dict(tbox_px, page_num, coord),
                "text": "",
                "confidence": float(getattr(t, "accuracy", 0) or 0) / 100.0,
                "raw_confidence": getattr(t, "accuracy", None),
                "source_tool": f"camelot_{flavor}",
                "attributes": {
                    "flavor": flavor,
                    "whitespace": getattr(t, "whitespace", None),
                    "accuracy": getattr(t, "accuracy", None),
                    "order": getattr(t, "order", None),
                },
                "pii_spans": [],
            })

            df = t.df
            cells_out: List[Dict[str, Any]] = []
            n_rows, n_cols = df.shape
            cam_cells = getattr(t, "cells", None) or []
            for r in range(n_rows):
                row_cells = cam_cells[r] if r < len(cam_cells) else []
                for c in range(n_cols):
                    text = str(df.iat[r, c]).strip()
                    if c < len(row_cells):
                        cell = row_cells[c]
                        cell_bbox_pts = (cell.x1, cell.y1, cell.x2, cell.y2)
                        cb_px = _pdf_bbox_to_image_px(*cell_bbox_pts, page_h_pts, dpi)
                        cell_bbox = _bbox_dict(cb_px, page_num, coord)
                    else:
                        cell_bbox = None
                    cells_out.append({
                        "row": r,
                        "col": c,
                        "rowspan": 1,
                        "colspan": 1,
                        "text": text,
                        "bbox": cell_bbox,
                        "multiline": "\n" in text,
                    })
            out_pages[page_num]["tables"].append({
                "region_id": region_id,
                "orientation": "horizontal",
                "border_mode": "ruled" if flavor == "lattice" else "whitespace",
                "n_rows": n_rows,
                "n_cols": n_cols,
                "cells": cells_out,
            })

    return {"pages": [out_pages[i] for i in page_indices]}


def _pdf_bbox_to_image_px(
    x1: float, y1: float, x2: float, y2: float, page_h_pts: float, dpi: int
) -> Tuple[float, float, float, float]:
    scale = dpi / 72.0
    nx1 = x1 * scale
    nx2 = x2 * scale
    ny1 = (page_h_pts - y2) * scale
    ny2 = (page_h_pts - y1) * scale
    return nx1, ny1, nx2 - nx1, ny2 - ny1


def _bbox_dict(b, page_index: int, coord: str) -> Dict[str, Any]:
    x, y, w, h = b
    return {"x": float(x), "y": float(y), "w": float(w), "h": float(h), "page_index": page_index, "coord_space": coord}


def _bbox_from_cells(t) -> Tuple[float, float, float, float]:
    cells = getattr(t, "cells", None) or []
    flat = [c for row in cells for c in row]
    if not flat:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(c.x1 for c in flat), min(c.y1 for c in flat), max(c.x2 for c in flat), max(c.y2 for c in flat))


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
