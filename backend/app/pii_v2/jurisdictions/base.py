"""Jurisdiction plugin contract (.prompt/009 §4.3)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Optional

ValidatorFn = Callable[[str], bool]


@dataclass
class RecognizerSpec:
    """A regex-based recogniser combined with optional validator + context boost."""

    entity_type: str
    pattern: str
    score: float = 0.5
    jurisdiction: str = "GLOBAL_COMMON"
    context_terms: List[str] = field(default_factory=list)
    context_boost: float = 0.2
    validator: Optional[ValidatorFn] = None
    flags: int = re.IGNORECASE

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


class JurisdictionPlugin(ABC):
    code: str = ""
    display_name: str = ""

    @abstractmethod
    def get_recognizers(self) -> List[RecognizerSpec]: ...

    def get_test_cases(self) -> List[dict]:
        return []
