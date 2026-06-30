"""RAGFlow deepdoc stage — subprocess-isolated.

Wraps :mod:`app.workers.deepdoc_worker`. One stage class drives all five
solutions; the only thing each solution differs on is ``params.ocr_backend``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.pipeline.ssl_env import ssl_env_overrides


def _deepdoc_env() -> Dict[str, str]:
    """SSL bundle + 1-thread native pools.

    SSL: first-run model downloads pull from HuggingFace's ``InfiniFlow/deepdoc``
    repo — needs the system CA bundle on macOS.
    Threads: ONNX Runtime + the optional OCR backends (paddle / easyocr /
    torch-based doctr) all spawn their own thread pools; pin everything to 1
    so first-run loading doesn't OOM on 8 GB Macs.
    """
    env = dict(ssl_env_overrides())
    env.update({
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
    })
    return env


@dataclass
class DeepdocStage(SubprocessStage):
    name: str = "ocr_deepdoc"
    tool: str = "deepdoc"
    worker_module: str = "app.workers.deepdoc_worker"
    timeout_sec: float = 900.0
    params: Dict[str, Any] = field(
        default_factory=lambda: {
            "ocr_backend": "default",
            "layout_score_threshold": 0.4,
        }
    )
    extra_env: Dict[str, str] = field(default_factory=_deepdoc_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
