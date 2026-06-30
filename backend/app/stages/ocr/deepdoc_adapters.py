"""OCR backends for the deepdoc pipeline.

Deepdoc's vendored ``OCR`` class exposes ``detect()`` / ``recognize_batch()``
that are tightly coupled to its ONNX text-detection + text-recognition
heads. For benchmarking we want to feed the deepdoc layout + table-structure
models with text from *other* OCR systems (tesseract / easyocr / doctr /
paddleocr) and compare which combination produces the best end-to-end
result — same pattern the ``img2table_*`` family already follows.

Rather than monkey-patching deepdoc's internals, the worker uses these
adapters to produce a *common shape* — a list of ``OCRResult`` per page —
and the worker glues that into the format deepdoc's ``LayoutRecognizer``
expects (a list of dicts with ``text/x0/top/x1/bottom``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Protocol

import numpy as np


@dataclass
class OCRResult:
    """One detected text line."""

    # Axis-aligned bbox in image pixel coords.
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    confidence: float = 1.0


class DeepdocOCRBackend(Protocol):
    """Each adapter exposes a single call producing OCRResults for one page."""

    name: str

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        ...


# ---------------------------------------------------------------------------
# default — use deepdoc's own ONNX OCR via the vendored class
# ---------------------------------------------------------------------------

class DefaultDeepdocOCR:
    """Wraps the vendored ``deepdoc.vision.ocr.OCR`` instance.

    Note: import is deferred to ``__init__`` because deepdoc.* requires the
    ragflow-stubs path to be set up first (done in the worker entry point).
    """

    name = "default"

    def __init__(self) -> None:
        from deepdoc.vision.ocr import OCR  # type: ignore
        self._ocr = OCR()
        # Default ``self._ocr.drop_score`` is 0.5; the recognizer reports
        # low confidence on a lot of bank-statement / form text whose visual
        # content is fine. Lower the threshold so we emit those tokens
        # instead of dropping them to empty strings — the cards otherwise
        # surface 0 OCR regions and tables look empty.
        try:
            self._ocr.drop_score = 0.0
        except Exception:  # noqa: BLE001
            pass

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        import sys as _sys

        det = self._ocr.detect(img_rgb)
        if det is None:
            print(
                "[deepdoc_baseline] OCR.detect returned None — text detector model "
                "load may have failed or input image was invalid.",
                file=_sys.stderr,
            )
            return []
        # detect() yields zip(boxes, [("",0), ...]); reify so we can iterate twice
        items = list(det)
        if not items:
            print(
                "[deepdoc_baseline] OCR.detect returned 0 boxes for this page.",
                file=_sys.stderr,
            )
            return []
        boxes = [b for b, _ in items]
        try:
            crops = [
                self._ocr.get_rotate_crop_image(img_rgb, np.asarray(b, dtype=np.float32))
                for b in boxes
            ]
        except Exception as exc:  # noqa: BLE001
            print(
                f"[deepdoc_baseline] get_rotate_crop_image failed: {type(exc).__name__}: {exc}",
                file=_sys.stderr,
            )
            return []
        try:
            texts = self._ocr.recognize_batch(crops)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[deepdoc_baseline] recognize_batch failed: {type(exc).__name__}: {exc}",
                file=_sys.stderr,
            )
            return []

        n_total = len(texts)
        n_empty = sum(1 for t in texts if not (t or "").strip())
        if n_empty == n_total and n_total:
            # Recognizer ran but produced no text. Surface a sample of the
            # first few raw outputs so the user can tell whether the model
            # is returning '' (likely model load issue), whitespace, or
            # low-confidence-blanked entries.
            sample = [repr(t)[:40] for t in texts[:5]]
            print(
                f"[deepdoc_baseline] recognize_batch returned {n_total} entries, "
                f"all empty after strip. drop_score={getattr(self._ocr, 'drop_score', '?')}. "
                f"Sample: {sample}",
                file=_sys.stderr,
            )

        out: List[OCRResult] = []
        for box, text in zip(boxes, texts):
            x0, y0, x1, y1 = _quad_to_axis_rect(box)
            t = (text or "").strip()
            if not t:
                continue
            out.append(OCRResult(x0=x0, y0=y0, x1=x1, y1=y1, text=t, confidence=1.0))
        print(
            f"[deepdoc_baseline] detected {n_total} text boxes, recognised "
            f"{len(out)} non-empty tokens",
            file=_sys.stderr,
        )
        return out


# ---------------------------------------------------------------------------
# tesseract
# ---------------------------------------------------------------------------

class TesseractDeepdocOCR:
    name = "tesseract"

    def __init__(self, lang: str = "eng") -> None:
        self.lang = lang

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        import pytesseract
        from PIL import Image

        img = Image.fromarray(img_rgb)
        data = pytesseract.image_to_data(img, lang=self.lang, output_type=pytesseract.Output.DICT)
        # Group tesseract words by line key (block, par, line)
        lines: dict[tuple, dict[str, Any]] = {}
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            x0 = float(data["left"][i])
            y0 = float(data["top"][i])
            x1 = x0 + float(data["width"][i])
            y1 = y0 + float(data["height"][i])
            entry = lines.setdefault(key, {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "words": [], "confs": []})
            entry["x0"] = min(entry["x0"], x0)
            entry["y0"] = min(entry["y0"], y0)
            entry["x1"] = max(entry["x1"], x1)
            entry["y1"] = max(entry["y1"], y1)
            entry["words"].append(text)
            if conf >= 0:
                entry["confs"].append(conf)
        out: List[OCRResult] = []
        for entry in lines.values():
            text = " ".join(entry["words"])
            conf = (sum(entry["confs"]) / len(entry["confs"]) / 100.0) if entry["confs"] else 0.5
            out.append(OCRResult(x0=entry["x0"], y0=entry["y0"], x1=entry["x1"], y1=entry["y1"], text=text, confidence=conf))
        return out


# ---------------------------------------------------------------------------
# easyocr
# ---------------------------------------------------------------------------

class EasyOCRDeepdocOCR:
    name = "easyocr"

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang[:2] if len(lang) == 3 else lang
        import easyocr  # type: ignore
        self._reader = easyocr.Reader([self.lang], gpu=False, verbose=False)

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        results = self._reader.readtext(img_rgb, detail=1, paragraph=False)
        out: List[OCRResult] = []
        for (quad, text, conf) in results:
            t = (text or "").strip()
            if not t:
                continue
            xs = [float(p[0]) for p in quad]
            ys = [float(p[1]) for p in quad]
            out.append(OCRResult(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), text=t, confidence=float(conf)))
        return out


# ---------------------------------------------------------------------------
# doctr
# ---------------------------------------------------------------------------

class DoctrDeepdocOCR:
    name = "doctr"

    def __init__(self) -> None:
        from doctr.models import ocr_predictor  # type: ignore
        self._model = ocr_predictor(pretrained=True, assume_straight_pages=True)

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        from doctr.io import DocumentFile  # type: ignore
        h, w = img_rgb.shape[:2]
        # DocTR DocumentFile expects bytes/path — encode in-memory.
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.fromarray(img_rgb).save(buf, format="PNG")
        doc = DocumentFile.from_images([buf.getvalue()])
        result = self._model(doc)
        out: List[OCRResult] = []
        for block in result.pages[0].blocks:
            for line in block.lines:
                parts = []
                lx0 = ly0 = float("inf")
                lx1 = ly1 = float("-inf")
                confs = []
                for word in line.words:
                    (rx1, ry1), (rx2, ry2) = word.geometry
                    parts.append(word.value)
                    confs.append(float(word.confidence))
                    lx0 = min(lx0, rx1 * w)
                    ly0 = min(ly0, ry1 * h)
                    lx1 = max(lx1, rx2 * w)
                    ly1 = max(ly1, ry2 * h)
                if not parts:
                    continue
                text = " ".join(parts).strip()
                if not text:
                    continue
                conf = sum(confs) / len(confs) if confs else 1.0
                out.append(OCRResult(x0=lx0, y0=ly0, x1=lx1, y1=ly1, text=text, confidence=conf))
        return out


# ---------------------------------------------------------------------------
# paddleocr — reuses the OCR-baseline pin (PP-OCRv4) for parity on 8 GB Macs
# ---------------------------------------------------------------------------

class PaddleDeepdocOCR:
    name = "paddle"

    def __init__(self, lang: str = "en", ocr_version: str = "PP-OCRv4") -> None:
        from paddleocr import PaddleOCR  # type: ignore
        try:
            self._reader = PaddleOCR(
                ocr_version=ocr_version,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang=lang,
            )
        except TypeError:
            self._reader = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang=lang,
            )

    def recognize_page(self, img_rgb: np.ndarray) -> List[OCRResult]:
        # paddleocr 3.x accepts numpy arrays directly via predict()
        results = self._reader.predict(img_rgb)
        out: List[OCRResult] = []
        iterable = results if isinstance(results, list) else [results]
        for page_res in iterable:
            if page_res is None:
                continue
            texts = getattr(page_res, "rec_texts", None) or (page_res.get("rec_texts") if isinstance(page_res, dict) else None)
            scores = getattr(page_res, "rec_scores", None) or (page_res.get("rec_scores") if isinstance(page_res, dict) else None)
            polys = getattr(page_res, "rec_polys", None) or (page_res.get("rec_polys") if isinstance(page_res, dict) else None)
            if texts is None or polys is None:
                continue
            for text, score, poly in zip(texts, scores or [1.0] * len(texts), polys):
                t = (str(text) or "").strip()
                if not t:
                    continue
                pts = list(poly)
                xs = [float(p[0]) for p in pts]
                ys = [float(p[1]) for p in pts]
                out.append(OCRResult(
                    x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys),
                    text=t, confidence=float(score or 0.0),
                ))
        return out


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------

_BACKENDS = {
    "default": DefaultDeepdocOCR,
    "tesseract": TesseractDeepdocOCR,
    "easyocr": EasyOCRDeepdocOCR,
    "doctr": DoctrDeepdocOCR,
    "paddle": PaddleDeepdocOCR,
}


def build_backend(name: str, **kwargs: Any) -> DeepdocOCRBackend:
    """Construct an OCR backend by name. Raises on unknown name."""
    if name not in _BACKENDS:
        raise ValueError(f"Unknown deepdoc OCR backend: {name!r}. Known: {sorted(_BACKENDS)}")
    return _BACKENDS[name](**kwargs)


def _quad_to_axis_rect(quad: Any) -> tuple[float, float, float, float]:
    """Convert a 4-point polygon to (x0, y0, x1, y1)."""
    pts = list(quad)
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return min(xs), min(ys), max(xs), max(ys)
