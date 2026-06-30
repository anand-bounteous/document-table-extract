"""docling stage — subprocess-isolated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.pipeline.ssl_env import ssl_env_overrides


def _docling_env() -> Dict[str, str]:
    """SSL bundle override + MPS float64 fallback on Apple Silicon."""
    env = dict(ssl_env_overrides())
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    return env


@dataclass
class DoclingStage(SubprocessStage):
    name: str = "vision_docling"
    tool: str = "docling"
    worker_module: str = "app.workers.docling_worker"
    timeout_sec: float = 1800.0
    # ocr_backend picks docling's built-in OCR engine:
    #   "easyocr"   — docling default; deep-learning detector+recognizer
    #   "tesseract" — TesseractCliOcrOptions; requires `tesseract` in PATH
    #   "rapidocr"  — RapidOcrOptions; PaddleOCR-derived ONNX runtime
    params: Dict[str, Any] = field(default_factory=lambda: {"ocr_backend": "easyocr"})
    extra_env: Dict[str, str] = field(default_factory=_docling_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
