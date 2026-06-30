"""EasyOCR stage — subprocess-isolated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage


@dataclass
class EasyOCRStage(SubprocessStage):
    name: str = "ocr_easyocr"
    tool: str = "easyocr"
    worker_module: str = "app.workers.easyocr_worker"
    params: Dict[str, Any] = field(default_factory=lambda: {"lang": "en"})

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
