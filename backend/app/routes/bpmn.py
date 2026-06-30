"""BPMN diagram endpoints — serve from on-disk .bpmn files so they are editable.

Files live in backend/app/bpmn/*.bpmn.
If a file is missing the XML is generated on-the-fly and written to disk
so subsequent requests (and Camunda Modeler) see the same file.

GET /bpmn/master            → master_pipeline.bpmn
GET /bpmn/{solution_name}   → {solution_name}.bpmn
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.bpmn.generator import generate_bpmn, generate_master_bpmn
from app.pipeline.base import registered

router = APIRouter(prefix="/bpmn", tags=["bpmn"])

BPMN_DIR = Path(__file__).parent.parent / "bpmn"


def _read_or_generate_master() -> str:
    path = BPMN_DIR / "master_pipeline.bpmn"
    if path.exists():
        return path.read_text(encoding="utf-8")
    xml = generate_master_bpmn()
    path.write_text(xml, encoding="utf-8")
    return xml


def _read_or_generate_solution(solution_name: str) -> str:
    path = BPMN_DIR / f"{solution_name}.bpmn"
    if path.exists():
        return path.read_text(encoding="utf-8")
    sols = registered()
    if solution_name not in sols:
        raise HTTPException(404, f"solution not found: {solution_name}")
    sol = sols[solution_name]
    xml = generate_bpmn(sol.name, sol.display_name, [s.name for s in sol.stages])
    path.write_text(xml, encoding="utf-8")
    return xml


@router.get("/master")
def get_master_bpmn():
    xml = _read_or_generate_master()
    return Response(content=xml, media_type="application/xml")


@router.get("/{solution_name}")
def get_bpmn(solution_name: str):
    # Guard against path traversal
    if "/" in solution_name or "\\" in solution_name or solution_name.startswith("."):
        raise HTTPException(400, "invalid solution name")
    try:
        xml = _read_or_generate_solution(solution_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    return Response(content=xml, media_type="application/xml")
