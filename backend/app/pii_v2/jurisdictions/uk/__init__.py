"""UK jurisdiction plugin (.prompt/009 §8)."""

from __future__ import annotations

import re
from typing import List

from app.pii_v2.jurisdictions.base import JurisdictionPlugin, RecognizerSpec
from app.pii_v2.jurisdictions.uk.validators import (
    is_valid_nhs_number,
    is_valid_uk_iban,
    is_valid_uk_nino,
)


class UKPlugin(JurisdictionPlugin):
    code = "UK"
    display_name = "United Kingdom"

    def get_recognizers(self) -> List[RecognizerSpec]:
        return [
            RecognizerSpec(
                entity_type="UK_POSTCODE",
                pattern=r"\b(?:GIR\s?0AA|(?:[A-PR-UWYZ][A-HK-Y0-9][A-HJKPSTUW0-9]?[ABEHMNPRVWXY0-9]?\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b",
                score=0.9,
                jurisdiction="UK",
                context_terms=["postcode", "post code", "address"],
            ),
            RecognizerSpec(
                entity_type="UK_PHONE_NUMBER",
                pattern=r"(?:\+44\s?\(?0?\)?|\b0)(?:\d\s?){9,10}",
                score=0.75,
                jurisdiction="UK",
                context_terms=["phone", "mobile", "tel", "contact", "call", "sms"],
                flags=re.IGNORECASE,
            ),
            RecognizerSpec(
                entity_type="UK_NATIONAL_INSURANCE_NUMBER",
                pattern=r"\b(?!BG)(?!GB)(?!KN)(?!NK)(?!NT)(?!TN)(?!ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
                score=0.9,
                jurisdiction="UK",
                context_terms=["national insurance", "ni number", "nino"],
                validator=is_valid_uk_nino,
            ),
            RecognizerSpec(
                entity_type="UK_SORT_CODE",
                pattern=r"\b\d{2}[-\s]\d{2}[-\s]\d{2}\b",
                score=0.7,
                jurisdiction="UK",
                context_terms=["sort code", "bank details"],
            ),
            RecognizerSpec(
                entity_type="UK_BANK_ACCOUNT_NUMBER",
                pattern=r"\b\d{8}\b",
                score=0.4,
                jurisdiction="UK",
                context_terms=["account", "bank", "account number", "a/c"],
                context_boost=0.35,
            ),
            RecognizerSpec(
                entity_type="UK_IBAN",
                pattern=r"\bGB\d{2}[A-Z]{4}\d{14}\b",
                score=0.9,
                jurisdiction="UK",
                context_terms=["iban"],
                validator=is_valid_uk_iban,
            ),
            RecognizerSpec(
                entity_type="UK_NHS_NUMBER",
                pattern=r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{4}\b",
                score=0.6,
                jurisdiction="UK",
                context_terms=["nhs", "patient", "medical"],
                context_boost=0.3,
                validator=is_valid_nhs_number,
            ),
            RecognizerSpec(
                entity_type="UK_UTR",
                pattern=r"\b\d{10}\b",
                score=0.4,
                jurisdiction="UK",
                context_terms=["utr", "unique taxpayer", "tax reference", "hmrc"],
                context_boost=0.45,
            ),
            RecognizerSpec(
                entity_type="UK_DRIVING_LICENCE_NUMBER",
                pattern=r"\b[A-Z9]{5}\d{6}[A-Z9]{2}\d[A-Z]{2}\b",
                score=0.85,
                jurisdiction="UK",
                context_terms=["driving licence", "dvla"],
                flags=0,
            ),
        ]
