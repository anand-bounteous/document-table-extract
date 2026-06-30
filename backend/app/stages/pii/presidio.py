"""PII detection over already-normalized Regions.

Two-pass design:
  1. Detect every PII span Presidio + UK regex find.
  2. Universal mask: for each detected value, scan every region on every page
     for that same substring and emit a PII span there too — catching cases
     Presidio missed (e.g. an account number repeated outside a labelled
     context, or a name reappearing in a table cell).

Outputs:
  * Each Region's `pii_spans` is populated with bboxes + masked text + the
    Fernet token id (in `attributes["token"]`) so the API can reveal the
    original later.
  * `pii/token-map.fernet` — Fernet-encrypted JSON `{token: original}`.
  * `pii/page-NNN-redacted.png` — always written when PII is present;
     filled black rectangles over every PII bbox (used by Claude Vision pre-mask).
  * `pii/page-NNN-masked.png` — annotated red boxes (transparent fill) +
     redacted text overlay; this is the "show me the masked image" artifact
     users link to from the UI.
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.core.schemas import BBox, PiiSpan, Region
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.pii")

UK_SORT_CODE_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
UK_ACCOUNT_CTX_RE = re.compile(
    r"\b(?:account(?:\s*(?:no\.?|number|#))?|a/c)\b[^0-9]{0,16}(\d{8})\b", re.I
)
UK_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)


@dataclass
class PresidioPII:
    name: str = "pii_presidio"
    tool: str = "presidio+regex"
    redact_image: bool = True
    universal_mask: bool = True
    mask_char: str = "*"
    min_universal_len: int = 4

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        analyzer = _try_load_presidio()

        # ---- Pass 1: per-region detection -------------------------------
        token_map: Dict[str, str] = {}  # token -> original
        value_to_token: Dict[str, str] = {}  # original -> token (reuse)
        value_to_entity: Dict[str, str] = {}  # original -> entity_type
        detected_per_page: Dict[int, List[Tuple[Region, PiiSpan]]] = {idx: [] for idx in state.pages}

        # On resume the runner records already-processed page indices in
        # ``ctx.skip_pages``. Skipping them here keeps the redaction
        # idempotent — without this, region.pii_spans would get the same
        # entities appended again on every resume pass.
        skip_pages = set(getattr(ctx, "skip_pages", None) or ())

        for idx, page in state.pages.items():
            if idx in skip_pages:
                continue
            for region in page.regions:
                for span in _analyze(region.text, analyzer=analyzer):
                    raw_value = region.text[span.start : span.end]
                    if not raw_value.strip():
                        continue
                    token, entity = self._record(raw_value, span.entity_type, token_map, value_to_token, value_to_entity)
                    span.masked_value = _mask_value(raw_value, entity, self.mask_char)
                    span.bbox = _span_bbox(region, span)
                    region.pii_spans.append(span)
                    region.attributes.setdefault("pii_tokens", []).append(token)
                    self._tag_span_with_token(span, token)
                    detected_per_page[idx].append((region, span))

        # ---- Pass 2: universal mask -------------------------------------
        if self.universal_mask and value_to_token:
            for idx, page in state.pages.items():
                if idx in skip_pages:
                    continue
                for region in page.regions:
                    additions = _find_extra_occurrences(
                        region, value_to_token, value_to_entity, min_len=self.min_universal_len
                    )
                    for new_span in additions:
                        raw_value = region.text[new_span.start : new_span.end]
                        entity = value_to_entity.get(raw_value, new_span.entity_type)
                        token = value_to_token[raw_value]
                        new_span.masked_value = _mask_value(raw_value, entity, self.mask_char)
                        new_span.bbox = _span_bbox(region, new_span)
                        self._tag_span_with_token(new_span, token)
                        region.pii_spans.append(new_span)
                        detected_per_page[idx].append((region, new_span))

        # ---- Persist + render --------------------------------------------
        if token_map:
            ctx.save_bytes("pii/token-map.fernet", _encrypt_token_map(token_map))
            ctx.save_json("pii/token-map.index.json", {
                "n_tokens": len(token_map),
                "values": sorted({value_to_entity[v]: 0 for v in value_to_entity}.keys()),
            })

        for idx, items in detected_per_page.items():
            if not items or idx in skip_pages:
                continue
            png = ctx.page_images.get(idx)
            if png is None:
                # Defensive — shouldn't happen now that ctx.page_images is
                # always kept complete, but skip rather than crash.
                continue
            if self.redact_image:
                ctx.save_bytes(
                    f"pii/page-{idx:03d}-redacted.png",
                    _redacted_image(png, items),
                )
                state.extras.setdefault("pii_redacted", {})[idx] = ctx.artifact_path(
                    f"pii/page-{idx:03d}-redacted.png"
                )
            ctx.save_bytes(
                f"pii/page-{idx:03d}-masked.png",
                _masked_overlay_image(png, items),
            )

        # Same-length mock-redacted variants — feeds the new run-dashboard
        # PII card so the legacy OCR flow can also pass safe text/image to
        # an LLM. Single global mock_to_original mapping per solution: same
        # original always maps to the same mock across pages, so the file
        # the user downloads to "restore" later is small and stable.
        self._emit_mock_variants(ctx, detected_per_page, skip_pages)

        return state

    def _emit_mock_variants(
        self,
        ctx: "RunContext",
        detected_per_page: Dict[int, List[Tuple[Region, PiiSpan]]],
        skip_pages: set,
    ) -> None:
        """Bridge into ``app.pii_v2.redaction`` to produce same-length mocks +
        annotated/clean redacted PNGs + an encrypted mock→original mapping.

        Falls back gracefully when the redaction module isn't importable
        (e.g. a constrained install). Per-page failures are logged + skipped
        — never break the run.
        """
        try:
            from app.pii_v2.redaction.image_redactor import redact_image as _redact_image
            from app.pii_v2.redaction.mapping import RedactionMapping, save_encrypted, save_index
            from app.pii_v2.redaction.mock_generators import mock_for
            from app.pii_v2.redaction.text_redactor import DiffSpan
        except ImportError:
            logger.info("pii_v2.redaction unavailable; skipping mock variants")
            return

        import hashlib
        import random as _random

        run_seed = f"{ctx.run_id}::{ctx.solution_name}"
        mock_to_original: Dict[str, str] = {}
        original_to_mock: Dict[str, str] = {}
        entity_type_counts: Dict[str, int] = {}

        def _mock_for(original: str, entity_type: str) -> str:
            key = f"{entity_type}::{original}"
            if key in original_to_mock:
                return original_to_mock[key]
            seed_bytes = hashlib.sha256(
                f"{run_seed}::{entity_type}::{original}".encode("utf-8")
            ).digest()
            rng = _random.Random(int.from_bytes(seed_bytes[:8], "big"))
            mock = mock_for(entity_type, original, rng)
            original_to_mock[key] = mock
            mock_to_original[mock] = original
            return mock

        for idx, items in detected_per_page.items():
            if not items or idx in skip_pages:
                continue
            png = ctx.page_images.get(idx)
            if png is None:
                continue
            diff_spans: List[DiffSpan] = []
            for region, span in items:
                value = region.text[span.start : span.end]
                if not value:
                    continue
                mock = _mock_for(value, span.entity_type)
                entity_type_counts[span.entity_type] = (
                    entity_type_counts.get(span.entity_type, 0) + 1
                )
                bbox = span.bbox
                bbox_dict = (
                    {
                        "x": float(bbox.x),
                        "y": float(bbox.y),
                        "w": float(bbox.w),
                        "h": float(bbox.h),
                        "page_index": int(bbox.page_index),
                        "coord_space": bbox.coord_space,
                    }
                    if bbox is not None
                    else None
                )
                diff_spans.append(DiffSpan(
                    start=span.start,
                    end=span.end,
                    original=value,
                    mock=mock,
                    entity_type=span.entity_type,
                    bbox_px=bbox_dict,
                ))
            try:
                clean = _redact_image(png, diff_spans, annotate=False)
                if clean is not None:
                    ctx.save_bytes(f"pii/page-{idx:03d}-mock-redacted.png", clean)
                annotated = _redact_image(png, diff_spans, annotate=True)
                if annotated is not None:
                    ctx.save_bytes(
                        f"pii/page-{idx:03d}-mock-redacted-annotated.png", annotated,
                    )
            except Exception:  # noqa: BLE001
                logger.exception("mock variant render failed for page %d", idx)

        if mock_to_original:
            mapping = RedactionMapping(
                pii_run_id=ctx.run_id,
                document_id=ctx.document_id,
                page_index=-1,           # solution-wide mapping
                ocr=ctx.solution_name,
                detector="presidio_legacy",
                mock_to_original=mock_to_original,
                entity_types=entity_type_counts,
            )
            mapping_path = ctx.artifact_path("pii/mock-mapping.fernet")
            save_encrypted(mapping, mapping_path)
            save_index(mapping, ctx.artifact_path("pii/mock-mapping.index.json"))

    # ----- helpers ----------------------------------------------------

    def _record(
        self,
        value: str,
        entity_type: str,
        token_map: Dict[str, str],
        value_to_token: Dict[str, str],
        value_to_entity: Dict[str, str],
    ) -> Tuple[str, str]:
        if value not in value_to_token:
            token = uuid.uuid4().hex[:8]
            token_map[token] = value
            value_to_token[value] = token
            value_to_entity[value] = entity_type
        return value_to_token[value], value_to_entity.get(value, entity_type)

    def _tag_span_with_token(self, span: PiiSpan, token: str) -> None:
        span.token = token


def _try_load_presidio():
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore

        return AnalyzerEngine()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Presidio unavailable (%s) — falling back to regex-only detection", exc)
        return None


def _analyze(text: str, *, analyzer) -> List[PiiSpan]:
    spans: List[PiiSpan] = []
    if analyzer is not None:
        try:
            results = analyzer.analyze(
                text=text,
                language="en",
                entities=[
                    "PERSON",
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER",
                    "IBAN_CODE",
                    "CREDIT_CARD",
                    "LOCATION",
                ],
            )
            for r in results:
                spans.append(
                    PiiSpan(
                        entity_type=r.entity_type,
                        start=int(r.start),
                        end=int(r.end),
                        score=float(r.score),
                        masked_value="",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Presidio analyze failed: %s", exc)

    for m in UK_SORT_CODE_RE.finditer(text):
        spans.append(PiiSpan(entity_type="UK_SORT_CODE", start=m.start(), end=m.end(), score=0.95, masked_value=""))
    for m in UK_ACCOUNT_CTX_RE.finditer(text):
        spans.append(PiiSpan(entity_type="UK_ACCOUNT_NUMBER", start=m.start(1), end=m.end(1), score=0.95, masked_value=""))
    for m in UK_POSTCODE_RE.finditer(text):
        spans.append(PiiSpan(entity_type="UK_POSTCODE", start=m.start(), end=m.end(), score=0.9, masked_value=""))
    return _dedupe(spans)


def _find_extra_occurrences(
    region: Region,
    value_to_token: Dict[str, str],
    value_to_entity: Dict[str, str],
    *,
    min_len: int,
) -> List[PiiSpan]:
    """Find occurrences of any known PII value inside this region's text."""
    text = region.text
    out: List[PiiSpan] = []
    existing = {(s.start, s.end) for s in region.pii_spans}
    for value in value_to_token:
        if len(value) < min_len:
            continue
        for m in re.finditer(re.escape(value), text):
            if (m.start(), m.end()) in existing:
                continue
            existing.add((m.start(), m.end()))
            entity = value_to_entity.get(value, "UNKNOWN")
            out.append(
                PiiSpan(
                    entity_type=entity,
                    start=m.start(),
                    end=m.end(),
                    score=0.75,
                    masked_value="",
                )
            )
    return out


def _dedupe(spans: List[PiiSpan]) -> List[PiiSpan]:
    seen: Dict[Tuple[str, int, int], PiiSpan] = {}
    for s in spans:
        k = (s.entity_type, s.start, s.end)
        if k not in seen or seen[k].score < s.score:
            seen[k] = s
    return sorted(seen.values(), key=lambda x: (x.start, -x.score))


def _mask_value(value: str, entity_type: str, mask: str) -> str:
    if entity_type in {"UK_ACCOUNT_NUMBER", "CREDIT_CARD", "IBAN_CODE"} and len(value) >= 4:
        return mask * (len(value) - 4) + value[-4:]
    if entity_type in {"PERSON", "LOCATION"}:
        return f"[{entity_type}]"
    return mask * len(value)


def _span_bbox(region: Region, span: PiiSpan) -> Optional[BBox]:
    if not region.text:
        return None
    L = len(region.text)
    if L == 0:
        return None
    x_per_char = region.bbox.w / max(1, L)
    x1 = region.bbox.x + x_per_char * span.start
    x2 = region.bbox.x + x_per_char * span.end
    return BBox(
        x=x1,
        y=region.bbox.y,
        w=max(2, x2 - x1),
        h=region.bbox.h,
        page_index=region.bbox.page_index,
        coord_space=region.bbox.coord_space,
    )


def _redacted_image(png_path: Path, items: List[Tuple[Region, PiiSpan]]) -> bytes:
    """Solid-black redactions (used as input to Claude Vision)."""
    img = Image.open(png_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for _region, span in items:
        if span.bbox is None:
            continue
        b = span.bbox
        draw.rectangle([b.x, b.y, b.x2, b.y2], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _masked_overlay_image(png_path: Path, items: List[Tuple[Region, PiiSpan]]) -> bytes:
    """User-facing 'masked' view: red bordered + tinted boxes with the masked text written over them."""
    img = Image.open(png_path).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    font = _safe_font()
    for _region, span in items:
        if span.bbox is None:
            continue
        b = span.bbox
        # Solid red fill so the original characters can't be seen, then write the masked text on top.
        draw.rectangle([b.x, b.y, b.x2, b.y2], fill=(255, 80, 80, 230), outline=(180, 0, 0, 255), width=2)
        draw.text((b.x + 2, b.y + 1), span.masked_value or "***", fill=(0, 0, 0, 255), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _safe_font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except Exception:
        return ImageFont.load_default()


def _encrypt_token_map(token_map: Dict[str, str]) -> bytes:
    plaintext = json.dumps(token_map).encode("utf-8")
    key = settings.pii_mask_key
    if not key:
        logger.warning("PII_MASK_KEY not set — token map will be stored unencrypted")
        return plaintext
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode()).encrypt(plaintext)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fernet encryption failed (%s) — storing token map unencrypted", exc)
        return plaintext
