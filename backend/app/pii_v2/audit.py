"""Audit recording for pii_v2 detectors.

Mirrors the shape of ``app.core.schemas.AuditStep`` so the frontend's
existing ``AuditTimeline`` component can render pii_v2 timelines without
modification.

Usage from a detector:

    audit = AuditCollector()
    with audit.time("normalize", "unicodedata.NFKC"):
        norm = normalize(text)
    with audit.time("regex_detect", "presidio_regex.uk_postcode"):
        ents = run_recognizers(norm)
    ...
    # AuditCollector.to_list() goes into DetectorResult.metadata["audit"].
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class PiiAuditStep:
    stage_name: str
    tool: str
    order: int
    started_at: str
    duration_ms: float
    status: str = "ok"  # "ok" | "skipped" | "error"
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "tool": self.tool,
            "order": self.order,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "message": self.message,
            "metadata": self.metadata,
        }


class AuditCollector:
    def __init__(self) -> None:
        self.steps: List[PiiAuditStep] = []

    @contextmanager
    def time(
        self,
        stage_name: str,
        tool: str,
        *,
        inputs: List[str] | None = None,
    ):
        order = len(self.steps)
        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        step = PiiAuditStep(
            stage_name=stage_name,
            tool=tool,
            order=order,
            started_at=started_at,
            duration_ms=0.0,
            inputs=list(inputs or []),
        )
        self.steps.append(step)
        try:
            yield step
            step.duration_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:  # noqa: BLE001
            step.duration_ms = (time.perf_counter() - t0) * 1000.0
            step.status = "error"
            step.message = f"{type(exc).__name__}: {exc}"
            raise

    def record(
        self,
        stage_name: str,
        tool: str,
        *,
        duration_ms: float = 0.0,
        status: str = "ok",
        inputs: List[str] | None = None,
        outputs: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        message: str = "",
    ) -> PiiAuditStep:
        step = PiiAuditStep(
            stage_name=stage_name,
            tool=tool,
            order=len(self.steps),
            started_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            status=status,
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            metadata=dict(metadata or {}),
            message=message,
        )
        self.steps.append(step)
        return step

    def to_list(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.steps]
