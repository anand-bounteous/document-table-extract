"""Pipeline primitives: Stage protocol, Solution dataclass, RunState."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol, Set

from app.core.schemas import PageResult, PdfKind, Region, TableModel

if TYPE_CHECKING:
    from app.pipeline.context import RunContext


@dataclass
class RunState:
    """Mutable workspace passed stage-to-stage during a solution run.

    Stages mutate this object; the runner harvests its final state into a SolutionResult.
    """

    pages: Dict[int, PageResult] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

    def page(self, idx: int, *, w: int, h: int, dpi: int, pdf_kind: PdfKind) -> PageResult:
        if idx not in self.pages:
            self.pages[idx] = PageResult(
                page_index=idx, width=w, height=h, dpi=dpi, pdf_kind=pdf_kind
            )
        return self.pages[idx]

    def all_regions(self) -> List[Region]:
        out: List[Region] = []
        for p in self.pages.values():
            out.extend(p.regions)
        return out

    def all_tables(self) -> List[TableModel]:
        out: List[TableModel] = []
        for p in self.pages.values():
            out.extend(p.tables)
        return out


class Stage(Protocol):
    """A single tool invocation. Pure-ish: reads context + state, writes state."""

    name: str

    def run(self, ctx: "RunContext", state: RunState) -> RunState: ...


@dataclass
class Solution:
    name: str
    display_name: str
    description: str
    supported_kinds: Set[PdfKind]
    stages: List[Stage]
    enabled: bool = True
    model: Optional[str] = None

    def supports(self, kind: PdfKind) -> bool:
        return kind in self.supported_kinds or "mixed" in self.supported_kinds


# --- Registry ----------------------------------------------------------------

_REGISTRY: Dict[str, Solution] = {}


def register(solution: Solution) -> Solution:
    if solution.name in _REGISTRY:
        raise ValueError(f"Solution '{solution.name}' already registered")
    _REGISTRY[solution.name] = solution
    return solution


def registered() -> Dict[str, Solution]:
    return dict(_REGISTRY)


def get(name: str) -> Solution:
    if name not in _REGISTRY:
        raise KeyError(f"Solution '{name}' not registered")
    return _REGISTRY[name]


SolutionFactory = Callable[[], Solution]
