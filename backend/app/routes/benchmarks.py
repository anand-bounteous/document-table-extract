"""Cross-document benchmark analysis routes."""

from __future__ import annotations

import logging
import threading
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app import benchmark_analyzer, benchmark_store

logger = logging.getLogger("ote.routes.benchmarks")
router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


class BenchmarkSelection(BaseModel):
    document_id: str
    run_id: str
    page_indices: List[int]


class CreateAnalysisRequest(BaseModel):
    name: str = ""
    selections: List[BenchmarkSelection]


@router.post("/analyze")
def create_analysis(req: CreateAnalysisRequest, background: BackgroundTasks):
    if not req.selections:
        raise HTTPException(400, "selections must include at least one document")
    rec = benchmark_store.init(
        name=req.name,
        selections=[s.model_dump() for s in req.selections],
    )
    background.add_task(_run_in_thread, rec["id"])
    return {"id": rec["id"], "status": rec["status"]}


def _run_in_thread(analysis_id: str) -> None:
    t = threading.Thread(
        target=benchmark_analyzer.run_analysis,
        args=(analysis_id,),
        daemon=True,
        name=f"benchmark-{analysis_id}",
    )
    t.start()


@router.get("")
def list_analyses(limit: int = 50):
    return {"analyses": benchmark_store.list_all(limit=limit)}


@router.get("/{analysis_id}")
def get_analysis(analysis_id: str):
    rec = benchmark_store.load(analysis_id)
    if rec is None:
        raise HTTPException(404, f"analysis not found: {analysis_id}")
    return rec


@router.delete("/{analysis_id}")
def delete_analysis(analysis_id: str):
    ok = benchmark_store.delete(analysis_id)
    if not ok:
        raise HTTPException(404, f"analysis not found: {analysis_id}")
    return {"deleted": analysis_id}
