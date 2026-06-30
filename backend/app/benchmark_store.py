"""Cross-document benchmark analyses.

A *benchmark analysis* is a saved resource that captures a selection of
(document, run, pages) plus the LLM-summarized comparison output. Persisted
as one JSON per analysis at ``storage/benchmark_analyses/<id>.json``.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_LOCK = threading.Lock()


def _root() -> Path:
    p = settings.runs_path.parent / "benchmark_analyses"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(analysis_id: str) -> Path:
    return _root() / f"{analysis_id}.json"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init(*, name: str, selections: List[Dict[str, Any]]) -> Dict[str, Any]:
    rec = {
        "id": new_id(),
        "name": name or "(unnamed)",
        "created_at": _now(),
        "updated_at": _now(),
        "status": "pending",
        "selections": selections,
        "review_snapshot": None,
        "metrics_snapshot": None,
        "llm_input_preview": None,
        "llm_summary": None,
        "error": None,
    }
    save(rec)
    return rec


def save(rec: Dict[str, Any]) -> None:
    rec["updated_at"] = _now()
    with _LOCK:
        _path(rec["id"]).write_text(json.dumps(rec, indent=2, default=str))


def load(analysis_id: str) -> Optional[Dict[str, Any]]:
    p = _path(analysis_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_all(limit: int = 100) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in sorted(_root().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "id": data.get("id"),
            "name": data.get("name"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "n_documents": len(data.get("selections") or []),
            "error": data.get("error"),
        })
        if len(out) >= limit:
            break
    return out


def delete(analysis_id: str) -> bool:
    p = _path(analysis_id)
    if not p.exists():
        return False
    p.unlink()
    return True
