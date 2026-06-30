"""img2table stage — subprocess-isolated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage


@dataclass
class Img2TableStage(SubprocessStage):
    name: str = "tables_img2table"
    tool: str = "img2table"
    worker_module: str = "app.workers.img2table_worker"
    ocr_backend: str = "tesseract"
    params: Dict[str, Any] = field(
        default_factory=lambda: {
            "lang": "eng",
            "implicit_rows": True,
            "borderless_tables": True,
            "min_confidence": 50,
        }
    )

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = {**self.params, "ocr_backend": self.ocr_backend}
        return payload
