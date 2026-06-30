"""Subprocess isolation for heavy / native-lib stages.

A native crash in paddlepaddle or torch must not kill FastAPI. Each isolated stage
spawns a fresh ``python -m <worker_module>`` process, hands it the page-image
paths + params over stdin (JSON), and reads back a JSON result. The parent
process is the only one touching Pydantic models.

Worker contract (every ``app.workers.<name>`` module):

    if __name__ == "__main__":
        import json, sys
        payload = json.loads(sys.stdin.read())
        result = work(payload)
        sys.stdout.write(json.dumps(result))

The payload schema is whatever the subclass sends. The expected result schema is::

    {
      "pages": [
        {
          "page_index": int,
          "regions": [ {<Region.model_dump()>}, ... ],
          "tables": [ {<TableModel.model_dump(), with cells>}, ... ],
          "full_text": "..."          # optional
        }
      ]
    }
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.schemas import BBox, PiiSpan, Region, RegionType, TableCell, TableModel
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.pipeline.isolation")


class SubprocessStageError(RuntimeError):
    """Raised when the worker subprocess crashes or returns non-JSON."""


@dataclass
class SubprocessStage:
    """Base for stages that must run in a subprocess.

    Subclasses provide ``worker_module`` (importable path that has a ``__main__``)
    and override :meth:`build_payload` / :meth:`apply_result` to translate.
    """

    name: str = "subprocess"
    tool: str = "subprocess"
    worker_module: str = ""
    timeout_sec: float = 600.0
    extra_env: Dict[str, str] = field(default_factory=dict)
    # 0 = send all pages in one subprocess call (current behaviour).
    # >0 = chunk pages into N-page subprocess invocations. The model reloads
    # between chunks but per-chunk peak RAM stays bounded — useful for
    # very long PDFs where per-page intermediates accumulate.
    pages_per_chunk: int = 0

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        if not self.worker_module:
            raise SubprocessStageError("worker_module must be set on the subclass")

        # On resume the runner records already-completed page indices in
        # ``ctx.skip_pages`` so heavy subprocess workers don't waste time
        # re-OCRing them. ``ctx.page_images`` stays complete (in-process
        # stages need it) — we just drop the skip-set from this stage's
        # work list.
        skip = set(ctx.skip_pages or ())
        all_indices = [i for i in sorted(ctx.page_images.keys()) if i not in skip]

        if not all_indices:
            logger.info(
                "%s: all pages already completed (resume) — skipping subprocess",
                self.name,
            )
            return state

        if self.pages_per_chunk and self.pages_per_chunk > 0 and len(all_indices) > self.pages_per_chunk:
            chunks: List[List[int]] = [
                all_indices[i : i + self.pages_per_chunk]
                for i in range(0, len(all_indices), self.pages_per_chunk)
            ]
        else:
            chunks = [all_indices]

        for chunk_idx, page_subset in enumerate(chunks):
            self._run_chunk(ctx, state, page_subset, chunk_idx, len(chunks))

        return state

    def _run_chunk(
        self,
        ctx: RunContext,
        state: RunState,
        page_subset: List[int],
        chunk_idx: int,
        n_chunks: int,
    ) -> None:
        """Run the worker subprocess for one page subset."""
        # Build a per-chunk payload by overriding ctx.page_images with the
        # subset. build_payload reads from ctx.page_images so we restore
        # afterwards.
        original_images = ctx.page_images
        ctx.page_images = {idx: original_images[idx] for idx in page_subset}
        try:
            payload = self.build_payload(ctx, state)
            # Hand the worker the total page count so the progress JSON it
            # writes can render "page 3 / 10" rather than "page 3 / 2"
            # when chunking is active.
            payload["__progress_total"] = len(original_images)
            payload["__progress_offset"] = sum(len(c) for c in [[idx for idx in original_images if idx < page_subset[0]]] if page_subset)
        finally:
            ctx.page_images = original_images

        suffix = "" if n_chunks == 1 else f".chunk{chunk_idx}"
        ctx.save_json(f"{self.name}/request{suffix}.json", payload)

        # Workers write the result JSON to OTE_RESULT_PATH so that anything
        # else they (or their child processes) emit to stdout is irrelevant.
        result_path = ctx.artifact_path(f"{self.name}/result{suffix}.json")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        if result_path.exists():
            result_path.unlink()
        # Progress file is shared across chunks for a single (stage, run) so
        # the UI sees a continuously-advancing counter.
        progress_path = ctx.artifact_path(f"{self.name}/progress.json")
        # Page-loop workers stream incremental snapshots here so a timeout /
        # crash mid-loop doesn't waste the already-processed pages.
        partial_path = ctx.artifact_path(f"{self.name}/result{suffix}.partial.json")
        if partial_path.exists():
            partial_path.unlink()

        env = {
            **os.environ,
            **self.extra_env,
            "OTE_RESULT_PATH": str(result_path),
            "OTE_PROGRESS_PATH": str(progress_path),
            "OTE_PARTIAL_PATH": str(partial_path),
        }
        timed_out = False
        try:
            proc = subprocess.run(
                [sys.executable, "-m", self.worker_module],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=env,
                cwd=str(_repo_backend_root()),
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            proc_returncode = -1
            proc_stdout = exc.stdout if isinstance(exc.stdout, str) else (
                exc.stdout.decode("utf-8", "replace") if exc.stdout else ""
            )
            proc_stderr = exc.stderr if isinstance(exc.stderr, str) else (
                exc.stderr.decode("utf-8", "replace") if exc.stderr else ""
            )
        else:
            proc_returncode = proc.returncode
            proc_stdout = proc.stdout
            proc_stderr = proc.stderr

        if proc_stdout:
            ctx.save_text(f"{self.name}/stdout{suffix}.log", proc_stdout)
        stderr_artifact_id: Optional[str] = None
        if proc_stderr:
            stderr_artifact_id = ctx.save_text(f"{self.name}/stderr{suffix}.log", proc_stderr)

        # Recovery: on timeout OR non-zero exit, if the worker streamed a
        # partial result before dying, treat that as a successful "partial"
        # result. This means pages processed before the failure stay in the
        # final SolutionResult instead of being thrown away.
        if (timed_out or proc_returncode != 0) and partial_path.exists():
            try:
                partial_result = json.loads(partial_path.read_text())
                partial_result.setdefault("partial", True)
                logger.warning(
                    "worker %s %s (returncode=%s) — recovering partial result with %d pages",
                    self.worker_module,
                    "timed out" if timed_out else "exited",
                    proc_returncode,
                    len(partial_result.get("pages") or []),
                )
                self.apply_result(ctx, state, partial_result)
                # Signal partial recovery to the runner. The runner promotes
                # the SolutionResult.status to "partial" so the dashboard
                # shows a Resume button instead of pretending the run was
                # clean.
                partial_stages = state.extras.setdefault("partial_stages", [])
                reason = "timeout" if timed_out else f"exit {proc_returncode}"
                partial_stages.append({
                    "stage_name": self.name,
                    "worker_module": self.worker_module,
                    "reason": reason,
                    "recovered_pages": len(partial_result.get("pages") or []),
                })
                return
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("partial recovery failed for %s: %s", self.worker_module, exc)

        if timed_out:
            err_suffix = f" (see {stderr_artifact_id})" if stderr_artifact_id else ""
            raise SubprocessStageError(
                f"worker {self.worker_module} timed out after {self.timeout_sec}s{err_suffix}"
            )
        if proc_returncode != 0:
            tail = _summarize_error(proc_stderr)
            err_suffix = f" (see {stderr_artifact_id})" if stderr_artifact_id else ""
            hint = _exit_hint(proc_returncode)
            raise SubprocessStageError(
                f"worker {self.worker_module} exited {proc_returncode}{hint}: {tail}{err_suffix}"
            )
        if not result_path.exists():
            raise SubprocessStageError(
                f"worker {self.worker_module} did not write OTE_RESULT_PATH"
            )
        try:
            result = json.loads(result_path.read_text())
        except json.JSONDecodeError as exc:
            raise SubprocessStageError(
                f"worker {self.worker_module} wrote non-JSON result: {exc}"
            ) from exc

        self.apply_result(ctx, state, result)

        # Mark progress done when the last chunk finishes.
        if chunk_idx == n_chunks - 1:
            try:
                from app.workers._io import write_progress  # noqa: F401 — sanity check
                # Parent-side completion sentinel; workers write per-page,
                # we just confirm the "done" status at chunk end.
                if progress_path.exists():
                    blob = json.loads(progress_path.read_text())
                    blob["status"] = "done"
                    progress_path.write_text(json.dumps(blob))
            except Exception:  # noqa: BLE001
                pass

    # ----- subclass hooks --------------------------------------------------

    def build_payload(self, ctx: RunContext, state: RunState) -> Dict[str, Any]:
        return {
            "pdf_path": str(ctx.pdf_path),
            "pages": {
                idx: {
                    "image_path": str(path),
                    "width": state.pages[idx].width,
                    "height": state.pages[idx].height,
                    "dpi": state.pages[idx].dpi,
                }
                for idx, path in ctx.page_images.items()
            },
            "pdf_kind": ctx.pdf_kind,
        }

    def apply_result(self, ctx: RunContext, state: RunState, result: Dict[str, Any]) -> None:
        """Default merger: deserialize Regions/Tables and append to matching pages."""
        for page_dict in result.get("pages", []) or []:
            idx = int(page_dict.get("page_index", 0))
            if idx not in state.pages:
                continue
            page = state.pages[idx]
            for r in page_dict.get("regions", []) or []:
                page.regions.append(_region_from_dict(r))
            for t in page_dict.get("tables", []) or []:
                page.tables.append(_table_from_dict(t))
            full_text = page_dict.get("full_text")
            if full_text:
                page.full_text = (page.full_text + "\n" + full_text).strip() if page.full_text else full_text
        failures = result.get("failures") or []
        if failures:
            ctx.save_json(f"{self.name}/failures.json", failures)
            state.extras.setdefault("worker_failures", {})[self.name] = failures


def _repo_backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _summarize_error(stderr: str) -> str:
    """Pull the last non-empty line out of a Python traceback for a one-liner."""
    lines = [ln for ln in (stderr or "").splitlines() if ln.strip()]
    if not lines:
        return "(no stderr)"
    return lines[-1][:300]


def _exit_hint(rc: int) -> str:
    """Translate negative POSIX exit codes (signal numbers) into a hint."""
    if rc >= 0:
        return ""
    sig = -rc
    hints = {
        5: " (SIGTRAP — native library hit a debug-trap, usually thread-pool contention or an assertion on Apple Silicon; the stage pins OMP/MKL/OpenBLAS to 1 thread, but if it still trips, try `arch -x86_64` or upgrading paddle/torch.)",
        6: " (SIGABRT — abort, often C++ assertion in a native library.)",
        7: " (SIGBUS — memory access error in a native library.)",
        9: " (SIGKILL — process killed; on macOS this is almost always the OOM killer. Free RAM and retry, or disable heavy optional models for this solution.)",
        11: " (SIGSEGV — segmentation fault in a native library.)",
        15: " (SIGTERM — process terminated externally.)",
    }
    return hints.get(sig, f" (signal {sig})")


# --- deserializers (parent-side; workers emit plain dicts) -------------------


def _region_from_dict(d: Dict[str, Any]) -> Region:
    b = d.get("bbox") or {}
    type_lookup = {t.value for t in RegionType}
    rtype = d.get("type", "unknown")
    if rtype not in type_lookup:
        rtype = "unknown"
    bbox = BBox(
        x=float(b.get("x", 0)),
        y=float(b.get("y", 0)),
        w=float(b.get("w", 0)),
        h=float(b.get("h", 0)),
        page_index=int(b.get("page_index", 0)),
        coord_space=str(b.get("coord_space", "image_px@300")),
    )
    pii = [
        PiiSpan(
            entity_type=str(p.get("entity_type", "")),
            start=int(p.get("start", 0)),
            end=int(p.get("end", 0)),
            score=float(p.get("score", 0.0)),
            masked_value=str(p.get("masked_value", "")),
            bbox=_bbox_or_none(p.get("bbox")),
            token=p.get("token"),
        )
        for p in d.get("pii_spans", []) or []
    ]
    return Region(
        id=str(d.get("id") or uuid.uuid4().hex[:10]),
        type=RegionType(rtype),
        bbox=bbox,
        text=str(d.get("text", "")),
        confidence=float(d.get("confidence", 0.0)),
        raw_confidence=d.get("raw_confidence"),
        source_tool=str(d.get("source_tool", "")),
        parent_id=d.get("parent_id"),
        attributes=d.get("attributes") or {},
        artifact_refs=d.get("artifact_refs") or [],
        pii_spans=pii,
    )


def _bbox_or_none(b: Optional[Dict[str, Any]]) -> Optional[BBox]:
    if not b:
        return None
    return BBox(
        x=float(b.get("x", 0)),
        y=float(b.get("y", 0)),
        w=float(b.get("w", 0)),
        h=float(b.get("h", 0)),
        page_index=int(b.get("page_index", 0)),
        coord_space=str(b.get("coord_space", "image_px@300")),
    )


def _table_from_dict(d: Dict[str, Any]) -> TableModel:
    cells: List[TableCell] = []
    for c in d.get("cells", []) or []:
        cells.append(
            TableCell(
                row=int(c.get("row", 0)),
                col=int(c.get("col", 0)),
                rowspan=int(c.get("rowspan", 1)),
                colspan=int(c.get("colspan", 1)),
                text=str(c.get("text", "")),
                bbox=_bbox_or_none(c.get("bbox")),
                multiline=bool(c.get("multiline", False)),
                confidence=c.get("confidence"),
            )
        )
    return TableModel(
        region_id=str(d.get("region_id") or uuid.uuid4().hex[:10]),
        orientation=d.get("orientation", "horizontal"),
        border_mode=d.get("border_mode", "unknown"),
        n_rows=int(d.get("n_rows", 0)),
        n_cols=int(d.get("n_cols", 0)),
        cells=cells,
        html=d.get("html"),
    )
