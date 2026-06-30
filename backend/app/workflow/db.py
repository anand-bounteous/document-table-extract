"""SQLite persistence for workflow runs and stage events."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

_DB_PATH: Optional[Path] = None


def _db_path() -> Path:
    if _DB_PATH is not None:
        return _DB_PATH
    storage = Path(__file__).parent.parent.parent.parent / "storage"
    storage.mkdir(exist_ok=True)
    return storage / "workflows.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id       TEXT NOT NULL,
                solution     TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'running',
                started_at   REAL NOT NULL,
                updated_at   REAL NOT NULL,
                PRIMARY KEY (run_id, solution)
            );

            CREATE TABLE IF NOT EXISTS stage_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT NOT NULL,
                solution     TEXT NOT NULL,
                stage_name   TEXT NOT NULL,
                status       TEXT NOT NULL,
                started_at   REAL NOT NULL,
                duration_ms  REAL,
                error_msg    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_stage_run ON stage_events(run_id, solution);
        """)


def start_run(run_id: str, solution: str) -> None:
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO workflow_runs(run_id, solution, status, started_at, updated_at) "
            "VALUES (?, ?, 'running', ?, ?)",
            (run_id, solution, now, now),
        )


def finish_run(run_id: str, solution: str, status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE workflow_runs SET status=?, updated_at=? WHERE run_id=? AND solution=?",
            (status, time.time(), run_id, solution),
        )


def record_stage(
    run_id: str,
    solution: str,
    stage_name: str,
    status: str,
    started_at: float,
    duration_ms: Optional[float] = None,
    error_msg: Optional[str] = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO stage_events(run_id, solution, stage_name, status, started_at, duration_ms, error_msg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, solution, stage_name, status, started_at, duration_ms, error_msg),
        )
