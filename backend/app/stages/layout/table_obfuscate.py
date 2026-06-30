"""Crop each table and overlay cell text with a character-preserving substitution cipher."""

from __future__ import annotations

import io
import random
import string
from dataclasses import dataclass
from typing import List

from app.pipeline.base import RunState
from app.pipeline.context import RunContext


def _build_maps(seed: int = 42) -> tuple[dict[str, str], dict[str, str]]:
    rng = random.Random(seed)
    lc = list(string.ascii_lowercase)
    sl = lc[:]
    rng.shuffle(sl)
    uc = list(string.ascii_uppercase)
    su = uc[:]
    rng.shuffle(su)
    dg = list(string.digits)
    sd = dg[:]
    rng.shuffle(sd)
    letter_map = {c: s for c, s in zip(lc, sl)} | {c: s for c, s in zip(uc, su)}
    digit_map = {c: s for c, s in zip(dg, sd)}
    return letter_map, digit_map


_LETTER_MAP, _DIGIT_MAP = _build_maps()


def obfuscate(text: str) -> str:
    return "".join(_LETTER_MAP.get(c) or _DIGIT_MAP.get(c) or c for c in text)


def _render_obfuscated(img, cells: list, n_rows: int, n_cols: int, font) -> None:
    """Draw obfuscated text over each cell.

    Uses cell.bbox when available; falls back to a uniform grid estimate when not.
    """
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    iw, ih = img.size

    # Pre-compute uniform cell size for fallback
    cell_w = iw / max(n_cols, 1)
    cell_h = ih / max(n_rows, 1)

    # Build a lookup by (row, col) for grid fallback
    cell_map = {(c.row, c.col): c for c in cells}

    for (r, c), cell in cell_map.items():
        if not cell.text:
            continue
        obf = obfuscate(cell.text)
        if cell.bbox:
            b = cell.bbox
            draw.rectangle([b.x, b.y, b.x2, b.y2], fill="white")
            draw.text((b.x + 2, b.y + 2), obf, fill="black", font=font)
        else:
            # Uniform grid fallback
            x0 = c * cell_w
            y0 = r * cell_h
            x1 = x0 + cell_w
            y1 = y0 + cell_h
            draw.rectangle([x0, y0, x1, y1], fill="white")
            draw.text((x0 + 3, y0 + 3), obf, fill="black", font=font)


@dataclass
class TableObfuscateStage:
    name: str = "table_obfuscate"
    font_size: int = 12

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        from PIL import Image, ImageFont

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", self.font_size)
        except Exception:
            try:
                font = ImageFont.truetype("arial.ttf", self.font_size)
            except Exception:
                font = ImageFont.load_default()

        for idx, page in state.pages.items():
            png_path = ctx.page_images.get(idx)
            if not png_path:
                continue

            refs: list[str] = []
            img_base = Image.open(png_path)

            # custom_tables — cells always have bboxes from the geometric heuristic
            for k, ct in enumerate(page.custom_tables):
                b = (ct.detection or {}).get("bbox")
                if not b:
                    continue
                x, y, w, h = b.get("x", 0), b.get("y", 0), b.get("w", 0), b.get("h", 0)
                if w < 4 or h < 4:
                    continue
                cropped = img_base.crop((x, y, x + w, y + h)).copy()
                # shift cell bboxes into crop coordinate space
                shifted = _shift_cells(ct.cells, x, y)
                _render_obfuscated(cropped, shifted, ct.n_rows, ct.n_cols, font)
                rel = f"tables/page-{idx:03d}-custom-{k:02d}-obfuscated.png"
                buf = io.BytesIO()
                cropped.save(buf, "PNG")
                ctx.save_bytes(rel, buf.getvalue())
                refs.append(ctx.artifact_id(rel))

            # upstream tables — cells may lack bboxes; grid fallback handles that
            region_map = {r.id: r for r in page.regions}
            for k, t in enumerate(page.tables):
                region = region_map.get(t.region_id or "")
                if not (region and region.bbox):
                    continue
                b = region.bbox
                if b.w < 4 or b.h < 4:
                    continue
                cropped = img_base.crop((b.x, b.y, b.x2, b.y2)).copy()
                shifted = _shift_cells(t.cells, b.x, b.y)
                _render_obfuscated(cropped, shifted, t.n_rows, t.n_cols, font)
                rel = f"tables/page-{idx:03d}-table-{k:02d}-obfuscated.png"
                buf = io.BytesIO()
                cropped.save(buf, "PNG")
                ctx.save_bytes(rel, buf.getvalue())
                refs.append(ctx.artifact_id(rel))

            page.table_obfuscated_refs = refs

        return state


def _shift_cells(cells: list, ox: float, oy: float) -> list:
    """Return a new list of cells with bboxes shifted by (-ox, -oy)."""
    result = []
    for cell in cells:
        if cell.bbox:
            shifted = cell.model_copy(update={
                "bbox": cell.bbox.model_copy(update={
                    "x": cell.bbox.x - ox,
                    "y": cell.bbox.y - oy,
                })
            })
            result.append(shifted)
        else:
            result.append(cell)
    return result
