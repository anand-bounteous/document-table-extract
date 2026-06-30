"""Candidate D: Piiranha + UK/banking regex (.prompt/009 §9.4).

Combines the regex pipeline with the Piiranha token-classification model.
Subprocess-isolated; model loads per call.
"""

from __future__ import annotations

import logging
from typing import List

from app.pii_v2 import merger, risk
from app.pii_v2.audit import AuditCollector
from app.pii_v2.base import BaseDetector
from app.pii_v2.detectors.presidio_regex_detector import PresidioRegexDetector
from app.pii_v2.registry import register_detector
from app.pii_v2.schema import PIIEntity
from app.pii_v2.subprocess_detector import call_worker

logger = logging.getLogger(__name__)


@register_detector
class PiiranhaDetector(BaseDetector):
    name = "piiranha"
    display_name = "Piiranha + UK regex"
    description = (
        "Regex pipeline plus the Piiranha PII model (iiiorg/piiranha-v1) "
        "for dedicated PII NER. Subprocess-isolated."
    )
    requires_models = ("iiiorg/piiranha-v1-detect-personal-information",)

    def detect(self, text: str, audit: AuditCollector | None = None) -> List[PIIEntity]:
        from contextlib import nullcontext
        regex = PresidioRegexDetector(jurisdictions=self.jurisdictions).detect(text, audit=audit)
        with audit.time("ml_detect", "piiranha.subprocess") if audit else nullcontext() as step:
            try:
                ml = call_worker(
                    worker_module="app.workers.pii_piiranha_worker",
                    text=text,
                    jurisdictions=list(self.jurisdictions),
                )
                if step is not None:
                    step.outputs = [f"ml_entities:{len(ml)}"]
            except Exception as exc:  # noqa: BLE001
                logger.warning("piiranha worker failed: %s; returning regex-only output", exc)
                if step is not None:
                    step.status = "skipped"
                    step.message = f"{type(exc).__name__}: {exc}"
                return regex
        return risk.apply(merger.merge(regex + ml))
