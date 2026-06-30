"""Stub for ``rag.nlp.rag_tokenizer``.

Upstream is a heavy CJK-aware tokenizer with HMM-based segmentation. The only
calls we observe in vendored ``deepdoc/vision/*``:

- ``rag_tokenizer.tokenize(text)``  — returns space-separated tokens.
- ``rag_tokenizer.tag(token)``      — returns a POS-ish tag, only checked
  against the literal string ``"nr"`` (Chinese personal-name marker) in
  ``table_structure_recognizer.py`` for surname disambiguation.

For English bank statements and most benchmark documents in this harness,
whitespace tokenization + a non-``"nr"`` tag is correct. CJK accuracy will
degrade but the benchmark still runs end-to-end.
"""

from __future__ import annotations

import re


def tokenize(text: str) -> str:
    """Whitespace-tokenize ``text``. Matches upstream's interface: it returns
    a single string with tokens joined by spaces (callers .split()) ."""
    if not text:
        return ""
    return " ".join(re.findall(r"\S+", text))


def tag(token: str) -> str:  # noqa: ARG001
    """Always-non-"nr" stub. Upstream uses this for CJK personal-name
    detection in table-structure heuristics; English-only docs aren't
    affected."""
    return "n"
