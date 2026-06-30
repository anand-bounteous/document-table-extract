"""Piiranha-backed PII detection worker.

Piiranha is a HuggingFace token-classification model dedicated to PII. We
wrap it via the standard transformers pipeline. Reads
``{"text": str, "jurisdictions": [str]}`` from stdin; writes
``{"entities": [...]}`` to ``$OTE_RESULT_PATH``.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from app.workers._io import run_worker

_DEFAULT_MODEL = os.environ.get(
    "PII_V2_PIIRANHA_MODEL", "iiiorg/piiranha-v1-detect-personal-information"
)

_LABEL_TO_ENTITY_TYPE = {
    "GIVENNAME": "PERSON",
    "SURNAME": "PERSON",
    "NAME": "PERSON",
    "EMAIL": "EMAIL_ADDRESS",
    "TELEPHONENUM": "UK_PHONE_NUMBER",
    "STREET": "UK_ADDRESS",
    "CITY": "LOCATION",
    "ZIPCODE": "UK_POSTCODE",
    "POSTCODE": "UK_POSTCODE",
    "DATEOFBIRTH": "DATE_OF_BIRTH",
    "DOB": "DATE_OF_BIRTH",
    "BUILDINGNUM": "UK_ADDRESS",
    "IDCARDNUM": "PASSPORT_NUMBER",
    "DRIVERLICENSENUM": "UK_DRIVING_LICENCE_NUMBER",
    "PASSPORT": "UK_PASSPORT_NUMBER",
    "ACCOUNTNUM": "UK_BANK_ACCOUNT_NUMBER",
    "CREDITCARDNUMBER": "CREDIT_CARD_NUMBER",
    "SOCIALNUM": "UK_NATIONAL_INSURANCE_NUMBER",
    "SSN": "UK_NATIONAL_INSURANCE_NUMBER",
    "TAXNUM": "UK_UTR",
    "IBAN": "UK_IBAN",
    "USERNAME": "USERNAME",
}


def _detect(text: str) -> list[dict]:
    from transformers import pipeline  # type: ignore

    nlp = pipeline(
        "token-classification",
        model=_DEFAULT_MODEL,
        aggregation_strategy="simple",
    )
    raw = nlp(text)
    out: list[dict] = []
    for ent in raw:
        label = re.sub(r"^[BIO]-", "", str(ent.get("entity_group") or ent.get("entity") or "")).upper()
        entity_type = _LABEL_TO_ENTITY_TYPE.get(label, label or "UNKNOWN")
        out.append({
            "entity_type": entity_type,
            "text": str(ent["word"]).strip(),
            "start": int(ent["start"]),
            "end": int(ent["end"]),
            "score": float(ent.get("score", 0.0)),
            "source": "piiranha",
            "detection_method": "ml",
            "jurisdiction": "UK" if entity_type.startswith("UK_") else None,
            "risk_level": None,
            "sensitivity_category": None,
            "metadata": {"piiranha_label": label},
        })
    return out


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = payload.get("text") or ""
    if not text:
        return {"entities": []}
    return {"entities": _detect(text)}


if __name__ == "__main__":
    run_worker(work)
