"""Detect whether a PDF is vector (has real text) or scanned (image-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import fitz

from app.core.schemas import PdfKind


def classify(path: Path, *, min_chars_per_page: int = 32) -> Tuple[PdfKind, int]:
    """Return (kind, n_pages).

    Heuristic: a page with >= ``min_chars_per_page`` extractable characters
    counts as vector. If every page passes, the doc is ``vector``; if none do,
    ``scanned``; otherwise ``mixed``.
    """
    doc = fitz.open(str(path))
    try:
        n = doc.page_count
        if n == 0:
            return "unknown", 0
        vector_pages = 0
        for p in doc:
            txt = p.get_text("text") or ""
            if len(txt.strip()) >= min_chars_per_page:
                vector_pages += 1
        if vector_pages == n:
            return "vector", n
        if vector_pages == 0:
            return "scanned", n
        return "mixed", n
    finally:
        doc.close()
