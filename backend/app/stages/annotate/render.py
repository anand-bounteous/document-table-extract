"""Render annotated page PNGs: color-coded labeled boxes + a PII red layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.core.schemas import RegionType
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.annotate")


COLOR_BY_TYPE: Dict[str, Tuple[int, int, int]] = {
    RegionType.LOGO.value: (0, 180, 0),
    RegionType.NORMAL_TEXT.value: (120, 120, 120),
    RegionType.TABLE.value: (0, 80, 220),
    RegionType.TABLE_HEADER.value: (0, 180, 220),
    RegionType.TABLE_ROW.value: (80, 160, 220),
    RegionType.TABLE_CELL.value: (140, 180, 230),
    RegionType.IMAGE.value: (140, 90, 60),
    RegionType.HANDWRITING_SIGNATURE.value: (240, 140, 0),
    RegionType.SEAL.value: (160, 60, 200),
    RegionType.WATERMARK.value: (220, 200, 0),
    RegionType.KV_PAIR.value: (60, 160, 160),
    RegionType.UNKNOWN.value: (140, 140, 140),
}
PII_COLOR = (220, 30, 30)
CUSTOM_TABLE_COLOR = (0, 160, 160)  # teal


@dataclass
class AnnotatePage:
    name: str = "annotate_render"
    tool: str = "pillow"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        font = _safe_font()
        for idx, page in state.pages.items():
            base = Image.open(ctx.page_images[idx]).convert("RGB")
            draw = ImageDraw.Draw(base, "RGBA")
            for region in page.regions:
                color = COLOR_BY_TYPE.get(region.type.value, (140, 140, 140))
                draw.rectangle(
                    [region.bbox.x, region.bbox.y, region.bbox.x2, region.bbox.y2],
                    outline=color + (255,),
                    width=2,
                )
                label = f"{region.type.value} {region.confidence:.2f}"
                draw.text(
                    (region.bbox.x + 2, max(0, region.bbox.y - 12)),
                    label,
                    fill=color + (255,),
                    font=font,
                )
                for span in region.pii_spans:
                    if span.bbox is None:
                        continue
                    draw.rectangle(
                        [span.bbox.x, span.bbox.y, span.bbox.x2, span.bbox.y2],
                        outline=PII_COLOR + (255,),
                        width=2,
                    )
                    draw.text(
                        (span.bbox.x + 2, span.bbox.y2 + 1),
                        span.entity_type,
                        fill=PII_COLOR + (255,),
                        font=font,
                    )
            # Custom-table outlines drawn on top so they're visible
            for ct in page.custom_tables:
                bbox_dict = (ct.detection or {}).get("bbox")
                if not bbox_dict:
                    continue
                x = bbox_dict.get("x", 0)
                y = bbox_dict.get("y", 0)
                w = bbox_dict.get("w", 0)
                h = bbox_dict.get("h", 0)
                draw.rectangle(
                    [x, y, x + w, y + h],
                    outline=CUSTOM_TABLE_COLOR + (255,),
                    width=3,
                )
                draw.text(
                    (x + 2, max(0, y - 14)),
                    f"custom {ct.orientation} {ct.n_rows}×{ct.n_cols}",
                    fill=CUSTOM_TABLE_COLOR + (255,),
                    font=font,
                )
            rel = f"annotated/page-{idx:03d}.png"
            import io

            buf = io.BytesIO()
            base.save(buf, format="PNG")
            ctx.save_bytes(rel, buf.getvalue())
            page.annotated_image_ref = ctx.artifact_id(rel)
        return state


def _safe_font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except Exception:
        return ImageFont.load_default()
