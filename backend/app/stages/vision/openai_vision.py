"""OpenAI Vision stage: GPT-4o structured extraction (identical prompt to ClaudeVision)."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from app.config import settings
from app.core.schemas import BBox, Region, RegionType, TableCell, TableModel
from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.ssl_env import system_ca_bundle
from app.stages.vision.claude_vision import PROMPT, _payload_to_models, _parse_json, _b64_image

logger = logging.getLogger("ote.stage.vision.openai")


@dataclass
class OpenAIVision:
    name: str = "vision_openai"
    tool: str = "openai_vision"
    use_redacted: bool = True
    model: Optional[str] = None
    max_tokens: int = 8192

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError("openai package not installed: pip install openai") from e

        import httpx  # type: ignore
        ca_bundle = system_ca_bundle()
        http_client = httpx.Client(verify=ca_bundle) if ca_bundle else None
        client = OpenAI(api_key=settings.openai_api_key, http_client=http_client)
        model = self.model or settings.openai_model
        total_usage: Dict[str, Any] = {"model": model, "input_tokens": 0, "output_tokens": 0}

        for idx, page in state.pages.items():
            img_path = self._pick_image(idx, ctx, state)
            img_b64, media = _b64_image(img_path)
            try:
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=self.max_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{media};base64,{img_b64}", "detail": "high"},
                                },
                                {"type": "text", "text": PROMPT},
                            ],
                        }
                    ],
                )
            except Exception as exc:
                logger.error("OpenAI call failed for page %d: %s", idx, exc)
                raise

            usage_obj = getattr(response, "usage", None)
            if usage_obj:
                total_usage["model"] = model
                total_usage["input_tokens"] += getattr(usage_obj, "prompt_tokens", 0)
                total_usage["output_tokens"] += getattr(usage_obj, "completion_tokens", 0)

            raw = ""
            choices = getattr(response, "choices", None) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                raw = (getattr(msg, "content", None) or "").strip()

            ctx.save_text(f"vision/page-{idx:03d}-raw.txt", raw)
            payload = _parse_json(raw) if raw else {"regions": [], "tables": [], "full_text": ""}
            ctx.save_json(f"vision/page-{idx:03d}-response.json", payload)
            regions, tables, full_text = _payload_to_models(payload, page_index=idx, dpi=page.dpi, tool=self.tool)
            page.regions.extend(regions)
            page.tables.extend(tables)
            page.full_text = full_text or page.full_text

        if ctx.current_handle is not None:
            ctx.current_handle.usage = total_usage
        return state

    def _pick_image(self, idx: int, ctx: RunContext, state: RunState) -> Path:
        if self.use_redacted:
            redacted: Dict[int, Path] = state.extras.get("pii_redacted", {})
            if idx in redacted:
                return redacted[idx]
        return ctx.page_images[idx]
