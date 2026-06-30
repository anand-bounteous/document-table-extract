"""USER_CUSTOM jurisdiction plugin — the manual-annotation feedback loop.

Reads the global custom-dictionary file at
``storage/pii_runs/_custom_dictionary/<jurisdiction>.json`` populated by
:mod:`app.pii_v2_manual_store` and emits one exact-string ``RecognizerSpec``
per (entity_type, text) entry. The score is configurable via
``PII_V2_USER_CUSTOM_SCORE`` (default ``0.85``).

This plugin is implicitly included on every regex detection so the user's
prior corrections benefit subsequent runs without manual configuration.
"""

from __future__ import annotations

import os
import re
from typing import List

from app.config import settings
from app.pii_v2.jurisdictions.base import JurisdictionPlugin, RecognizerSpec


def _score() -> float:
    return float(os.environ.get("PII_V2_USER_CUSTOM_SCORE", "0.85"))


def _load_dictionary_entries() -> List[dict]:
    from app import pii_v2_manual_store

    rows: List[dict] = []
    for name in pii_v2_manual_store.list_dictionaries():
        rows.extend(pii_v2_manual_store.read_custom_dictionary(name))
    return rows


class UserCustomPlugin(JurisdictionPlugin):
    code = "USER_CUSTOM"
    display_name = "User custom (manual annotations)"

    def get_recognizers(self) -> List[RecognizerSpec]:
        rows = _load_dictionary_entries()
        score = _score()
        specs: List[RecognizerSpec] = []
        for row in rows:
            text = str(row.get("text", "")).strip()
            entity_type = str(row.get("entity_type", "")).strip()
            if not text or not entity_type:
                continue
            specs.append(RecognizerSpec(
                entity_type=entity_type,
                pattern=rf"\b{re.escape(text)}\b",
                score=score,
                jurisdiction="USER_CUSTOM",
                context_terms=[],
                context_boost=0.0,
                flags=re.IGNORECASE,
            ))
        return specs
