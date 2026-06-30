"""Persistence for JSONL-mode PII benchmark runs.

Layout:

    storage/pii_runs/_datasets/<dataset_id>.jsonl     # uploaded annotated dataset
    storage/pii_runs/_datasets/<dataset_id>.meta.json # filename + record count

    storage/pii_runs/_dataset_runs/<dataset_run_id>/
        run.json                                       # status + per-detector summary
        <detector>/predictions.jsonl                   # one line per record
        <detector>/false_positives.csv
        <detector>/false_negatives.csv
        report.json                                    # aggregated metrics
        report.md                                      # markdown summary
"""

from __future__ import annotations

import csv
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.config import settings

_LOCK = threading.Lock()


def _root() -> Path:
    p = settings.pii_v2_runs_path
    (p / "_datasets").mkdir(parents=True, exist_ok=True)
    (p / "_dataset_runs").mkdir(parents=True, exist_ok=True)
    return p


def _datasets_dir() -> Path:
    _root()
    return settings.pii_v2_runs_path / "_datasets"


def _dataset_runs_dir() -> Path:
    _root()
    return settings.pii_v2_runs_path / "_dataset_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- datasets -------------------------------------------------------------

def save_dataset(content: bytes, filename: str) -> Dict[str, Any]:
    dataset_id = uuid.uuid4().hex[:12]
    target = _datasets_dir() / f"{dataset_id}.jsonl"
    target.write_bytes(content)
    n_records = sum(1 for line in target.read_text().splitlines() if line.strip())
    meta = {
        "dataset_id": dataset_id,
        "filename": filename,
        "n_records": n_records,
        "uploaded_at": _now_iso(),
    }
    (_datasets_dir() / f"{dataset_id}.meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def list_datasets() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(_datasets_dir().glob("*.meta.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:  # noqa: BLE001
            continue
    return out


def get_dataset_path(dataset_id: str) -> Optional[Path]:
    p = _datasets_dir() / f"{dataset_id}.jsonl"
    return p if p.exists() else None


def get_dataset_meta(dataset_id: str) -> Optional[Dict[str, Any]]:
    p = _datasets_dir() / f"{dataset_id}.meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def iter_records(dataset_id: str) -> Iterable[Dict[str, Any]]:
    p = get_dataset_path(dataset_id)
    if p is None:
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


# ---- dataset runs ---------------------------------------------------------

def init_dataset_run(
    *,
    dataset_id: str,
    detector_names: List[str],
    jurisdictions: List[str],
) -> str:
    dataset_run_id = uuid.uuid4().hex[:12]
    d = _dataset_runs_dir() / dataset_run_id
    d.mkdir(parents=True, exist_ok=True)
    state = {
        "dataset_run_id": dataset_run_id,
        "dataset_id": dataset_id,
        "detector_names": detector_names,
        "jurisdictions": jurisdictions,
        "status": "running",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "per_detector": {
            n: {"status": "pending", "records_done": 0}
            for n in detector_names
        },
    }
    _write_run_state(dataset_run_id, state)
    return dataset_run_id


def _state_path(dataset_run_id: str) -> Path:
    return _dataset_runs_dir() / dataset_run_id / "run.json"


def _write_run_state(dataset_run_id: str, state: Dict[str, Any]) -> None:
    _state_path(dataset_run_id).write_text(json.dumps(state, indent=2, default=str))


def read_dataset_run(dataset_run_id: str) -> Optional[Dict[str, Any]]:
    p = _state_path(dataset_run_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def mark_detector(dataset_run_id: str, detector: str, **fields: Any) -> None:
    with _LOCK:
        state = read_dataset_run(dataset_run_id)
        if state is None:
            return
        entry = state["per_detector"].setdefault(detector, {})
        entry.update(fields)
        entry["updated_at"] = _now_iso()
        state["updated_at"] = _now_iso()
        _write_run_state(dataset_run_id, state)


def finalize_dataset_run(dataset_run_id: str, summary: Dict[str, Any]) -> None:
    with _LOCK:
        state = read_dataset_run(dataset_run_id)
        if state is None:
            return
        state["status"] = "done"
        state["finished_at"] = _now_iso()
        state["updated_at"] = _now_iso()
        state["summary"] = summary
        _write_run_state(dataset_run_id, state)


def detector_dir(dataset_run_id: str, detector: str) -> Path:
    d = _dataset_runs_dir() / dataset_run_id / detector
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_csv(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in columns})


def report_path(dataset_run_id: str, kind: str) -> Path:
    """kind ∈ {'report.json', 'report.md'}"""
    return _dataset_runs_dir() / dataset_run_id / kind


def list_dataset_runs(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(_dataset_runs_dir().glob("*/run.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            state = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "dataset_run_id": state.get("dataset_run_id"),
            "dataset_id": state.get("dataset_id"),
            "status": state.get("status"),
            "detector_names": state.get("detector_names", []),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
        })
        if len(out) >= limit:
            break
    return out
