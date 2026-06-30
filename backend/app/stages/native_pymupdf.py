"""Native-PDF text + table extraction via PyMuPDF.

Reads the PDF's text layer directly — no rasterization, no OCR. Vector PDFs
only; the runner skips this solution automatically when ``pdf_kind`` is
``scanned``. Mixed PDFs are not currently supported (only fully vector docs).

PyMuPDF returns coordinates in PDF points (top-left origin in pymupdf's
``rect``); we scale by ``dpi/72`` to land in the canonical ``image_px@<dpi>``
space.

The stage runs three enrichment passes after the bare text/table extraction,
each gated by a config flag:

* ``native_pymupdf_emit_font_details`` — stamp font name / size / color /
  bold / italic / underline-flag from ``get_text("dict")`` spans onto every
  text region's ``attributes``.
* ``native_pymupdf_emit_drawings`` — walk ``get_drawings()`` and label each
  text region with its background_color (rect fills underneath the line) and
  a has_underline flag (horizontal stroke just below the baseline).
* ``native_pymupdf_emit_template`` — emit a per-page "template" artifact
  pair: ``template.pdf`` (vector PDF with every text run redacted) and
  ``template-NNN.png`` (raster of same). Useful for downstream layout
  benchmarking — same graphics + images, no text.

The cross-cutting ``native_pdf_emit_visual_codes`` flag (shared with
pdfplumber) also runs here when enabled — QR/barcodes from the page raster
become first-class regions.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.core.schemas import BBox, Region, RegionType, TableCell, TableModel
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.native_pymupdf")


# PyMuPDF span "flags" bitfield. Documented in
# https://pymupdf.readthedocs.io/en/latest/textpage.html#text-extraction-flags
_FLAG_SUPERSCRIPT = 1
_FLAG_ITALIC = 2
_FLAG_SERIFED = 4
_FLAG_MONOSPACED = 8
_FLAG_BOLD = 16


def _flag_bold(flags: int, fontname: str) -> bool:
    if flags & _FLAG_BOLD:
        return True
    f = (fontname or "").lower()
    return any(tok in f for tok in ("-bold", "bold", "black", "heavy"))


def _flag_italic(flags: int, fontname: str) -> bool:
    if flags & _FLAG_ITALIC:
        return True
    f = (fontname or "").lower()
    return any(tok in f for tok in ("-italic", "italic", "oblique"))


def _color_to_hex(color_int: Any) -> Optional[str]:
    """PyMuPDF reports color as an sRGB-packed int (0xRRGGBB)."""
    try:
        i = int(color_int)
    except (TypeError, ValueError):
        return None
    if i < 0:
        return None
    return f"#{i:06x}"


def _bbox_overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


@dataclass
class NativePyMuPDFStage:
    name: str = "pymupdf_native"
    tool: str = "pymupdf"

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        import fitz  # type: ignore

        emit_font = settings.native_pymupdf_emit_font_details
        emit_drawings = settings.native_pymupdf_emit_drawings
        emit_template = settings.native_pymupdf_emit_template
        emit_visual = settings.native_pdf_emit_visual_codes

        doc = fitz.open(str(ctx.pdf_path))
        try:
            for idx, page_result in state.pages.items():
                if idx >= doc.page_count:
                    continue
                page = doc[idx]
                dpi = page_result.dpi
                scale = dpi / 72.0

                with ctx.audit.time(
                    self.name, self.tool,
                    params={
                        "emit_font_details": emit_font,
                        "emit_drawings": emit_drawings,
                        "emit_template": emit_template,
                        "emit_visual_codes": emit_visual,
                        "page_index": idx,
                    },
                ) as h:
                    regions = _extract_text_regions(page, idx, dpi, scale, self.tool, emit_font)
                    tables = _extract_tables(page, idx, dpi, scale)

                    if emit_drawings and regions:
                        _enrich_with_drawings(page, regions, scale)

                    # Persist text regions
                    page_result.regions.extend(regions)
                    for tbl_region, tbl_model in tables:
                        page_result.regions.append(tbl_region)
                        page_result.tables.append(tbl_model)

                    page_result.full_text = "\n".join(r.text for r in regions if r.text.strip())

                    out_ref = ctx.save_json(
                        f"pymupdf_native/page-{idx:03d}.json",
                        {
                            "regions": [r.model_dump() for r in regions],
                            "tables": [t.model_dump() for _, t in tables],
                            "flags": {
                                "font_details": emit_font,
                                "drawings": emit_drawings,
                            },
                        },
                    )
                    h.add_output(out_ref)
                    h.message = (
                        f"{len(regions)} regions, {len(tables)} tables"
                        f"{' [+font]' if emit_font else ''}"
                        f"{' [+bg/underline]' if emit_drawings else ''}"
                    )

                # Optional template artifact pass.
                if emit_template:
                    _emit_template_artifacts(ctx, doc, idx, dpi)

                # Optional visual-code pass (raster-based; reuses pii_v2 extractor).
                if emit_visual and idx in ctx.page_images:
                    _emit_visual_codes(ctx, page_result, idx)
        finally:
            doc.close()
        return state


def _extract_text_regions(
    page: Any, page_index: int, dpi: int, scale: float, tool: str, emit_font: bool,
) -> List[Region]:
    """Pull line-level text Regions from page.get_text("dict")."""
    out: List[Region] = []
    coord = f"image_px@{dpi}"
    try:
        data = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return out

    for block in data.get("blocks", []) or []:
        if block.get("type", 0) != 0:  # 0 = text block, 1 = image
            continue
        for line in block.get("lines", []) or []:
            spans = line.get("spans", []) or []
            text_parts: List[str] = []
            for span in spans:
                t = (span.get("text") or "").strip()
                if t:
                    text_parts.append(t)
            text = " ".join(text_parts).strip()
            bbox_pts = line.get("bbox")
            if not text or not bbox_pts or len(bbox_pts) != 4:
                continue
            x1, y1, x2, y2 = (float(v) for v in bbox_pts)
            bbox = BBox(
                x=x1 * scale,
                y=y1 * scale,
                w=(x2 - x1) * scale,
                h=(y2 - y1) * scale,
                page_index=page_index,
                coord_space=coord,
            )
            attrs: Dict[str, Any] = {"span_count": len(spans)}
            if emit_font and spans:
                # Dominant span = first non-empty span. For mixed-style lines we
                # also expose the per-span style list so the UI can chip-render it.
                primary = next((s for s in spans if (s.get("text") or "").strip()), spans[0])
                fontname = str(primary.get("font", ""))
                flags = int(primary.get("flags", 0) or 0)
                attrs["font"] = fontname
                attrs["font_size"] = float(primary.get("size", 0) or 0)
                attrs["font_color"] = _color_to_hex(primary.get("color"))
                attrs["bold"] = _flag_bold(flags, fontname)
                attrs["italic"] = _flag_italic(flags, fontname)
                # PyMuPDF doesn't carry an "underline" flag — that comes from
                # the drawing pass below (set to None as a sentinel here so a
                # consumer can distinguish "no drawing pass ran" from "no
                # underline").
                attrs["underline"] = None
                # bg_color also filled by the drawing pass.
                attrs["bg_color"] = None
                # Per-span style detail (only when the line has > 1 style).
                if len(spans) > 1:
                    attrs["spans_style"] = [
                        {
                            "text": (s.get("text") or "").strip(),
                            "font": s.get("font"),
                            "size": s.get("size"),
                            "color": _color_to_hex(s.get("color")),
                            "bold": _flag_bold(int(s.get("flags", 0) or 0), str(s.get("font", ""))),
                            "italic": _flag_italic(int(s.get("flags", 0) or 0), str(s.get("font", ""))),
                        }
                        for s in spans
                    ]
            out.append(
                Region(
                    id=uuid.uuid4().hex[:10],
                    type=RegionType.NORMAL_TEXT,
                    bbox=bbox,
                    text=text,
                    confidence=1.0,
                    source_tool=tool,
                    attributes=attrs,
                )
            )
    return out


def _enrich_with_drawings(page: Any, regions: List[Region], scale: float) -> None:
    """Walk ``page.get_drawings()`` for fills + horizontal strokes.

    For each text region we look for:
      * a filled rect whose bbox covers ≥ 50% of the region's bbox →
        ``bg_color = #rrggbb`` of that fill (excluding white).
      * a horizontal stroke just below the region baseline (within ~2pt) →
        ``underline = True``.
    """
    try:
        drawings = page.get_drawings() or []
    except Exception:  # noqa: BLE001
        return

    fills: List[Tuple[Tuple[float, float, float, float], str]] = []
    underlines: List[Tuple[float, float, float, float]] = []
    for d in drawings:
        rect = d.get("rect")
        if rect is None or len(rect) != 4:
            continue
        # PyMuPDF Rect supports x0,y0,x1,y1
        try:
            x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        bbox_pts = (x0, y0, x1, y1)
        d_type = d.get("type") or ""
        fill = d.get("fill")
        if fill is not None and ("f" in d_type or d_type == "f"):
            # Skip pure-white fills (don't count as a real background).
            hex_color = _rgb_seq_to_hex(fill)
            if hex_color and hex_color.lower() != "#ffffff":
                fills.append((bbox_pts, hex_color))
        if ("s" in d_type or d_type == "s") and (y1 - y0) < 3.0 and (x1 - x0) > 8.0:
            underlines.append(bbox_pts)

    if not fills and not underlines:
        return

    for r in regions:
        # Region bbox is in image_px; convert back to PDF points for comparison.
        rx1 = r.bbox.x / scale
        ry1 = r.bbox.y / scale
        rx2 = rx1 + r.bbox.w / scale
        ry2 = ry1 + r.bbox.h / scale
        r_area = max(1e-6, (rx2 - rx1) * (ry2 - ry1))

        # Background: pick the fill with the largest overlap, if ≥ 50%.
        best_fill: Optional[Tuple[float, str]] = None
        for (b, hex_color) in fills:
            overlap = _bbox_overlap((rx1, ry1, rx2, ry2), b)
            frac = overlap / r_area
            if frac >= 0.5 and (best_fill is None or frac > best_fill[0]):
                best_fill = (frac, hex_color)
        if best_fill is not None:
            r.attributes["bg_color"] = best_fill[1]
            r.attributes["bg_color_overlap"] = round(best_fill[0], 2)

        # Underline: horizontal stroke whose y is within 2pt of the baseline
        # and whose x-extent overlaps the line by at least 60%.
        for (bx1, by1, bx2, by2) in underlines:
            below_baseline = (ry2 - 1.0) <= by1 <= (ry2 + 3.0)
            if not below_baseline:
                continue
            stroke_w = bx2 - bx1
            line_w = max(1e-6, rx2 - rx1)
            x_overlap = max(0.0, min(bx2, rx2) - max(bx1, rx1))
            if (x_overlap / line_w) >= 0.6 and stroke_w >= 0.4 * line_w:
                r.attributes["underline"] = True
                break
        else:
            # Only stamp False when the pass actually ran; leaves it as None
            # if there were no underline candidates at all (so the UI can
            # still tell the difference).
            if underlines and r.attributes.get("underline") is None:
                r.attributes["underline"] = False


def _rgb_seq_to_hex(seq: Any) -> Optional[str]:
    """PyMuPDF fills are tuples of floats in [0,1]; convert to #rrggbb."""
    try:
        if seq is None:
            return None
        if isinstance(seq, (int, float)):
            # Single-channel (grayscale): treat as gray.
            v = int(max(0.0, min(1.0, float(seq))) * 255)
            return f"#{v:02x}{v:02x}{v:02x}"
        if len(seq) == 1:
            v = int(max(0.0, min(1.0, float(seq[0]))) * 255)
            return f"#{v:02x}{v:02x}{v:02x}"
        if len(seq) >= 3:
            r = int(max(0.0, min(1.0, float(seq[0]))) * 255)
            g = int(max(0.0, min(1.0, float(seq[1]))) * 255)
            b = int(max(0.0, min(1.0, float(seq[2]))) * 255)
            return f"#{r:02x}{g:02x}{b:02x}"
    except (TypeError, ValueError):
        return None
    return None


def _emit_template_artifacts(ctx: "RunContext", doc: Any, page_index: int, dpi: int) -> None:
    """Write a `template.pdf` (every text run redacted) + `template-NNN.png`.

    Implementation: open a fresh copy of the PDF so we don't mutate the
    primary doc, redact every text bbox on the page, apply, render to PNG.
    PyMuPDF's ``add_redact_annot`` + ``apply_redactions`` strips the underlying
    text content; whether **images** and **line-art / graphics** survive is
    controlled by two config flags (both default ``False`` — preserve):

    * ``native_pymupdf_template_remove_images`` — when True, images that
      overlap a text bbox are blanked out (``apply_redactions(images=2)``).
    * ``native_pymupdf_template_remove_graphics`` — when True, vector
      line-art / fills contained in a text bbox are removed
      (``apply_redactions(graphics=1)``).
    """
    import fitz  # type: ignore

    remove_images = settings.native_pymupdf_template_remove_images
    remove_graphics = settings.native_pymupdf_template_remove_graphics
    images_mode = 2 if remove_images else 0      # 0 = ignore, 2 = blank pixels
    graphics_mode = 1 if remove_graphics else 0  # 0 = ignore, 1 = remove if contained

    with ctx.audit.time(
        "pymupdf_template", "pymupdf",
        params={
            "page_index": page_index,
            "dpi": dpi,
            "remove_images": remove_images,
            "remove_graphics": remove_graphics,
        },
    ) as h:
        try:
            tdoc = fitz.open(str(ctx.pdf_path))
            try:
                if page_index >= tdoc.page_count:
                    h.skipped(f"page {page_index} out of range")
                    return
                tpage = tdoc[page_index]
                # Walk every text line, add a redact annot covering its bbox.
                try:
                    text_dict = tpage.get_text("dict")
                except Exception:  # noqa: BLE001
                    h.skipped("get_text(dict) failed")
                    return
                n_redacted = 0
                for block in text_dict.get("blocks", []) or []:
                    if block.get("type", 0) != 0:
                        continue
                    for line in block.get("lines", []) or []:
                        bb = line.get("bbox")
                        if not bb or len(bb) != 4:
                            continue
                        rect = fitz.Rect(*[float(v) for v in bb])
                        # fill=None → don't paint a rectangle over the area;
                        # apply_redactions(images=0, graphics=0, text=0) keeps
                        # the background graphics intact and removes ONLY the
                        # text glyphs. Result: page looks like the original
                        # with the characters erased, not white boxes pasted on.
                        tpage.add_redact_annot(rect, fill=None)
                        n_redacted += 1
                if n_redacted == 0:
                    h.skipped("no text lines on page")
                    return
                tpage.apply_redactions(images=images_mode, graphics=graphics_mode, text=0)

                pdf_ref = ctx.save_bytes(
                    f"pymupdf_native/template/template-{page_index:03d}.pdf",
                    tdoc.convert_to_pdf(from_page=page_index, to_page=page_index),
                )
                # Render the redacted page as PNG.
                zoom = dpi / 72.0
                pix = tpage.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                png_ref = ctx.save_bytes(
                    f"pymupdf_native/template/template-{page_index:03d}.png",
                    pix.tobytes("png"),
                )
                h.add_output(pdf_ref)
                h.add_output(png_ref)
                kept = []
                if not remove_images:
                    kept.append("images")
                if not remove_graphics:
                    kept.append("graphics")
                kept_str = ("kept " + "+".join(kept)) if kept else "stripped images+graphics"
                h.message = f"redacted {n_redacted} text lines · {kept_str}"
            finally:
                tdoc.close()
        except Exception as exc:  # noqa: BLE001
            h.status = "error"
            h.message = f"{type(exc).__name__}: {exc}"


def _emit_visual_codes(ctx: "RunContext", page_result: Any, page_index: int) -> None:
    """Run pii_v2.visual_extractor on the page raster; emit QR/barcode Regions."""
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
                        source_tool=f"pymupdf+{code.get('source', 'cv2.qrcode')}",
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


def _extract_tables(
    page: Any, page_index: int, dpi: int, scale: float
) -> List[Tuple[Region, TableModel]]:
    """Use PyMuPDF's find_tables() to detect ruled+whitespace tables on the page."""
    coord = f"image_px@{dpi}"
    results: List[Tuple[Region, TableModel]] = []

    try:
        finder = page.find_tables()
    except Exception:  # noqa: BLE001
        # find_tables() requires pymupdf >= 1.23; if missing or it bails on this
        # page, just skip silently.
        return results

    tables_attr = getattr(finder, "tables", None) or []
    for tbl in tables_attr:
        try:
            bbox_pts = tbl.bbox
            extracted: List[List[Any]] = tbl.extract() or []
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
            source_tool="pymupdf",
            attributes={"detector": "pymupdf.find_tables"},
        )

        n_rows = len(extracted)
        n_cols = max((len(r) for r in extracted), default=0)
        cells: List[TableCell] = []
        rows_attr = getattr(tbl, "rows", None) or []
        for r_idx, row in enumerate(extracted):
            row_cell_rects = []
            if r_idx < len(rows_attr):
                row_cell_rects = getattr(rows_attr[r_idx], "cells", None) or []
            for c_idx, raw_text in enumerate(row):
                text = "" if raw_text is None else str(raw_text)
                cell_bbox = None
                if c_idx < len(row_cell_rects):
                    rect = row_cell_rects[c_idx]
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
                    border_mode="mixed",
                    n_rows=n_rows,
                    n_cols=n_cols,
                    cells=cells,
                ),
            )
        )
    return results
