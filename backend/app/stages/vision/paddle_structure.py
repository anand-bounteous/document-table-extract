"""PaddleOCR PP-Structure stage — subprocess-isolated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.pipeline.ssl_env import ssl_env_overrides


def _paddle_env() -> Dict[str, str]:
    """Reduce paddle's thread/native-lib footprint on Apple Silicon.

    SIGTRAP / SIGABRT crashes inside paddle's native stack are usually thread-
    contention between MKL / OpenBLAS / OpenMP / Paddle's own thread pool.
    Pinning every thread library to 1 worker is the standard workaround.
    """
    env = dict(ssl_env_overrides())
    env.setdefault("FLAGS_use_cinn", "0")
    env.setdefault("FLAGS_allocator_strategy", "naive_best_fit")
    import os as _os
    ncpu = str(min(4, _os.cpu_count() or 2))
    env.setdefault("OMP_NUM_THREADS", ncpu)
    env.setdefault("MKL_NUM_THREADS", ncpu)
    env.setdefault("OPENBLAS_NUM_THREADS", ncpu)
    env.setdefault("NUMEXPR_NUM_THREADS", ncpu)
    env.setdefault("VECLIB_MAXIMUM_THREADS", ncpu)
    env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    # Tokenizers (downstream dep) emits its own thread warning + can fork-bomb under load
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    return env


@dataclass
class PaddleStructureStage(SubprocessStage):
    name: str = "vision_paddle_structure"
    tool: str = "paddle_pp_structure"
    worker_module: str = "app.workers.paddle_structure_worker"
    timeout_sec: float = 600.0
    params: Dict[str, Any] = field(default_factory=lambda: {"lang": "en"})
    extra_env: Dict[str, str] = field(default_factory=_paddle_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload
