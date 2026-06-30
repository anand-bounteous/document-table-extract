"""Shared I/O for isolated workers.

Workers read a JSON payload from stdin and write a JSON result to the path in
``$OTE_RESULT_PATH``. They MUST NOT write the result to stdout, because child
binaries (tesseract, ghostscript, java, paddle) may emit banners that would
corrupt stdout.

Workers may additionally write a tiny per-page progress record to the path in
``$OTE_PROGRESS_PATH`` via :func:`write_progress`. The parent process reads
this file on each ``GET /runs/<id>`` poll and surfaces the page progress in
the UI.

Long page-loop workers can also stream incremental result snapshots to
``$OTE_PARTIAL_PATH`` via :func:`write_partial`. If the subprocess later
times out or crashes, :class:`app.pipeline.isolation.SubprocessStage` falls
back to the last partial snapshot so already-processed pages aren't lost.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Dict


def run_worker(work: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = work(payload)
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)

    out_path = os.environ.get("OTE_RESULT_PATH")
    if not out_path:
        sys.stderr.write("OTE_RESULT_PATH not set\n")
        sys.exit(3)
    with open(out_path, "w") as f:
        json.dump(result, f)


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

_PROGRESS_START_TS = time.time()


def write_progress(current: int, total: int, status: str = "running", **extras: Any) -> None:
    """Best-effort write of a tiny progress record.

    Called by page-loop workers at the top of each page iteration. ``current``
    is 1-indexed (page 1 of N). ``status`` is ``"running" | "done" | "error"``.
    Extra kwargs are merged into the JSON so workers can surface
    backend-specific tags (e.g. ``ocr_backend="tesseract"``).

    Writes are atomic (write tmp + rename) so the parent never reads a torn
    JSON. Silent no-op if ``OTE_PROGRESS_PATH`` is unset (e.g. running a
    worker outside the harness).
    """
    out_path = os.environ.get("OTE_PROGRESS_PATH")
    if not out_path:
        return
    payload = {
        "current_page": int(current),
        "total_pages": int(total),
        "status": status,
        "elapsed_sec": round(time.time() - _PROGRESS_START_TS, 2),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **extras,
    }
    tmp = f"{out_path}.tmp"
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, out_path)
    except Exception:  # noqa: BLE001
        # Progress is best-effort — never let it break a real run.
        try:
            os.unlink(tmp)
        except OSError:
            pass


def write_partial(partial_result: Dict[str, Any]) -> None:
    """Atomically persist an incremental snapshot of the worker's result.

    Called by page-loop workers after each page completes so that, if the
    subprocess later times out or crashes, the parent process can recover
    everything that finished. Silent no-op when ``OTE_PARTIAL_PATH`` is
    unset.

    Workers typically pass the same dict they'd eventually return from
    ``work(payload)`` — with the ``pages`` list growing per iteration.
    """
    out_path = os.environ.get("OTE_PARTIAL_PATH")
    if not out_path:
        return
    tmp = f"{out_path}.tmp"
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(partial_result, f)
        os.replace(tmp, out_path)
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp)
        except OSError:
            pass
