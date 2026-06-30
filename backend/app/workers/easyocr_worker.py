"""EasyOCR worker: deep-learning OCR baseline (text regions, no table structure).

stdin payload:
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": "...", "width": int, "height": int, "dpi": int}, ... },
      "params": { "lang": "en" }
    }
"""

from __future__ import annotations

import traceback
import sys
import uuid
from typing import Any, Dict, List


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import easyocr  # type: ignore

    params = payload.get("params") or {}
    lang = params.get("lang", "en")
    # EasyOCR uses 2-letter ISO codes; strip trailing characters if 3-letter tesseract code passed
    if len(lang) == 3:
        lang = lang[:2]

    reader = easyocr.Reader([lang], gpu=False, verbose=False)

    from app.workers._io import write_progress
    _pages = list(payload.get("pages", {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="easyocr")
        coord = f"image_px@{p['dpi']}"
        regions: List[Dict[str, Any]] = []
        try:
            results = reader.readtext(p["image_path"], detail=1, paragraph=False)
            for (bbox_quad, text, confidence) in results:
                text = (text or "").strip()
                if not text:
                    continue
                xs = [pt[0] for pt in bbox_quad]
                ys = [pt[1] for pt in bbox_quad]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                regions.append({
                    "id": uuid.uuid4().hex[:10],
                    "type": "normal_text",
                    "bbox": {
                        "x": float(x), "y": float(y),
                        "w": float(w), "h": float(h),
                        "page_index": idx, "coord_space": coord,
                    },
                    "text": text,
                    "confidence": float(confidence),
                    "source_tool": "easyocr",
                    "attributes": {},
                    "pii_spans": [],
                })
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)

        pages_out.append({
            "page_index": idx,
            "regions": regions,
            "tables": [],
            "full_text": "\n".join(r["text"] for r in regions),
        })
        from app.workers._io import write_partial as _wp
        _wp({"pages": list(pages_out)})

    return {"pages": pages_out}


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
