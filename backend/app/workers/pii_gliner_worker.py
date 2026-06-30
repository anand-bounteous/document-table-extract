"""GLiNER-backed PII detection worker.

Reads ``{"text": str, "jurisdictions": [str]}`` from stdin and writes
``{"entities": [...]}`` to ``$OTE_RESULT_PATH``. Lazy-loads the GLiNER model
on first call inside the subprocess; on a fresh subprocess this is paid
once. The detector class spawns one subprocess per detection call so the
model is dropped between detections — fine for benchmark mode, less so for
hot serving (which is a future concern).
"""

from __future__ import annotations

import os
from typing import Any, Dict

from app.workers._io import run_worker

_DEFAULT_MODEL = os.environ.get("PII_V2_GLINER_MODEL", "urchade/gliner_small-v2.1")
_DEFAULT_THRESHOLD = float(os.environ.get("PII_V2_GLINER_THRESHOLD", "0.5"))

_LABEL_TO_ENTITY_TYPE = {
    "person": "PERSON",
    "address": "UK_ADDRESS",
    "postcode": "UK_POSTCODE",
    "phone number": "UK_PHONE_NUMBER",
    "email address": "EMAIL_ADDRESS",
    "bank account number": "UK_BANK_ACCOUNT_NUMBER",
    "sort code": "UK_SORT_CODE",
    "national insurance number": "UK_NATIONAL_INSURANCE_NUMBER",
    "passport number": "UK_PASSPORT_NUMBER",
    "driving licence number": "UK_DRIVING_LICENCE_NUMBER",
    "customer id": "CUSTOMER_ID",
    "account id": "ACCOUNT_ID",
    "payment reference": "PAYMENT_REFERENCE",
    "health information": "HEALTH_INFORMATION",
    "criminal offence information": "CRIMINAL_OFFENCE_INFORMATION",
    "vulnerable customer information": "VULNERABLE_CUSTOMER_INDICATOR",
    "iban": "UK_IBAN",
    "credit card number": "CREDIT_CARD_NUMBER",
    "date of birth": "DATE_OF_BIRTH",
}

_LABELS = list(_LABEL_TO_ENTITY_TYPE.keys())


def _detect(text: str, jurisdictions: list[str]) -> list[dict]:
    from gliner import GLiNER  # type: ignore

    model = GLiNER.from_pretrained(_DEFAULT_MODEL)
    raw = model.predict_entities(text, _LABELS, threshold=_DEFAULT_THRESHOLD)
    out: list[dict] = []
    for ent in raw:
        label = ent["label"].lower()
        entity_type = _LABEL_TO_ENTITY_TYPE.get(label, label.upper().replace(" ", "_"))
        out.append({
            "entity_type": entity_type,
            "text": ent["text"],
            "start": int(ent["start"]),
            "end": int(ent["end"]),
            "score": float(ent.get("score", 0.0)),
            "source": "gliner",
            "detection_method": "ml",
            "jurisdiction": "UK" if entity_type.startswith("UK_") else None,
            "risk_level": None,
            "sensitivity_category": None,
            "metadata": {"gliner_label": ent["label"]},
        })
    return out


def work(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = payload.get("text") or ""
    jurisdictions = payload.get("jurisdictions") or ["GLOBAL_COMMON", "UK"]
    if not text:
        return {"entities": []}
    return {"entities": _detect(text, jurisdictions)}


if __name__ == "__main__":
    run_worker(work)
