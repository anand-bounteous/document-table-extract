"""Validators for global entities."""

from __future__ import annotations

import re


_CARD_CLEAN = re.compile(r"[\s\-]")


def is_valid_luhn_card(value: str) -> bool:
    cleaned = _CARD_CLEAN.sub("", value)
    if not cleaned.isdigit() or not 13 <= len(cleaned) <= 19:
        return False
    digits = [int(c) for c in cleaned]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def is_valid_iban(value: str) -> bool:
    cleaned = re.sub(r"\s+", "", value).upper()
    if not 15 <= len(cleaned) <= 34:
        return False
    if not re.match(r"^[A-Z]{2}\d{2}", cleaned):
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False
