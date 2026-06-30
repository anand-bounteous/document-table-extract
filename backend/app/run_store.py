"""Filesystem-backed run store: storage/runs/<run_id>/<solution>/result.json + status."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.core.schemas import DocumentResult, SolutionResult

_LOCK = threading.Lock()


def runs_root() -> Path:
    p = settings.runs_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_dir(run_id: str) -> Path:
    return runs_root() / run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(run_id: str) -> Optional[Dict]:
    p = run_dir(run_id) / "run.json"
    if not p.exists():
        return None
    text = p.read_text().strip()
    if not text:
        return None
    return json.loads(text)


def _write_state(run_id: str, state: Dict) -> None:
    (run_dir(run_id) / "run.json").write_text(json.dumps(state, indent=2, default=str))


def init_run(run_id: str, document: DocumentResult, solution_names: List[str]) -> None:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    state = {
        "run_id": run_id,
        "document": document.model_dump(mode="json"),
        "solution_names": solution_names,
        "completed": [],
        "status": "running",
        "started_at": now,
        "updated_at": now,
        "solution_status": {
            name: {"state": "pending", "queued_at": now}
            for name in solution_names
        },
    }
    with _LOCK:
        _write_state(run_id, state)


def set_pii_v2_link(run_id: str, pii_run_id: str) -> None:
    """Stamp the paired pii_v2 run id so /runs/<id> can render a cross-link chip."""
    with _LOCK:
        state = _read_state(run_id)
        if state is None:
            return
        state["pii_v2_run_id"] = pii_run_id
        state["updated_at"] = _now_iso()
        _write_state(run_id, state)


def mark_solution(run_id: str, name: str, state_name: str, **extra) -> None:
    """Update one solution's status. state_name ∈ {pending, running, done, error, skipped}."""
    with _LOCK:
        state = _read_state(run_id)
        if state is None:
            return
        ss = state.setdefault("solution_status", {})
        cur = ss.get(name) or {}
        cur["state"] = state_name
        cur["updated_at"] = _now_iso()
        cur.update(extra)
        ss[name] = cur
        state["updated_at"] = _now_iso()
        _write_state(run_id, state)


def write_solution(run_id: str, result: SolutionResult) -> None:
    d = run_dir(run_id) / result.solution_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(result.model_dump_json(indent=2))
    with _LOCK:
        state = _read_state(run_id)
        if state is None:
            return
        if result.solution_name not in state["completed"]:
            state["completed"].append(result.solution_name)
        ss = state.setdefault("solution_status", {})
        if result.status == "error":
            finished_state = "error"
        elif result.status == "skipped":
            finished_state = "skipped"
        elif result.status == "partial":
            # Recovered some pages but a sub-stage timed out / crashed —
            # surface this so the Resume button on the run page picks it up.
            finished_state = "partial"
        else:
            finished_state = "done"
        n_pages_done = len(result.pages or [])
        n_pages_expected = int(
            ((state.get("document") or {}).get("n_pages") or 0)
        ) if state else 0
        ss[result.solution_name] = {
            **(ss.get(result.solution_name) or {}),
            "state": finished_state,
            "updated_at": _now_iso(),
            "result_status": result.status,
            "overall_confidence": result.overall_confidence,
            "duration_ms": result.timings.total_ms,
            "error": result.error,
            "n_pages_done": n_pages_done,
            "n_pages_expected": n_pages_expected,
        }
        if set(state["completed"]) >= set(state["solution_names"]):
            state["status"] = "done"
            state["finished_at"] = _now_iso()
        state["updated_at"] = _now_iso()
        _write_state(run_id, state)


def read_run(run_id: str) -> Optional[Dict]:
    state = _read_state(run_id)
    if state is None:
        return None
    state["solution_results"] = []
    for name in state["solution_names"]:
        rp = run_dir(run_id) / name / "result.json"
        if rp.exists():
            state["solution_results"].append(json.loads(rp.read_text()))
    return state


def list_runs(limit: int = 50) -> List[Dict]:
    out: List[Dict] = []
    for p in sorted(runs_root().glob("*/run.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            state = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "run_id": state.get("run_id"),
            "status": state.get("status"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "updated_at": state.get("updated_at"),
            "document": state.get("document"),
            "solution_names": state.get("solution_names", []),
            "solution_status": state.get("solution_status", {}),
            "completed": state.get("completed", []),
        })
        if len(out) >= limit:
            break
    return out


def list_artifact(run_id: str, artifact_id: str) -> Optional[Path]:
    """Artifact ids look like ``<solution>:<relative/path>``."""
    if ":" not in artifact_id:
        return None
    solution, rel = artifact_id.split(":", 1)
    rel = rel.lstrip("/")
    p = (run_dir(run_id) / solution / "artifacts" / rel).resolve()
    base = (run_dir(run_id) / solution / "artifacts").resolve()
    try:
        p.relative_to(base)
    except ValueError:
        return None
    return p if p.exists() else None


def solution_log_path(run_id: str, name: str) -> Path:
    """Path to the per-solution log file (created lazily by the runner)."""
    return run_dir(run_id) / name / "log.txt"


def run_log_path(run_id: str) -> Path:
    return run_dir(run_id) / "run.log"
