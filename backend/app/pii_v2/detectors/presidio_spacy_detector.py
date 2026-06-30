"""Candidate B: Presidio + spaCy (.prompt/009 §9.2).

Adds contextual NER (PERSON, ORG, LOC) on top of the regex pipeline.
``spacy`` and the ``en_core_web_sm`` model are optional. If either is
missing the detector falls back to regex-only and surfaces a notice in
``DetectorResult.metadata['warning']``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.pii_v2 import merger, risk
from app.pii_v2.audit import AuditCollector
from app.pii_v2.base import BaseDetector
from app.pii_v2.detectors.presidio_regex_detector import PresidioRegexDetector
from app.pii_v2.registry import register_detector
from app.pii_v2.schema import PIIEntity

logger = logging.getLogger(__name__)

_SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORGANISATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "DATE": "DATE",
    "FAC": "LOCATION",
    "NORP": "ORGANISATION",
}


@register_detector
class PresidioSpacyDetector(BaseDetector):
    name = "presidio_spacy"
    display_name = "Presidio + spaCy NER"
    description = (
        "Regex pipeline plus spaCy NER for contextual PII (names, "
        "organisations, locations, dates). Falls back to regex-only when "
        "spaCy is unavailable."
    )
    requires_models = ("en_core_web_sm",)

    _nlp: Optional[object] = None
    _spacy_unavailable = False

    def _get_nlp(self):  # pragma: no cover — model-dependent
        if self._spacy_unavailable:
            return None
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning("spacy model 'en_core_web_sm' not installed; falling back to regex-only")
                self._spacy_unavailable = True
                return None
        except ImportError:
            logger.warning("spaCy not installed; falling back to regex-only")
            self._spacy_unavailable = True
            return None
        return self._nlp

    def detect(self, text: str, audit: AuditCollector | None = None) -> List[PIIEntity]:
        regex_detector = PresidioRegexDetector(jurisdictions=self.jurisdictions)
        entities: List[PIIEntity] = regex_detector.detect(text, audit=audit)
        nlp = self._get_nlp()
        if nlp is None or not text:
            return entities
        from contextlib import nullcontext
        with audit.time("ner", "spacy.en_core_web_sm") if audit else nullcontext() as step:
            doc = nlp(text)
            added = 0
            for ent in doc.ents:
                mapped = _SPACY_LABEL_MAP.get(ent.label_)
                if not mapped:
                    continue
                entities.append(
                    PIIEntity(
                        entity_type=mapped,
                        text=ent.text,
                        start=ent.start_char,
                        end=ent.end_char,
                        score=0.7,
                        source="spacy_ner",
                        detection_method="ner",
                        jurisdiction=None,
                        metadata={"spacy_label": ent.label_},
                    )
                )
                added += 1
            if step is not None:
                step.outputs = [f"ner_entities:{added}"]
        merged = merger.merge(entities)
        return risk.apply(merged)
