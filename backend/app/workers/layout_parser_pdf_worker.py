"""Layout-Parser (PDF-native) worker.

Differences vs. ``layout_parser_worker``:

- Uses ``lp.load_pdf()`` (under the hood, pdfplumber) to read the PDF's text
  layer directly. Text-layer "word tokens" become first-class regions tagged
  as ``normal_text`` with ``attributes.source = "pdf_text"`` — no OCR, no
  recognition error.
- Still runs ``PaddleDetectionLayoutModel`` on the rasterized page for
  Figure / Table / Title detection (those classes don't live in the PDF
  text layer). Visual blocks are tagged ``attributes.source = "visual"``.

The combination is meaningfully different from the rasterized-image-only
``layout_parser`` card: text positions are exact (from the PDF stream) while
the visual model only fires on non-text structural elements.

Vector PDFs only — driven by the solution's ``supported_kinds={"vector"}``.

stdin payload (same shape as the other worker plus we read ``pdf_path``):
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": ..., "width": ..., "height": ..., "dpi": ...}, ... },
      "params": {
        "score_threshold": 0.5,
        "model_config": "lp://PubLayNet/ppyolov2_r50vd_dcn_365e/config",
        "use_visual_model": true   # set false to skip the model entirely
      }
    }
"""

from __future__ import annotations

import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


_LP_LABEL_TO_OUR_TYPE = {
    "Text": "normal_text",
    "Title": "kv_pair",
    "List": "normal_text",
    "Table": "table",
    "Figure": "image",
}


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import layoutparser as lp  # type: ignore
    from PIL import Image  # type: ignore

    params = payload.get("params") or {}
    score_threshold = float(params.get("score_threshold", 0.5))
    use_visual_model = bool(params.get("use_visual_model", True))
    pdf_path = payload["pdf_path"]
    pages_meta: Dict[str, Dict[str, Any]] = payload.get("pages") or {}

    # Step 1: pull text-layer blocks from the PDF directly. dpi=72 here means
    # "PDF points" — we scale to image_px below.
    try:
        pdf_layouts = lp.load_pdf(pdf_path, load_images=False)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        pdf_layouts = []

    # Step 2: visual model. Loaded lazily so a request with
    # use_visual_model=False (or visual_model_load_failure) still surfaces
    # the text-layer blocks.
    visual_model = None
    if use_visual_model:
        try:
            label_map = params.get("label_map") or {0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
            model_config = params.get(
                "model_config",
                "lp://PubLayNet/ppyolov2_r50vd_dcn_365e/config",
            )
            visual_model = lp.PaddleDetectionLayoutModel(
                config_path=model_config,
                label_map=label_map,
                enforce_cpu=True,
            )
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            visual_model = None

    from app.workers._io import write_progress
    _pages = list(pages_meta.items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="layout_parser_pdf")
        dpi = int(p["dpi"])
        coord = f"image_px@{dpi}"
        scale = dpi / 72.0   # PDF points → image pixels at run DPI

        regions: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        # --- text-layer blocks (PDF points → image_px) -----------------
        if idx < len(pdf_layouts):
            for block in pdf_layouts[idx]:
                text = (getattr(block, "text", "") or "").strip()
                x1, y1, x2, y2 = block.coordinates
                x1 *= scale; y1 *= scale; x2 *= scale; y2 *= scale
                if x2 <= x1 or y2 <= y1 or not text:
                    continue
                regions.append({
                    "id": uuid.uuid4().hex[:10],
                    "type": "normal_text",
                    "bbox": {
                        "x": float(x1), "y": float(y1),
                        "w": float(x2 - x1), "h": float(y2 - y1),
                        "page_index": idx, "coord_space": coord,
                    },
                    "text": text,
                    # Text comes straight from the PDF stream — max confidence.
                    "confidence": 1.0,
                    "source_tool": "layout_parser/pdf_text",
                    "attributes": {
                        "source": "pdf_text",
                        "layout_label": "text",
                    },
                    "pii_spans": [],
                })

        # --- visual blocks (rasterized image @ run DPI) ----------------
        if visual_model is not None:
            try:
                img = Image.open(p["image_path"]).convert("RGB")
                import numpy as np
                arr = np.asarray(img)
                layout = visual_model.detect(arr)
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                layout = []

            for block in layout:
                score = float(getattr(block, "score", 0.0) or 0.0)
                if score < score_threshold:
                    continue
                label = str(block.type or "")
                # Skip the visual model's "Text" hits — the PDF text layer
                # is authoritative for text positions. Keep Title / List /
                # Table / Figure which are *layout* classifications that
                # the text layer alone can't supply.
                if label in ("Text",):
                    continue
                our_type = _LP_LABEL_TO_OUR_TYPE.get(label, "unknown")
                x1, y1, x2, y2 = block.coordinates
                x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                region_id = uuid.uuid4().hex[:10]
                regions.append({
                    "id": region_id,
                    "type": our_type,
                    "bbox": {
                        "x": x1, "y": y1,
                        "w": x2 - x1, "h": y2 - y1,
                        "page_index": idx, "coord_space": coord,
                    },
                    "text": "",
                    "confidence": score,
                    "source_tool": "layout_parser/visual",
                    "attributes": {
                        "source": "visual",
                        "layout_label": label.lower(),
                        "detector": "layout_parser.PaddleDetectionLayoutModel",
                    },
                    "pii_spans": [],
                })
                if our_type == "table":
                    tables.append({
                        "region_id": region_id,
                        "orientation": "horizontal",
                        "border_mode": "unknown",
                        "n_rows": 0,
                        "n_cols": 0,
                        "cells": [],
                    })

        label_str, scores = _classify_layout(regions)
        pages_out.append({
            "page_index": idx,
            "regions": regions,
            "tables": tables,
            "doc_format": label_str,
            "doc_format_scores": scores,
        })

    return {"pages": pages_out}


def _classify_layout(regions: List[Dict[str, Any]]) -> Tuple[str, Dict[str, float]]:
    """Mirror of DocFormatStage.classify_page operating on worker dicts."""
    if not regions:
        return "unknown", {}
    area_by_bucket: Dict[str, float] = {
        "tables": 0.0, "figures": 0.0, "text": 0.0, "headings": 0.0, "lists": 0.0, "other": 0.0,
    }
    n_headings = 0
    for r in regions:
        bb = r.get("bbox") or {}
        area = float(bb.get("w", 0)) * float(bb.get("h", 0))
        if area <= 0:
            continue
        rtype = r.get("type", "unknown")
        layout_label = str(((r.get("attributes") or {}).get("layout_label") or "")).lower()
        if rtype in ("table", "table_header", "table_row", "table_cell"):
            area_by_bucket["tables"] += area
        elif rtype == "image":
            area_by_bucket["figures"] += area
        elif rtype == "normal_text":
            if layout_label == "list":
                area_by_bucket["lists"] += area
            else:
                area_by_bucket["text"] += area
        elif rtype == "kv_pair":
            if layout_label in ("title", "header"):
                area_by_bucket["headings"] += area
                n_headings += 1
            else:
                area_by_bucket["other"] += area
        else:
            area_by_bucket["other"] += area
    total = sum(area_by_bucket.values())
    if total <= 0:
        return "unknown", {}
    scores = {k: v / total for k, v in area_by_bucket.items() if v > 0}
    tables_frac = scores.get("tables", 0.0)
    figures_frac = scores.get("figures", 0.0)
    text_frac = scores.get("text", 0.0)
    if tables_frac >= 0.35:
        return "tabular-heavy", scores
    if figures_frac >= 0.35:
        return "image-heavy", scores
    if n_headings >= 5 and tables_frac < 0.20:
        return "form-like", scores
    if text_frac >= 0.70:
        return "narrative", scores
    return "mixed", scores


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
