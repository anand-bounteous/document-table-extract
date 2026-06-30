"""Crop each detected table out of the page PNG and save as an artifact."""

from __future__ import annotations

import io
from dataclasses import dataclass

from app.pipeline.base import RunState
from app.pipeline.context import RunContext


@dataclass
class TableCropStage:
    name: str = "table_crop"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        from PIL import Image

        for idx, page in state.pages.items():
            png_path = ctx.page_images.get(idx)
            if not png_path:
                continue
            img = Image.open(png_path)
            refs: list[str] = []

            # custom_tables: bbox stored in detection dict
            for k, ct in enumerate(page.custom_tables):
                b = (ct.detection or {}).get("bbox")
                if not b:
                    continue
                x, y, w, h = b.get("x", 0), b.get("y", 0), b.get("w", 0), b.get("h", 0)
                if w < 4 or h < 4:
                    continue
                cropped = img.crop((x, y, x + w, y + h))
                rel = f"tables/page-{idx:03d}-custom-{k:02d}.png"
                buf = io.BytesIO()
                cropped.save(buf, "PNG")
                ctx.save_bytes(rel, buf.getvalue())
                refs.append(ctx.artifact_id(rel))

            # upstream tables: bbox via linked region
            region_map = {r.id: r for r in page.regions}
            for k, t in enumerate(page.tables):
                region = region_map.get(t.region_id or "")
                if not (region and region.bbox):
                    continue
                b = region.bbox
                if b.w < 4 or b.h < 4:
                    continue
                cropped = img.crop((b.x, b.y, b.x2, b.y2))
                rel = f"tables/page-{idx:03d}-table-{k:02d}.png"
                buf = io.BytesIO()
                cropped.save(buf, "PNG")
                ctx.save_bytes(rel, buf.getvalue())
                refs.append(ctx.artifact_id(rel))

            page.table_crop_refs = refs

        return state
