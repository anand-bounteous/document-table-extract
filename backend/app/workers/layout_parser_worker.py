"""Layout-Parser worker: PubLayNet (Text / Title / List / Table / Figure).

Subprocess-isolated. Defaults to layoutparser's PaddleDetection backend (the
PubLayNet PP-YOLOv2 model) because that ships with the ``[ocr-paddle]``
extras stack everyone in this repo already has installed — and Detectron2 is
a notoriously painful install on Apple Silicon. Detectron2 is still
available as an opt-in via ``params.backend = "detectron2"``.

stdin payload:
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": "...", "width": int, "height": int, "dpi": int}, ... },
      "params": {
        "score_threshold": 0.5,
        "backend": "paddle" | "detectron2",
        "model_config": "lp://PubLayNet/..."
      }
    }

The worker also authoritatively computes ``doc_format`` per page from the
layout label distribution, so the layout-parser solution doesn't have to rely
on the shared ``DocFormatStage``.
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
    backend = str(params.get("backend", "paddle")).lower()
    label_map = params.get("label_map") or {0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}

    if backend == "detectron2":
        # Requires detectron2 to be installed separately (see SETUP.md).
        model_config = params.get(
            "model_config",
            "lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config",
        )
        model = lp.Detectron2LayoutModel(
            config_path=model_config,
            label_map=label_map,
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", score_threshold],
        )
    else:
        # PaddleDetection PubLayNet — uses the paddlepaddle install everyone
        # already has via [ocr-paddle]. Downloads the model on first run.
        #
        # layoutparser 0.3.x's PaddleDetectionLayoutModel constructor does
        # NOT expose a `threshold` kwarg (unlike Detectron2LayoutModel). We
        # filter detections by score in post-processing below.
        # In layoutparser 0.3.x the Paddle PubLayNet model key is
        # ``ppyolov2_r50vd_dcn_365e`` (no ``_publaynet`` suffix — that suffix
        # is only used by the Detectron2 catalog). Verified via
        # ``layoutparser.models.paddledetection.catalog.MODEL_CATALOG``.
        model_config = params.get(
            "model_config",
            "lp://PubLayNet/ppyolov2_r50vd_dcn_365e/config",
        )
        model = lp.PaddleDetectionLayoutModel(
            config_path=model_config,
            label_map=label_map,
            enforce_cpu=True,
        )

    from app.workers._io import write_progress
    _pages = list((payload.get("pages") or {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="layout_parser")
        dpi = int(p["dpi"])
        coord = f"image_px@{dpi}"
        regions: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        try:
            img = Image.open(p["image_path"]).convert("RGB")
            import numpy as np
            arr = np.asarray(img)
            layout = model.detect(arr)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            pages_out.append({
                "page_index": idx,
                "regions": [],
                "tables": [],
                "doc_format": "unknown",
                "doc_format_scores": {},
            })
            continue

        for block in layout:
            score = float(getattr(block, "score", 0.0) or 0.0)
            # PaddleDetectionLayoutModel doesn't support a constructor-level
            # threshold, so we filter here for parity with the Detectron2
            # backend (where the threshold is baked into the model via
            # extra_config).
            if score < score_threshold:
                continue
            label = str(block.type or "")
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
                "source_tool": "layout_parser",
                "attributes": {
                    "layout_label": label.lower(),
                    "detector": "layout_parser.Detectron2LayoutModel",
                },
                "pii_spans": [],
            })
            if our_type == "table":
                # Empty TableModel placeholder so the Tables panel shows the
                # count; cell extraction is delegated to other solutions.
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
    """Mirrors DocFormatStage.classify_page but operates on raw worker dicts."""
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
