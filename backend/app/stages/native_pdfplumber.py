"""Native-PDF text + table extraction via pdfplumber.

pdfplumber (built on pdfminer.six) reads the PDF text layer directly and uses
geometric heuristics over PDF drawing operators to detect tables — both ruled
and whitespace-aligned. Vector PDFs only; runner auto-skips on scanned docs.

pdfplumber returns coordinates in PDF points (top-left origin matching its own
``page.bbox`` convention); we scale by ``dpi/72`` to land in the canonical
``image_px@<dpi>`` space.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, List, Tuple

from app.config import settings
from app.core.schemas import BBox, Region, RegionType, TableCell, TableModel
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.native_pdfplumber")


@dataclass
class NativePdfPlumberStage:
    name: str = "pdfplumber_native"
    tool: str = "pdfplumber"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        import pdfplumber  # type: ignore

        emit_visual = settings.native_pdf_emit_visual_codes

        with pdfplumber.open(str(ctx.pdf_path)) as pdf:
            for idx, page_result in state.pages.items():
                if idx >= len(pdf.pages):
                    continue
                page = pdf.pages[idx]
                dpi = page_result.dpi
                scale = dpi / 72.0

                with ctx.audit.time(
                    self.name, self.tool,
                    params={"emit_visual_codes": emit_visual, "page_index": idx},
                ) as h:
                    regions = _extract_text_regions(page, idx, dpi, scale, self.tool)
                    tables = _extract_tables(page, idx, dpi, scale)
                    extras = _extract_extras(page, idx, dpi, scale)

                    page_result.regions.extend(regions)
                    page_result.regions.extend(extras)
                    for tbl_region, tbl_model in tables:
                        page_result.regions.append(tbl_region)
                        page_result.tables.append(tbl_model)

                    page_result.full_text = "\n".join(r.text for r in regions if r.text.strip())
                    out_ref = ctx.save_json(
                        f"pdfplumber_native/page-{idx:03d}.json",
                        {
                            "regions": [r.model_dump() for r in regions],
                            "extras": [r.model_dump() for r in extras],
                            "tables": [t.model_dump() for _, t in tables],
                            "drawing": {
                                "lines": len(getattr(page, "lines", []) or []),
                                "rects": len(getattr(page, "rects", []) or []),
                                "curves": len(getattr(page, "curves", []) or []),
                            },
                        },
                    )
                    h.add_output(out_ref)
                    h.message = (
                        f"{len(regions)} regions, {len(tables)} tables, "
                        f"{len(extras)} extras"
                    )

                if emit_visual and idx in ctx.page_images:
                    _emit_visual_codes(ctx, page_result, idx)
        return state


def _emit_visual_codes(ctx: "RunContext", page_result: Any, page_index: int) -> None:
    """Same as the pymupdf-side helper — kept local so each stage stamps its own
    ``source_tool`` prefix and emits its own audit step.
    """
    page_image = ctx.page_images.get(page_index)
    if not page_image:
        return
    with ctx.audit.time(
        "visual_codes", "opencv+pyzbar",
        params={"page_index": page_index},
    ) as h:
        try:
            from app.pii_v2 import visual_extractor

            result = visual_extractor.extract_all(page_image)
            codes = result.get("codes", []) or []
            if not codes:
                h.skipped("no QR/barcode found")
                return
            coord = f"image_px@{page_result.dpi}"
            for code in codes:
                bbox_px = code.get("bbox_px") or {}
                x = float(bbox_px.get("x", 0))
                y = float(bbox_px.get("y", 0))
                w = float(bbox_px.get("w", 0))
                hgt = float(bbox_px.get("h", 0))
                if w <= 0 or hgt <= 0:
                    continue
                page_result.regions.append(
                    Region(
                        id=uuid.uuid4().hex[:10],
                        type=RegionType.IMAGE,
                        bbox=BBox(
                            x=x, y=y, w=w, h=hgt,
                            page_index=page_index, coord_space=coord,
                        ),
                        text=str(code.get("data") or ""),
                        confidence=float(code.get("score") or 0.9),
                        source_tool=f"pdfplumber+{code.get('source', 'cv2.qrcode')}",
                        attributes={
                            "object_type": "visual_code",
                            "code_type": code.get("type"),
                            "data": code.get("data"),
                            "source": code.get("source"),
                        },
                    )
                )
            h.message = f"{len(codes)} visual code(s) found"
        except Exception as exc:  # noqa: BLE001
            h.status = "error"
            h.message = f"{type(exc).__name__}: {exc}"


def _extract_text_regions(
    page: Any, page_index: int, dpi: int, scale: float, tool: str
) -> List[Region]:
    """Group word-level boxes into line-level Regions using pdfplumber.extract_words."""
    coord = f"image_px@{dpi}"
    out: List[Region] = []
    try:
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
    except Exception:  # noqa: BLE001
        return out

    # Group words by visually-distinct line: same `top` to within a small tolerance.
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda d: (round(float(d.get("top", 0)), 1), float(d.get("x0", 0)))):
        top = float(w.get("top", 0))
        if lines and abs(top - float(lines[-1][0].get("top", 0))) <= 2.0:
            lines[-1].append(w)
        else:
            lines.append([w])

    for line_words in lines:
        if not line_words:
            continue
        line_words.sort(key=lambda d: float(d.get("x0", 0)))
        text = " ".join(str(w.get("text", "")).strip() for w in line_words if w.get("text"))
        text = text.strip()
        if not text:
            continue
        x1 = min(float(w.get("x0", 0)) for w in line_words)
        y1 = min(float(w.get("top", 0)) for w in line_words)
        x2 = max(float(w.get("x1", 0)) for w in line_words)
        y2 = max(float(w.get("bottom", 0)) for w in line_words)
        bbox = BBox(
            x=x1 * scale,
            y=y1 * scale,
            w=(x2 - x1) * scale,
            h=(y2 - y1) * scale,
            page_index=page_index,
            coord_space=coord,
        )
        out.append(
            Region(
                id=uuid.uuid4().hex[:10],
                type=RegionType.NORMAL_TEXT,
                bbox=bbox,
                text=text,
                # Text comes directly from the PDF stream — no recognition.
                confidence=1.0,
                source_tool=tool,
                attributes={"word_count": len(line_words)},
            )
        )
    return out


_TABLE_STRATEGIES: List[Tuple[str, dict]] = [
    # default: ruled lines (rules drawn in the PDF). Works on bank statements
    # with visible borders. Fails silently on whitespace-aligned tables.
    ("lines", {"vertical_strategy": "lines", "horizontal_strategy": "lines"}),
    # text-position fallback: infers column/row boundaries from word x/y
    # clusters. Catches most invoice / statement tables without rules.
    ("text", {"vertical_strategy": "text", "horizontal_strategy": "text"}),
    # mixed strategy — vertical from rules, horizontal from text alignment.
    # Useful when the PDF has column dividers but no row borders.
    ("mixed", {"vertical_strategy": "lines", "horizontal_strategy": "text"}),
]


def _extract_tables(
    page: Any, page_index: int, dpi: int, scale: float
) -> List[Tuple[Region, TableModel]]:
    """Use pdfplumber's find_tables() across multiple strategies.

    Default ``find_tables()`` only uses ruled lines and misses whitespace
    tables entirely — empirically that's why our cards stayed empty on most
    bank statements. We try the three common strategies and emit tables from
    the first one that returns any, deduplicating by bbox-overlap.
    """
    coord = f"image_px@{dpi}"
    results: List[Tuple[Region, TableModel]] = []

    found: List[Any] = []
    chosen_strategy = "none"
    for strategy_name, settings in _TABLE_STRATEGIES:
        try:
            candidate = page.find_tables(settings) or []
        except Exception:  # noqa: BLE001
            continue
        if candidate:
            found = candidate
            chosen_strategy = strategy_name
            break

    for tbl in found:
        try:
            bbox_pts = tbl.bbox
            extracted = tbl.extract() or []
        except Exception:  # noqa: BLE001
            continue
        if not bbox_pts or len(bbox_pts) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox_pts)
        region_id = uuid.uuid4().hex[:10]
        table_bbox = BBox(
            x=x1 * scale,
            y=y1 * scale,
            w=(x2 - x1) * scale,
            h=(y2 - y1) * scale,
            page_index=page_index,
            coord_space=coord,
        )
        region = Region(
            id=region_id,
            type=RegionType.TABLE,
            bbox=table_bbox,
            text="",
            confidence=1.0,
            source_tool="pdfplumber",
            attributes={
                "detector": "pdfplumber.find_tables",
                "strategy": chosen_strategy,
            },
        )

        n_rows = len(extracted)
        n_cols = max((len(r) for r in extracted), default=0)
        cells: List[TableCell] = []
        cell_rects = getattr(tbl, "cells", None) or []
        for r_idx, row in enumerate(extracted):
            for c_idx, raw_text in enumerate(row):
                text = "" if raw_text is None else str(raw_text)
                # pdfplumber.tbl.cells is a flat list of (x0, top, x1, bottom)
                # in row-major order; reconstruct an index.
                flat_idx = r_idx * n_cols + c_idx
                cell_bbox = None
                if flat_idx < len(cell_rects):
                    rect = cell_rects[flat_idx]
                    if rect is not None and len(rect) == 4:
                        cx1, cy1, cx2, cy2 = (float(v) for v in rect)
                        cell_bbox = BBox(
                            x=cx1 * scale,
                            y=cy1 * scale,
                            w=(cx2 - cx1) * scale,
                            h=(cy2 - cy1) * scale,
                            page_index=page_index,
                            coord_space=coord,
                        )
                cells.append(
                    TableCell(
                        row=r_idx,
                        col=c_idx,
                        text=text,
                        bbox=cell_bbox,
                        multiline="\n" in text,
                    )
                )

        results.append(
            (
                region,
                TableModel(
                    region_id=region_id,
                    orientation="horizontal",
                    border_mode="ruled" if chosen_strategy == "lines" else (
                        "whitespace" if chosen_strategy == "text" else "mixed"
                    ),
                    n_rows=n_rows,
                    n_cols=n_cols,
                    cells=cells,
                ),
            )
        )
    return results


def _extract_extras(
    page: Any, page_index: int, dpi: int, scale: float
) -> List[Region]:
    """Pull embedded images, hyperlinks, and annotations as Regions.

    pdfplumber exposes these as plain dicts with ``x0/top/x1/bottom`` in PDF
    points. They give us more information per card than just text + tables —
    a financial statement carries logos (images), email/web hyperlinks, and
    sometimes reviewer annotations.
    """
    coord = f"image_px@{dpi}"
    out: List[Region] = []

    def _to_bbox(item: dict) -> "BBox | None":
        try:
            x0 = float(item.get("x0", item.get("x", 0)))
            y0 = float(item.get("top", item.get("y0", 0)))
            x1 = float(item.get("x1", x0))
            y1 = float(item.get("bottom", item.get("y1", y0)))
        except (TypeError, ValueError):
            return None
        if x1 <= x0 or y1 <= y0:
            return None
        return BBox(
            x=x0 * scale,
            y=y0 * scale,
            w=(x1 - x0) * scale,
            h=(y1 - y0) * scale,
            page_index=page_index,
            coord_space=coord,
        )

    for img in (getattr(page, "images", None) or []):
        bbox = _to_bbox(img)
        if bbox is None:
            continue
        out.append(Region(
            id=uuid.uuid4().hex[:10],
            type=RegionType.IMAGE,
            bbox=bbox,
            text="",
            confidence=1.0,
            source_tool="pdfplumber",
            attributes={
                "name": str(img.get("name", "")),
                "object_type": "image",
                "width": img.get("width"),
                "height": img.get("height"),
            },
        ))

    for link in (getattr(page, "hyperlinks", None) or []):
        bbox = _to_bbox(link)
        if bbox is None:
            continue
        uri = str(link.get("uri") or link.get("URI") or "")
        out.append(Region(
            id=uuid.uuid4().hex[:10],
            type=RegionType.KV_PAIR,
            bbox=bbox,
            text=uri,
            confidence=1.0,
            source_tool="pdfplumber",
            attributes={"object_type": "hyperlink", "uri": uri},
        ))

    for ann in (getattr(page, "annots", None) or []):
        bbox = _to_bbox(ann)
        if bbox is None:
            continue
        subtype = str(ann.get("subtype") or ann.get("Subtype") or "")
        contents = ann.get("contents") or ann.get("Contents") or ""
        # contents can be bytes/PDFString; cast defensively
        try:
            text = str(contents)
        except Exception:  # noqa: BLE001
            text = ""
        out.append(Region(
            id=uuid.uuid4().hex[:10],
            type=RegionType.KV_PAIR,
            bbox=bbox,
            text=text,
            confidence=1.0,
            source_tool="pdfplumber",
            attributes={"object_type": "annotation", "subtype": subtype},
        ))

    return out
