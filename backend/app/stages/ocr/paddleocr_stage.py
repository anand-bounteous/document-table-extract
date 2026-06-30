"""PaddleOCR baseline stage — subprocess-isolated.

Standalone text detection + recognition (PP-OCRv4), no layout / table model.
Heavier per-page than easyocr / doctr but multilingual-capable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.stages.vision.paddle_structure import _paddle_env


def _paddle_ocr_env() -> Dict[str, str]:
    """Like :func:`_paddle_env` but pins every native thread pool to 1 worker.

    The OCR-only pipeline doesn't benefit from multi-threaded BLAS the way
    PP-Structure does, and giving each pool 4 workers triples baseline RSS —
    enough to cross the OOM threshold on an 8 GB Mac. One-thread mode trades
    a few seconds of latency for a much smaller memory footprint.
    """
    env = _paddle_env()
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        env[key] = "1"
    return env


@dataclass
class PaddleOCRStage(SubprocessStage):
    name: str = "ocr_paddleocr"
    tool: str = "paddleocr"
    worker_module: str = "app.workers.paddleocr_worker"
    timeout_sec: float = 600.0
    # Default ocr_version=PP-OCRv4 keeps the recognizer model ~3× smaller than
    # paddleocr 3.x's PP-OCRv5 default and avoids OOM on 8 GB Macs.
    params: Dict[str, Any] = field(default_factory=lambda: {"lang": "en", "ocr_version": "PP-OCRv4"})
    extra_env: Dict[str, str] = field(default_factory=_paddle_ocr_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
