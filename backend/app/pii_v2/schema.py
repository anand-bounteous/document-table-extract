"""Common output schema shared by every pii_v2 detector.

Mirrors .prompt/009 §7. Detectors return ``list[PIIEntity]``; the merger,
masker, and benchmark evaluator all operate on this shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PIIEntity:
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    source: str            # which recogniser / sub-model produced this span
    detection_method: str  # "regex" | "ner" | "ml" | "hybrid" | "validator"
    jurisdiction: Optional[str] = None
    risk_level: Optional[str] = None          # "high" | "medium" | "low"
    sensitivity_category: Optional[str] = None  # "personal_data" | "special_category" | ...
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "score": self.score,
            "source": self.source,
            "detection_method": self.detection_method,
            "jurisdiction": self.jurisdiction,
            "risk_level": self.risk_level,
            "sensitivity_category": self.sensitivity_category,
            "metadata": self.metadata,
        }


@dataclass
class DetectorResult:
    """One detector's output for a single text input."""

    detector_name: str
    entities: List[PIIEntity]
    text_len: int
    latency_ms: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detector_name": self.detector_name,
            "entities": [e.to_dict() for e in self.entities],
            "text_len": self.text_len,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class BenchmarkRecord:
    """One annotated record from a JSONL benchmark dataset (.prompt/009 §13)."""

    id: str
    text: str
    entities: List[PIIEntity]
    metadata: Dict[str, Any] = field(default_factory=dict)
