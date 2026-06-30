"""Camelot stage — subprocess-isolated; vector-only at the Solution level."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage


@dataclass
class CamelotStage(SubprocessStage):
    name: str = "tables_camelot"
    tool: str = "camelot"
    worker_module: str = "app.workers.camelot_worker"
    flavors: List[str] = field(default_factory=lambda: ["lattice", "stream"])
    # Per-flavor advanced kwargs forwarded to camelot.read_pdf()
    # e.g. {"lattice": {"line_scale": 40, "copy_text": ["v"]}, "stream": {"edge_tol": 50}}
    flavor_kwargs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        payload["params"] = {
            "flavors": self.flavors,
            "flavor_kwargs": self.flavor_kwargs,
        }
        return payload
