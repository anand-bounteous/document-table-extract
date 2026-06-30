"""DocTR worker: two-stage deep-learning OCR baseline (text regions, no table structure).

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
    import os
    # Force CPU inference — MPS float64 gap on Apple Silicon
    os.environ.setdefault("DOCTR_MULTIPROCESSING_DISABLE", "TRUE")

    from doctr.models import ocr_predictor  # type: ignore
    from doctr.io import DocumentFile  # type: ignore

    model = ocr_predictor(pretrained=True, assume_straight_pages=True)

    from app.workers._io import write_progress
    _pages = list(payload.get("pages", {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool="doctr")
        coord = f"image_px@{p['dpi']}"
        w_px = int(p["width"])
        h_px = int(p["height"])
        regions: List[Dict[str, Any]] = []

        try:
            doc = DocumentFile.from_images([p["image_path"]])
            result = model(doc)
            # result.pages is a list; we only passed one image so index 0
            for block in result.pages[0].blocks:
                for line in block.lines:
                    line_text_parts = []
                    line_bbox = None
                    for word in line.words:
                        # word.geometry: ((x1,y1),(x2,y2)) in [0,1] relative coords
                        (rx1, ry1), (rx2, ry2) = word.geometry
                        x = rx1 * w_px
                        y = ry1 * h_px
                        w = (rx2 - rx1) * w_px
                        h = (ry2 - ry1) * h_px
                        line_text_parts.append(word.value)
                        if line_bbox is None:
                            line_bbox = [x, y, x + w, y + h]
                        else:
                            line_bbox[0] = min(line_bbox[0], x)
                            line_bbox[1] = min(line_bbox[1], y)
                            line_bbox[2] = max(line_bbox[2], x + w)
                            line_bbox[3] = max(line_bbox[3], y + h)
                    if not line_text_parts or line_bbox is None:
                        continue
                    lx, ly, lx2, ly2 = line_bbox
                    text = " ".join(line_text_parts)
                    # Use line-level confidence: mean of word confidences
                    conf = sum(w.confidence for w in line.words) / max(len(line.words), 1)
                    regions.append({
                        "id": uuid.uuid4().hex[:10],
                        "type": "normal_text",
                        "bbox": {
                            "x": float(lx), "y": float(ly),
                            "w": float(lx2 - lx), "h": float(ly2 - ly),
                            "page_index": idx, "coord_space": coord,
                        },
                        "text": text,
                        "confidence": float(conf),
                        "source_tool": "doctr",
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
