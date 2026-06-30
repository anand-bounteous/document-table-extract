"""Span merger.

Implements the deterministic conflict rules from .prompt/009 §10:

- Exact same span: keep the highest-scoring entity.
- Structured-over-contextual for the configured entity list: prefer the
  recogniser-based detection.
- Nested entities: keep the more specific one unless the configuration
  explicitly allows both (used for ADDRESS + POSTCODE).
- Sensitive indicators: preserve even on overlap.
"""

from __future__ import annotations

from typing import Iterable, List, Set

from app.pii_v2.schema import PIIEntity


STRUCTURED_PREFERENCE: Set[str] = {
    "UK_SORT_CODE",
    "UK_BANK_ACCOUNT_NUMBER",
    "CREDIT_CARD_NUMBER",
    "UK_IBAN",
    "IBAN",
    "UK_NATIONAL_INSURANCE_NUMBER",
    "UK_POSTCODE",
    "UK_PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "UK_NHS_NUMBER",
}

ALLOW_PARENT_CHILD: Set[tuple[str, str]] = {
    ("UK_ADDRESS", "UK_POSTCODE"),
}

SENSITIVE_PRESERVE: Set[str] = {
    "VULNERABLE_CUSTOMER_INDICATOR",
    "HEALTH_INFORMATION",
    "CRIMINAL_OFFENCE_INFORMATION",
}


def _overlaps(a: PIIEntity, b: PIIEntity) -> bool:
    return not (a.end <= b.start or b.end <= a.start)


def _same_span(a: PIIEntity, b: PIIEntity) -> bool:
    return a.start == b.start and a.end == b.end


def _contains(outer: PIIEntity, inner: PIIEntity) -> bool:
    return outer.start <= inner.start and outer.end >= inner.end and outer != inner


def merge(entities: Iterable[PIIEntity]) -> List[PIIEntity]:
    ents = sorted(entities, key=lambda e: (e.start, -e.end, -e.score))
    kept: List[PIIEntity] = []
    for ent in ents:
        if ent.entity_type in SENSITIVE_PRESERVE:
            kept.append(ent)
            continue
        replaced = False
        drop = False
        for i, k in enumerate(kept):
            if not _overlaps(ent, k):
                continue
            if _same_span(ent, k):
                if ent.score > k.score:
                    kept[i] = ent
                    replaced = True
                else:
                    drop = True
                break
            if _contains(k, ent) or _contains(ent, k):
                pair = (k.entity_type, ent.entity_type)
                rev = (ent.entity_type, k.entity_type)
                if pair in ALLOW_PARENT_CHILD or rev in ALLOW_PARENT_CHILD:
                    continue
                outer, inner = (k, ent) if _contains(k, ent) else (ent, k)
                outer_structured = outer.entity_type in STRUCTURED_PREFERENCE
                inner_structured = inner.entity_type in STRUCTURED_PREFERENCE
                if outer_structured and inner_structured:
                    # Both structured -> keep the higher-confidence span. Ties
                    # to the outer (more specific recogniser, e.g. NINO over a
                    # generic 6-digit sort-code-like span).
                    if outer.score >= inner.score:
                        if outer is k:
                            drop = True
                        else:
                            kept[i] = ent
                            replaced = True
                    else:
                        if outer is k:
                            kept[i] = ent
                            replaced = True
                        else:
                            drop = True
                    break
                if inner_structured:
                    if outer is k:
                        kept[i] = ent
                        replaced = True
                    else:
                        drop = True
                    break
                if outer is k:
                    drop = True
                else:
                    kept[i] = ent
                    replaced = True
                break
            if ent.entity_type in STRUCTURED_PREFERENCE and k.entity_type not in STRUCTURED_PREFERENCE:
                kept[i] = ent
                replaced = True
                break
            if k.entity_type in STRUCTURED_PREFERENCE and ent.entity_type not in STRUCTURED_PREFERENCE:
                drop = True
                break
            if ent.score > k.score:
                kept[i] = ent
                replaced = True
            else:
                drop = True
            break
        if not (replaced or drop):
            kept.append(ent)
    kept.sort(key=lambda e: (e.start, e.end))
    return kept
