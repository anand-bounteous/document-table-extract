"""JSONL-mode PII benchmark REST surface (.prompt/009 §13–14)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app import pii_v2_dataset_store as ds
from app.config import settings
from app.pii_dataset_runner import execute_dataset_run
from app.pii_v2.registry import list_detectors

logger = logging.getLogger("ote.pii_dataset_benchmarks")
router = APIRouter(prefix="/pii-benchmarks/dataset", tags=["pii-dataset-benchmarks"])


@router.get("/datasets")
def list_datasets():
    return {"datasets": ds.list_datasets()}


@router.post("/datasets")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith((".jsonl", ".json")):
        raise HTTPException(400, "expected a .jsonl file")
    content = await file.read()
    return ds.save_dataset(content=content, filename=file.filename)


@router.get("/runs")
def list_dataset_runs(limit: int = 50):
    return {"runs": ds.list_dataset_runs(limit=limit)}


class DatasetRunRequest(BaseModel):
    dataset_id: str
    detector_names: Optional[List[str]] = None
    jurisdictions: Optional[List[str]] = None


@router.post("/runs")
def create_dataset_run(req: DatasetRunRequest, background_tasks: BackgroundTasks):
    if ds.get_dataset_path(req.dataset_id) is None:
        raise HTTPException(404, f"dataset not found: {req.dataset_id}")
    detector_names = req.detector_names or list(list_detectors().keys())
    available = set(list_detectors().keys())
    missing = [d for d in detector_names if d not in available]
    if missing:
        raise HTTPException(400, f"unknown detectors: {missing} (have: {sorted(available)})")
    jurisdictions = req.jurisdictions or settings.pii_v2_default_jurisdictions_list

    dataset_run_id = ds.init_dataset_run(
        dataset_id=req.dataset_id,
        detector_names=detector_names,
        jurisdictions=jurisdictions,
    )
    background_tasks.add_task(
        execute_dataset_run,
        dataset_run_id=dataset_run_id,
        dataset_id=req.dataset_id,
        detector_names=detector_names,
        jurisdictions=jurisdictions,
    )
    return {"dataset_run_id": dataset_run_id, "detector_names": detector_names}


@router.get("/runs/{dataset_run_id}")
def get_dataset_run(dataset_run_id: str):
    state = ds.read_dataset_run(dataset_run_id)
    if state is None:
        raise HTTPException(404, f"dataset_run not found: {dataset_run_id}")
    return state


@router.get("/runs/{dataset_run_id}/report.md", response_class=PlainTextResponse)
def get_report_md(dataset_run_id: str):
    p: Path = ds.report_path(dataset_run_id, "report.md")
    if not p.exists():
        raise HTTPException(404, "report not ready")
    return p.read_text()


@router.get("/runs/{dataset_run_id}/{detector}/false_positives.csv")
def get_fp_csv(dataset_run_id: str, detector: str):
    p = ds.detector_dir(dataset_run_id, detector) / "false_positives.csv"
    if not p.exists():
        raise HTTPException(404, "csv not ready")
    return FileResponse(p, media_type="text/csv", filename="false_positives.csv")


@router.get("/runs/{dataset_run_id}/{detector}/false_negatives.csv")
def get_fn_csv(dataset_run_id: str, detector: str):
    p = ds.detector_dir(dataset_run_id, detector) / "false_negatives.csv"
    if not p.exists():
        raise HTTPException(404, "csv not ready")
    return FileResponse(p, media_type="text/csv", filename="false_negatives.csv")
