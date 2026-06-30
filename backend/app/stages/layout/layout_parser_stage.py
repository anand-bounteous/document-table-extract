"""Layout-Parser stage — subprocess-isolated.

Wraps :mod:`app.workers.layout_parser_worker` and additionally copies the
worker-computed ``doc_format`` / ``doc_format_scores`` into the matching
``PageResult`` so the UI can show the format pill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.pipeline.ssl_env import ssl_env_overrides


def _layout_parser_env() -> Dict[str, str]:
    """Pin native thread pools to 1 worker so the backend doesn't fork-bomb,
    and point SSL at the system CA bundle for the first-run model download
    (paddlepaddle.org.cn / Dropbox mirror)."""
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
class LayoutParserStage(SubprocessStage):
    name: str = "layout_parser_detect"
    tool: str = "layout_parser"
    worker_module: str = "app.workers.layout_parser_worker"
    timeout_sec: float = 900.0
    params: Dict[str, Any] = field(default_factory=lambda: {"score_threshold": 0.5})
    extra_env: Dict[str, str] = field(default_factory=_layout_parser_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload

    def apply_result(self, ctx: RunContext, state: RunState, result: Dict[str, Any]) -> None:
        super().apply_result(ctx, state, result)
        # Copy doc_format / doc_format_scores into PageResult — base class
        # only knows about regions + tables.
        for page_dict in result.get("pages", []) or []:
            idx = int(page_dict.get("page_index", 0))
            if idx not in state.pages:
                continue
            fmt = page_dict.get("doc_format")
            scores = page_dict.get("doc_format_scores") or {}
            if fmt:
                state.pages[idx].doc_format = fmt
            if scores:
                state.pages[idx].doc_format_scores = dict(scores)
