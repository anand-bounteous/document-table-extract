"""Stub for ``common.file_utils``.

Only one symbol is consumed by ``deepdoc/vision/*``:
``get_project_base_directory()`` — used to locate the on-disk model cache.
Upstream returns the ragflow checkout root; we substitute the user's home
cache directory so model weights land somewhere durable per user.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_project_base_directory() -> str:
    """Return a directory where deepdoc can cache its ONNX model artifacts.

    Upstream uses this as the project root and reads from
    ``<root>/rag/res/deepdoc/`` for layout / TSR / OCR weights. We mirror
    that subpath under ``~/.cache/ragflow/`` so the cache survives
    re-installs and is shared across runs.
    """
    base = os.environ.get("RAGFLOW_DEEPDOC_CACHE") or os.path.expanduser("~/.cache/ragflow")
    Path(base).mkdir(parents=True, exist_ok=True)
    return base


def traversal_files(path):  # noqa: ANN001
    """Stub: only used by upstream CLI demos we don't vendor."""
    return []
