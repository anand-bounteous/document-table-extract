"""docling worker: high-level document converter.

We invoke ``DocumentConverter().convert(pdf_path)`` and walk the resulting
``DoclingDocument``. docling reports bboxes in PDF points; we convert to image
pixels at the run DPI (top-left origin).
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


def _build_ocr_options(backend: str):
    """Resolve ``ocr_backend`` to the matching docling OCR options class.

    Falls back to EasyOCR with a logged note if the requested backend's deps
    aren't available, so a missing tesseract binary or onnxruntime install
    doesn't kill the whole run — the resulting card will say "easyocr (fallback
    from <requested>)" so the UI is honest about what actually ran.
    """
    from docling.datamodel.pipeline_options import (  # type: ignore
        EasyOcrOptions, TesseractCliOcrOptions, RapidOcrOptions,
    )
    name = (backend or "easyocr").lower()
    if name in {"tesseract", "tesseract_cli", "tesseract-cli"}:
        return TesseractCliOcrOptions(force_full_page_ocr=False), "tesseract_cli"
    if name in {"rapidocr", "rapid"}:
        try:
            return RapidOcrOptions(force_full_page_ocr=False), "rapidocr"
        except Exception as exc:  # noqa: BLE001
            print(f"[docling_worker] RapidOcrOptions unavailable: {exc}; falling back to easyocr", file=sys.stderr)
            return EasyOcrOptions(force_full_page_ocr=False), "easyocr (fallback from rapidocr)"
    return EasyOcrOptions(force_full_page_ocr=False), "easyocr"


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
    from docling.datamodel.base_models import InputFormat  # type: ignore
    from docling.datamodel.pipeline_options import (  # type: ignore
        AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions,
    )
    import fitz  # type: ignore

    pdf_path = payload["pdf_path"]
    pages_meta: Dict[str, Dict[str, Any]] = payload.get("pages", {}) or {}
    page_indices = sorted(int(k) for k in pages_meta.keys())
    params = payload.get("params") or {}
    requested_backend = str(params.get("ocr_backend", "easyocr"))

    doc = fitz.open(pdf_path)
    try:
        page_heights = {i: doc[i].rect.height for i in range(doc.page_count)}
    finally:
        doc.close()

    # docling processes the entire document in one convert() call. Emit a
    # coarse "1 of total" so the UI shows activity while convert is running.
    from app.workers._io import write_progress
    _total = int(payload.get("__progress_total", len(page_indices)))
    _offset = int(payload.get("__progress_offset", 0))
    if page_indices:
        write_progress(_offset + 1, _total, "running", tool="docling")

    # Custom backends (doctr / trocr_*) aren't docling-native; we run docling
    # with do_ocr=False (layout + PDF text only) and overwrite each region's
    # text via the chosen engine in a post-pass.
    is_custom_backend = requested_backend.lower() in {"doctr", "trocr_hw", "trocr_handwritten", "trocr_printed"}
    if is_custom_backend:
        ocr_options = None
        resolved_backend = requested_backend.lower()
    else:
        ocr_options, resolved_backend = _build_ocr_options(requested_backend)

    # Apple Silicon MPS does not implement float64, which docling's models hit.
    # Force CPU until docling/torch handle the missing dtype gracefully.
    if is_custom_backend:
        pipeline_options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
            do_ocr=False,
        )
    else:
        pipeline_options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
            ocr_options=ocr_options,
        )
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = conv.convert(pdf_path)
    ddoc = result.document

    pages_out: Dict[int, Dict[str, Any]] = {i: {"page_index": i, "regions": [], "tables": [], "full_text": ""} for i in page_indices}
    text_buffers: Dict[int, List[str]] = {i: [] for i in page_indices}

    for item, _level in ddoc.iterate_items():
        label = getattr(item, "label", None) or ""
        text = getattr(item, "text", None) or ""
        for prov in getattr(item, "prov", []) or []:
            page_no = int(getattr(prov, "page_no", 1)) - 1
            if page_no not in pages_out:
                continue
            bbox = getattr(prov, "bbox", None)
            if bbox is None:
                continue
            meta = pages_meta[str(page_no)]
            dpi = int(meta["dpi"])
            coord = f"image_px@{dpi}"
            page_h = page_heights.get(page_no, 0)
            bx, by, bw, bh = _docling_bbox_to_image_px(bbox, page_h, dpi)
            rtype = _map_label(label)
            region_id = uuid.uuid4().hex[:10]
            pages_out[page_no]["regions"].append({
                "id": region_id,
                "type": rtype,
                "bbox": {"x": bx, "y": by, "w": bw, "h": bh, "page_index": page_no, "coord_space": coord},
                "text": text,
                "confidence": 0.85,
                "source_tool": "docling",
                "attributes": {
                    "docling_label": label,
                    "ref": getattr(item, "self_ref", None),
                    "ocr_backend": resolved_backend,
                },
                "pii_spans": [],
            })
            if text:
                text_buffers[page_no].append(text)

    for t_item in getattr(ddoc, "tables", []) or []:
        data = getattr(t_item, "data", None)
        if data is None or not getattr(data, "grid", None):
            continue
        grid = data.grid
        n_rows = len(grid)
        n_cols = max((len(r) for r in grid), default=0)
        for prov in getattr(t_item, "prov", []) or []:
            page_no = int(getattr(prov, "page_no", 1)) - 1
            if page_no not in pages_out:
                continue
            meta = pages_meta[str(page_no)]
            dpi = int(meta["dpi"])
            coord = f"image_px@{dpi}"
            page_h = page_heights.get(page_no, 0)
            tx, ty, tw, th = _docling_bbox_to_image_px(prov.bbox, page_h, dpi)
            region_id = uuid.uuid4().hex[:10]
            pages_out[page_no]["regions"].append({
                "id": region_id,
                "type": "table",
                "bbox": {"x": tx, "y": ty, "w": tw, "h": th, "page_index": page_no, "coord_space": coord},
                "text": "",
                "confidence": 0.85,
                "source_tool": "docling",
                "attributes": {"docling_label": "table", "ocr_backend": resolved_backend},
                "pii_spans": [],
            })
            cells_out: List[Dict[str, Any]] = []
            covered: set[tuple[int, int]] = set()
            for r_idx, row in enumerate(grid):
                for c_idx, cell in enumerate(row):
                    if (r_idx, c_idx) in covered:
                        continue  # phantom repetition of a spanned cell
                    cell_text = (getattr(cell, "text", None) or "").strip()
                    rs = int(getattr(cell, "row_span", 1) or 1)
                    cs = int(getattr(cell, "col_span", 1) or 1)
                    is_header = bool(
                        getattr(cell, "column_header", False)
                        or getattr(cell, "row_header", False)
                        or getattr(cell, "row_section", False)
                    )
                    cells_out.append({
                        "row": r_idx,
                        "col": c_idx,
                        "rowspan": rs,
                        "colspan": cs,
                        "text": cell_text,
                        "bbox": None,
                        "multiline": "\n" in cell_text,
                        "is_header": is_header,
                    })
                    for dr in range(rs):
                        for dc in range(cs):
                            if dr or dc:
                                covered.add((r_idx + dr, c_idx + dc))
            cells_out, n_rows = _split_merged_rows(cells_out, n_rows)
            pages_out[page_no]["tables"].append({
                "region_id": region_id,
                "orientation": "horizontal",
                "border_mode": "mixed",
                "n_rows": n_rows,
                "n_cols": n_cols,
                "cells": cells_out,
            })

    # Custom-backend post-OCR: overwrite every text region's text with the
    # output of doctr / trocr-hw / trocr-printed applied to the region's bbox
    # crop. Tables stay on docling's native extraction (cell-text reconstruction
    # from layout pixels is a different beast). If the engine's deps aren't
    # installed, we fall back to whatever docling left in the region.
    if is_custom_backend:
        from app.workers._docling_post_ocr import get_post_ocr_fn
        from PIL import Image  # type: ignore

        ocr_fn = get_post_ocr_fn(requested_backend)
        if ocr_fn is None:
            resolved_backend = f"easyocr (fallback from {requested_backend})"
            print(f"[docling_worker] {requested_backend} unavailable; leaving docling output untouched", file=sys.stderr)
        else:
            page_image_cache: Dict[int, Any] = {}
            for page_no in page_indices:
                meta = pages_meta[str(page_no)]
                try:
                    page_image_cache[page_no] = Image.open(meta["image_path"]).convert("RGB")
                except Exception as exc:  # noqa: BLE001
                    print(f"[docling_worker] cannot open page {page_no} image: {exc}", file=sys.stderr)

            text_buffers = {i: [] for i in page_indices}
            for page_no, page_payload in pages_out.items():
                img = page_image_cache.get(page_no)
                if img is None:
                    continue
                for region in page_payload["regions"]:
                    if region.get("type") == "table":
                        continue
                    b = region["bbox"]
                    x = max(0, int(b.get("x", 0)))
                    y = max(0, int(b.get("y", 0)))
                    w = max(1, int(b.get("w", 0)))
                    h = max(1, int(b.get("h", 0)))
                    x2 = min(img.width, x + w)
                    y2 = min(img.height, y + h)
                    if x2 <= x or y2 <= y:
                        continue
                    crop = img.crop((x, y, x2, y2))
                    new_text = ocr_fn(crop)
                    if new_text:
                        region["text"] = new_text
                    region["attributes"]["ocr_backend"] = resolved_backend
                    if region["text"]:
                        text_buffers[page_no].append(region["text"])
            # Update tables' ocr_backend attribute too so the card metadata is consistent.
            for page_payload in pages_out.values():
                for region in page_payload["regions"]:
                    if region.get("type") == "table":
                        region["attributes"]["ocr_backend"] = resolved_backend

    for i in page_indices:
        pages_out[i]["full_text"] = "\n".join(text_buffers[i])

    return {"pages": [pages_out[i] for i in page_indices]}


def _split_merged_rows(cells_out: List[Dict[str, Any]], n_rows: int) -> tuple:
    """Detect and split rows where docling merged multiple physical table rows.

    docling joins content from multiple PDF rows into a single grid row when
    there are no horizontal rules between rows, using \\n as a separator within
    each cell. The minimum non-zero \\n count across cells in a row tells us
    how many rows were merged.  Cells with more \\n tokens than that minimum
    are divided into equal-sized groups (e.g. a 6-token date "16\\nJun\\n19\\n17\\nJun\\n19"
    with n_splits=2 becomes "16 Jun 19" and "17 Jun 19").
    """
    import math
    from collections import defaultdict

    by_row: Dict[int, List] = defaultdict(list)
    for c in cells_out:
        by_row[c["row"]].append(c)

    new_cells: List[Dict[str, Any]] = []
    row_offset = 0

    for r in range(n_rows):
        row_cells = by_row.get(r, [])
        if not row_cells:
            continue

        base = r + row_offset

        # Only consider simple (non-spanned, non-empty) cells for split detection
        nl_counts = [
            c["text"].count("\n")
            for c in row_cells
            if c["rowspan"] == 1 and c["colspan"] == 1 and c["text"].strip()
        ]

        if not nl_counts or max(nl_counts) == 0:
            # No merging detected — normalize any stray \n to space
            for c in row_cells:
                new_cells.append({**c, "row": base,
                                   "text": c["text"].replace("\n", " ").strip()})
            continue

        # Minimum non-zero \n count = number of extra rows that were merged in
        min_nl = min(x for x in nl_counts if x > 0)
        n_splits = min_nl + 1
        row_offset += min_nl

        for c in row_cells:
            if c["rowspan"] != 1 or c["colspan"] != 1:
                # Spanned cell: widen to cover all new sub-rows, normalize text
                new_cells.append({**c, "row": base,
                                   "rowspan": c["rowspan"] + min_nl,
                                   "text": c["text"].replace("\n", " ").strip()})
                continue

            raw_parts = c["text"].split("\n") if c["text"].strip() else [""]
            n_parts = len(raw_parts)

            if n_parts <= 1:
                # Single value — assign to first sub-row; leave rest empty
                new_cells.append({**c, "row": base,
                                   "rowspan": 1, "text": raw_parts[0].strip()})
                for sub in range(1, n_splits):
                    new_cells.append({**c, "row": base + sub,
                                       "rowspan": 1, "text": "", "multiline": False})
            elif n_parts == n_splits:
                # One part per sub-row (e.g. "BALANCE FORWARD\nATM WITHDRAWAL...")
                for sub, part in enumerate(raw_parts):
                    new_cells.append({**c, "row": base + sub,
                                       "rowspan": 1, "text": part.strip(), "multiline": False})
            else:
                # More tokens than splits (e.g. 6 words for 2 dates) — group evenly
                chunk = math.ceil(n_parts / n_splits)
                for sub in range(n_splits):
                    group = raw_parts[sub * chunk: (sub + 1) * chunk]
                    text = " ".join(p.strip() for p in group if p.strip())
                    new_cells.append({**c, "row": base + sub,
                                       "rowspan": 1, "text": text, "multiline": False})

    return new_cells, n_rows + row_offset


def _docling_bbox_to_image_px(bbox, page_h_pts: float, dpi: int) -> Tuple[float, float, float, float]:
    """docling BBox has l/r/t/b in PDF points; t/b origin depends on coord_origin."""
    scale = dpi / 72.0
    l = float(getattr(bbox, "l", 0))
    r = float(getattr(bbox, "r", 0))
    t = float(getattr(bbox, "t", 0))
    b = float(getattr(bbox, "b", 0))
    origin = getattr(bbox, "coord_origin", None)
    origin_name = getattr(origin, "name", str(origin or "")).upper()
    if "BOTTOM" in origin_name:
        y1 = (page_h_pts - max(t, b)) * scale
        y2 = (page_h_pts - min(t, b)) * scale
    else:
        y1 = min(t, b) * scale
        y2 = max(t, b) * scale
    x1, x2 = min(l, r) * scale, max(l, r) * scale
    return x1, y1, x2 - x1, y2 - y1


def _map_label(label: str) -> str:
    label = (label or "").lower()
    if "title" in label or "header" in label or "section" in label:
        return "kv_pair"
    if "table" in label:
        return "table"
    if "picture" in label or "figure" in label or "image" in label:
        return "image"
    if "caption" in label:
        return "normal_text"
    return "normal_text"


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
