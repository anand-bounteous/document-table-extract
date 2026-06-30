"""Encrypted ``mock_value → original_value`` mapping store.

The mapping is what lets a downstream "restore" step (out of scope for
this round) reverse the redaction after the LLM has processed the
redacted text/image. We store two files per cell:

- ``mapping.fernet`` — Fernet-encrypted JSON of ``{mock: original}``.
- ``mapping.index.json`` — plaintext metadata (entity-type counts) so the
  UI can show "5 entities redacted (3 PERSON, 2 UK_POSTCODE)" without
  decrypting anything.

Encryption reuses the same key (``settings.pii_mask_key``) as the legacy
``app.stages.pii.presidio`` token map, so the operational pattern is
consistent. Without a key, the warning matches the legacy behaviour and
plaintext is stored.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RedactionMapping:
    pii_run_id: str
    document_id: str
    page_index: int
    ocr: str
    detector: str
    mock_to_original: Dict[str, str] = field(default_factory=dict)
    entity_types: Dict[str, int] = field(default_factory=dict)

    def to_index(self) -> Dict[str, Any]:
        """Plaintext-safe metadata. NEVER contains raw originals or mocks."""
        return {
            "pii_run_id": self.pii_run_id,
            "document_id": self.document_id,
            "page_index": self.page_index,
            "ocr": self.ocr,
            "detector": self.detector,
            "n_mappings": len(self.mock_to_original),
            "entity_types": dict(self.entity_types),
        }


def _encrypt(payload: Dict[str, str]) -> bytes:
    """Mirror of :func:`app.stages.pii.presidio._encrypt_token_map`."""
    plaintext = json.dumps(payload).encode("utf-8")
    key = settings.pii_mask_key
    if not key:
        logger.warning("PII_MASK_KEY not set — redaction mapping stored unencrypted")
        return plaintext
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode()).encrypt(plaintext)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fernet encryption failed (%s) — storing redaction mapping unencrypted", exc)
        return plaintext


def save_encrypted(mapping: RedactionMapping, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encrypt(mapping.mock_to_original))


def save_index(mapping: RedactionMapping, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping.to_index(), indent=2))


def load_index(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def load_encrypted(path: Path) -> Dict[str, str] | None:
    """Decrypt + return the mock→original mapping. Returns ``None`` when the
    file is missing or the key isn't configured."""
    if not path.exists():
        return None
    blob = path.read_bytes()
    key = settings.pii_mask_key
    if not key:
        # The file may have been stored unencrypted (no key at write time).
        try:
            return json.loads(blob.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
    try:
        from cryptography.fernet import Fernet
        plaintext = Fernet(key.encode()).decrypt(blob)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        # Could be unencrypted JSON that was written without a key.
        try:
            return json.loads(blob.decode("utf-8"))
        except Exception:
            logger.warning("could not decrypt %s: %s", path, exc)
            return None
