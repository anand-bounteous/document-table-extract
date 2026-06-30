"""RAGFlow deepdoc benchmark worker (vendored layout + TSR + swappable OCR).

Layout pipeline:
    page raster --> OCR-backend.recognize_page    (default ONNX OR adapter)
                          |
                          v
                    OCR-result dicts (per page)
                          |
                          v
            LayoutRecognizer4YOLOv10(image_list, ocr_res)
                          |
                          v
            text/title/table/figure regions w/ layout_type
                          |
                          v
            for each table region: crop -> TableStructureRecognizer
                          |
                          v
            emit Regions + TableModels in our schema

The vendored sources live at ``backend/vendor/deepdoc/vision/``; ``common.*``
and ``rag.*`` are minimally stubbed in ``backend/vendor/_ragflow_stubs/``.

stdin payload:
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": ..., "width": ..., "height": ..., "dpi": ...}, ... },
      "params": {
        "ocr_backend": "default" | "tesseract" | "easyocr" | "doctr" | "paddle",
        "layout_score_threshold": 0.4
      }
    }
"""

from __future__ import annotations

import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List


def _ensure_vendor_on_path() -> None:
    """Prepend the vendored deepdoc + ragflow-stubs directories to sys.path."""
    backend_root = Path(__file__).resolve().parent.parent.parent  # backend/
    vendor = backend_root / "vendor"
    if not vendor.exists():
        raise RuntimeError(f"deepdoc vendor dir missing: {vendor}")
    for p in (str(vendor), str(vendor / "_ragflow_stubs")):
        if p not in sys.path:
            sys.path.insert(0, p)


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_vendor_on_path()

    import numpy as np
    from PIL import Image

    # Deferred imports so the path setup above is in effect
    from deepdoc.vision.layout_recognizer import LayoutRecognizer4YOLOv10  # type: ignore
    from deepdoc.vision.table_structure_recognizer import TableStructureRecognizer  # type: ignore
    from app.stages.ocr.deepdoc_adapters import build_backend, OCRResult

    params = payload.get("params") or {}
    backend_name = str(params.get("ocr_backend", "default"))
    layout_thr = float(params.get("layout_score_threshold", 0.4))
    pages_meta: Dict[str, Dict[str, Any]] = payload.get("pages") or {}
    if not pages_meta:
        return {"pages": []}

    ocr_backend = build_backend(backend_name)
    layouter = LayoutRecognizer4YOLOv10("layout")
    tsr = TableStructureRecognizer()

    # Process pages in input order
    sorted_idx = sorted(int(k) for k in pages_meta.keys())
    images: List[np.ndarray] = []
    ocr_results_per_page: List[List[OCRResult]] = []

    from app.workers._io import write_progress
    _total = int(payload.get("__progress_total", len(sorted_idx)))
    _offset = int(payload.get("__progress_offset", 0))

    for _pos, idx in enumerate(sorted_idx):
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool=f"deepdoc/{backend_name}")
        p = pages_meta[str(idx)]
        img_path = p["image_path"]
        try:
            img = np.asarray(Image.open(img_path).convert("RGB"))
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            images.append(np.zeros((1, 1, 3), dtype=np.uint8))
            ocr_results_per_page.append([])
            continue
        images.append(img)
        try:
            ocr_results_per_page.append(ocr_backend.recognize_page(img))
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            ocr_results_per_page.append([])

    # Build ocr_res input for LayoutRecognizer: per-page list of dicts.
    ocr_res_for_layouter: List[List[Dict[str, Any]]] = []
    for ocr_list in ocr_results_per_page:
        ocr_res_for_layouter.append([
            {
                "text": r.text,
                "x0": r.x0, "x1": r.x1,
                "top": r.y0, "bottom": r.y1,
                # layouter expects a layout_type to be writable on the dict
                "layout_type": None,
            }
            for r in ocr_list
        ])

    # LayoutRecognizer.__call__ mutates ocr_res dicts in place (adds
    # ``layout_type`` / ``layoutno``), then returns a FLAT list of all OCR
    # dicts across every page plus a separate per-page list of layout
    # regions. We don't use the flat list — iterating it would require
    # filtering by page_number — and instead pull layout_type back off our
    # own per-page dicts via the shared identity (mutation happened in
    # place). For text regions we just emit each OCR result as NORMAL_TEXT;
    # non-text structural regions come from ``page_layouts[pos]`` below.
    try:
        _flat_ocr, page_layouts = layouter(
            images, ocr_res_for_layouter, scale_factor=1, thr=layout_thr, drop=True,
        )
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        # Surface a clean error per page so the card shows what happened.
        return {
            "pages": [{"page_index": i, "regions": [], "tables": []} for i in sorted_idx],
            "failures": [{"stage": "layout_recognizer", "message": traceback.format_exc().splitlines()[-1]}],
        }

    pages_out: List[Dict[str, Any]] = []
    for pos, idx in enumerate(sorted_idx):
        p = pages_meta[str(idx)]
        dpi = int(p["dpi"])
        coord = f"image_px@{dpi}"
        img = images[pos]
        ocr_list = ocr_results_per_page[pos]
        layout_for_page = page_layouts[pos] if pos < len(page_layouts) else []
        # In-place mutated OCR dicts (carry layout_type tag from layouter).
        ocr_tagged_for_page = ocr_res_for_layouter[pos] if pos < len(ocr_res_for_layouter) else []

        regions: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        # OCR-derived text regions. Use the in-place-tagged dict for the
        # layout label if available (1:1 with our input order); if the dict
        # was dropped by the garbage filter, fall back to "text".
        for i, ocr in enumerate(ocr_list):
            tagged = ocr_tagged_for_page[i] if i < len(ocr_tagged_for_page) else {}
            if not isinstance(tagged, dict):
                tagged = {}
            layout_label = str(tagged.get("layout_type") or "text").lower()
            rtype = _layout_label_to_region_type(layout_label, has_text=True)
            regions.append({
                "id": uuid.uuid4().hex[:10],
                "type": rtype,
                "bbox": {
                    "x": float(ocr.x0), "y": float(ocr.y0),
                    "w": float(ocr.x1 - ocr.x0), "h": float(ocr.y1 - ocr.y0),
                    "page_index": idx, "coord_space": coord,
                },
                "text": ocr.text,
                "confidence": float(ocr.confidence),
                "source_tool": f"deepdoc/{backend_name}",
                "attributes": {"layout_label": layout_label, "ocr_backend": backend_name},
                "pii_spans": [],
            })

        # Layout-only regions (tables, figures, titles without OCR overlap) +
        # collect table regions for TSR. Track each crop's page-pixel offset
        # so we can rewrite TSR's crop-local coords back to full-page coords.
        table_crops: List[np.ndarray] = []
        table_region_ids: List[str] = []
        table_offsets: List[tuple[int, int]] = []   # (cx0, cy0) per crop
        for lt in layout_for_page:
            label = str(lt.get("type", "")).lower()
            score = float(lt.get("score", 0.0) or 0.0)
            x0 = float(lt.get("x0", 0.0))
            x1 = float(lt.get("x1", 0.0))
            y0 = float(lt.get("top", 0.0))
            y1 = float(lt.get("bottom", 0.0))
            if x1 <= x0 or y1 <= y0:
                continue
            rtype = _layout_label_to_region_type(label, has_text=False)
            region_id = uuid.uuid4().hex[:10]
            regions.append({
                "id": region_id,
                "type": rtype,
                "bbox": {
                    "x": x0, "y": y0,
                    "w": x1 - x0, "h": y1 - y0,
                    "page_index": idx, "coord_space": coord,
                },
                "text": "",
                "confidence": score,
                "source_tool": f"deepdoc/{backend_name}",
                "attributes": {"layout_label": label, "source": "layout"},
                "pii_spans": [],
            })
            if label == "table":
                try:
                    h, w = img.shape[:2]
                    cx0 = max(0, int(x0)); cy0 = max(0, int(y0))
                    cx1 = min(w, int(x1)); cy1 = min(h, int(y1))
                    if cx1 > cx0 and cy1 > cy0:
                        table_crops.append(img[cy0:cy1, cx0:cx1])
                        table_region_ids.append(region_id)
                        table_offsets.append((cx0, cy0))
                except Exception:  # noqa: BLE001
                    traceback.print_exc(file=sys.stderr)

        if table_crops:
            try:
                tsr_results = tsr(table_crops)
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                tsr_results = [[] for _ in table_crops]
            for region_id, lts, (off_x, off_y) in zip(
                table_region_ids, tsr_results, table_offsets
            ):
                table_model = _build_table_cells(
                    region_id=region_id,
                    tsr_bands=lts,
                    offset_x=off_x,
                    offset_y=off_y,
                    page_index=idx,
                    coord_space=coord,
                    ocr_results=ocr_list,
                )
                tables.append(table_model)

        full_text = "\n".join(r["text"] for r in regions if r.get("text"))
        pages_out.append({
            "page_index": idx,
            "regions": regions,
            "tables": tables,
            "full_text": full_text,
        })
        from app.workers._io import write_partial as _wp
        _wp({"pages": list(pages_out)})

    return {"pages": pages_out}


def _build_table_cells(
    *,
    region_id: str,
    tsr_bands: List[Dict[str, Any]],
    offset_x: int,
    offset_y: int,
    page_index: int,
    coord_space: str,
    ocr_results: List[Any],
) -> Dict[str, Any]:
    """Build a TableModel dict from deepdoc TSR's row/column band detections.

    TSR returns each row and column as a separate band with label
    ``"table row"``, ``"table column"``, ``"table column header"``, etc.
    Bands' coordinates are in **table-crop pixels** — we add the crop's
    ``(offset_x, offset_y)`` to land in full-page pixel coords. The grid is
    formed by Cartesian product (rows × columns). For each (row, col) cell
    we find OCR text whose centre falls inside the cell bbox.
    """
    def _shift(band: Dict[str, Any]) -> Dict[str, float]:
        return {
            "x0": float(band.get("x0", 0.0)) + offset_x,
            "x1": float(band.get("x1", 0.0)) + offset_x,
            "top": float(band.get("top", 0.0)) + offset_y,
            "bottom": float(band.get("bottom", 0.0)) + offset_y,
        }

    rows = [
        _shift(b) for b in tsr_bands
        if "row" in str(b.get("label", "")).lower()
    ]
    cols = [
        _shift(b) for b in tsr_bands
        if "column" in str(b.get("label", "")).lower()
    ]
    rows.sort(key=lambda b: b["top"])
    cols.sort(key=lambda b: b["x0"])

    n_rows = len(rows)
    n_cols = len(cols)

    cells: List[Dict[str, Any]] = []
    if n_rows > 0 and n_cols > 0:
        # Pre-compute every cell bbox.
        cell_bboxes: Dict[tuple[int, int], tuple[float, float, float, float]] = {}
        for r_idx, row in enumerate(rows):
            for c_idx, col in enumerate(cols):
                x0 = col["x0"]; x1 = col["x1"]
                y0 = row["top"]; y1 = row["bottom"]
                if x1 <= x0 or y1 <= y0:
                    continue
                cell_bboxes[(r_idx, c_idx)] = (x0, y0, x1, y1)

        # Assign each OCR result to exactly one cell. TSR row / column bands
        # often overlap on the edges, so a naive "centre-in-bbox" check
        # places the same text in 2-5 neighbouring cells (the "showing same
        # data multiple times" bug). Tiebreaker: closest cell centre among
        # cells that contain the OCR centre. Track by OCR list index so
        # later text-ordering doesn't need a re-scan.
        # cell_idx_to_ocr_idx: cell key -> list of (sort_x, ocr_index)
        cell_assignments: Dict[tuple[int, int], List[tuple[float, int]]] = {key: [] for key in cell_bboxes}
        for o_idx, ocr in enumerate(ocr_results):
            text = (ocr.text or "").strip()
            if not text:
                continue
            cx = (ocr.x0 + ocr.x1) * 0.5
            cy = (ocr.y0 + ocr.y1) * 0.5
            best_key: tuple[int, int] | None = None
            best_dist = float("inf")
            for key, (x0, y0, x1, y1) in cell_bboxes.items():
                if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                    continue
                ccx = (x0 + x1) * 0.5
                ccy = (y0 + y1) * 0.5
                d = (ccx - cx) * (ccx - cx) + (ccy - cy) * (ccy - cy)
                if d < best_dist:
                    best_dist = d
                    best_key = key
            if best_key is not None:
                cell_assignments[best_key].append((float(ocr.x0), o_idx))

        # Emit cells row-major; text is concatenated in left-to-right order
        # inside each cell.
        for (r_idx, c_idx), (x0, y0, x1, y1) in sorted(cell_bboxes.items()):
            frags = sorted(cell_assignments[(r_idx, c_idx)], key=lambda p: p[0])
            text = " ".join(ocr_results[o_idx].text.strip() for _, o_idx in frags).strip()
            cells.append({
                "row": r_idx,
                "col": c_idx,
                "rowspan": 1,
                "colspan": 1,
                "text": text,
                "bbox": {
                    "x": x0, "y": y0,
                    "w": x1 - x0, "h": y1 - y0,
                    "page_index": page_index, "coord_space": coord_space,
                },
                "multiline": "\n" in text,
            })

    return {
        "region_id": region_id,
        "orientation": "horizontal",
        "border_mode": "mixed",
        "n_rows": n_rows,
        "n_cols": n_cols,
        "cells": cells,
    }


def _layout_label_to_region_type(label: str, *, has_text: bool) -> str:
    """Map deepdoc layout labels onto our RegionType enum values."""
    label = (label or "").lower()
    if "table" in label and "caption" not in label:
        return "table"
    if "figure" in label and "caption" not in label:
        return "image"
    if "title" in label or "header" in label:
        return "kv_pair"
    if has_text:
        return "normal_text"
    if label in ("reference", "equation"):
        return "normal_text"
    return "normal_text"


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
