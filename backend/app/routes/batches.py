"""Multi-document batch lifecycle.

A batch is a user submission of N documents × M solutions. Documents run
sequentially in the order submitted. For each document, the existing
``_execute_run`` machinery applies (which itself uses the auto-tuned
solution-concurrency scheduler).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app import batch_store, document_store, run_store
from app.config import settings
from app.pipeline import base

logger = logging.getLogger("ote.batches")
router = APIRouter(prefix="/batches", tags=["batches"])


class BatchRequest(BaseModel):
    document_ids: List[str]
    solution_names: List[str]
    dpi: Optional[int] = None


@router.get("")
def list_batches(limit: int = 50):
    return {"batches": batch_store.list_batches(limit=limit)}


@router.post("")
def create_batch(req: BatchRequest, background_tasks: BackgroundTasks):
    if not req.document_ids:
        raise HTTPException(400, "document_ids is required")
    if not req.solution_names:
        raise HTTPException(400, "solution_names is required")
    missing = [n for n in req.solution_names if n not in base.registered()]
    if missing:
        raise HTTPException(400, f"unknown solutions: {missing}")

    dpi = req.dpi or settings.default_dpi
    batch_id = uuid.uuid4().hex[:12]
    docs_meta: list[dict] = []
    for doc_id in req.document_ids:
        try:
            meta = document_store.get_document_meta(doc_id)
        except FileNotFoundError:
            raise HTTPException(404, f"document not found: {doc_id}")
        run_id = uuid.uuid4().hex[:12]
        document = document_store.empty_document_result(doc_id)
        # Pre-initialise the run row so the UI can deep-link before the
        # background task gets to it.
        run_store.init_run(run_id, document, req.solution_names)
        docs_meta.append({
            "document_id": doc_id,
            "filename": meta.get("filename") or doc_id,
            "run_id": run_id,
            "pdf_kind": meta.get("pdf_kind", "unknown"),
            "n_pages": meta.get("n_pages", 0),
            "path": meta["path"],
        })

    batch_store.init_batch(
        batch_id=batch_id,
        solution_names=req.solution_names,
        documents=[{k: v for k, v in d.items() if k != "path"} for d in docs_meta],
        dpi=dpi,
    )

    background_tasks.add_task(
        _execute_batch,
        batch_id=batch_id,
        docs=docs_meta,
        solution_names=req.solution_names,
        dpi=dpi,
    )

    return {
        "batch_id": batch_id,
        "run_ids": [d["run_id"] for d in docs_meta],
    }


@router.get("/{batch_id}")
def get_batch(batch_id: str):
    state = batch_store.read_batch(batch_id)
    if state is None:
        raise HTTPException(404, f"batch not found: {batch_id}")

    # Inline each document's run state so the UI can render solution cards
    # in-place without a second round-trip per doc.
    for doc in state.get("documents", []):
        rid = doc.get("run_id")
        if not rid:
            continue
        run_state = run_store.read_run(rid)
        if run_state is not None:
            doc["run"] = run_state
    # Stats roll-up.
    docs = state.get("documents", []) or []
    state["stats"] = {
        "total": len(docs),
        "queued": sum(1 for d in docs if d.get("status") == "queued"),
        "running": sum(1 for d in docs if d.get("status") == "running"),
        "done": sum(1 for d in docs if d.get("status") == "done"),
        "error": sum(1 for d in docs if d.get("status") == "error"),
    }
    return state


def _execute_batch(
    *,
    batch_id: str,
    docs: list[dict],
    solution_names: List[str],
    dpi: int,
) -> None:
    # Doc-level concurrency = 1 by design. Within a doc, the per-solution
    # ThreadPoolExecutor in _execute_run (sized by compute_solution_concurrency)
    # handles parallelism.
    from app.routes.runs import _execute_run  # local import to avoid a cycle

    for doc in docs:
        run_id = doc["run_id"]
        batch_store.update_document_status(batch_id, run_id, "running")
        try:
            _execute_run(
                run_id=run_id,
                document_id=doc["document_id"],
                pdf_path_str=doc["path"],
                pdf_kind=doc["pdf_kind"],
                n_pages=doc["n_pages"],
                solution_names=solution_names,
                dpi=dpi,
            )
            batch_store.update_document_status(batch_id, run_id, "done")
            logger.info("batch %s: doc %s done", batch_id, doc["document_id"])
        except Exception:  # noqa: BLE001
            batch_store.update_document_status(batch_id, run_id, "error")
            logger.exception("batch %s: doc %s failed", batch_id, doc["document_id"])
