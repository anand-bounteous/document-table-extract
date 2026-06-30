"""Tabula worker: vector-PDF tables via tabula-py (JVM-backed).

Tabula returns row/col data as DataFrames + lattice/stream bounding boxes in PDF
points (top-left origin, unlike Camelot). We convert to image pixels at run DPI.
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import tabula  # type: ignore

    pdf_path = payload["pdf_path"]
    pages_meta: Dict[str, Dict[str, Any]] = payload.get("pages", {}) or {}
    if not pages_meta:
        return {"pages": []}

    page_indices = sorted(int(k) for k in pages_meta.keys())
    pages_arg = [i + 1 for i in page_indices]

    # Tabula processes all pages in a single read_pdf call per flavour; emit
    # a coarse "1 of total" so the UI shows activity.
    from app.workers._io import write_progress
    _total = int(payload.get("__progress_total", len(page_indices)))
    _offset = int(payload.get("__progress_offset", 0))
    if page_indices:
        write_progress(_offset + 1, _total, "running", tool="tabula")

    params = payload.get("params") or {}
    # Support both legacy {lattice: bool, stream: bool} and new {flavors: [...]} param shapes
    flavors_param = params.get("flavors")
    if flavors_param is not None:
        do_lattice = "lattice" in flavors_param
        do_stream = "stream" in flavors_param
    else:
        do_lattice = bool(params.get("lattice", True))
        do_stream = bool(params.get("stream", True))
    guess = bool(params.get("guess", False))

    all_dfs: List[Dict[str, Any]] = []
    for mode_name, mode_kwargs in [
        ("lattice", {"lattice": True, "multiple_tables": True}),
        ("stream", {"stream": True, "multiple_tables": True, "guess": guess}),
    ]:
        if not (do_lattice if mode_name == "lattice" else do_stream):
            continue
        try:
            dfs = tabula.read_pdf(pdf_path, pages=pages_arg, **mode_kwargs)
            for df in dfs:
                all_dfs.append({"df": df, "mode": mode_name})
        except Exception as exc:  # noqa: BLE001
            print(f"tabula mode={mode_name} failed: {exc}", file=sys.stderr)

    if not all_dfs:
        return {"pages": [{"page_index": i, "regions": [], "tables": []} for i in page_indices]}

    pages_out: Dict[int, Dict[str, Any]] = {i: {"page_index": i, "regions": [], "tables": []} for i in page_indices}

    df_per_page: Dict[int, List[Dict[str, Any]]] = {i: [] for i in page_indices}
    n = len(all_dfs)
    pages_n = len(page_indices)
    if n == pages_n:
        for i, item in zip(page_indices, all_dfs):
            df_per_page[i].append(item)
    else:
        for j, item in enumerate(all_dfs):
            df_per_page[page_indices[j % pages_n]].append(item)

    for page_idx in page_indices:
        meta = pages_meta[str(page_idx)]
        dpi = int(meta["dpi"])
        coord = f"image_px@{dpi}"
        w_px, h_px = int(meta["width"]), int(meta["height"])
        for item in df_per_page[page_idx]:
            df = item["df"]
            mode = item["mode"]
            n_rows, n_cols = df.shape
            region_id = uuid.uuid4().hex[:10]
            pages_out[page_idx]["regions"].append({
                "id": region_id,
                "type": "table",
                "bbox": {"x": 0, "y": 0, "w": w_px, "h": h_px, "page_index": page_idx, "coord_space": coord},
                "text": "",
                "confidence": 0.7,
                "source_tool": f"tabula_{mode}",
                "attributes": {"mode": mode},
                "pii_spans": [],
            })
            cells_out: List[Dict[str, Any]] = []
            header = list(df.columns)
            for c_idx, col_name in enumerate(header):
                text = str(col_name).strip()
                if text and text.lower() != f"unnamed: {c_idx}":
                    cells_out.append({"row": 0, "col": c_idx, "rowspan": 1, "colspan": 1, "text": text, "bbox": None, "multiline": False, "is_header": True})
            row_offset = 1 if any(cells_out) else 0
            for r in range(n_rows):
                for c in range(n_cols):
                    text = str(df.iat[r, c])
                    if text == "nan":
                        text = ""
                    cells_out.append({"row": r + row_offset, "col": c, "rowspan": 1, "colspan": 1, "text": text, "bbox": None, "multiline": "\n" in text, "is_header": False})
            pages_out[page_idx]["tables"].append({
                "region_id": region_id,
                "orientation": "horizontal",
                "border_mode": "ruled" if mode == "lattice" else "whitespace",
                "n_rows": n_rows + row_offset,
                "n_cols": n_cols,
                "cells": cells_out,
            })

    return {"pages": [pages_out[i] for i in page_indices]}


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
