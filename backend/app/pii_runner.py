"""pii_v2 orchestration: OCR producer fan-out × detector fan-out.

Per :doc:`.prompt/009`, the new track operates on *text*. For a PDF input we
need extracted text first. The "text producers" are existing solutions whose
``Region.text`` field carries the OCR or native-PDF text.

Two modes:

- **Standalone** (no ``paired_run_ids``): we call each producer ourselves via
  :func:`run_solution`, store the runs under
  ``storage/pii_runs/<pii_run_id>/<doc_id>/_producers/``, then sweep text per
  page.
- **Paired** (PII benchmark fired alongside the existing flow): instead of
  re-running OCR, we read text from the parallel ``/runs/<run_id>/...``
  results that the main pipeline already produced. The producer subset is
  intersected with what the paired run actually executed, so the user picks
  it once and the PII track piggybacks.

A *skipped* cell is written when a producer can't supply text for a page
(not registered, didn't support the doc kind, errored, or returned empty
text). That way the dashboard shows the reason instead of perpetual
"pending".
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app import pii_v2_store, run_store
from app.pipeline import base
from app.pipeline.runner import run_solution
from app.pipeline.scheduler import compute_solution_concurrency
from app.pii_v2.registry import get_detector
from app.pii_v2.schema import DetectorResult
from app.pii_v2.text_layout import RegionSpan, serialize_index

logger = logging.getLogger("ote.pii_runner")


def execute_pii_run(
    *,
    pii_run_id: str,
    docs: List[Dict[str, Any]],
    ocr_producers: List[str],
    detector_names: List[str],
    jurisdictions: List[str],
    dpi: int,
) -> None:
    """Background task entry point. Mutates pii_v2_store as it progresses."""
    for doc in docs:
        document_id = doc["document_id"]
        pdf_path = Path(doc["path"])
        pdf_kind = doc.get("pdf_kind", "unknown")
        n_pages = int(doc.get("n_pages", 0) or 0)
        paired_run_id = doc.get("paired_run_id")
        pii_v2_store.update_document_status(pii_run_id, document_id, "running")

        registry = base.registered()
        try:
            text_by_page, region_index_by_producer, producer_status = _resolve_text(
                pii_run_id=pii_run_id,
                document_id=document_id,
                pdf_path=pdf_path,
                pdf_kind=pdf_kind,
                n_pages=n_pages,
                producers=ocr_producers,
                dpi=dpi,
                paired_run_id=paired_run_id,
                registry=registry,
            )
            _run_visual_extractor(
                pii_run_id=pii_run_id,
                document_id=document_id,
                n_pages=n_pages,
                pdf_path=pdf_path,
                paired_run_id=paired_run_id,
                producer_runs_root=pii_v2_store.run_dir(pii_run_id) / document_id / "_producers",
            )
            _persist_text_layout(
                pii_run_id=pii_run_id,
                document_id=document_id,
                region_index_by_producer=region_index_by_producer,
            )
            _write_producer_status_cells(
                pii_run_id=pii_run_id,
                document_id=document_id,
                n_pages=n_pages,
                producers=ocr_producers,
                detector_names=detector_names,
                producer_status=producer_status,
            )
            _run_detectors(
                pii_run_id=pii_run_id,
                document_id=document_id,
                text_by_page=text_by_page,
                detector_names=detector_names,
                jurisdictions=jurisdictions,
                region_index_by_producer=region_index_by_producer,
            )
            # If any producer hit an error (e.g. trocr timed out and the
            # paired /runs solution propagated status=error/partial), the
            # detection cells for that producer are skipped/error stubs
            # rather than real PII output. Mark the document "partial" so
            # the Resume button surfaces — otherwise the user sees
            # status=done while a slice of producers silently failed.
            errored_producers = [
                name for name, st in (producer_status or {}).items()
                if (st or {}).get("status") == "error"
            ]
            if errored_producers:
                logger.info(
                    "pii_run %s: doc %s partial — producers errored: %s",
                    pii_run_id, document_id, errored_producers,
                )
                pii_v2_store.update_document_status(pii_run_id, document_id, "partial")
            else:
                pii_v2_store.update_document_status(pii_run_id, document_id, "done")
            logger.info("pii_run %s: doc %s done", pii_run_id, document_id)
        except Exception:  # noqa: BLE001
            logger.exception("pii_run %s: doc %s failed", pii_run_id, document_id)
            pii_v2_store.update_document_status(pii_run_id, document_id, "error")


def _resolve_text(
    *,
    pii_run_id: str,
    document_id: str,
    pdf_path: Path,
    pdf_kind: str,
    n_pages: int,
    producers: List[str],
    dpi: int,
    paired_run_id: Optional[str],
    registry: Dict[str, Any],
) -> Tuple[
    Dict[str, Dict[int, str]],
    Dict[str, Dict[int, List[RegionSpan]]],
    Dict[str, Dict[str, Any]],
]:
    """Return (text, region_index, producer_status) all keyed by producer.

    The region_index lets the dashboard map char-offset PII spans back to
    pixel bboxes for image overlays. ``producer_status[name]`` looks like
    ``{"status": "ok"|"skipped"|"error", "reason": "..."}``.
    """
    if paired_run_id:
        # The paired /runs background task starts at the same time as us, so
        # its result.json files don't exist yet. Wait until each requested
        # producer reaches a terminal state (done / error / skipped) before
        # reading. Without this, every producer would be stamped 'skipped: not
        # in paired /runs result set' immediately.
        _wait_for_paired_producers(
            pii_run_id=pii_run_id,
            paired_run_id=paired_run_id,
            producers=producers,
            registry=registry,
        )
        text, region_index, status = _read_text_from_paired_run(
            paired_run_id=paired_run_id,
            producers=producers,
            registry=registry,
        )
        if text:
            return text, region_index, status
        # Every producer in the paired run came back skipped/error — there's
        # nothing useful to consume; fall back to running producers ourselves
        # so the PII track still produces results.
        logger.info(
            "pii_run %s: paired run %s yielded no usable text; falling back to running producers",
            pii_run_id, paired_run_id,
        )

    return _produce_text_per_page(
        pii_run_id=pii_run_id,
        document_id=document_id,
        pdf_path=pdf_path,
        pdf_kind=pdf_kind,
        n_pages=n_pages,
        producers=producers,
        dpi=dpi,
        registry=registry,
    )


_PAIRED_WAIT_TIMEOUT_SEC = 60 * 60          # 1 hour hard cap
_PAIRED_WAIT_POLL_SEC = 2.0                  # how often we check run_store
_TERMINAL_STATES = {"done", "error", "skipped"}


def _wait_for_paired_producers(
    *,
    pii_run_id: str,
    paired_run_id: str,
    producers: List[str],
    registry: Dict[str, Any],
) -> None:
    """Block until every registered producer in the paired run is terminal.

    The PII track is paired when both flows are launched together. The paired
    /runs background task starts at the same moment as this pii_run, so we
    must wait for its solutions to finish before reading their result.json
    files. We only wait for producers the paired run actually selected; any
    producer the paired run didn't pick is treated as already-terminal.
    """
    wanted = [p for p in producers if p in registry]
    if not wanted:
        return

    deadline = time.time() + _PAIRED_WAIT_TIMEOUT_SEC
    last_log = 0.0
    while time.time() < deadline:
        state = run_store.read_run(paired_run_id)
        if state is None:
            logger.warning(
                "pii_run %s: paired run %s does not exist; aborting wait",
                pii_run_id, paired_run_id,
            )
            return
        solution_status = state.get("solution_status") or {}
        selected = set(state.get("solution_names") or [])
        outstanding: List[str] = []
        for name in wanted:
            if name not in selected:
                # Paired run didn't pick this producer; nothing to wait for.
                continue
            cur = (solution_status.get(name) or {}).get("state")
            if cur not in _TERMINAL_STATES:
                outstanding.append(name)
        if not outstanding or state.get("status") == "done":
            logger.info(
                "pii_run %s: paired run %s producers ready (%d in scope)",
                pii_run_id, paired_run_id, len(wanted),
            )
            return
        now = time.time()
        if now - last_log > 10:
            logger.info(
                "pii_run %s: waiting on paired run %s — %d producer(s) still running: %s",
                pii_run_id, paired_run_id, len(outstanding), ",".join(outstanding[:5]),
            )
            last_log = now
        time.sleep(_PAIRED_WAIT_POLL_SEC)
    logger.warning(
        "pii_run %s: paired-run wait timed out after %ds (paired=%s)",
        pii_run_id, _PAIRED_WAIT_TIMEOUT_SEC, paired_run_id,
    )


def _read_text_from_paired_run(
    *,
    paired_run_id: str,
    producers: List[str],
    registry: Dict[str, Any],
) -> Tuple[
    Dict[str, Dict[int, str]],
    Dict[str, Dict[int, List[RegionSpan]]],
    Dict[str, Dict[str, Any]],
]:
    """Read text + region index from /runs/<paired_run_id>/<solution>/result.json files."""
    text_by_producer: Dict[str, Dict[int, str]] = {}
    index_by_producer: Dict[str, Dict[int, List[RegionSpan]]] = {}
    status: Dict[str, Dict[str, Any]] = {}

    run_dir = run_store.run_dir(paired_run_id)
    for name in producers:
        if name not in registry:
            status[name] = {"status": "skipped", "reason": "solution not registered"}
            continue
        result_path = run_dir / name / "result.json"
        if not result_path.exists():
            status[name] = {"status": "skipped", "reason": "not in paired /runs result set"}
            continue
        try:
            data = json.loads(result_path.read_text())
        except Exception:  # noqa: BLE001
            status[name] = {"status": "error", "reason": "result.json could not be parsed"}
            continue
        if data.get("status") == "skipped":
            status[name] = {"status": "skipped", "reason": data.get("skipped_reason") or "solution skipped"}
            continue
        if data.get("status") == "error":
            status[name] = {"status": "error", "reason": data.get("error") or "solution errored"}
            continue
        pages_text, region_index = _join_pages_text(data.get("pages") or [])
        if not any(pages_text.values()):
            status[name] = {"status": "skipped", "reason": "no text in regions"}
            continue
        text_by_producer[name] = pages_text
        index_by_producer[name] = region_index
        status[name] = {"status": "ok", "reason": f"reused from /runs/{paired_run_id}"}
    return text_by_producer, index_by_producer, status


def _produce_text_per_page(
    *,
    pii_run_id: str,
    document_id: str,
    pdf_path: Path,
    pdf_kind: str,
    n_pages: int,
    producers: List[str],
    dpi: int,
    registry: Dict[str, Any],
) -> Tuple[
    Dict[str, Dict[int, str]],
    Dict[str, Dict[int, List[RegionSpan]]],
    Dict[str, Dict[str, Any]],
]:
    """Run each registered text-producer solution; return per-producer text + region index + status."""
    valid = [p for p in producers if p in registry]
    invalid = [p for p in producers if p not in registry]
    status: Dict[str, Dict[str, Any]] = {
        p: {"status": "skipped", "reason": "solution not registered"} for p in invalid
    }
    text_by_producer: Dict[str, Dict[int, str]] = {}
    index_by_producer: Dict[str, Dict[int, List[RegionSpan]]] = {}

    if not valid:
        return text_by_producer, index_by_producer, status

    n_concurrent, reason = compute_solution_concurrency(len(valid))
    logger.info("pii_run %s/%s: %d producers, %d at a time (%s)",
                pii_run_id, document_id, len(valid), n_concurrent, reason)

    producer_runs_root = pii_v2_store.run_dir(pii_run_id) / document_id / "_producers"
    producer_runs_root.mkdir(parents=True, exist_ok=True)

    def _produce(name: str) -> None:
        sol = base.get(name)
        try:
            result = run_solution(
                solution=sol,
                run_id=f"pii-{pii_run_id[:6]}-{name}",
                document_id=document_id,
                pdf_path=pdf_path,
                pdf_kind=pdf_kind,  # type: ignore[arg-type]
                n_pages=n_pages,
                runs_dir=producer_runs_root,
                dpi=dpi,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("pii_run %s: producer %s failed: %s", pii_run_id, name, exc)
            status[name] = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
            return
        if result.status == "skipped":
            status[name] = {"status": "skipped", "reason": result.skipped_reason or "solution skipped"}
            return
        if result.status == "error":
            status[name] = {"status": "error", "reason": result.error or "solution errored"}
            return
        pages_text, region_index = _join_pages_text([p.model_dump() for p in result.pages])
        if not any(pages_text.values()):
            status[name] = {"status": "skipped", "reason": "no text in regions"}
            return
        text_by_producer[name] = pages_text
        index_by_producer[name] = region_index
        status[name] = {"status": "ok", "reason": "produced text"}

    with ThreadPoolExecutor(max_workers=n_concurrent, thread_name_prefix=f"pii-{pii_run_id[:6]}") as pool:
        futures = [pool.submit(_produce, name) for name in valid]
        for f in futures:
            try:
                f.result()
            except Exception:  # noqa: BLE001
                logger.exception("pii producer task failed")
    return text_by_producer, index_by_producer, status


def _join_pages_text(
    pages: List[Dict[str, Any]],
) -> Tuple[Dict[int, str], Dict[int, List[RegionSpan]]]:
    """Join sorted region texts per page; emit a parallel char-range index.

    The index lets later steps (image-modal overlays, post-process search)
    resolve a char-offset PII span back to its source region's pixel bbox.

    Returns ``(text_by_page, region_index_by_page)``.
    """
    text_out: Dict[int, str] = {}
    index_out: Dict[int, List[RegionSpan]] = {}
    for page in pages:
        idx = int(page.get("page_index", -1))
        if idx < 0:
            continue
        regions = page.get("regions") or []
        def _key(r: Dict[str, Any]) -> Tuple[float, float]:
            bbox = r.get("bbox") or {}
            return (float(bbox.get("y", 0.0)), float(bbox.get("x", 0.0)))
        regions = sorted(regions, key=_key)

        parts: List[str] = []
        region_spans: List[RegionSpan] = []
        cursor = 0
        for r in regions:
            text = str(r.get("text", "")).strip()
            if not text:
                continue
            if parts:
                parts.append("\n")
                cursor += 1
            bbox = r.get("bbox") or {}
            region_spans.append(RegionSpan(
                start=cursor,
                end=cursor + len(text),
                region_id=str(r.get("id") or f"page-{idx}-r{len(region_spans)}"),
                bbox={
                    "x": float(bbox.get("x", 0.0)),
                    "y": float(bbox.get("y", 0.0)),
                    "w": float(bbox.get("w", 0.0)),
                    "h": float(bbox.get("h", 0.0)),
                    "page_index": int(bbox.get("page_index", idx)),
                    "coord_space": str(bbox.get("coord_space", "image_px@300")),
                },
                text_len=len(text),
            ))
            parts.append(text)
            cursor += len(text)
        text_out[idx] = "".join(parts)
        index_out[idx] = region_spans
    return text_out, index_out


def _run_visual_extractor(
    *,
    pii_run_id: str,
    document_id: str,
    n_pages: int,
    pdf_path: Path,
    paired_run_id: Optional[str],
    producer_runs_root: Path,
) -> None:
    """Detect QR codes + barcodes per page image (independent of OCR producers)."""
    from app.config import settings
    from app.core.rasterize import rasterize_pdf
    from app.pii_v2 import visual_extractor

    if not settings.pii_v2_visual_enabled:
        logger.info("pii_run %s: visual extractor disabled by config", pii_run_id)
        return

    # Find an image path per page. Preference order:
    #   1. paired /runs/<id>/<solution>/artifacts/pages/page-NNN.png if available
    #   2. any pii_run producer's rasterised pages
    #   3. rasterize the source PDF ourselves into a private cache
    candidate_dirs: List[Path] = []
    if paired_run_id:
        run_dir_path = run_store.run_dir(paired_run_id)
        for sol_dir in sorted(run_dir_path.glob("*/artifacts/pages")):
            candidate_dirs.append(sol_dir)
    if producer_runs_root.exists():
        for sol_dir in sorted(producer_runs_root.glob("*/*/artifacts/pages")):
            candidate_dirs.append(sol_dir)
    image_for_page: Dict[int, Path] = {}
    for d in candidate_dirs:
        for p in d.glob("page-*.png"):
            try:
                idx = int(p.stem.split("-")[-1])  # rasterize names are 0-based
            except ValueError:
                continue
            image_for_page.setdefault(idx, p)
    if not image_for_page and pdf_path.exists():
        raster_dir = pii_v2_store.run_dir(pii_run_id) / document_id / "_visual_raster"
        raster_dir.mkdir(parents=True, exist_ok=True)
        rasters = rasterize_pdf(pdf_path, raster_dir, dpi=settings.default_dpi)
        for r in rasters:
            image_for_page[r.page_index] = r.png_path

    for idx in range(max(n_pages, 1)):
        visual_extractor.persist_for_page(
            pii_run_id=pii_run_id,
            document_id=document_id,
            page_index=idx,
            image_path=image_for_page.get(idx),
        )


def _load_legacy_entities(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
) -> Dict[str, Any]:
    """Synthesise a detector result for the 'presidio_legacy' card.

    Reads the legacy ``PresidioPII`` output (per-region ``pii_spans``) from
    the paired ``/runs/<paired_run_id>/<ocr>/result.json`` and converts it
    into ``PIIEntity`` objects with global char offsets in the joined page
    text. No actual detection happens here — the detection already
    happened during the paired OCR run; we just expose its spans inside
    the pii_v2 benchmark matrix.

    Returns a dict shaped like a ``DetectorResult.metadata`` blob so the
    caller can stamp it into the cell payload uniformly.
    """
    from app.pii_v2.schema import PIIEntity

    state = pii_v2_store.read_run(pii_run_id)
    # Doc-specific paired run only. Iterating all paired_ids would pick
    # doc-1's legacy spans for every other doc when paired with /batches.
    paired_run_id = pii_v2_store.paired_run_id_for_doc(state, document_id)
    paired_ids = [paired_run_id] if paired_run_id else []
    if not paired_ids:
        return {"entities": [], "audit": [], "latency_ms": 0.0,
                "error": f"no paired run for doc {document_id}"}

    for rid in paired_ids:
        result_path = run_store.run_dir(rid) / ocr / "result.json"
        if not result_path.exists():
            continue
        try:
            data = json.loads(result_path.read_text())
        except Exception as exc:  # noqa: BLE001
            return {"entities": [], "audit": [], "latency_ms": 0.0,
                    "error": f"could not read paired result.json: {exc}"}

        # Replay the same reading-order join the runner uses so char offsets
        # in the entities line up with text_by_page[page_index].
        target_page = next(
            (p for p in (data.get("pages") or []) if int(p.get("page_index", -1)) == page_index),
            None,
        )
        if target_page is None:
            return {"entities": [], "audit": [], "latency_ms": 0.0, "error": "page not in paired result"}

        regions = sorted(
            target_page.get("regions") or [],
            key=lambda r: (float((r.get("bbox") or {}).get("y", 0.0)),
                           float((r.get("bbox") or {}).get("x", 0.0))),
        )
        entities: List[PIIEntity] = []
        cursor = 0
        first = True
        for r in regions:
            text = str(r.get("text", "")).strip()
            if not text:
                continue
            if not first:
                cursor += 1   # newline join
            first = False
            base = cursor
            for span in (r.get("pii_spans") or []):
                try:
                    start = base + int(span["start"])
                    end = base + int(span["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                entity_type = span.get("entity_type") or "UNKNOWN"
                entities.append(PIIEntity(
                    entity_type=entity_type,
                    text=text[span["start"]:span["end"]],
                    start=start,
                    end=end,
                    score=float(span.get("score", 0.85)),
                    source="presidio_legacy",
                    detection_method="regex+spacy",
                    jurisdiction=None,
                    metadata={
                        "discovery": "lib",
                        "masked_value": span.get("masked_value"),
                        "token": span.get("token"),
                    },
                ))
            cursor += len(text)
        return {
            "entities": entities,
            "audit": [{
                "stage_name": "presidio_legacy.read",
                "tool": "PresidioPII (from paired /runs)",
                "order": 0,
                "started_at": "",
                "duration_ms": 0.0,
                "status": "ok",
                "inputs": [f"paired_run={rid}", f"solution={ocr}"],
                "outputs": [f"entities:{len(entities)}"],
                "message": "",
                "metadata": {"source": "result.json::pages[].regions[].pii_spans"},
            }],
            "latency_ms": 0.0,
            "error": None,
        }
    return {"entities": [], "audit": [], "latency_ms": 0.0,
            "error": "no result.json in paired runs"}


def _find_page_image_for_redaction(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
) -> Optional[Path]:
    """Same preference order as the GET /page-image route — paired /runs
    rasters → pii_run producer rasters → visual-extractor cache."""
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        return None
    filename = f"page-{page_index:03d}.png"
    # Doc-specific paired run only — global iter would return doc-1's image
    # for every doc in a multi-doc paired run.
    paired_run_id = pii_v2_store.paired_run_id_for_doc(state, document_id)
    if paired_run_id:
        run_root = run_store.run_dir(paired_run_id)
        for png in run_root.glob(f"*/artifacts/pages/{filename}"):
            return png
    pii_root = pii_v2_store.run_dir(pii_run_id) / document_id
    for png in pii_root.glob(f"_producers/*/*/artifacts/pages/{filename}"):
        return png
    cache = pii_root / "_visual_raster" / filename
    if cache.exists():
        return cache
    return None


def _persist_text_layout(
    *,
    pii_run_id: str,
    document_id: str,
    region_index_by_producer: Dict[str, Dict[int, List[RegionSpan]]],
) -> None:
    """Write per (ocr, page) char-range → bbox index so the dashboard
    can resolve PII char spans into image bboxes lazily."""
    base_dir = pii_v2_store.run_dir(pii_run_id) / document_id / "text_layout"
    for ocr_name, by_page in region_index_by_producer.items():
        ocr_dir = base_dir / ocr_name
        ocr_dir.mkdir(parents=True, exist_ok=True)
        for page_index, spans in by_page.items():
            (ocr_dir / f"page-{page_index:03d}.json").write_text(
                json.dumps(serialize_index(spans), indent=2, default=str)
            )


def _write_producer_status_cells(
    *,
    pii_run_id: str,
    document_id: str,
    n_pages: int,
    producers: List[str],
    detector_names: List[str],
    producer_status: Dict[str, Dict[str, Any]],
) -> None:
    """Stamp a skipped/error cell for every (producer, detector, page) combination
    whose producer didn't actually yield text."""
    if n_pages <= 0:
        # Best-effort default — write one entry for page 0 so the UI can show
        # the reason for every producer.
        n_pages = 1
    for name in producers:
        s = producer_status.get(name, {"status": "skipped", "reason": "no status recorded"})
        if s.get("status") == "ok":
            continue
        for page_index in range(n_pages):
            for det in detector_names:
                pii_v2_store.write_cell(
                    pii_run_id=pii_run_id,
                    document_id=document_id,
                    page_index=page_index,
                    ocr=name,
                    detector=det,
                    text="",
                    result_payload={
                        "detector_name": det,
                        "entities": [],
                        "text_len": 0,
                        "latency_ms": 0.0,
                        "error": None,
                        "metadata": {
                            "ocr_status": s.get("status"),
                            "ocr_reason": s.get("reason"),
                        },
                    },
                )


def _run_detectors(
    *,
    pii_run_id: str,
    document_id: str,
    text_by_page: Dict[str, Dict[int, str]],
    detector_names: List[str],
    jurisdictions: List[str],
    region_index_by_producer: Optional[Dict[str, Dict[int, List[RegionSpan]]]] = None,
) -> None:
    """Run each detector across every page of every producer, then post-process
    the per-(ocr × detector) results before persisting cells.

    Post-process needs cross-page context (e.g. shortname-of in page 2 must
    reference a fullname detection on page 1), so we batch per (ocr × detector)
    rather than the older per-(ocr × page) loop.
    """
    from app.config import settings as _settings
    from app.pii_v2.audit import AuditCollector
    from app.pii_v2.post_process import run_post_process
    from app.pii_v2.redaction import redact_cell
    from app.pii_v2_manual_store import read_for as read_manual_annotations

    manual_annotations = read_manual_annotations(document_id=document_id, pii_run_id=pii_run_id)
    redaction_enabled = getattr(_settings, "pii_v2_redaction_enabled", True)

    for ocr_name, pages_text in text_by_page.items():
        for det_name in detector_names:
            # 'presidio_legacy' is synthetic — no class in the registry. It
            # reads each page's entities from the paired /runs result.json
            # so the dashboard surfaces the legacy PresidioPII output as a
            # benchmark candidate next to the 5 detectors.
            is_legacy = det_name == "presidio_legacy"
            detector_cls = None
            if not is_legacy:
                try:
                    detector_cls = get_detector(det_name)
                except KeyError:
                    logger.warning(
                        "pii_run %s: unknown detector %s, skipping", pii_run_id, det_name,
                    )
                    continue

            # Detect per page.
            per_page_entities: Dict[int, list] = {}
            per_page_audits: Dict[int, list] = {}
            per_page_latency: Dict[int, float] = {}
            per_page_error: Dict[int, str | None] = {}
            for page_index, text in pages_text.items():
                if not text:
                    continue
                if is_legacy:
                    legacy = _load_legacy_entities(
                        pii_run_id=pii_run_id,
                        document_id=document_id,
                        page_index=page_index,
                        ocr=ocr_name,
                    )
                    per_page_entities[page_index] = legacy["entities"]
                    per_page_audits[page_index] = legacy["audit"]
                    per_page_latency[page_index] = legacy["latency_ms"]
                    per_page_error[page_index] = legacy["error"]
                else:
                    detector = detector_cls(jurisdictions=jurisdictions)
                    result: DetectorResult = detector.detect_with_timing(text)
                    per_page_entities[page_index] = list(result.entities)
                    per_page_audits[page_index] = (
                        result.metadata.get("audit", []) if result.metadata else []
                    )
                    per_page_latency[page_index] = result.latency_ms
                    per_page_error[page_index] = result.error

            # Post-process across pages for this (ocr × detector).
            post_audit = AuditCollector()
            per_page_entities, occurrences = run_post_process(
                per_page_entities=per_page_entities,
                text_by_page={k: v for k, v in pages_text.items() if v},
                manual_annotations=manual_annotations,
                audit=post_audit,
            )
            post_audit_steps = post_audit.to_list()

            # Persist per-page cells.
            for page_index, text in pages_text.items():
                if not text:
                    continue
                ents = per_page_entities.get(page_index, [])
                payload = {
                    "detector_name": det_name,
                    "entities": [e.to_dict() for e in ents],
                    "text_len": len(text),
                    "latency_ms": per_page_latency.get(page_index, 0.0),
                    "error": per_page_error.get(page_index),
                    "metadata": {
                        "audit": per_page_audits.get(page_index, []) + post_audit_steps,
                        "occurrences": {k: v.to_dict() for k, v in occurrences.items()},
                    },
                }
                pii_v2_store.write_cell(
                    pii_run_id=pii_run_id,
                    document_id=document_id,
                    page_index=page_index,
                    ocr=ocr_name,
                    detector=det_name,
                    text=text,
                    result_payload=payload,
                )

                if redaction_enabled and ents:
                    region_index = (
                        (region_index_by_producer or {})
                        .get(ocr_name, {})
                        .get(page_index, [])
                    )
                    page_image = _find_page_image_for_redaction(
                        pii_run_id=pii_run_id,
                        document_id=document_id,
                        page_index=page_index,
                    )
                    art = redact_cell(
                        pii_run_id=pii_run_id,
                        document_id=document_id,
                        page_index=page_index,
                        ocr=ocr_name,
                        detector=det_name,
                        text=text,
                        entities=ents,
                        region_index=region_index,
                        page_image_path=page_image,
                        out_dir=pii_v2_store.cell_dir(
                            pii_run_id, document_id, page_index, ocr_name, det_name,
                        ) / "redaction",
                    )
                    # Update the cell summary in-place so the dashboard shows
                    # the "redacted: N" chip without an extra round-trip.
                    pii_v2_store.update_cell_summary(
                        pii_run_id=pii_run_id,
                        document_id=document_id,
                        page_index=page_index,
                        ocr=ocr_name,
                        detector=det_name,
                        extra={"redaction": art.to_dict()},
                    )
