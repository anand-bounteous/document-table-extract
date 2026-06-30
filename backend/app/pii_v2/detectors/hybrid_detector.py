"""Candidate E: Hybrid detector (.prompt/009 §9.5).

Implements the recommended hybrid logic:

1. Normalise text.
2. Run high-confidence structured recognisers (regex).
3. Run the best available contextual ML detector — GLiNER preferred, then
   Piiranha, then spaCy, finally regex-only when none are available.
4. Merge with structured-over-contextual conflict rules already in
   :mod:`app.pii_v2.merger`.
5. Apply risk + composite rules.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from app.pii_v2 import merger, risk
from app.pii_v2.audit import AuditCollector
from app.pii_v2.base import BaseDetector
from app.pii_v2.detectors.gliner_detector import GLiNERDetector
from app.pii_v2.detectors.piiranha_detector import PiiranhaDetector
from app.pii_v2.detectors.presidio_regex_detector import PresidioRegexDetector
from app.pii_v2.detectors.presidio_spacy_detector import PresidioSpacyDetector
from app.pii_v2.registry import register_detector
from app.pii_v2.schema import PIIEntity
from app.pii_v2.subprocess_detector import call_worker

logger = logging.getLogger(__name__)


def _try_call(worker_module: str, text: str, jurisdictions: Sequence[str]) -> Optional[List[PIIEntity]]:
    try:
        return call_worker(
            worker_module=worker_module,
            text=text,
            jurisdictions=list(jurisdictions),
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("hybrid: %s unavailable (%s)", worker_module, exc)
        return None


@register_detector
class HybridDetector(BaseDetector):
    name = "hybrid"
    display_name = "Hybrid (regex + best-available NER)"
    description = (
        "Structured regex recognisers combined with the strongest contextual "
        "detector available at runtime (GLiNER → Piiranha → spaCy → regex-only). "
        "Production candidate per .prompt/009 §9.5."
    )
    requires_models = ()

    def detect(self, text: str, audit: AuditCollector | None = None) -> List[PIIEntity]:
        from contextlib import nullcontext
        regex = PresidioRegexDetector(jurisdictions=self.jurisdictions).detect(text, audit=audit)
        contextual: List[PIIEntity] = []
        chosen = "regex_only"
        with audit.time("ml_detect", "hybrid.contextual_picker") if audit else nullcontext() as step:
            ml = _try_call("app.workers.pii_gliner_worker", text, self.jurisdictions)
            if ml is not None:
                contextual = ml
                chosen = "gliner"
            else:
                ml = _try_call("app.workers.pii_piiranha_worker", text, self.jurisdictions)
                if ml is not None:
                    contextual = ml
                    chosen = "piiranha"
                else:
                    spacy_result = PresidioSpacyDetector(jurisdictions=self.jurisdictions).detect(text)
                    regex_keys = {(e.entity_type, e.start, e.end) for e in regex}
                    contextual = [e for e in spacy_result if (e.entity_type, e.start, e.end) not in regex_keys]
                    chosen = "spacy" if contextual else "regex_only"
            if step is not None:
                step.metadata["chosen"] = chosen
                step.outputs = [f"contextual_entities:{len(contextual)}"]
        merged = merger.merge(regex + contextual)
        return risk.apply(merged)
