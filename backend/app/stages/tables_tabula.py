"""Tabula stage — subprocess-isolated; vector-only at the Solution level."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.pipeline.base import RunState
from app.pipeline.context import RunContext
from app.pipeline.isolation import SubprocessStage


@dataclass
class TabulaStage(SubprocessStage):
    name: str = "tables_tabula"
    tool: str = "tabula"
    worker_module: str = "app.workers.tabula_worker"
    # New-style: explicit flavors list
    flavors: Optional[List[str]] = None
    # Legacy booleans kept for backwards compatibility
    lattice: bool = True
    stream: bool = True
    guess: bool = False

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        payload = super().build_payload(ctx, state)
        params: Dict[str, Any] = {"guess": self.guess}
        if self.flavors is not None:
            params["flavors"] = self.flavors
        else:
            params["lattice"] = self.lattice
            params["stream"] = self.stream
        payload["params"] = params
        return payload
