"""img2table worker: detect bordered + borderless tables on rasterized pages.

stdin payload (subset used):
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": "...", "width": int, "height": int, "dpi": int}, ... },
      "params": { "ocr": "tesseract", "borderless_tables": true, "implicit_rows": true }
    }

stdout: SubprocessStage's expected result schema.
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from typing import Any, Dict, List


def _make_ocr(backend: str, params: dict):
    """Factory: return an img2table OCR object for the requested backend."""
    backend = (backend or "tesseract").lower()
    lang = params.get("lang", "eng")
    if backend == "tesseract":
        from img2table.ocr import TesseractOCR  # type: ignore
        return TesseractOCR(n_threads=1, lang=lang)
    if backend == "easyocr":
        from img2table.ocr import EasyOCR  # type: ignore
        # EasyOCR uses 2-letter codes (en, fr, …) while Tesseract uses 3-letter (eng)
        easy_lang = lang if len(lang) == 2 else lang[:2]
        # img2table's EasyOCR wrapper takes lang + kw (kwargs forwarded to easyocr.Reader)
        return EasyOCR(lang=[easy_lang], kw={"gpu": False, "verbose": False})
    if backend == "doctr":
        from img2table.ocr import DocTR  # type: ignore
        return DocTR(detect_language=False)
    if backend == "paddle":
        from img2table.ocr import PaddleOCR  # type: ignore
        paddle_lang = params.get("paddle_lang", "en")
        # Use mobile models to avoid OOM on machines with limited RAM.
        # Server models (default) can exceed 4 GB when combined with img2table.
        kw = params.get("paddle_kw", {
            "ocr_version": "PP-OCRv4",
            "det_model_dir": None,
            "rec_model_dir": None,
        })
        return PaddleOCR(lang=paddle_lang, kw=kw)
    raise ValueError(f"unknown ocr_backend: {backend!r}")


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    from img2table.document import Image  # type: ignore
    params = payload.get("params") or {}
    ocr = _make_ocr(params.get("ocr_backend", "tesseract"), params)

    from app.workers._io import write_progress
    _pages = list(payload.get("pages", {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="img2table")
        coord = f"image_px@{p['dpi']}"
        try:
            img_doc = Image(src=p["image_path"])  # type: ignore
            tables = img_doc.extract_tables(
                ocr=ocr,
                implicit_rows=bool(params.get("implicit_rows", True)),
                borderless_tables=bool(params.get("borderless_tables", True)),
                min_confidence=int(params.get("min_confidence", 50)),
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            failures.append({"page_index": idx, "error": f"{type(exc).__name__}: {exc}"})
            pages_out.append({"page_index": idx, "regions": [], "tables": []})
            continue

        out_regions: List[Dict[str, Any]] = []
        out_tables: List[Dict[str, Any]] = []
        for t in tables:
            try:
                tbb = t.bbox
                region_id = uuid.uuid4().hex[:10]
                out_regions.append({
                    "id": region_id,
                    "type": "table",
                    "bbox": {
                        "x": float(tbb.x1), "y": float(tbb.y1),
                        "w": float(tbb.x2 - tbb.x1), "h": float(tbb.y2 - tbb.y1),
                        "page_index": idx, "coord_space": coord,
                    },
                    "text": "",
                    "confidence": float(_table_confidence(t)),
                    "source_tool": "img2table",
                    "attributes": {"title": getattr(t, "title", None) or ""},
                    "pii_spans": [],
                })
                rows = t.content or {}
                row_keys = sorted(rows.keys())
                cells_out: List[Dict[str, Any]] = []
                max_cols = 0
                for r_idx, r_key in enumerate(row_keys):
                    row_cells = rows[r_key] or []
                    max_cols = max(max_cols, len(row_cells))
                    for c_idx, cell in enumerate(row_cells):
                        cb = getattr(cell, "bbox", None)
                        cell_value = getattr(cell, "value", None)
                        text = (cell_value or "").strip() if isinstance(cell_value, str) else ""
                        cell_bbox = None
                        if cb is not None:
                            cell_bbox = {
                                "x": float(cb.x1), "y": float(cb.y1),
                                "w": float(cb.x2 - cb.x1), "h": float(cb.y2 - cb.y1),
                                "page_index": idx, "coord_space": coord,
                            }
                        cells_out.append({
                            "row": r_idx, "col": c_idx,
                            "rowspan": 1, "colspan": 1,
                            "text": text,
                            "bbox": cell_bbox,
                            "multiline": "\n" in text,
                        })
                out_tables.append({
                    "region_id": region_id,
                    "orientation": "horizontal",
                    "border_mode": "mixed",
                    "n_rows": len(row_keys),
                    "n_cols": max_cols,
                    "cells": cells_out,
                })
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                failures.append({"page_index": idx, "error": f"table-walk {type(exc).__name__}: {exc}"})

        pages_out.append({
            "page_index": idx,
            "regions": out_regions,
            "tables": out_tables,
        })

    return {"pages": pages_out, "failures": failures}


def _table_confidence(t) -> float:
    """img2table doesn't expose a single confidence; approximate via cell-fill ratio."""
    rows = t.content or {}
    total = 0
    filled = 0
    for r in rows.values():
        for c in r:
            total += 1
            v = getattr(c, "value", None) or ""
            if v.strip():
                filled += 1
    if total == 0:
        return 0.0
    return max(0.4, min(1.0, filled / total))


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
