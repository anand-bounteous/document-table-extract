"""Stub for RAGFlow's ``common`` package — only what ``deepdoc/vision/*`` reads.

Upstream's ``common/__init__.py`` re-exports a ``settings`` module — keep that
shape so ``from common import settings`` works.
"""

from . import settings  # noqa: F401
