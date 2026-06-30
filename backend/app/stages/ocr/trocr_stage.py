"""TrOCR stage — subprocess-isolated.

EasyOCR detector + HuggingFace TrOCR recognizer. Two solutions share this
stage with different ``params.model_id`` / ``params.mode``:

    microsoft/trocr-base-handwritten  →  HANDWRITING_SIGNATURE regions
    microsoft/trocr-base-printed      →  NORMAL_TEXT regions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.pipeline.ssl_env import ssl_env_overrides


def _trocr_env() -> Dict[str, str]:
    """Pin native thread pools to 1 and point SSL at the system CA bundle so
    HuggingFace downloads succeed on macOS (certifi's bundle is missing some
    roots that huggingface.co's CDN serves)."""
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
class TrOCRStage(SubprocessStage):
    name: str = "ocr_trocr"
    tool: str = "trocr"
    worker_module: str = "app.workers.trocr_worker"
    timeout_sec: float = 900.0
    params: Dict[str, Any] = field(
        default_factory=lambda: {
            "model_id": "microsoft/trocr-base-handwritten",
            "mode": "handwritten",
            "lang": "en",
        }
    )
    extra_env: Dict[str, str] = field(default_factory=_trocr_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
