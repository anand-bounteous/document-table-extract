"""SpiffWorkflow BPMN execution engine for OTE solutions."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.camunda.parser.CamundaParser import CamundaParser
from SpiffWorkflow.task import TaskState

from app.workflow import db as wfdb

if TYPE_CHECKING:
    from app.pipeline.base import RunState, Solution
    from app.pipeline.context import RunContext

logger = logging.getLogger("ote.workflow")

BPMN_DIR = Path(__file__).parent.parent / "bpmn"


class OTEWorkflowEngine:
    """Execute a Solution's stages in BPMN order via SpiffWorkflow."""

    def run_solution(
        self,
        solution: "Solution",
        ctx: "RunContext",
        state: "RunState",
        on_stage_complete: "Callable[[str, RunState], None] | None" = None,
    ) -> "RunState":
        """Drive the SpiffWorkflow for ``solution``.

        ``on_stage_complete`` (if provided) is called after every stage
        succeeds. The runner uses this hook to persist partial SolutionResult
        snapshots so the UI sees per-page output as it streams in — and so
        that, on timeout/error mid-execution, the pages that completed are
        already on disk.
        """
        bpmn_path = BPMN_DIR / f"{solution.name}.bpmn"
        if not bpmn_path.exists():
            raise FileNotFoundError(f"BPMN not found: {bpmn_path}")

        parser = CamundaParser()
        parser.add_bpmn_file(str(bpmn_path))
        spec = parser.get_spec(solution.name)
        wf = BpmnWorkflow(spec)

        stage_map = {s.name: s for s in solution.stages}

        wfdb.start_run(ctx.run_id, solution.name)
        try:
            while not wf.is_completed():
                wf.do_engine_steps()
                for task in wf.get_tasks(state=TaskState.READY):
                    stage_name = task.task_spec.name
                    t_start = time.time()
                    if stage_name in stage_map:
                        stage = stage_map[stage_name]
                        try:
                            with ctx.audit.time(stage_name, getattr(stage, "tool", stage_name)) as handle:
                                ctx.current_handle = handle
                                state = stage.run(ctx, state)
                                ctx.current_handle = None
                            duration_ms = (time.time() - t_start) * 1000
                            wfdb.record_stage(ctx.run_id, solution.name, stage_name, "done", t_start, duration_ms)
                            if on_stage_complete is not None:
                                try:
                                    on_stage_complete(stage_name, state)
                                except Exception:  # noqa: BLE001
                                    # Progress callbacks must never break the run.
                                    logger.exception("on_stage_complete failed for %s", stage_name)
                        except Exception as exc:
                            ctx.current_handle = None
                            duration_ms = (time.time() - t_start) * 1000
                            wfdb.record_stage(
                                ctx.run_id, solution.name, stage_name, "error",
                                t_start, duration_ms, f"{type(exc).__name__}: {exc}",
                            )
                            wfdb.finish_run(ctx.run_id, solution.name, "error")
                            raise
                    task.complete()

            wfdb.finish_run(ctx.run_id, solution.name, "done")
        except Exception:
            wfdb.finish_run(ctx.run_id, solution.name, "error")
            raise

        return state
