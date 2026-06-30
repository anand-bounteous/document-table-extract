"""Tesseract OCR stage: word-level bbox + confidence → grouped Regions."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytesseract
from PIL import Image

from app.core.confidence import from_tesseract_word_conf, length_weighted
from app.core.geometry import bbox_from_xyxy
from app.core.schemas import BBox, Region, RegionType
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.tesseract")


@dataclass
class TesseractOCR:
    name: str = "ocr_tesseract"
    tool: str = "tesseract"
    use_preprocessed: bool = False
    psm: int = 6
    lang: str = "eng"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        for idx, page in state.pages.items():
            img_path = self._pick_image(idx, ctx, state)
            words = self._ocr(img_path, page.dpi, idx)
            regions = _group_words_to_regions(words, page_index=idx, dpi=page.dpi, tool=self.tool)
            page.regions.extend(regions)
            page.full_text = "\n".join(r.text for r in regions if r.text.strip())
            ctx.save_json(f"tesseract/page-{idx:03d}-words.json", [r.model_dump() for r in regions])
        return state

    def _pick_image(self, idx: int, ctx: RunContext, state: RunState) -> Path:
        if self.use_preprocessed:
            preproc: Dict[int, Path] = state.extras.get("preproc", {})
            if idx in preproc:
                return preproc[idx]
        return ctx.page_images[idx]

    def _ocr(self, img_path: Path, dpi: int, page_index: int) -> List[Region]:
        img = Image.open(img_path)
        config = f"--psm {self.psm}"
        data = pytesseract.image_to_data(
            img, lang=self.lang, config=config, output_type=pytesseract.Output.DICT
        )
        words: List[Region] = []
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            bbox = bbox_from_xyxy(
                data["left"][i],
                data["top"][i],
                data["left"][i] + data["width"][i],
                data["top"][i] + data["height"][i],
                page_index=page_index,
                dpi=dpi,
            )
            words.append(
                Region(
                    id=uuid.uuid4().hex[:10],
                    type=RegionType.NORMAL_TEXT,
                    bbox=bbox,
                    text=text,
                    confidence=from_tesseract_word_conf(conf),
                    raw_confidence=conf,
                    source_tool=self.tool,
                    attributes={
                        "block_num": data["block_num"][i],
                        "par_num": data["par_num"][i],
                        "line_num": data["line_num"][i],
                        "word_num": data["word_num"][i],
                    },
                )
            )
        return words


def _group_words_to_regions(
    words: List[Region], *, page_index: int, dpi: int, tool: str
) -> List[Region]:
    """Group word-level Regions into line-level Regions using tesseract block/par/line ids."""
    if not words:
        return []
    by_line: Dict[tuple, List[Region]] = {}
    for w in words:
        key = (
            w.attributes.get("block_num"),
            w.attributes.get("par_num"),
            w.attributes.get("line_num"),
        )
        by_line.setdefault(key, []).append(w)

    lines: List[Region] = []
    for key, line_words in by_line.items():
        line_words.sort(key=lambda r: r.bbox.x)
        text = " ".join(w.text for w in line_words)
        x1 = min(w.bbox.x for w in line_words)
        y1 = min(w.bbox.y for w in line_words)
        x2 = max(w.bbox.x2 for w in line_words)
        y2 = max(w.bbox.y2 for w in line_words)
        bbox = BBox(
            x=x1, y=y1, w=x2 - x1, h=y2 - y1, page_index=page_index, coord_space=f"image_px@{dpi}"
        )
        lines.append(
            Region(
                id=uuid.uuid4().hex[:10],
                type=RegionType.NORMAL_TEXT,
                bbox=bbox,
                text=text,
                confidence=length_weighted(line_words),
                source_tool=tool,
                attributes={"line_key": list(key), "word_count": len(line_words)},
            )
        )
    lines.sort(key=lambda r: (r.bbox.y, r.bbox.x))
    return lines
