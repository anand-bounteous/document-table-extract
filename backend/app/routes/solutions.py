"""Solution catalog (mirrors the in-process registry)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.schemas import SolutionDescriptor
from app.pipeline.base import registered

router = APIRouter(prefix="/solutions", tags=["solutions"])


@router.get("")
def list_solutions():
    out = []
    for sol in registered().values():
        out.append(
            SolutionDescriptor(
                name=sol.name,
                display_name=sol.display_name,
                description=sol.description,
                supported_kinds=sorted(sol.supported_kinds),
                stages=[s.name for s in sol.stages],
                enabled=sol.enabled,
                model=sol.model,
            ).model_dump()
        )
    return {"solutions": out}
