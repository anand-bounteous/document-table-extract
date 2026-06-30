"""Masking modes per .prompt/009 §12.

Five modes: ``replace``, ``partial``, ``hash``, ``tokenise``, ``remove``.
Masking operates on a *list of spans* over a *single source string*. Spans must
be non-overlapping; the merger should run first.

Output preserves character offsets *of the unmasked text*. The
``apply_masking`` helper returns both the new text and a list of
``(original_span, new_span)`` tuples so downstream callers can rebuild offsets
for redacted images.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from app.pii_v2.schema import PIIEntity


MASKING_DEFAULTS: Dict[str, str] = {
    "CREDIT_CARD_NUMBER": "partial",
    "CARD_CVV": "replace",
    "UK_BANK_ACCOUNT_NUMBER": "partial",
    "UK_SORT_CODE": "partial",
    "UK_IBAN": "partial",
    "IBAN": "partial",
    "UK_NATIONAL_INSURANCE_NUMBER": "replace",
    "UK_NHS_NUMBER": "replace",
    "EMAIL_ADDRESS": "partial",
    "UK_PHONE_NUMBER": "partial",
    "UK_POSTCODE": "replace",
    "UK_ADDRESS": "replace",
    "PERSON": "replace",
}


@dataclass
class MaskingResult:
    masked_text: str
    mapping: List[Tuple[Tuple[int, int], Tuple[int, int]]]


def mask_replace(entity: PIIEntity) -> str:
    return f"<{entity.entity_type}>"


def mask_partial(entity: PIIEntity) -> str:
    raw = entity.text
    if len(raw) <= 4:
        return "*" * len(raw)
    if "@" in raw:  # email
        local, _, domain = raw.partition("@")
        kept = local[:1] if local else ""
        return f"{kept}{'*' * max(1, len(local) - 1)}@{domain}"
    keep = max(2, len(raw) // 4)
    return raw[:keep] + "*" * (len(raw) - keep * 2) + raw[-keep:]


def mask_hash(entity: PIIEntity) -> str:
    digest = hashlib.sha256(entity.text.encode("utf-8")).hexdigest()
    return f"HASH_{digest[:8]}"


_token_counters: Dict[str, int] = {}


def mask_tokenise(entity: PIIEntity) -> str:
    _token_counters.setdefault(entity.entity_type, 0)
    _token_counters[entity.entity_type] += 1
    return f"TOKEN_{entity.entity_type}_{_token_counters[entity.entity_type]:06d}"


def mask_remove(entity: PIIEntity) -> str:  # noqa: ARG001
    return ""


_MODES = {
    "replace": mask_replace,
    "partial": mask_partial,
    "hash": mask_hash,
    "tokenise": mask_tokenise,
    "remove": mask_remove,
}


def apply_masking(
    text: str,
    entities: Iterable[PIIEntity],
    mode_overrides: Dict[str, str] | None = None,
    default_mode: str = "replace",
) -> MaskingResult:
    overrides = mode_overrides or {}
    ents = sorted(entities, key=lambda e: e.start)
    out: List[str] = []
    mapping: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    cursor = 0
    new_cursor = 0
    for ent in ents:
        if ent.start < cursor:
            continue  # overlap — caller should merge first
        out.append(text[cursor:ent.start])
        new_cursor += ent.start - cursor
        mode_name = overrides.get(ent.entity_type, MASKING_DEFAULTS.get(ent.entity_type, default_mode))
        masker = _MODES.get(mode_name, mask_replace)
        replacement = masker(ent)
        out.append(replacement)
        mapping.append(((ent.start, ent.end), (new_cursor, new_cursor + len(replacement))))
        new_cursor += len(replacement)
        cursor = ent.end
    out.append(text[cursor:])
    return MaskingResult(masked_text="".join(out), mapping=mapping)


def reset_token_counters() -> None:
    """Reset between runs so token IDs restart at 1."""
    _token_counters.clear()
