"""RunContext + AuditRecorder shared by every stage in a single solution run."""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from app.core.schemas import AuditStep, PdfKind, StageStatus


@dataclass
class AuditRecorder:
    steps: List[AuditStep] = field(default_factory=list)
    _order: int = 0

    def add(self, step: AuditStep) -> None:
        self.steps.append(step)

    @contextmanager
    def time(
        self,
        stage_name: str,
        tool: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        inputs: Optional[List[str]] = None,
    ) -> Iterator["_AuditHandle"]:
        self._order += 1
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        handle = _AuditHandle(stage_name=stage_name, tool=tool, inputs=list(inputs or []))
        try:
            yield handle
            status: StageStatus = handle.status or "ok"
            message = handle.message
        except Exception as exc:  # noqa: BLE001
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            self.add(
                AuditStep(
                    stage_name=stage_name,
                    tool=tool,
                    order=self._order,
                    started_at=started,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    params=params or {},
                    inputs=handle.inputs,
                    outputs=handle.outputs,
                    status=status,
                    message=message,
                    usage=handle.usage,
                )
            )
            raise
        self.add(
            AuditStep(
                stage_name=stage_name,
                tool=tool,
                order=self._order,
                started_at=started,
                duration_ms=(time.perf_counter() - t0) * 1000,
                params=params or {},
                inputs=handle.inputs,
                outputs=handle.outputs,
                status=status,
                message=message,
                usage=handle.usage,
            )
        )


@dataclass
class _AuditHandle:
    stage_name: str
    tool: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    status: Optional[StageStatus] = None
    message: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)

    def add_output(self, artifact_id: str) -> None:
        self.outputs.append(artifact_id)

    def add_input(self, artifact_id: str) -> None:
        self.inputs.append(artifact_id)

    def skipped(self, reason: str) -> None:
        self.status = "skipped"
        self.message = reason


@dataclass
class RunContext:
    """Per-(run, solution) workspace.

    Each solution gets its own artifacts dir under
    ``storage/runs/<run_id>/<solution>/artifacts/``. Artifact ids are
    deterministic-ish (``<solution>:<basename>``) so the report can link to them.
    """

    run_id: str
    solution_name: str
    document_id: str
    pdf_path: Path
    artifacts_dir: Path
    pdf_kind: PdfKind
    n_pages: int
    dpi: int
    audit: AuditRecorder = field(default_factory=AuditRecorder)
    page_images: Dict[int, Path] = field(default_factory=dict)
    # Pages the runner has marked as "already done" — populated on resume so
    # expensive SubprocessStage workers can skip them. ``page_images`` itself
    # stays complete (one entry per rasterised page) because in-process stages
    # like PresidioPII look up ``page_images[idx]`` directly while iterating
    # ``state.pages``; emptying those entries would break them.
    skip_pages: set = field(default_factory=set)
    params: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)
    current_handle: Optional["_AuditHandle"] = field(default=None, repr=False)

    @classmethod
    def new(
        cls,
        *,
        run_id: str,
        solution_name: str,
        document_id: str,
        pdf_path: Path,
        runs_dir: Path,
        pdf_kind: PdfKind,
        n_pages: int,
        dpi: int,
    ) -> "RunContext":
        art = runs_dir / run_id / solution_name / "artifacts"
        art.mkdir(parents=True, exist_ok=True)
        return cls(
            run_id=run_id,
            solution_name=solution_name,
            document_id=document_id,
            pdf_path=pdf_path,
            artifacts_dir=art,
            pdf_kind=pdf_kind,
            n_pages=n_pages,
            dpi=dpi,
        )

    def artifact_id(self, name: str) -> str:
        return f"{self.solution_name}:{name}"

    def save_bytes(self, name: str, data: bytes) -> str:
        path = self.artifacts_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.artifact_id(name)

    def save_text(self, name: str, text: str) -> str:
        path = self.artifacts_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return self.artifact_id(name)

    def save_json(self, name: str, obj: Any) -> str:
        return self.save_text(name, json.dumps(obj, indent=2, default=str))

    def artifact_path(self, name: str) -> Path:
        return self.artifacts_dir / name


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]
