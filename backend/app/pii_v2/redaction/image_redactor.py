"""White-fill detected PII bboxes on a page image and draw the mock text in place.

The same-length invariant from :mod:`mock_generators` means the mock text
typically fits the original bbox at the same font size. We still
auto-shrink when proportional fonts make the rendered width exceed the
bbox, because PIL's reported character widths can vary across fonts.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from app.config import settings
from app.pii_v2.redaction.text_redactor import DiffSpan

logger = logging.getLogger(__name__)


def _find_font_path() -> Optional[Path]:
    """Locate a usable .ttf. Honours ``settings.pii_v2_redaction_font_path``
    when set, then falls back to common macOS / Linux paths.

    Returns ``None`` when nothing is found — the caller drops to
    ``ImageFont.load_default()`` which renders as a small bitmap.
    """
    configured = getattr(settings, "pii_v2_redaction_font_path", None)
    candidates: List[str] = []
    if configured:
        candidates.append(configured)
    candidates.extend([
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ])
    for p in candidates:
        if p and Path(p).exists():
            return Path(p)
    return None


def _fit_font(text: str, bbox_w: float, bbox_h: float):
    """Pick the largest font size that fits ``text`` inside the bbox."""
    from PIL import ImageFont

    font_path = _find_font_path()
    # Starting size — derive from the bbox height so we match the original
    # text scale on the page. Cap at 96 to avoid pathological values.
    max_size = max(8, min(96, int(bbox_h * 0.85)))
    if font_path is None:
        return ImageFont.load_default(), max_size

    for size in range(max_size, 6, -1):
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except Exception:  # noqa: BLE001
            return ImageFont.load_default(), max_size
        try:
            length = font.getlength(text)
        except AttributeError:  # very old Pillow
            length = font.getsize(text)[0]  # type: ignore[attr-defined]
        if length <= bbox_w * 1.02:  # 2% slack
            return font, size
    # Couldn't fit at any size — return the smallest we tried.
    try:
        return ImageFont.truetype(str(font_path), size=7), 7
    except Exception:  # noqa: BLE001
        return ImageFont.load_default(), 7


def redact_image(
    page_image_path: Path,
    diff_spans: Iterable[DiffSpan],
    annotate: bool = False,
) -> Optional[bytes]:
    """Return PNG bytes with each PII bbox erased and the mock text drawn in.

    When ``annotate`` is True the redacted image also gets a thin green
    outline + a small entity-type label above each bbox — useful for the
    UI's side-by-side comparison so the user can see exactly *where* the
    mock text was placed. The clean variant (``annotate=False``) is what
    you pass to an LLM.

    ``None`` when the image path can't be opened. Spans without a
    ``bbox_px`` are skipped (the text redaction still records them so the
    UI can show the mapping).
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("Pillow not installed; skipping image redaction")
        return None

    if not page_image_path.exists():
        logger.info("page image %s missing; skipping image redaction", page_image_path)
        return None

    try:
        img = Image.open(page_image_path).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not open %s: %s", page_image_path, exc)
        return None

    draw = ImageDraw.Draw(img)
    spans_drawn: list[tuple[DiffSpan, float, float, float, float, int]] = []
    for span in diff_spans:
        bbox = span.bbox_px
        if not bbox:
            continue
        x = float(bbox.get("x", 0))
        y = float(bbox.get("y", 0))
        w = float(bbox.get("w", 0))
        h = float(bbox.get("h", 0))
        if w <= 0 or h <= 0:
            continue
        # 1. White-fill — no original pixels remain.
        draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
        # 2. Draw the mock text centred vertically in the bbox.
        font, size = _fit_font(span.mock, w, h)
        try:
            ascent, _descent = font.getmetrics()  # type: ignore[attr-defined]
            text_h = ascent
        except Exception:  # noqa: BLE001
            text_h = size
        ty = max(y, y + (h - text_h) / 2)
        draw.text((x, ty), span.mock, fill=(0, 0, 0), font=font)
        spans_drawn.append((span, x, y, w, h, size))

    if annotate and spans_drawn:
        # Second pass: outline each redacted box in green + tiny entity-type
        # label above it. Done in a separate loop so labels never sit
        # underneath a later-drawn redaction.
        from PIL import ImageFont
        label_font_path = _find_font_path()
        try:
            label_font = (
                ImageFont.truetype(str(label_font_path), size=11)
                if label_font_path
                else ImageFont.load_default()
            )
        except Exception:  # noqa: BLE001
            label_font = ImageFont.load_default()
        for span, x, y, w, h, _ in spans_drawn:
            draw.rectangle([x, y, x + w, y + h], outline=(26, 127, 55), width=2)
            label = span.entity_type
            try:
                lw = label_font.getlength(label)
            except AttributeError:  # very old Pillow
                lw = label_font.getsize(label)[0]  # type: ignore[attr-defined]
            # Backdrop pill so the label is readable on any background.
            label_y = max(0.0, y - 14)
            draw.rectangle(
                [x, label_y, x + lw + 6, label_y + 12],
                fill=(26, 127, 55),
            )
            draw.text((x + 3, label_y), label, fill=(255, 255, 255), font=label_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
