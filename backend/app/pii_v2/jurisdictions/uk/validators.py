"""UK-specific validators (.prompt/009 §8)."""

from __future__ import annotations

import re

from app.pii_v2.jurisdictions.global_common.validators import is_valid_iban


_NINO_CLEAN = re.compile(r"\s+")


def is_valid_uk_nino(value: str) -> bool:
    cleaned = _NINO_CLEAN.sub("", value).upper()
    if len(cleaned) != 9:
        return False
    bad_prefixes = {"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"}
    if cleaned[:2] in bad_prefixes:
        return False
    if not re.match(r"^[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\d{6}[A-D]$", cleaned):
        return False
    return True


def is_valid_uk_iban(value: str) -> bool:
    cleaned = re.sub(r"\s+", "", value).upper()
    if not cleaned.startswith("GB") or len(cleaned) != 22:
        return False
    return is_valid_iban(cleaned)


def is_valid_nhs_number(value: str) -> bool:
    digits = re.sub(r"[\s\-]", "", value)
    if not digits.isdigit() or len(digits) != 10:
        return False
    total = sum(int(d) * (10 - i) for i, d in enumerate(digits[:9]))
    remainder = total % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return False
    return check == int(digits[9])
