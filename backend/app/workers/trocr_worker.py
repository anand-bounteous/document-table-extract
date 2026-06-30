"""TrOCR worker: HuggingFace transformer OCR with EasyOCR line detection.

TrOCR (https://huggingface.co/docs/transformers/model_doc/trocr) is recognition-only.
We reuse EasyOCR's ``Reader.detect()`` to find line boxes, crop each box from
the page image, and feed the crops to TrOCR.

stdin payload:
    {
      "pdf_path": "...",
      "pages": { "<idx>": {"image_path": "...", "width": int, "height": int, "dpi": int}, ... },
      "params": {
        "model_id": "microsoft/trocr-base-handwritten" | "microsoft/trocr-base-printed",
        "mode": "handwritten" | "printed",
        "lang": "en"
      }
    }
"""

from __future__ import annotations

import sys
import traceback
import uuid
from typing import Any, Dict, List, Tuple


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    import gc

    import easyocr  # type: ignore
    import torch  # type: ignore
    from PIL import Image  # type: ignore
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # type: ignore

    params = payload.get("params") or {}
    model_id = params.get("model_id", "microsoft/trocr-base-handwritten")
    mode = params.get("mode", "handwritten")
    lang = params.get("lang", "en")
    if len(lang) == 3:
        lang = lang[:2]

    # Output region type — handwriting flows through the Signatures bucket;
    # printed flows through the standard normal_text bucket.
    out_region_type = "handwriting_signature" if mode == "handwritten" else "normal_text"

    # Models load once per subprocess run.
    processor = TrOCRProcessor.from_pretrained(model_id)
    model = VisionEncoderDecoderModel.from_pretrained(model_id)
    model.eval()

    # CPU-only — Apple Silicon MPS has float64 gaps that trip TrOCR's beam
    # search, and we already pin thread counts via extra_env.
    device = torch.device("cpu")
    model.to(device)

    detector = easyocr.Reader([lang], gpu=False, verbose=False)

    from app.workers._io import write_progress
    _pages = list((payload.get("pages") or {}).items())
    _total = int(payload.get("__progress_total", len(_pages)))
    _offset = int(payload.get("__progress_offset", 0))

    pages_out: List[Dict[str, Any]] = []
    for _pos, (idx_str, p) in enumerate(_pages):
        idx = int(idx_str)
        write_progress(_offset + _pos + 1, _total, "running", page_index=idx, tool=f"trocr/{mode}")
        dpi = int(p["dpi"])
        coord = f"image_px@{dpi}"
        regions: List[Dict[str, Any]] = []

        try:
            img = Image.open(p["image_path"]).convert("RGB")
            boxes = _detect_lines(detector, p["image_path"])
            for (x1, y1, x2, y2) in boxes:
                text, conf = _recognize(model, processor, img, (x1, y1, x2, y2), device)
                if not text:
                    continue
                regions.append({
                    "id": uuid.uuid4().hex[:10],
                    "type": out_region_type,
                    "bbox": {
                        "x": float(x1), "y": float(y1),
                        "w": float(x2 - x1), "h": float(y2 - y1),
                        "page_index": idx, "coord_space": coord,
                    },
                    "text": text,
                    "confidence": conf,
                    "source_tool": f"trocr/{mode}",
                    "attributes": {"model_id": model_id, "mode": mode},
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
        gc.collect()

    return {"pages": pages_out}


def _detect_lines(reader: Any, image_path: str) -> List[Tuple[float, float, float, float]]:
    """Run EasyOCR's detector and return axis-aligned (x1,y1,x2,y2) boxes."""
    boxes: List[Tuple[float, float, float, float]] = []
    try:
        # detect() returns (horizontal_list, free_list) — horizontal first.
        horizontal, _free = reader.detect(image_path)
        # horizontal is a nested list: [[ [x1,x2,y1,y2], ... ]]
        for batch in horizontal or []:
            for box in batch or []:
                if len(box) >= 4:
                    x1, x2, y1, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
                    if x2 > x1 and y2 > y1:
                        boxes.append((x1, y1, x2, y2))
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
    return boxes


def _recognize(model: Any, processor: Any, img: Any, box: Tuple[float, float, float, float], device: Any) -> Tuple[str, float]:
    """Crop ``box`` from ``img`` and run TrOCR. Returns (text, mean-token-prob)."""
    import torch  # type: ignore

    x1, y1, x2, y2 = box
    crop = img.crop((x1, y1, x2, y2))
    if crop.width < 2 or crop.height < 2:
        return "", 0.0

    pixel_values = processor(images=crop, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        outputs = model.generate(
            pixel_values,
            max_new_tokens=128,
            return_dict_in_generate=True,
            output_scores=True,
        )
    ids = outputs.sequences[0]
    text = processor.batch_decode([ids], skip_special_tokens=True)[0].strip()

    # Approximate per-token confidence as the mean softmax probability of the
    # argmax tokens. TrOCR doesn't expose calibrated confidences; this is the
    # standard approximation.
    conf = 0.0
    if outputs.scores:
        try:
            probs = [torch.softmax(s, dim=-1)[0].max().item() for s in outputs.scores]
            if probs:
                conf = float(sum(probs) / len(probs))
        except Exception:  # noqa: BLE001
            conf = 0.0
    return text, conf


if __name__ == "__main__":
    from app.workers._io import run_worker
    run_worker(work)
