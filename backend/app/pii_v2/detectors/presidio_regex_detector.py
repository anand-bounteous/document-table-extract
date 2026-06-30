"""Candidate A: Presidio + UK/banking regex recognisers (.prompt/009 §9.1).

We bypass the full Presidio engine and apply our own jurisdiction-driven
regex pipeline directly. This keeps the dependency optional — the detector
runs even when ``presidio-analyzer`` is not installed. When Presidio *is*
installed, callers can still combine this detector's regex output with a
Presidio NER pass via the hybrid detector.
"""

from __future__ import annotations

from typing import List

from app.pii_v2 import merger, normalizer, risk
from app.pii_v2.audit import AuditCollector
from app.pii_v2.base import BaseDetector
from app.pii_v2.jurisdictions import collect_recognizers
from app.pii_v2.registry import register_detector
from app.pii_v2.schema import PIIEntity


def _context_boost(text_lower: str, span_start: int, terms: list[str], window: int = 60) -> bool:
    if not terms:
        return False
    lo = max(0, span_start - window)
    hi = min(len(text_lower), span_start + window)
    haystack = text_lower[lo:hi]
    return any(t in haystack for t in terms)


@register_detector
class PresidioRegexDetector(BaseDetector):
    name = "presidio_regex"
    display_name = "Presidio + UK/banking regex"
    description = (
        "Jurisdiction-driven regex recognisers with checksum validators "
        "(Luhn, IBAN MOD-97, NHS, NINO format) and context-term score boost."
    )

    def detect(self, text: str, audit: AuditCollector | None = None) -> List[PIIEntity]:
        if not text:
            return []
        with (audit.time("normalize", "unicodedata.NFKC") if audit else _nullctx()):
            norm = normalizer.normalize(text)
        recognizers = collect_recognizers(list(self.jurisdictions))
        lower = norm.original.lower()
        entities: List[PIIEntity] = []
        per_recognizer_counts: dict[str, int] = {}
        with (
            audit.time(
                "regex_detect",
                f"presidio_regex.{len(recognizers)}_recognizers",
                inputs=[f"text:{len(text)}c", f"jurisdictions:{','.join(self.jurisdictions)}"],
            )
            if audit
            else _nullctx()
        ) as step:
            for spec in recognizers:
                pattern = spec.compile()
                for match in pattern.finditer(norm.original):
                    value = match.group(0)
                    if spec.validator and not spec.validator(value):
                        continue
                    score = spec.score
                    if _context_boost(lower, match.start(), [t.lower() for t in spec.context_terms]):
                        score = min(1.0, score + spec.context_boost)
                    entities.append(
                        PIIEntity(
                            entity_type=spec.entity_type,
                            text=value,
                            start=match.start(),
                            end=match.end(),
                            score=score,
                            source=f"{spec.jurisdiction.lower()}_regex",
                            detection_method="regex",
                            jurisdiction=spec.jurisdiction,
                            metadata={"recognizer": spec.entity_type},
                        )
                    )
                    per_recognizer_counts[spec.entity_type] = (
                        per_recognizer_counts.get(spec.entity_type, 0) + 1
                    )
            if step is not None:
                step.metadata["per_recognizer_counts"] = per_recognizer_counts
                step.outputs = [f"entities:{len(entities)}"]
        with (audit.time("merge", "pii_v2.merger.merge") if audit else _nullctx()) as step:
            merged = merger.merge(entities)
            if step is not None:
                step.metadata["n_in"] = len(entities)
                step.metadata["n_out"] = len(merged)
        with (audit.time("risk", "pii_v2.risk.apply") if audit else _nullctx()):
            final = risk.apply(merged)
        return final


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _nullctx():
    yield None
