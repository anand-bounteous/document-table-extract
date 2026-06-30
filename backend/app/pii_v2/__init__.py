"""Independent PII detection + benchmarking subsystem.

This package implements the UK-banking PII detection POC described in
``.prompt/009-uk_banking_pii_detection_poc_plan.md``. It is intentionally
parallel to the existing in-pipeline ``app.stages.pii.presidio`` stage:

- ``pii_v2`` runs against extracted text (from any baseline OCR producer) and
  emits a normalised ``PIIEntity`` schema with risk + jurisdiction metadata.
- The existing ``PresidioPII`` stage stays untouched inside each OCR/table
  solution. Both coexist; both render their own dashboards.

Public surface: import ``PIIEntity`` from :mod:`.schema`, ``BaseDetector`` from
:mod:`.base`, and the detector registry from :mod:`.registry`.
"""

from app.pii_v2 import detectors as _detectors  # noqa: F401 — side-effect: register
from app.pii_v2.base import BaseDetector
from app.pii_v2.registry import get_detector, list_detectors, register_detector
from app.pii_v2.schema import PIIEntity

__all__ = [
    "BaseDetector",
    "PIIEntity",
    "get_detector",
    "list_detectors",
    "register_detector",
]
