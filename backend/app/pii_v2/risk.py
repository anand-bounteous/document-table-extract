"""Risk classification + composite rules (.prompt/009 §11)."""

from __future__ import annotations

from typing import Iterable, List, Set

from app.pii_v2.schema import PIIEntity


HIGH_RISK: Set[str] = {
    "CREDIT_CARD_NUMBER",
    "CARD_CVV",
    "UK_BANK_ACCOUNT_NUMBER",
    "UK_IBAN",
    "IBAN",
    "UK_NATIONAL_INSURANCE_NUMBER",
    "UK_NHS_NUMBER",
}

MEDIUM_RISK: Set[str] = {
    "UK_POSTCODE",
    "UK_PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "PERSON",
    "UK_ADDRESS",
    "ADDRESS",
    "CUSTOMER_ID",
    "UK_SORT_CODE",
    "UK_PASSPORT_NUMBER",
    "PASSPORT_NUMBER",
    "DATE_OF_BIRTH",
    "UK_DRIVING_LICENCE_NUMBER",
    "UK_UTR",
}

LOW_RISK: Set[str] = {
    "ORGANISATION",
    "LOCATION",
    "DATE",
    "URL",
    "IP_ADDRESS",
}

SPECIAL_CATEGORY: Set[str] = {
    "UK_NHS_NUMBER",
    "HEALTH_INFORMATION",
    "RELIGION_OR_BELIEF",
    "POLITICAL_OPINION",
    "TRADE_UNION_MEMBERSHIP",
    "SEXUAL_ORIENTATION",
    "BIOMETRIC_IDENTIFIER",
    "GENETIC_INFORMATION",
}


def classify(entity_type: str) -> str:
    if entity_type in HIGH_RISK:
        return "high"
    if entity_type in MEDIUM_RISK:
        return "medium"
    if entity_type in LOW_RISK:
        return "low"
    return "medium"


def sensitivity(entity_type: str) -> str:
    if entity_type in SPECIAL_CATEGORY:
        return "special_category"
    return "personal_data"


_SORT_ACCOUNT = {"UK_SORT_CODE", "UK_BANK_ACCOUNT_NUMBER"}
_NAME_POSTCODE = {"PERSON", "UK_POSTCODE"}
_NAME_DOB = {"PERSON", "DATE_OF_BIRTH"}


def apply(entities: Iterable[PIIEntity]) -> List[PIIEntity]:
    """Stamp risk_level + sensitivity_category on each entity. Mutates in place."""
    ents = list(entities)
    types_present = {e.entity_type for e in ents}
    sort_account_hit = _SORT_ACCOUNT.issubset(types_present)
    name_postcode_hit = _NAME_POSTCODE.issubset(types_present)
    name_dob_hit = _NAME_DOB.issubset(types_present)
    for e in ents:
        if e.risk_level is None:
            e.risk_level = classify(e.entity_type)
        if e.sensitivity_category is None:
            e.sensitivity_category = sensitivity(e.entity_type)
        if sort_account_hit and e.entity_type in _SORT_ACCOUNT:
            e.risk_level = "high"
            e.metadata.setdefault("composite_rule", "sort_code_plus_account_number")
        if name_postcode_hit and e.entity_type in _NAME_POSTCODE:
            e.risk_level = "high"
            e.metadata.setdefault("composite_rule", "name_plus_postcode")
        if name_dob_hit and e.entity_type in _NAME_DOB:
            e.risk_level = "high"
            e.metadata.setdefault("composite_rule", "name_plus_date_of_birth")
    return ents
