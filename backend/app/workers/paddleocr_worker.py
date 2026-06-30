"""PaddleOCR baseline worker: text detection + recognition (no table structure).

This mirrors easyocr/doctr workers — a standalone OCR pass that emits
line-level text regions. Uses the lightweight PP-OCRv4 text pipeline rather
than the heavyweight PP-Structure layout/table pipeline.

stdin payload:
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": "...", "width": int, "height": int, "dpi": int}, ... },
      "params": { "lang": "en" }
    }
"""

from __future__ import annotations

import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import gc

    from paddleocr import PaddleOCR  # type: ignore

    params = payload.get("params") or {}
    lang = params.get("lang", "en")

    # PP-OCRv5 mobile is the default in paddleocr>=3 and peaks well above 8 GB
    # in the recognizer; PP-OCRv4 mobile is ~3× smaller and fits comfortably.
    # Callers can opt back into v5 by passing `params.ocr_version = "PP-OCRv5"`.
    ocr_version = params.get("ocr_version", "PP-OCRv4")
    init_kwargs: Dict[str, Any] = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "lang": lang,
    }
    try:
        reader = PaddleOCR(ocr_version=ocr_version, **init_kwargs)
    except TypeError:
        # Older paddleocr without `ocr_version` kwarg — fall back to defaults.
        reader = PaddleOCR(**init_kwargs)

    from app.workers._io import write_partial, write_progress
    _pages = list((payload.get("pages") or {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="paddleocr")
        coord = f"image_px@{p['dpi']}"
        regions: List[Dict[str, Any]] = []
        try:
            results = reader.predict(p["image_path"])
            for line in _iter_text_lines(results):
                text, confidence, quad = line
                text = (text or "").strip()
                if not text or quad is None:
                    continue
                x, y, w, h = _quad_to_axis_rect(quad)
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
                    "source_tool": "paddleocr",
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
        # Stream incremental partial so a later-page timeout doesn't lose
        # the work we just finished.
        write_partial({"pages": list(pages_out)})
        # Drop the per-page result + paddle's intermediate tensors before
        # loading the next page — keeps peak RSS bounded on small Macs.
        del results
        gc.collect()

    return {"pages": pages_out}


def _iter_text_lines(results: Any):
    """Yield (text, confidence, quad) tuples from PaddleOCR.predict output.

    PaddleOCR's predict() shape has shifted across releases — handle both the
    older ``[(quad, (text, conf)), ...]`` per-page layout and the newer
    OCRResult-style dict with ``rec_texts``/``rec_scores``/``rec_polys``.
    """
    if results is None:
        return
    iterable = results if isinstance(results, list) else [results]
    for page_res in iterable:
        if page_res is None:
            continue
        # newer OCRResult / dict-like
        if isinstance(page_res, dict) or hasattr(page_res, "get"):
            texts = page_res.get("rec_texts") if isinstance(page_res, dict) else getattr(page_res, "json", lambda: {})()
            # try attribute access first
            t = getattr(page_res, "rec_texts", None) or (page_res.get("rec_texts") if isinstance(page_res, dict) else None)
            s = getattr(page_res, "rec_scores", None) or (page_res.get("rec_scores") if isinstance(page_res, dict) else None)
            polys = getattr(page_res, "rec_polys", None) or (page_res.get("rec_polys") if isinstance(page_res, dict) else None)
            if t is not None and s is not None and polys is not None:
                for text, score, poly in zip(t, s, polys):
                    yield str(text), float(score or 0.0), poly
                continue
        # legacy list-of-tuples per page
        if isinstance(page_res, list):
            for entry in page_res:
                if not entry:
                    continue
                try:
                    quad, payload2 = entry
                    if isinstance(payload2, (list, tuple)) and len(payload2) >= 2:
                        text, conf = payload2[0], payload2[1]
                        yield str(text), float(conf or 0.0), quad
                except Exception:  # noqa: BLE001
                    continue


def _quad_to_axis_rect(quad: Any) -> Tuple[float, float, float, float]:
    """Convert a 4-point polygon (numpy array or list of [x,y]) to (x, y, w, h)."""
    pts = list(quad)
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    x = min(xs)
    y = min(ys)
    return x, y, max(xs) - x, max(ys) - y


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
