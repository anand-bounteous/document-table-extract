"""Visual identifier extraction: QR (always) + barcode (optional).

QR is decoded via ``cv2.QRCodeDetector`` (OpenCV is in core deps).
Barcodes use ``pyzbar``, which lives in the ``[pii-v2-visual]`` optional
extras and requires ``brew install zbar`` on macOS. The detector skips
barcode work cleanly when pyzbar isn't importable.

Output schema: a list of ``VisualCode`` dicts with payload + pixel bbox
+ source. Stored per page at:
``storage/pii_runs/<id>/<doc_id>/visual/page-<NNN>.json``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ote.pii_v2.visual")


@dataclass
class VisualCode:
    type: str            # "QR_CODE" | "BAR_CODE"
    payload: str
    bbox_px: Dict[str, float]   # {x, y, w, h}
    source: str          # "cv2.qrcode" | "pyzbar"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "bbox_px": self.bbox_px,
            "source": self.source,
            "metadata": self.metadata,
        }


def extract_qr_cv2(image_path: Path) -> List[VisualCode]:
    """Decode QR codes via OpenCV's built-in detector."""
    import cv2  # type: ignore
    import numpy as np

    img = cv2.imread(str(image_path))
    if img is None:
        return []
    detector = cv2.QRCodeDetector()
    out: List[VisualCode] = []
    # detectAndDecodeMulti returns multiple codes per image.
    try:
        ok, decoded_texts, points, _ = detector.detectAndDecodeMulti(img)
    except cv2.error:
        return []
    if not ok or points is None:
        return []
    for text, pts in zip(decoded_texts, points):
        if not text:
            continue
        if pts is None or len(pts) < 4:
            continue
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        x = min(xs)
        y = min(ys)
        w = max(xs) - x
        h = max(ys) - y
        out.append(VisualCode(
            type="QR_CODE",
            payload=str(text),
            bbox_px={"x": x, "y": y, "w": w, "h": h},
            source="cv2.qrcode",
        ))
    return out


def extract_barcodes_pyzbar(image_path: Path) -> List[VisualCode]:
    """Decode 1D barcodes via pyzbar. Silently returns [] when unavailable."""
    try:
        from pyzbar import pyzbar  # type: ignore
        from PIL import Image
    except ImportError:
        logger.info("pyzbar not installed; barcode detection skipped")
        return []
    try:
        codes = pyzbar.decode(Image.open(image_path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("pyzbar decode failed for %s: %s", image_path, exc)
        return []
    out: List[VisualCode] = []
    for c in codes:
        rect = c.rect
        out.append(VisualCode(
            type="BAR_CODE",
            payload=c.data.decode("utf-8", errors="replace"),
            bbox_px={"x": float(rect.left), "y": float(rect.top),
                     "w": float(rect.width), "h": float(rect.height)},
            source="pyzbar",
            metadata={"barcode_type": str(c.type)},
        ))
    return out


def extract_all(image_path: Path) -> Dict[str, Any]:
    """Run every available extractor and return the union."""
    if not image_path.exists():
        return {"codes": [], "skipped": ["image not found"]}
    codes: List[VisualCode] = []
    skipped: List[str] = []
    try:
        codes.extend(extract_qr_cv2(image_path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("cv2 QR extraction failed for %s", image_path)
        skipped.append(f"qr_cv2: {type(exc).__name__}: {exc}")
    bc = extract_barcodes_pyzbar(image_path)
    if not bc:
        try:
            import pyzbar  # noqa: F401
        except ImportError:
            skipped.append("barcode: pyzbar not installed (uv pip install pyzbar; macOS: brew install zbar)")
    codes.extend(bc)
    return {
        "codes": [c.to_dict() for c in codes],
        "skipped": skipped,
    }


def persist_for_page(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
    image_path: Optional[Path],
) -> Dict[str, Any]:
    """Run extractors on the page image and persist the result.

    Returns the payload that was written.
    """
    from app import pii_v2_store

    out_dir = pii_v2_store.run_dir(pii_run_id) / document_id / "visual"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page-{page_index:03d}.json"
    if image_path is None or not image_path.exists():
        payload = {"codes": [], "skipped": ["page image unavailable"]}
    else:
        payload = extract_all(image_path)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return payload
