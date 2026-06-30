"""Text normalisation utilities shared by recognisers and detectors.

Normalisation is *additive*: the original text is preserved so that
``PIIEntity.start/end`` continue to index into the source string. A normalised
copy is exposed for recognisers that benefit (e.g. UK postcode space
normalisation).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class NormalizedText:
    original: str
    normalized: str


def normalize(text: str) -> NormalizedText:
    """Lowercase-stable, NFKC-normalised, single-space-collapsed copy."""
    nfkc = unicodedata.normalize("NFKC", text)
    collapsed = re.sub(r"[ \t]+", " ", nfkc)
    return NormalizedText(original=text, normalized=collapsed)


def normalize_postcode(value: str) -> str:
    """``"sw1a1aa"`` → ``"SW1A 1AA"``. Idempotent."""
    cleaned = re.sub(r"\s+", "", value).upper()
    if len(cleaned) < 5:
        return cleaned
    return cleaned[:-3] + " " + cleaned[-3:]


def strip_separators(value: str) -> str:
    """Remove all whitespace and common separators (used for IBAN/card validation)."""
    return re.sub(r"[\s\-]", "", value)
