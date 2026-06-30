"""Run lifecycle: POST /runs enqueues; GET streams partial results."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from app import document_store, run_store
from app.config import settings
from app.pipeline import base
from app.pipeline.runner import run_solution
from app.pipeline.scheduler import compute_solution_concurrency

logger = logging.getLogger("ote.runs")
router = APIRouter(prefix="/runs", tags=["runs"])


class RunRequest(BaseModel):
    document_id: str
    solution_names: List[str]
    dpi: Optional[int] = None


# --- per-solution log capture ----------------------------------------------

_LOG_FMT = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s", "%H:%M:%S")


class _ThreadNameFilter(logging.Filter):
    def __init__(self, thread_name: str) -> None:
        super().__init__()
        self._name = thread_name

    def filter(self, record: logging.LogRecord) -> bool:
        return record.threadName == self._name


def _attach_solution_log(run_id: str, solution_name: str, thread_name: str) -> logging.FileHandler:
    log_path = run_store.solution_log_path(run_id, solution_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_LOG_FMT)
    handler.addFilter(_ThreadNameFilter(thread_name))
    logging.getLogger("ote").addHandler(handler)
    return handler


def _detach_log(handler: logging.FileHandler) -> None:
    logging.getLogger("ote").removeHandler(handler)
    handler.close()


# --- routes -----------------------------------------------------------------


@router.get("")
def list_runs(limit: int = 50):
    return {"runs": run_store.list_runs(limit=limit)}


@router.post("")
def create_run(req: RunRequest, background_tasks: BackgroundTasks):
    try:
        meta = document_store.get_document_meta(req.document_id)
    except FileNotFoundError:
        raise HTTPException(404, f"document not found: {req.document_id}")
    missing = [n for n in req.solution_names if n not in base.registered()]
    if missing:
        raise HTTPException(400, f"unknown solutions: {missing}")

    run_id = uuid.uuid4().hex[:12]
    document = document_store.empty_document_result(req.document_id)
    run_store.init_run(run_id, document, req.solution_names)
    dpi = req.dpi or settings.default_dpi

    background_tasks.add_task(
        _execute_run,
        run_id=run_id,
        document_id=req.document_id,
        pdf_path_str=meta["path"],
        pdf_kind=meta["pdf_kind"],
        n_pages=meta["n_pages"],
        solution_names=req.solution_names,
        dpi=dpi,
    )
    return {"run_id": run_id, "status": "running", "document_id": req.document_id}


def _execute_run(
    *,
    run_id: str,
    document_id: str,
    pdf_path_str: str,
    pdf_kind: str,
    n_pages: int,
    solution_names: List[str],
    dpi: int,
) -> None:
    pdf_path = Path(pdf_path_str)
    n_concurrent, reason = compute_solution_concurrency(len(solution_names))
    logger.info(
        "run %s: %d solutions, %d at a time (%s)",
        run_id, len(solution_names), n_concurrent, reason,
    )

    def _one(name: str) -> None:
        sol = base.get(name)
        tname = f"run-{run_id}-{name}"
        # ThreadPoolExecutor threads have generated names — rename for the
        # log-filter to keep per-solution log isolation working.
        import threading as _threading
        _threading.current_thread().name = tname
        handler = _attach_solution_log(run_id, sol.name, tname)
        run_store.mark_solution(run_id, sol.name, "running", started_at=run_store._now_iso())
        logger.info("solution %s: started", sol.name)
        try:
            result = run_solution(
                solution=sol,
                run_id=run_id,
                document_id=document_id,
                pdf_path=pdf_path,
                pdf_kind=pdf_kind,  # type: ignore[arg-type]
                n_pages=n_pages,
                runs_dir=settings.runs_path,
                dpi=dpi,
            )
            logger.info(
                "solution %s: finished status=%s conf=%.3f ms=%.0f",
                sol.name, result.status, result.overall_confidence, result.timings.total_ms,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("solution %s crashed", sol.name)
            from app.core.schemas import SolutionResult

            result = SolutionResult(
                solution_name=sol.name, status="error", error=f"{type(exc).__name__}: {exc}"
            )
        finally:
            _detach_log(handler)
        run_store.write_solution(run_id, result)

    with ThreadPoolExecutor(max_workers=n_concurrent, thread_name_prefix=f"sol-{run_id[:6]}") as pool:
        futures = [pool.submit(_one, name) for name in solution_names]
        for f in futures:
            try:
                f.result()
            except Exception:  # noqa: BLE001
                logger.exception("solution task failed")


class ResumeRequest(BaseModel):
    """Optional filter for which solutions to resume.

    When ``solution_names`` is provided the resume only touches that subset
    (after intersecting it with the set of solutions that actually look
    incomplete). Pass a single name to drive the per-card Resume button on
    the run dashboard.
    """

    solution_names: Optional[List[str]] = None


def _is_incomplete(entry: dict) -> bool:
    """Internal-result inspection used by the Resume button visibility +
    the per-card eligibility check."""
    if entry.get("state") in ("error", "partial"):
        return True
    if entry.get("result_status") in ("error", "partial"):
        return True
    if entry.get("state") not in ("done", "skipped"):
        return True
    # Safety net — solution reported done but ran short of the page count.
    n_done = entry.get("n_pages_done")
    n_expected = entry.get("n_pages_expected")
    if (
        isinstance(n_done, int)
        and isinstance(n_expected, int)
        and n_expected > 0
        and n_done < n_expected
    ):
        return True
    return False


@router.post("/{run_id}/resume")
def resume_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    req: Optional[ResumeRequest] = None,
):
    """Re-run incomplete solutions on the SAME ``run_id``.

    Eligibility (per solution):
      - state in {error, partial} or result_status in {error, partial}
      - OR state is something other than done/skipped (e.g. pending/running stragglers)
      - OR n_pages_done < n_pages_expected (safety net for silently-truncated runs)

    Optional ``solution_names`` in the body narrows the resume to a subset —
    e.g. one specific card's Resume button sends ``{"solution_names": ["x"]}``.
    Solutions that pass the eligibility filter and are in scope get re-queued;
    everything else is left alone.

    Solutions that finished cleanly are left alone. Resume restarts each
    targeted solution from scratch — the existing pages get overwritten by
    the new run. For an explicit full re-execution use the ``re-run`` button
    (which creates a fresh ``run_id``).
    """
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")

    document = state.get("document") or {}
    document_id = document.get("document_id")
    if not document_id:
        raise HTTPException(400, "run has no document_id")
    try:
        meta = document_store.get_document_meta(document_id)
    except FileNotFoundError:
        raise HTTPException(404, f"document not found: {document_id}")

    solution_status = state.get("solution_status") or {}
    filter_set: Optional[set[str]] = set(req.solution_names) if req and req.solution_names else None
    failed: List[str] = []
    for name in state.get("solution_names") or []:
        if filter_set is not None and name not in filter_set:
            continue
        entry = solution_status.get(name) or {}
        if _is_incomplete(entry):
            failed.append(name)
    if not failed:
        raise HTTPException(
            400,
            "no failed or partial solutions to resume"
            + (f" in the requested subset {sorted(filter_set)}" if filter_set else ""),
        )

    # Reset their solution_status entries so the UI shows "running" again.
    now = run_store._now_iso()
    for name in failed:
        run_store.mark_solution(run_id, name, "pending", queued_at=now, started_at=None, error=None)
    # Flip the top-level state back to running.
    with run_store._LOCK:
        latest = run_store._read_state(run_id)
        if latest is not None:
            latest["status"] = "running"
            latest["finished_at"] = None
            latest["completed"] = [n for n in (latest.get("completed") or []) if n not in failed]
            latest["updated_at"] = now
            run_store._write_state(run_id, latest)

    dpi = settings.default_dpi
    background_tasks.add_task(
        _execute_run,
        run_id=run_id,
        document_id=document_id,
        pdf_path_str=meta["path"],
        pdf_kind=meta["pdf_kind"],
        n_pages=meta["n_pages"],
        solution_names=failed,
        dpi=dpi,
    )
    return {
        "run_id": run_id,
        "status": "running",
        "resumed_solutions": failed,
        "kept_solutions": [n for n in state.get("solution_names") or [] if n not in failed],
    }


@router.get("/{run_id}")
def get_run(run_id: str):
    state = run_store.read_run(run_id)
    if state is None:
        # Run dir may exist but JSON not yet flushed (race between POST /runs and first poll).
        # Return a minimal pending state so the UI can start polling without a 500/404 flash.
        d = run_store.run_dir(run_id)
        if d.exists():
            return {"run_id": run_id, "status": "pending", "solution_names": [], "completed": [], "solution_results": [], "solution_status": {}, "document": {"document_id": "", "filename": "", "pdf_kind": "unknown", "n_pages": 0}}
        raise HTTPException(404, f"run not found: {run_id}")

    # Attach live per-page progress for any solution still running. Workers
    # write progress.json under <run>/<solution>/artifacts/<stage>/progress.json
    # — we glob for it because the stage name varies per solution.
    try:
        sol_status = state.get("solution_status") or {}
        for sol_name, entry in sol_status.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("state") != "running":
                continue
            sol_dir = run_store.run_dir(run_id) / sol_name / "artifacts"
            if not sol_dir.exists():
                continue
            # Pick the most-recently-modified progress.json — the last stage
            # to write is the active one.
            latest = None
            latest_mtime = -1.0
            for p in sol_dir.rglob("progress.json"):
                try:
                    m = p.stat().st_mtime
                except OSError:
                    continue
                if m > latest_mtime:
                    latest = p
                    latest_mtime = m
            if latest is None:
                continue
            try:
                import json as _json
                entry["progress"] = _json.loads(latest.read_text())
            except Exception:  # noqa: BLE001
                # Torn read or stale file — skip silently.
                pass
    except Exception:  # noqa: BLE001
        logger.exception("progress attach failed for run %s", run_id)

    return state


@router.delete("/{run_id}")
def delete_run(run_id: str):
    """Delete a run and all its artifacts from disk."""
    import shutil
    d = run_store.run_dir(run_id)
    if not d.exists():
        raise HTTPException(404, f"run not found: {run_id}")
    shutil.rmtree(d)
    return {"deleted": run_id}


@router.get("/{run_id}/solutions/{name}")
def get_run_solution(run_id: str, name: str):
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    for r in state["solution_results"]:
        if r["solution_name"] == name:
            return r
    raise HTTPException(404, f"solution {name} not in run {run_id}")


@router.get("/{run_id}/solutions/{name}/log", response_class=PlainTextResponse)
def get_solution_log(run_id: str, name: str):
    log_path = run_store.solution_log_path(run_id, name)
    if not log_path.exists():
        raise HTTPException(404, f"no log yet for {name}")
    return log_path.read_text()


@router.get("/{run_id}/audit")
def get_run_audit(run_id: str):
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    timeline = []
    for r in state["solution_results"]:
        for step in r.get("audit", []):
            timeline.append({**step, "solution": r["solution_name"]})
    timeline.sort(key=lambda s: (s["solution"], s["order"]))
    return {"audit": timeline}


@router.get("/{run_id}/artifacts/{artifact_id:path}")
def get_artifact(run_id: str, artifact_id: str):
    path = run_store.list_artifact(run_id, artifact_id)
    if path is None:
        raise HTTPException(404, f"artifact not found: {artifact_id}")
    media = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
    return FileResponse(path, media_type=media)


@router.get("/{run_id}/solutions/{name}/pii")
def get_solution_pii(run_id: str, name: str):
    """Decrypt the Fernet token map for one solution and join in masked + entity info.

    Returns: `{tokens: [{token, entity, masked, original, n_occurrences, pages}], masked_pages: [{page_index, ref}]}`
    """
    import json
    from cryptography.fernet import Fernet

    from app.config import settings

    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    sol = next((r for r in state["solution_results"] if r["solution_name"] == name), None)
    if sol is None:
        raise HTTPException(404, f"solution {name} not in run {run_id}")

    map_artifact = f"{name}:pii/token-map.fernet"
    map_path = run_store.list_artifact(run_id, map_artifact)
    token_map: dict[str, str] = {}
    if map_path is not None:
        data = map_path.read_bytes()
        try:
            if settings.pii_mask_key:
                data = Fernet(settings.pii_mask_key.encode()).decrypt(data)
            token_map = json.loads(data.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not decrypt pii token map: %s", exc)

    occ: dict[str, dict] = {}
    for p in sol.get("pages") or []:
        for region in p.get("regions") or []:
            for span in region.get("pii_spans") or []:
                token = span.get("token") or ""
                entry = occ.setdefault(token, {
                    "token": token,
                    "entity": span.get("entity_type"),
                    "masked": span.get("masked_value"),
                    "original": token_map.get(token),
                    "n_occurrences": 0,
                    "pages": set(),
                })
                entry["n_occurrences"] += 1
                entry["pages"].add(p["page_index"])

    tokens = sorted(
        ({**v, "pages": sorted(v["pages"])} for v in occ.values()),
        key=lambda x: (-x["n_occurrences"], x["entity"] or ""),
    )

    masked_pages = []
    mock_redacted_pages: list[dict] = []
    for p in sol.get("pages") or []:
        idx = p["page_index"]
        rel = f"pii/page-{idx:03d}-masked.png"
        if run_store.list_artifact(run_id, f"{name}:{rel}") is not None:
            masked_pages.append({"page_index": idx, "ref": f"{name}:{rel}"})
        # New: same-length mock variants (clean + annotated). Emitted by the
        # PresidioPII stage's _emit_mock_variants bridge — feeds the new
        # run-dashboard card so the legacy flow has the same redacted-image
        # capability as the pii_v2 benchmark.
        clean_rel = f"pii/page-{idx:03d}-mock-redacted.png"
        annotated_rel = f"pii/page-{idx:03d}-mock-redacted-annotated.png"
        clean_exists = run_store.list_artifact(run_id, f"{name}:{clean_rel}") is not None
        annot_exists = run_store.list_artifact(run_id, f"{name}:{annotated_rel}") is not None
        if clean_exists or annot_exists:
            mock_redacted_pages.append({
                "page_index": idx,
                "clean_ref": f"{name}:{clean_rel}" if clean_exists else None,
                "annotated_ref": f"{name}:{annotated_rel}" if annot_exists else None,
            })

    # Plaintext mapping index (entity-type counts only). The ciphertext lives
    # at <run>/<name>/artifacts/pii/mock-mapping.fernet and is fetchable via
    # the existing artifacts route when the user wants to restore offline.
    mock_mapping_index = None
    mapping_idx_path = run_store.list_artifact(
        run_id, f"{name}:pii/mock-mapping.index.json",
    )
    if mapping_idx_path is not None:
        try:
            mock_mapping_index = json.loads(mapping_idx_path.read_text())
        except Exception:  # noqa: BLE001
            pass

    return {
        "tokens": tokens,
        "masked_pages": masked_pages,
        "mock_redacted_pages": mock_redacted_pages,
        "mock_mapping_index": mock_mapping_index,
        "mock_mapping_ref": f"{name}:pii/mock-mapping.fernet"
            if run_store.list_artifact(run_id, f"{name}:pii/mock-mapping.fernet") is not None
            else None,
    }


@router.get("/{run_id}/solutions/{name}/redacted-pdf")
def get_redacted_pdf(run_id: str, name: str):
    """Vector-safe redacted PDF download via PyMuPDF apply_redactions.

    For every region in this solution's pages that carries at least one
    ``pii_spans`` entry, we add a redact annot covering the region's bbox
    (scaled back from ``image_px@<dpi>`` to PDF points) and then call
    ``page.apply_redactions()`` — which physically removes the underlying text
    from the PDF stream. The output is a real PDF, not a rasterised PNG.

    Coarse-grained (region-level, not span-level) because regions are the unit
    that carries pii_spans in the legacy flow. Span-level char→pixel mapping
    lives in the pii_v2 track; if you want span-level redaction in a PDF,
    point this route at a pii_run instead of a /runs solution.
    """
    import fitz  # type: ignore

    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    sol = next((r for r in state["solution_results"] if r["solution_name"] == name), None)
    if sol is None:
        raise HTTPException(404, f"solution {name} not in run {run_id}")

    document_id = state.get("document", {}).get("document_id") or state.get("document_id")
    if not document_id:
        raise HTTPException(500, "document_id missing on run state")
    try:
        meta = document_store.get_document_meta(document_id)
    except FileNotFoundError:
        raise HTTPException(404, f"document not found: {document_id}")
    pdf_path = meta["path"]

    doc = fitz.open(pdf_path)
    try:
        n_redacted = 0
        for page_payload in sol.get("pages") or []:
            idx = int(page_payload.get("page_index", 0))
            if idx >= doc.page_count:
                continue
            dpi = int(page_payload.get("dpi", 200))
            scale = 72.0 / dpi  # image_px → PDF points
            page = doc[idx]
            for region in page_payload.get("regions") or []:
                if not (region.get("pii_spans") or []):
                    continue
                bbox = region.get("bbox") or {}
                x = float(bbox.get("x", 0)) * scale
                y = float(bbox.get("y", 0)) * scale
                w = float(bbox.get("w", 0)) * scale
                h = float(bbox.get("h", 0)) * scale
                if w <= 0 or h <= 0:
                    continue
                # fill=None → no visible rectangle painted; the underlying
                # background graphics (lines, fills, watermarks) stay in place.
                # apply_redactions(images=0, graphics=0, text=0) erases just
                # the text glyphs that fall inside the rect.
                page.add_redact_annot(fitz.Rect(x, y, x + w, y + h), fill=None)
                n_redacted += 1
            if n_redacted:
                page.apply_redactions(images=0, graphics=0, text=0)
        if n_redacted == 0:
            raise HTTPException(404, "no PII regions detected for this solution")
        buf = doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()

    return Response(
        content=buf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{document_id}-{name}-redacted.pdf"',
            "X-Redacted-Regions": str(n_redacted),
        },
    )


@router.get("/{run_id}/solutions/{name}/table-crops")
def get_table_crops(run_id: str, name: str):
    """Return crop artifact refs grouped by page for plain and obfuscated table images."""
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    sol = next((r for r in state["solution_results"] if r["solution_name"] == name), None)
    if sol is None:
        raise HTTPException(404, f"solution {name} not in run {run_id}")

    crops = []
    for p in sol.get("pages") or []:
        idx = p["page_index"]
        custom_tables = p.get("custom_tables") or []
        tables = p.get("tables") or []

        def _table_for(k: int) -> dict:
            if k < len(custom_tables):
                return custom_tables[k]
            i = k - len(custom_tables)
            return tables[i] if i < len(tables) else {}

        for k, ref in enumerate(p.get("table_crop_refs") or []):
            t = _table_for(k)
            crops.append({
                "page_index": idx, "kind": "plain", "ref": ref,
                "n_rows": t.get("n_rows", 0), "n_cols": t.get("n_cols", 0),
                "cells": t.get("cells") or [],
            })
        for k, ref in enumerate(p.get("table_obfuscated_refs") or []):
            t = _table_for(k)
            crops.append({
                "page_index": idx, "kind": "obfuscated", "ref": ref,
                "n_rows": t.get("n_rows", 0), "n_cols": t.get("n_cols", 0),
                "cells": t.get("cells") or [],
            })

    return {"crops": crops}
