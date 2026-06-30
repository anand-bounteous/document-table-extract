"""Layout-Parser (PDF-native) stage — subprocess-isolated.

Same shape as :mod:`app.stages.layout.layout_parser_stage` but points at the
``layout_parser_pdf_worker`` which reads the PDF via ``lp.load_pdf`` instead
of operating only on rasterized pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage
from app.stages.layout.layout_parser_stage import _layout_parser_env


@dataclass
class LayoutParserPdfStage(SubprocessStage):
    name: str = "layout_parser_pdf_detect"
    tool: str = "layout_parser_pdf"
    worker_module: str = "app.workers.layout_parser_pdf_worker"
    timeout_sec: float = 900.0
    params: Dict[str, Any] = field(
        default_factory=lambda: {
            "score_threshold": 0.5,
            "use_visual_model": True,
        }
    )
    extra_env: Dict[str, str] = field(default_factory=_layout_parser_env)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = self.params
        return payload

    def apply_result(self, ctx: RunContext, state: RunState, result: Dict[str, Any]) -> None:
        super().apply_result(ctx, state, result)
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
