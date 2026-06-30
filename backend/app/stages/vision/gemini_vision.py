"""Gemini Vision stage: Gemini structured extraction (identical prompt to ClaudeVision)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.ssl_env import ssl_env_overrides
from app.stages.vision.claude_vision import PROMPT, _payload_to_models, _parse_json

logger = logging.getLogger("ote.stage.vision.gemini")


@dataclass
class GeminiVision:
    name: str = "vision_gemini"
    tool: str = "gemini_vision"
    use_redacted: bool = True
    model: Optional[str] = None

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        try:
            import google.generativeai as genai  # type: ignore
            from PIL import Image as PILImage  # type: ignore
        except ImportError as e:
            raise RuntimeError("google-generativeai not installed: pip install -e '.[llm-gemini]'") from e

        # Set SSL env vars before any network call — macOS Homebrew Python needs this
        for k, v in ssl_env_overrides().items():
            os.environ.setdefault(k, v)

        genai.configure(api_key=settings.gemini_api_key)
        model_name = self.model or settings.gemini_model
        gen_model = genai.GenerativeModel(model_name)
        total_usage: Dict[str, Any] = {"model": model_name, "input_tokens": 0, "output_tokens": 0}

        for idx, page in state.pages.items():
            img_path = self._pick_image(idx, ctx, state)
            pil_img = PILImage.open(img_path).convert("RGB")
            try:
                response = gen_model.generate_content(
                    [pil_img, PROMPT],
                    generation_config={"temperature": 0, "max_output_tokens": 8192},
                    request_options={"timeout": 120},
                )
            except Exception as exc:
                logger.error("Gemini call failed for page %d: %s", idx, exc)
                raise

            meta = getattr(response, "usage_metadata", None)
            if meta:
                total_usage["input_tokens"] += getattr(meta, "prompt_token_count", 0) or 0
                total_usage["output_tokens"] += getattr(meta, "candidates_token_count", 0) or 0

            raw = ""
            try:
                raw = (response.text or "").strip()
            except Exception as exc:
                logger.warning("Gemini page %d: could not extract text from response: %s", idx, exc)

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
