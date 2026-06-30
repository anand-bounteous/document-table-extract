"""Filesystem-backed batch store.

A *batch* is a user submission of N documents × M solutions. Each document
in the batch gets its own run (the existing per-doc concept). The batch
itself just owns the ordered list of (document_id, run_id) pairs and a few
status bits so the UI can render a queue dashboard.

Layout: ``storage/runs/_batches/<batch_id>.json``
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batches_root() -> Path:
    p = settings.runs_path / "_batches"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _batch_path(batch_id: str) -> Path:
    return _batches_root() / f"{batch_id}.json"


def init_batch(
    batch_id: str,
    solution_names: List[str],
    documents: List[Dict[str, Any]],
    dpi: int,
) -> None:
    """Create the batch file. ``documents`` is a list of
    ``{document_id, filename, run_id, n_pages, pdf_kind}``."""
    now = _now_iso()
    state = {
        "batch_id": batch_id,
        "created_at": now,
        "updated_at": now,
        "status": "running",
        "solution_names": solution_names,
        "dpi": dpi,
        "documents": [
            {
                **doc,
                "status": "queued",  # queued | running | done | error
                "started_at": None,
                "finished_at": None,
            }
            for doc in documents
        ],
    }
    with _LOCK:
        _batch_path(batch_id).write_text(json.dumps(state, indent=2))


def read_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    p = _batch_path(batch_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def update_document_status(batch_id: str, run_id: str, status: str) -> None:
    """Set status on a specific (batch, doc) pair. ``status`` ∈
    ``queued | running | done | error``."""
    with _LOCK:
        state = read_batch(batch_id)
        if state is None:
            return
        now = _now_iso()
        for doc in state.get("documents", []):
            if doc.get("run_id") == run_id:
                doc["status"] = status
                if status == "running" and not doc.get("started_at"):
                    doc["started_at"] = now
                if status in ("done", "error") and not doc.get("finished_at"):
                    doc["finished_at"] = now
                break
        state["updated_at"] = now
        # Promote batch status: still running until every doc is terminal.
        terminal = ("done", "error")
        docs = state.get("documents", [])
        if docs and all(d.get("status") in terminal for d in docs):
            state["status"] = "done"
        _batch_path(batch_id).write_text(json.dumps(state, indent=2))


def list_batches(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    root = _batches_root()
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[:limit]:
        try:
            blob = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        docs = blob.get("documents", []) or []
        out.append({
            "batch_id": blob.get("batch_id"),
            "created_at": blob.get("created_at"),
            "status": blob.get("status"),
            "n_documents": len(docs),
            "n_done": sum(1 for d in docs if d.get("status") == "done"),
            "n_error": sum(1 for d in docs if d.get("status") == "error"),
            "n_running": sum(1 for d in docs if d.get("status") == "running"),
        })
    return out
