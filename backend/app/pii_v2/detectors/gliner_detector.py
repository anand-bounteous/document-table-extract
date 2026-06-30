"""Candidate C: Presidio + GLiNER (.prompt/009 §9.3).

Combines the regex pipeline with GLiNER's contextual NER for the labels we
care about. The model runs in a subprocess so its memory is released after
each detection — important when many detectors are benchmarked in parallel.
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
class GLiNERDetector(BaseDetector):
    name = "gliner"
    display_name = "Presidio regex + GLiNER"
    description = (
        "Regex pipeline plus GLiNER (urchade/gliner_small-v2.1) for "
        "contextual PII labels. Subprocess-isolated; loads model per call."
    )
    requires_models = ("urchade/gliner_small-v2.1",)

    def detect(self, text: str, audit: AuditCollector | None = None) -> List[PIIEntity]:
        from contextlib import nullcontext
        regex = PresidioRegexDetector(jurisdictions=self.jurisdictions).detect(text, audit=audit)
        with audit.time("ml_detect", "gliner.subprocess") if audit else nullcontext() as step:
            try:
                ml = call_worker(
                    worker_module="app.workers.pii_gliner_worker",
                    text=text,
                    jurisdictions=list(self.jurisdictions),
                )
                if step is not None:
                    step.outputs = [f"ml_entities:{len(ml)}"]
            except Exception as exc:  # noqa: BLE001
                logger.warning("gliner worker failed: %s; returning regex-only output", exc)
                if step is not None:
                    step.status = "skipped"
                    step.message = f"{type(exc).__name__}: {exc}"
                return regex
        return risk.apply(merger.merge(regex + ml))
