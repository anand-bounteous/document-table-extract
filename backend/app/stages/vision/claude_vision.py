"""Claude Vision stage: send rasterized page → ask for structured regions+tables.

Returns coordinates in the *original* image's pixel space, top-left origin —
i.e. exactly the schema's canonical space. The prompt enforces JSON output.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from PIL import Image

from app.config import settings
from app.core.schemas import BBox, Region, RegionType, TableCell, TableModel
from app.llm_io import logged_messages_create
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.vision")


PROMPT = """You are an expert document layout analyst.

I will give you a single page rasterized from a PDF at a fixed DPI. The image
coordinate system is **pixels, origin top-left**. Return ONLY a JSON object
matching this schema:

{
  "regions": [
    {
      "type": "logo|normal_text|table|table_header|table_row|table_cell|image|handwriting_signature|seal|watermark|kv_pair|unknown",
      "bbox": {"x": <px>, "y": <px>, "w": <px>, "h": <px>},
      "text": "<exact text in this region (empty for non-text regions)>",
      "confidence": 0.0..1.0
    }
  ],
  "tables": [
    {
      "bbox": {"x":..,"y":..,"w":..,"h":..},
      "orientation": "horizontal|vertical_kv",
      "border_mode": "ruled|whitespace|mixed",
      "n_rows": <int>,
      "n_cols": <int>,
      "cells": [
        {"row":0,"col":0,"text":"...","bbox":{"x":..,"y":..,"w":..,"h":..},"rowspan":1,"colspan":1,"multiline":false}
      ]
    }
  ],
  "full_text": "<linearized reading-order text for the whole page>"
}

Rules:
- bbox values MUST be pixel coordinates in the image you were shown, top-left origin.
- Every visible logo, table, signature/handwriting block, seal/stamp, and watermark must be its own region.
- For each table also emit one row per `table_row` region (so a separate table_row region for each row's bbox) — these may overlap the parent `table` region.
- Multiline cells must set "multiline": true and contain newlines inside "text".
- Output JSON ONLY (no markdown fences, no commentary).
"""


@dataclass
class ClaudeVision:
    name: str = "vision_claude"
    tool: str = "claude_vision"
    use_redacted: bool = True
    model: Optional[str] = None
    max_tokens: int = field(default_factory=lambda: settings.anthropic_max_tokens)

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        model = self.model or settings.anthropic_model

        total_usage: Dict[str, Any] = {"model": model, "input_tokens": 0, "output_tokens": 0}

        async def _run_all() -> None:
            for idx, page in state.pages.items():
                img_path = self._pick_image(idx, ctx, state)
                raw, payload, usage = await self._call(client, img_path, model)
                total_usage["model"] = usage.get("model", model)
                total_usage["input_tokens"] = total_usage["input_tokens"] + usage.get("input_tokens", 0)
                total_usage["output_tokens"] = total_usage["output_tokens"] + usage.get("output_tokens", 0)
                ctx.save_text(f"vision/page-{idx:03d}-raw.txt", raw)
                ctx.save_json(f"vision/page-{idx:03d}-response.json", payload)
                regions, tables, full_text = _payload_to_models(payload, page_index=idx, dpi=page.dpi, tool=self.tool)
                page.regions.extend(regions)
                page.tables.extend(tables)
                page.full_text = full_text or page.full_text

        asyncio.run(_run_all())
        if ctx.current_handle is not None:
            ctx.current_handle.usage = total_usage
        return state

    def _pick_image(self, idx: int, ctx: RunContext, state: RunState) -> Path:
        if self.use_redacted:
            redacted: Dict[int, Path] = state.extras.get("pii_redacted", {})
            if idx in redacted:
                return redacted[idx]
        return ctx.page_images[idx]

    async def _call(self, client: AsyncAnthropic, img_path: Path, model: str) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
        img_b64, media = _b64_image(img_path)
        response = await logged_messages_create(
            client,
            f"vision.claude.{img_path.name}",
            model=model,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media, "data": img_b64}},
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
        usage_obj = getattr(response, "usage", None)
        usage: Dict[str, Any] = {
            "model": getattr(response, "model", model),
            "input_tokens": getattr(usage_obj, "input_tokens", 0) if usage_obj else 0,
            "output_tokens": getattr(usage_obj, "output_tokens", 0) if usage_obj else 0,
        }
        blocks = getattr(response, "content", None) or []
        if not blocks or getattr(blocks[0], "type", None) != "text":
            return "", {"regions": [], "tables": [], "full_text": ""}, usage
        raw = (getattr(blocks[0], "text", None) or "").strip()
        return raw, _parse_json(raw), usage


def _b64_image(path: Path, *, max_bytes: int = 4_500_000) -> tuple[str, str]:
    raw = path.read_bytes()
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if len(raw) <= max_bytes:
        return base64.b64encode(raw).decode("utf-8"), media
    img = Image.open(io.BytesIO(raw))
    if img.mode == "RGBA":
        img = img.convert("RGB")
    for q in range(90, 40, -10):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q)
        if buf.tell() <= max_bytes:
            return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
    raise RuntimeError(f"could not compress {path} under {max_bytes} bytes")


def _parse_json(raw: str) -> Dict[str, Any]:
    """Best-effort JSON parse for Claude output.

    Tries strict json.loads first, then falls back to json-repair which fixes
    common LLM breakage: trailing commas, unescaped quotes in string values,
    missing closing braces, etc.
    """
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import repair_json  # type: ignore

        repaired = repair_json(txt, return_objects=False)
        return json.loads(repaired)
    except Exception:
        pass

    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise json.JSONDecodeError("could not parse or repair JSON", txt[:200], 0)


def _payload_to_models(
    payload: Dict[str, Any], *, page_index: int, dpi: int, tool: str
) -> tuple[List[Region], List[TableModel], str]:
    coord = f"image_px@{dpi}"
    regions: List[Region] = []
    type_lookup = {t.value for t in RegionType}
    for r in payload.get("regions", []) or []:
        b = r.get("bbox") or {}
        rtype_raw = (r.get("type") or "unknown").strip()
        rtype = rtype_raw if rtype_raw in type_lookup else "unknown"
        try:
            bbox = BBox(
                x=float(b.get("x", 0)),
                y=float(b.get("y", 0)),
                w=float(b.get("w", 0)),
                h=float(b.get("h", 0)),
                page_index=page_index,
                coord_space=coord,
            )
        except (TypeError, ValueError):
            continue
        regions.append(
            Region(
                id=uuid.uuid4().hex[:10],
                type=RegionType(rtype),
                bbox=bbox,
                text=str(r.get("text", "")),
                confidence=float(r.get("confidence", 0.7)),
                raw_confidence=r.get("confidence"),
                source_tool=tool,
            )
        )

    tables: List[TableModel] = []
    for t in payload.get("tables", []) or []:
        tb = t.get("bbox") or {}
        try:
            table_bbox = BBox(
                x=float(tb.get("x", 0)),
                y=float(tb.get("y", 0)),
                w=float(tb.get("w", 0)),
                h=float(tb.get("h", 0)),
                page_index=page_index,
                coord_space=coord,
            )
        except (TypeError, ValueError):
            continue
        table_region = Region(
            id=uuid.uuid4().hex[:10],
            type=RegionType.TABLE,
            bbox=table_bbox,
            source_tool=tool,
            attributes={"border_mode": t.get("border_mode", "unknown")},
        )
        regions.append(table_region)
        cells: List[TableCell] = []
        for c in t.get("cells", []) or []:
            cb = c.get("bbox") or {}
            try:
                cbox = BBox(
                    x=float(cb.get("x", 0)),
                    y=float(cb.get("y", 0)),
                    w=float(cb.get("w", 0)),
                    h=float(cb.get("h", 0)),
                    page_index=page_index,
                    coord_space=coord,
                )
            except (TypeError, ValueError):
                cbox = None
            cells.append(
                TableCell(
                    row=int(c.get("row", 0)),
                    col=int(c.get("col", 0)),
                    rowspan=int(c.get("rowspan", 1)),
                    colspan=int(c.get("colspan", 1)),
                    text=str(c.get("text", "")),
                    bbox=cbox,
                    multiline=bool(c.get("multiline", False)),
                )
            )
        tables.append(
            TableModel(
                region_id=table_region.id,
                orientation=t.get("orientation", "horizontal"),
                border_mode=t.get("border_mode", "unknown"),
                n_rows=int(t.get("n_rows", 0)),
                n_cols=int(t.get("n_cols", 0)),
                cells=cells,
            )
        )
    return regions, tables, str(payload.get("full_text", ""))
