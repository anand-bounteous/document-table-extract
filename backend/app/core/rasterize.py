"""Rasterize PDF pages to PNG at a target DPI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import fitz


@dataclass
class RasterPage:
    page_index: int
    dpi: int
    width: int
    height: int
    png_path: Path


def rasterize_pdf(pdf_path: Path, out_dir: Path, *, dpi: int = 300) -> List[RasterPage]:
    """Render every page of ``pdf_path`` to ``out_dir/page-<n>.png`` at ``dpi``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: List[RasterPage] = []
    doc = fitz.open(str(pdf_path))
    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            png = out_dir / f"page-{i:03d}.png"
            pix.save(str(png))
            pages.append(
                RasterPage(page_index=i, dpi=dpi, width=pix.width, height=pix.height, png_path=png)
            )
    finally:
        doc.close()
    return pages
