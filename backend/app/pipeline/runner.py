"""Execute a single Solution against a single document."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from app.core import confidence as conf_mod
from app.core.rasterize import rasterize_pdf
from app.core.schemas import PdfKind, SolutionResult, SolutionStatus, SolutionTimings
from app.pipeline.base import RunState, Solution
from app.pipeline.context import RunContext
from app.workflow import db as wfdb
from app.workflow.engine import OTEWorkflowEngine

logger = logging.getLogger("ote.runner")


def _snapshot_partial_result(
    *,
    solution_name: str,
    ctx: RunContext,
    state: RunState,
    last_stage: str,
    started_at: float,
) -> None:
    """Persist a partial SolutionResult to ``runs/<run_id>/<solution>/result.json``.

    Called after every stage succeeds so the UI sees per-page output stream in
    — and so a timeout / crash in a later stage doesn't waste the already-
    completed work.
    """
    try:
        pages = [state.pages[i] for i in sorted(state.pages.keys())]
        partial = SolutionResult(
            solution_name=solution_name,
            status="partial",
            pages=pages,
            audit=list(ctx.audit.steps),
            timings=SolutionTimings(
                total_ms=(time.perf_counter() - started_at) * 1000,
                by_stage={s.stage_name: s.duration_ms for s in ctx.audit.steps},
            ),
            artifacts_dir=str(ctx.artifacts_dir),
        )
        conf_mod.attach_overall(partial)
        target = ctx.artifacts_dir.parent / "result.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(partial.model_dump_json(indent=2))
    except Exception:  # noqa: BLE001
        logger.exception("partial snapshot failed after stage=%s", last_stage)


def run_solution(
    *,
    solution: Solution,
    run_id: str,
    document_id: str,
    pdf_path: Path,
    pdf_kind: PdfKind,
    n_pages: int,
    runs_dir: Path,
    dpi: int,
) -> SolutionResult:
    """Run every stage of ``solution`` against the given PDF.

    A solution that doesn't support ``pdf_kind`` is skipped with a reason and
    returns an empty SolutionResult — never silently empty success.
    """
    if not solution.supports(pdf_kind):
        return SolutionResult(
            solution_name=solution.name,
            status="skipped",
            skipped_reason=(
                f"solution does not support pdf_kind={pdf_kind} "
                f"(supported: {sorted(solution.supported_kinds)})"
            ),
        )

    ctx = RunContext.new(
        run_id=run_id,
        solution_name=solution.name,
        document_id=document_id,
        pdf_path=pdf_path,
        runs_dir=runs_dir,
        pdf_kind=pdf_kind,
        n_pages=n_pages,
        dpi=dpi,
    )

    raster_dir = ctx.artifacts_dir / "pages"
    rasters = rasterize_pdf(pdf_path, raster_dir, dpi=dpi)

    # Resume detection: if a result.json from a previous run of this exact
    # (run_id, solution) is still on disk, pre-populate state.pages from it
    # so the new pass only re-processes the missing pages. This is what
    # makes "Resume" actually a resume and not a full re-execution.
    state = RunState()
    existing_pages: set[int] = set()
    existing_result_path = ctx.artifacts_dir.parent / "result.json"
    if existing_result_path.exists():
        try:
            from app.core.schemas import PageResult
            existing_data = json.loads(existing_result_path.read_text())
            for p_dict in (existing_data.get("pages") or []):
                try:
                    page = PageResult.model_validate(p_dict)
                except Exception:
                    continue
                state.pages[page.page_index] = page
                existing_pages.add(page.page_index)
        except Exception:  # noqa: BLE001
            logger.exception("could not read existing result.json for resume on %s", solution.name)

    # Always register every rasterised page in ``ctx.page_images`` — many
    # in-process stages (e.g. PresidioPII) look up ``ctx.page_images[idx]``
    # directly while walking ``state.pages``. The resume signal goes through
    # ``ctx.skip_pages`` instead; SubprocessStage.build_payload filters the
    # payload by that set so heavy subprocess workers don't waste time on
    # already-completed pages.
    for r in rasters:
        ctx.page_images[r.page_index] = r.png_path
        page = state.page(r.page_index, w=r.width, h=r.height, dpi=r.dpi, pdf_kind=pdf_kind)
        if not page.page_image_ref:
            page.page_image_ref = ctx.artifact_id(f"pages/{r.png_path.name}")

    ctx.skip_pages.update(existing_pages)
    if existing_pages:
        n_remaining = max(0, n_pages - len(existing_pages))
        logger.info(
            "solution %s: resume mode — keeping %d completed page(s), %d remaining for subprocess stages",
            solution.name, len(existing_pages), n_remaining,
        )

    status: SolutionStatus = "ok"
    error: Optional[str] = None
    t0 = time.perf_counter()

    wfdb.init_db()

    def _on_stage_complete(stage_name: str, current_state: RunState) -> None:
        _snapshot_partial_result(
            solution_name=solution.name,
            ctx=ctx,
            state=current_state,
            last_stage=stage_name,
            started_at=t0,
        )

    try:
        state = OTEWorkflowEngine().run_solution(
            solution, ctx, state, on_stage_complete=_on_stage_complete,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow failed for solution %s", solution.name)
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        # Persist whatever stages already populated so the UI doesn't lose
        # them. The final result builder below also reads state.pages, but
        # this guarantees a result.json exists even if a downstream caller
        # (e.g. the routes layer) never calls write_solution.
        _snapshot_partial_result(
            solution_name=solution.name,
            ctx=ctx,
            state=state,
            last_stage="(crashed)",
            started_at=t0,
        )

    total_ms = (time.perf_counter() - t0) * 1000
    timings = SolutionTimings(
        total_ms=total_ms,
        by_stage={s.stage_name: s.duration_ms for s in ctx.audit.steps},
    )

    # If any stage recovered a partial result mid-execution (subprocess
    # timeout/crash but the worker streamed pages first), don't pretend the
    # solution succeeded cleanly. Promote to "partial" so the UI shows a
    # Resume button and the recovered pages still render.
    partial_stages = state.extras.get("partial_stages") or []
    if status == "ok" and partial_stages:
        status = "partial"
        if not error:
            stages = ", ".join(p.get("stage_name", "?") for p in partial_stages)
            error = f"partial recovery in stages: {stages}"

    # Safety net — even if no stage explicitly signalled partial recovery,
    # a successful-looking run that produced fewer pages than the document
    # has is *not* fully done. This catches in-process page-loop stages
    # (e.g., the tesseract baseline) that swallow per-page errors silently
    # and any future workers that forget to write_partial.
    n_done_pages = len(state.pages)
    if status == "ok" and n_pages > 0 and n_done_pages < n_pages:
        status = "partial"
        missing = sorted(set(range(n_pages)) - set(state.pages.keys()))
        if not error:
            preview = ", ".join(str(i + 1) for i in missing[:10])
            more = "" if len(missing) <= 10 else f", +{len(missing) - 10} more"
            error = f"{n_done_pages}/{n_pages} pages produced; missing pages: {preview}{more}"

    pages = [state.pages[i] for i in sorted(state.pages.keys())]
    result = SolutionResult(
        solution_name=solution.name,
        status=status,
        pages=pages,
        audit=list(ctx.audit.steps),
        timings=timings,
        artifacts_dir=str(ctx.artifacts_dir),
        error=error,
    )
    conf_mod.attach_overall(result)
    return result
