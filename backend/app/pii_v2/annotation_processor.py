"""Crop-and-extract pipeline for the manual annotation review step.

For each user-drawn bbox we:

1. Locate the matching page image (paired /runs raster → producer raster →
   visual-extractor cache, in that order — same fallback the page-image
   route uses).
2. Crop the bbox region and run a lightweight Tesseract OCR pass to recover
   the underlying text. This is independent of the OCR producers configured
   for the pii_run, so the user can annotate even on producers that didn't
   detect text in that area.
3. Run the visual extractor on the crop (QR via OpenCV, barcode via pyzbar
   when installed).
4. Walk every (ocr, detector) cell on the same page and check for spans
   whose pixel bbox overlaps the manual bbox — flagging which existing
   detectors already covered the region.

The route layer wraps this in a thin POST endpoint; results stream back as
``processed_annotations`` for the user to review before saving.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import pii_v2_store, run_store

logger = logging.getLogger("ote.pii_v2.annotation_processor")


def _bbox_iou(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Intersection-over-union for axis-aligned boxes with {x,y,w,h}."""
    ax1, ay1 = float(a.get("x", 0)), float(a.get("y", 0))
    ax2, ay2 = ax1 + float(a.get("w", 0)), ay1 + float(a.get("h", 0))
    bx1, by1 = float(b.get("x", 0)), float(b.get("y", 0))
    bx2, by2 = bx1 + float(b.get("w", 0)), by1 + float(b.get("h", 0))
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def _char_to_bbox(start: int, end: int, region_index: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Same heuristic as :func:`app.pii_v2.text_layout.char_to_bbox`, but operates
    on the JSON form persisted on disk so we don't have to rehydrate dataclasses."""
    overlapping = [rs for rs in region_index if not (rs["end"] <= start or end <= rs["start"])]
    if not overlapping:
        return None
    boxes: List[Dict[str, float]] = []
    for rs in overlapping:
        tl = rs.get("text_len") or max(1, rs["end"] - rs["start"])
        bbox = rs["bbox"]
        xpc = float(bbox.get("w", 0)) / max(1, tl)
        local_start = max(0, start - rs["start"])
        local_end = min(tl, end - rs["start"])
        if local_end <= local_start:
            continue
        x1 = float(bbox.get("x", 0)) + xpc * local_start
        x2 = float(bbox.get("x", 0)) + xpc * local_end
        boxes.append({
            "x": x1,
            "y": float(bbox.get("y", 0)),
            "x2": x2,
            "y2": float(bbox.get("y", 0)) + float(bbox.get("h", 0)),
        })
    if not boxes:
        return None
    x = min(b["x"] for b in boxes)
    y = min(b["y"] for b in boxes)
    x2 = max(b["x2"] for b in boxes)
    y2 = max(b["y2"] for b in boxes)
    return {"x": x, "y": y, "w": max(2.0, x2 - x), "h": max(2.0, y2 - y)}


def _find_page_image(pii_run_id: str, document_id: str, page_index: int) -> Optional[Path]:
    """Same preference order as ``GET /pii-benchmarks/.../page-image/...``."""
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        return None
    filename = f"page-{page_index:03d}.png"
    paired_run_id = pii_v2_store.paired_run_id_for_doc(state, document_id)
    if paired_run_id:
        run_dir_path = run_store.run_dir(paired_run_id)
        for png in run_dir_path.glob(f"*/artifacts/pages/{filename}"):
            return png
    pii_run_root = pii_v2_store.run_dir(pii_run_id) / document_id
    for png in pii_run_root.glob(f"_producers/*/*/artifacts/pages/{filename}"):
        return png
    raster_cache = pii_run_root / "_visual_raster" / filename
    if raster_cache.exists():
        return raster_cache
    return None


def _list_existing_detectors_for_page(
    pii_run_id: str,
    document_id: str,
    page_index: int,
) -> List[Dict[str, Any]]:
    """Iterate every (ocr × detector) cell on this page; return their entities
    with pixel bboxes resolved from the per-OCR text layout."""
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        return []
    detector_names: List[str] = state.get("detector_names") or []
    ocr_producers: List[str] = state.get("ocr_producers") or []

    out: List[Dict[str, Any]] = []
    for ocr in ocr_producers:
        layout = pii_v2_store.read_text_layout(pii_run_id, document_id, page_index, ocr) or []
        for det in detector_names:
            cell = pii_v2_store.read_cell(pii_run_id, document_id, page_index, ocr, det)
            if cell is None:
                continue
            for ent in cell.get("entities") or []:
                bbox = _char_to_bbox(int(ent["start"]), int(ent["end"]), layout)
                if bbox is None:
                    continue
                out.append({
                    "ocr": ocr,
                    "detector": det,
                    "entity_type": ent.get("entity_type"),
                    "text": ent.get("text"),
                    "score": ent.get("score"),
                    "bbox": bbox,
                    "discovery": (ent.get("metadata") or {}).get("discovery"),
                })
    return out


def _crop_and_ocr(image_path: Path, bbox_px: Dict[str, float]) -> str:
    """Crop the page image to ``bbox_px`` and run a lightweight Tesseract pass."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.info("tesseract / PIL not installed; skipping crop OCR")
        return ""
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not open page image %s: %s", image_path, exc)
        return ""
    x = max(0, int(bbox_px.get("x", 0)))
    y = max(0, int(bbox_px.get("y", 0)))
    w = max(1, int(bbox_px.get("w", 0)))
    h = max(1, int(bbox_px.get("h", 0)))
    x2 = min(img.width, x + w)
    y2 = min(img.height, y + h)
    if x2 <= x or y2 <= y:
        return ""
    crop = img.crop((x, y, x2, y2))
    try:
        text = pytesseract.image_to_string(crop) or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("tesseract on crop failed: %s", exc)
        return ""
    return text.strip()


def _crop_and_visual(image_path: Path, bbox_px: Dict[str, float]) -> List[Dict[str, Any]]:
    """Crop + run the visual extractor on the crop. Coordinates returned are
    relative to the crop (top-left = 0,0); the frontend can shift them back."""
    try:
        from PIL import Image
        from app.pii_v2 import visual_extractor
    except ImportError:
        return []
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception:  # noqa: BLE001
        return []
    x = max(0, int(bbox_px.get("x", 0)))
    y = max(0, int(bbox_px.get("y", 0)))
    w = max(1, int(bbox_px.get("w", 0)))
    h = max(1, int(bbox_px.get("h", 0)))
    x2 = min(img.width, x + w)
    y2 = min(img.height, y + h)
    if x2 <= x or y2 <= y:
        return []
    crop = img.crop((x, y, x2, y2))
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        crop.save(tmp.name)
        tmp_path = Path(tmp.name)
    try:
        result = visual_extractor.extract_all(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    # Shift bboxes back to page coords for downstream rendering.
    for code in result.get("codes", []):
        b = code.get("bbox_px") or {}
        code["bbox_px"] = {
            "x": float(b.get("x", 0)) + x,
            "y": float(b.get("y", 0)) + y,
            "w": float(b.get("w", 0)),
            "h": float(b.get("h", 0)),
        }
    return result.get("codes", [])


def _suggest_entity_type(text: str, visual_codes: List[Dict[str, Any]]) -> str:
    """Heuristic guess based on the crop OCR + visual codes."""
    if visual_codes:
        types = {c.get("type") for c in visual_codes}
        if "QR_CODE" in types:
            return "QR_CODE"
        if "BAR_CODE" in types:
            return "BAR_CODE"
    if not text:
        return "OTHER"
    t = text.strip()
    import re
    if re.search(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", t):
        return "EMAIL_ADDRESS"
    if re.search(r"https?://\S+", t):
        return "URL"
    if re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", t):
        return "UK_POSTCODE"
    if re.search(r"\+?\d[\d\s\-()]{7,}\d", t):
        return "UK_PHONE_NUMBER"
    if any(ch.isalpha() for ch in t):
        return "PERSON"
    return "OTHER"


def process_annotation(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
    bbox_px: Dict[str, float],
) -> Dict[str, Any]:
    """Process one pending annotation. Returns a payload suitable for review."""
    image_path = _find_page_image(pii_run_id, document_id, page_index)
    if image_path is None:
        return {
            "bbox_px": bbox_px,
            "extracted_text": "",
            "visual_codes": [],
            "matched_by": [],
            "suggested_entity_type": "OTHER",
            "error": "page image not found",
        }
    extracted_text = _crop_and_ocr(image_path, bbox_px)
    visual_codes = _crop_and_visual(image_path, bbox_px)

    existing = _list_existing_detectors_for_page(pii_run_id, document_id, page_index)
    matched_by: List[Dict[str, Any]] = []
    for det in existing:
        iou = _bbox_iou(bbox_px, det["bbox"])
        if iou > 0.05:  # any meaningful overlap
            matched_by.append({**det, "iou": round(iou, 3)})
    matched_by.sort(key=lambda d: d["iou"], reverse=True)

    return {
        "bbox_px": bbox_px,
        "extracted_text": extracted_text,
        "visual_codes": visual_codes,
        "matched_by": matched_by,
        "suggested_entity_type": _suggest_entity_type(extracted_text, visual_codes),
    }
