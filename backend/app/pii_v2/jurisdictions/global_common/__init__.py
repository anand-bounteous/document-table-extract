"""GLOBAL_COMMON plugin — entities that are jurisdiction-agnostic."""

from __future__ import annotations

from typing import List

from app.pii_v2.jurisdictions.base import JurisdictionPlugin, RecognizerSpec
from app.pii_v2.jurisdictions.global_common.validators import (
    is_valid_iban,
    is_valid_luhn_card,
)


class GlobalCommonPlugin(JurisdictionPlugin):
    code = "GLOBAL_COMMON"
    display_name = "Global Common"

    def get_recognizers(self) -> List[RecognizerSpec]:
        return [
            RecognizerSpec(
                entity_type="EMAIL_ADDRESS",
                pattern=r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
                score=0.9,
                jurisdiction="GLOBAL_COMMON",
                context_terms=["email", "e-mail", "contact"],
            ),
            RecognizerSpec(
                entity_type="IP_ADDRESS",
                pattern=r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
                score=0.85,
                jurisdiction="GLOBAL_COMMON",
            ),
            RecognizerSpec(
                entity_type="URL",
                pattern=r"\bhttps?://[^\s<>\"']+\b",
                score=0.85,
                jurisdiction="GLOBAL_COMMON",
            ),
            RecognizerSpec(
                entity_type="IBAN",
                pattern=r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
                score=0.7,
                jurisdiction="GLOBAL_COMMON",
                context_terms=["iban", "bank account"],
                validator=is_valid_iban,
                flags=0,
            ),
            RecognizerSpec(
                entity_type="SWIFT_BIC",
                pattern=r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b",
                score=0.7,
                jurisdiction="GLOBAL_COMMON",
                context_terms=["swift", "bic"],
                flags=0,
            ),
            RecognizerSpec(
                entity_type="CREDIT_CARD_NUMBER",
                pattern=r"\b(?:\d[ \-]?){13,19}\b",
                score=0.55,
                jurisdiction="GLOBAL_COMMON",
                context_terms=["card", "credit", "debit", "visa", "mastercard"],
                validator=is_valid_luhn_card,
            ),
            RecognizerSpec(
                entity_type="DATE",
                pattern=r"\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})\b",
                score=0.5,
                jurisdiction="GLOBAL_COMMON",
            ),
        ]
