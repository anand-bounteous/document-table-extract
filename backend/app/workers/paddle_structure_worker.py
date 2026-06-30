"""PaddleOCR PP-Structure (v3) worker: layout + table + OCR.

PPStructureV3 returns one result per input page. We call ``save_to_json`` to
get a stable serializable structure, then walk it. Bboxes are in input-image
pixels (top-left origin), which is already our canonical space.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List


_PADDLE_LABEL_TO_OUR_TYPE = {
    "text": "normal_text",
    "title": "kv_pair",
    "doc_title": "kv_pair",
    "paragraph_title": "kv_pair",
    "abstract": "normal_text",
    "content": "normal_text",
    "list": "normal_text",
    "header": "normal_text",
    "footer": "normal_text",
    "page_number": "normal_text",
    "reference": "normal_text",
    "table": "table",
    "table_title": "kv_pair",
    "figure": "image",
    "figure_title": "normal_text",
    "image": "image",
    "chart": "image",
    "chart_title": "normal_text",
    "formula": "normal_text",
    "seal": "seal",
    "stamp": "seal",
    "watermark": "watermark",
}


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    from paddleocr import PPStructureV3  # type: ignore

    params = payload.get("params") or {}
    # Disable every optional submodel that pulls a multi-hundred-MB checkpoint
    # we don't need for bank/financial documents — formula recognition alone
    # is ~1GB and is what OOMs an 8GB Mac when combined with the rest.
    pipeline = PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_seal_recognition=params.get("use_seal", False),
        use_formula_recognition=params.get("use_formula", False),
        use_chart_recognition=params.get("use_chart", False),
        use_region_detection=params.get("use_region", False),
        use_table_recognition=params.get("use_table", True),
        lang=params.get("lang", "en"),
    )

    from app.workers._io import write_progress
    _pages = list((payload.get("pages") or {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        for _pos, (idx_str, p) in enumerate(_pages):
            idx = int(idx_str)
            write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="paddle_structure")
            dpi = int(p["dpi"])
            coord = f"image_px@{dpi}"
            img_path = p["image_path"]

            try:
                outputs = pipeline.predict(input=img_path)
            except Exception as exc:  # noqa: BLE001
                print(f"page {idx}: paddle predict failed: {exc}", file=sys.stderr)
                pages_out.append({"page_index": idx, "regions": [], "tables": []})
                from app.workers._io import write_partial as _wp
                _wp({"pages": list(pages_out)})
                continue

            page_regions: List[Dict[str, Any]] = []
            page_tables: List[Dict[str, Any]] = []
            for j, res in enumerate(outputs):
                json_path = tmpd / f"p{idx}_r{j}.json"
                try:
                    res.save_to_json(save_path=str(json_path))
                except Exception:
                    json_path.write_text(json.dumps(getattr(res, "json", {}) or {}))
                try:
                    blob = json.loads(json_path.read_text())
                except Exception as exc:  # noqa: BLE001
                    print(f"page {idx} result {j} unreadable: {exc}", file=sys.stderr)
                    continue
                _walk(blob, idx, coord, page_regions, page_tables)

            pages_out.append({"page_index": idx, "regions": page_regions, "tables": page_tables})
            from app.workers._io import write_partial as _wp
            _wp({"pages": list(pages_out)})

    return {"pages": pages_out}


def _walk(blob: Any, page_index: int, coord: str, regions: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> None:
    """Walk paddle's nested JSON dict pulling out anything that looks like a labeled bbox."""
    if isinstance(blob, dict):
        bbox = blob.get("bbox") or blob.get("block_bbox") or blob.get("region_bbox")
        label = blob.get("block_label") or blob.get("label") or blob.get("type")
        if bbox and label and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            rtype = _PADDLE_LABEL_TO_OUR_TYPE.get(str(label).lower(), "unknown")
            x1, y1, x2, y2 = (float(v) for v in bbox)
            region_id = uuid.uuid4().hex[:10]
            text_value = blob.get("block_content") or blob.get("text") or blob.get("content") or ""
            if isinstance(text_value, (dict, list)):
                text_value = json.dumps(text_value)[:500]
            regions.append({
                "id": region_id,
                "type": rtype,
                "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "page_index": page_index, "coord_space": coord},
                "text": str(text_value),
                "confidence": float(blob.get("score") or blob.get("confidence") or 0.8),
                "source_tool": "paddle_pp_structure",
                "attributes": {"label": str(label)},
                "pii_spans": [],
            })
            if rtype == "table":
                _maybe_emit_table(blob, region_id, page_index, coord, tables)
        for v in blob.values():
            _walk(v, page_index, coord, regions, tables)
    elif isinstance(blob, list):
        for v in blob:
            _walk(v, page_index, coord, regions, tables)


def _maybe_emit_table(
    blob: Dict[str, Any], region_id: str, page_index: int, coord: str, tables: List[Dict[str, Any]]
) -> None:
    html = blob.get("html") or blob.get("table_html") or ""
    cells_raw = blob.get("cells") or blob.get("cell_bbox") or blob.get("table_cells") or []
    cells_out: List[Dict[str, Any]] = []
    n_rows = 0
    n_cols = 0
    for c in cells_raw if isinstance(cells_raw, list) else []:
        if not isinstance(c, dict):
            continue
        row = int(c.get("row", c.get("row_id", 0)))
        col = int(c.get("col", c.get("col_id", 0)))
        n_rows = max(n_rows, row + 1)
        n_cols = max(n_cols, col + 1)
        cb = c.get("bbox")
        cell_bbox = None
        if cb and isinstance(cb, (list, tuple)) and len(cb) == 4:
            cx1, cy1, cx2, cy2 = (float(v) for v in cb)
            cell_bbox = {"x": cx1, "y": cy1, "w": cx2 - cx1, "h": cy2 - cy1, "page_index": page_index, "coord_space": coord}
        text = str(c.get("text") or "")
        cells_out.append({
            "row": row, "col": col,
            "rowspan": int(c.get("rowspan", 1)),
            "colspan": int(c.get("colspan", 1)),
            "text": text,
            "bbox": cell_bbox,
            "multiline": "\n" in text,
        })
    if cells_out or html:
        tables.append({
            "region_id": region_id,
            "orientation": "horizontal",
            "border_mode": "mixed",
            "n_rows": n_rows,
            "n_cols": n_cols,
            "cells": cells_out,
            "html": html or None,
        })


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
