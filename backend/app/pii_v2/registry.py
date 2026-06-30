"""Detector registry — parallel to ``app.pipeline.base`` for the OCR/table side.

A detector registers itself at import time via :func:`register_detector`.
``app.pii_v2/__init__.py`` triggers ``detectors/`` import so registration is
side-effect-driven, exactly like the existing solution registry.
"""

from __future__ import annotations

from typing import Callable, Dict, Type

from app.pii_v2.base import BaseDetector

_REGISTRY: Dict[str, Type[BaseDetector]] = {}


def register_detector(cls: Type[BaseDetector]) -> Type[BaseDetector]:
    if not cls.name:
        raise ValueError(f"Detector {cls.__name__} has empty name")
    if cls.name in _REGISTRY:
        raise ValueError(f"Detector '{cls.name}' already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get_detector(name: str) -> Type[BaseDetector]:
    if name not in _REGISTRY:
        raise KeyError(f"Detector '{name}' not registered (have: {sorted(_REGISTRY)})")
    return _REGISTRY[name]


def list_detectors() -> Dict[str, Type[BaseDetector]]:
    return dict(_REGISTRY)


def describe_detectors() -> list[dict]:
    """Used by the /pii-benchmarks list endpoint."""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name or cls.name,
            "description": cls.description,
            "requires_models": list(cls.requires_models),
        }
        for cls in _REGISTRY.values()
    ]


def decorator() -> Callable[[Type[BaseDetector]], Type[BaseDetector]]:
    """Sugar: ``@register`` instead of ``register_detector(SomeDetector)``."""
    return register_detector


register = register_detector
