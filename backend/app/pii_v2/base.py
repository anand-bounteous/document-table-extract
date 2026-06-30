"""Detector contract.

Every pii_v2 detector implements :class:`BaseDetector`. Heavy ML detectors
(GLiNER, Piiranha) keep model loading lazy — the runner constructs one
instance per worker process so model load happens once per subprocess.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from app.pii_v2.audit import AuditCollector
from app.pii_v2.schema import DetectorResult, PIIEntity


class BaseDetector(ABC):
    name: str = ""
    display_name: str = ""
    description: str = ""
    requires_models: tuple[str, ...] = ()

    def __init__(self, jurisdictions: Optional[Sequence[str]] = None) -> None:
        self.jurisdictions = list(jurisdictions or ["GLOBAL_COMMON", "UK"])

    @abstractmethod
    def detect(self, text: str, audit: Optional[AuditCollector] = None) -> List[PIIEntity]:
        """Return all PII spans found in ``text``.

        ``audit`` is optional. When provided, subclasses push sub-phase
        steps into it (e.g. normalize → regex_detect → merge → risk)
        so the dashboard can render a per-detector audit timeline.
        """

    def detect_with_timing(self, text: str) -> DetectorResult:
        """Wrap :meth:`detect` with latency, audit capture, and error guard."""
        audit = AuditCollector()
        t0 = time.perf_counter()
        try:
            ents = self.detect(text, audit=audit)
            err: Optional[str] = None
        except Exception as exc:  # noqa: BLE001
            ents = []
            err = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return DetectorResult(
            detector_name=self.name,
            entities=ents,
            text_len=len(text),
            latency_ms=elapsed_ms,
            error=err,
            metadata={"audit": audit.to_list()},
        )
