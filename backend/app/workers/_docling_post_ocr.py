"""Custom OCR backends for docling that aren't shipped with docling itself.

docling's `OcrFactory` exposes EasyOCR / Tesseract / RapidOCR / OcrMac /
KserveV2 out of the box. To get DocTR or TrOCR (handwritten) under docling's
layout pipeline we'd need to subclass `BaseOcrModel` and register through
docling's plugin system — substantial work tied to internal API surface.

Pragmatic alternative: let docling produce the layout + table structure with
its OCR disabled (``do_ocr=False``), then **post-OCR** each text region by
cropping the page raster to the region's bbox and running our chosen engine
on the crop. The result is what the user actually wants: "docling's layout
pipeline + DocTR/TrOCR text". Same comparison value as a real backend, no
dependence on docling internals.

Model objects are heavy (100s of MB). Load once per subprocess via
:func:`load_post_ocr` and reuse across every region on every page.
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image  # type: ignore

logger = logging.getLogger("docling_post_ocr")


# Per-process model cache so models load exactly once across all pages.
_DOCTR_PIPE = None
_TROCR_HW = None  # (processor, model, device)
_TROCR_PRINTED = None
_EASYOCR_DETECTOR = None


def _load_doctr() -> Optional[Any]:
    global _DOCTR_PIPE
    if _DOCTR_PIPE is not None:
        return _DOCTR_PIPE
    try:
        import os
        os.environ.setdefault("DOCTR_MULTIPROCESSING_DISABLE", "TRUE")
        from doctr.models import ocr_predictor  # type: ignore

        _DOCTR_PIPE = ocr_predictor(pretrained=True, assume_straight_pages=True)
        return _DOCTR_PIPE
    except Exception as exc:  # noqa: BLE001
        print(f"[docling_post_ocr] DocTR unavailable: {exc}", file=sys.stderr)
        return None


def _load_trocr(model_id: str) -> Optional[Tuple[Any, Any, Any]]:
    global _TROCR_HW, _TROCR_PRINTED
    is_hw = "handwritten" in model_id
    cached = _TROCR_HW if is_hw else _TROCR_PRINTED
    if cached is not None:
        return cached
    try:
        import torch  # type: ignore
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # type: ignore

        processor = TrOCRProcessor.from_pretrained(model_id)
        model = VisionEncoderDecoderModel.from_pretrained(model_id)
        model.eval()
        device = torch.device("cpu")
        model.to(device)
        bundle = (processor, model, device)
        if is_hw:
            _TROCR_HW = bundle
        else:
            _TROCR_PRINTED = bundle
        return bundle
    except Exception as exc:  # noqa: BLE001
        print(f"[docling_post_ocr] TrOCR unavailable for {model_id}: {exc}", file=sys.stderr)
        return None


def _load_easyocr_detector(lang: str = "en") -> Optional[Any]:
    global _EASYOCR_DETECTOR
    if _EASYOCR_DETECTOR is not None:
        return _EASYOCR_DETECTOR
    try:
        import easyocr  # type: ignore

        _EASYOCR_DETECTOR = easyocr.Reader([lang], gpu=False, verbose=False)
        return _EASYOCR_DETECTOR
    except Exception as exc:  # noqa: BLE001
        print(f"[docling_post_ocr] EasyOCR detector unavailable: {exc}", file=sys.stderr)
        return None


def _ocr_crop_doctr(crop: Image.Image) -> str:
    """Run DocTR's full predictor on a region crop; join words → lines → text."""
    pipe = _load_doctr()
    if pipe is None or crop.width < 2 or crop.height < 2:
        return ""
    try:
        import numpy as np  # type: ignore

        arr = np.array(crop.convert("RGB"))
        result = pipe([arr])
        lines: List[str] = []
        for block in result.pages[0].blocks:
            for line in block.lines:
                words = [w.value for w in line.words if (w.value or "").strip()]
                if words:
                    lines.append(" ".join(words))
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return ""


def _ocr_crop_trocr(crop: Image.Image, model_id: str, lang: str = "en") -> str:
    """Detect lines inside ``crop`` with EasyOCR, then recognise each line with TrOCR.

    TrOCR is line-only — feeding it a paragraph crop returns only the first
    line. We slice the crop into line crops via EasyOCR's detector first.
    """
    bundle = _load_trocr(model_id)
    detector = _load_easyocr_detector(lang)
    if bundle is None or detector is None or crop.width < 2 or crop.height < 2:
        return ""
    processor, model, device = bundle
    try:
        import io
        import numpy as np  # type: ignore
        import torch  # type: ignore

        # easyocr.detect accepts ndarray; pass the crop directly so we don't
        # have to write a temp file for every region.
        arr = np.array(crop.convert("RGB"))
        horizontal, _free = detector.detect(arr)
        boxes: List[Tuple[float, float, float, float]] = []
        for batch in horizontal or []:
            for box in batch or []:
                if len(box) >= 4:
                    x1, x2, y1, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
                    if x2 > x1 and y2 > y1:
                        boxes.append((x1, y1, x2, y2))

        # Fallback: if no lines detected, try the whole crop as one line.
        if not boxes:
            boxes = [(0.0, 0.0, float(crop.width), float(crop.height))]

        # Sort lines top-to-bottom so the joined text reads naturally.
        boxes.sort(key=lambda b: b[1])

        lines: List[str] = []
        for (x1, y1, x2, y2) in boxes:
            line_crop = crop.crop((x1, y1, x2, y2))
            if line_crop.width < 2 or line_crop.height < 2:
                continue
            pixel_values = processor(images=line_crop, return_tensors="pt").pixel_values.to(device)
            with torch.no_grad():
                outputs = model.generate(pixel_values, max_new_tokens=128)
            text = processor.batch_decode(outputs, skip_special_tokens=True)[0].strip()
            if text:
                lines.append(text)
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return ""


def get_post_ocr_fn(ocr_backend: str) -> Optional[Callable[[Image.Image], str]]:
    """Return a callable ``(PIL.Image) -> str`` for the requested custom backend.

    Returns ``None`` if the backend is one of docling's native engines (caller
    should not post-OCR in that case) or if the backend's deps aren't
    available (caller falls back to docling's native OCR).
    """
    name = (ocr_backend or "").lower()
    if name == "doctr":
        if _load_doctr() is None:
            return None
        return _ocr_crop_doctr
    if name in {"trocr_hw", "trocr_handwritten"}:
        if _load_trocr("microsoft/trocr-base-handwritten") is None:
            return None
        return lambda c: _ocr_crop_trocr(c, "microsoft/trocr-base-handwritten")
    if name in {"trocr_printed"}:
        if _load_trocr("microsoft/trocr-base-printed") is None:
            return None
        return lambda c: _ocr_crop_trocr(c, "microsoft/trocr-base-printed")
    return None
