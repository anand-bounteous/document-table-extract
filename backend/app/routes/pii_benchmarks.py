"""REST surface for the pii_v2 benchmark track.

The PDF-mode endpoints mirror the /batches contract: client posts document
ids + optional detector / OCR-producer overrides, server returns a
``pii_run_id`` immediately, work runs in a BackgroundTask, client polls
``GET /pii-benchmarks/{id}`` for matrix state.

JSONL dataset-mode endpoints will be added in Stage 8 (deferred).
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import document_store, pii_v2_manual_store, pii_v2_store, run_store
from app.config import settings
from app.pii_runner import execute_pii_run
from app.pii_v2.registry import describe_detectors, list_detectors

logger = logging.getLogger("ote.pii_benchmarks")
router = APIRouter(prefix="/pii-benchmarks", tags=["pii-benchmarks"])


class PiiRunRequest(BaseModel):
    document_ids: List[str]
    detector_names: Optional[List[str]] = None
    ocr_producers: Optional[List[str]] = None
    jurisdictions: Optional[List[str]] = None
    dpi: Optional[int] = None
    paired_run_ids: Optional[List[str]] = None  # parallel /runs ids when "both flows" was selected
    paired_batch_id: Optional[str] = None


@router.get("/detectors")
def list_detector_descriptors():
    return {"detectors": describe_detectors()}


# Per-detector architecture descriptors — the "HLD" payload returned by
# /detectors/{name}/capabilities. Each entry is a list of pipeline stages
# the user can read top-to-bottom to understand what the detector does.
_DETECTOR_ARCHITECTURE: dict[str, list[dict]] = {
    "presidio_regex": [
        {"stage": "normalize", "tool": "unicodedata.NFKC + whitespace collapse",
         "blurb": "Normalises Unicode and collapses repeated spaces so regex offsets line up."},
        {"stage": "regex_detect", "tool": "RecognizerSpec[] from jurisdiction plugins",
         "blurb": "Runs every regex in the active jurisdictions (GLOBAL_COMMON + UK + USER_CUSTOM + EXTRAS) against the page text. Validators (Luhn, MOD-97, NHS checksum) run inline."},
        {"stage": "context_boost", "tool": "context_terms scan",
         "blurb": "Adds up to 0.3 to a span's score when contextual cues (`sort code`, `iban`, etc.) sit within 60 chars."},
        {"stage": "merge", "tool": "pii_v2.merger.merge",
         "blurb": "Deterministic overlap resolution. Structured types win over contextual; longer matches beat shorter."},
        {"stage": "risk", "tool": "pii_v2.risk.apply",
         "blurb": "Stamps risk_level + sensitivity_category; promotes name+postcode, sort_code+account, name+DOB combos to high risk."},
    ],
    "presidio_spacy": [
        {"stage": "regex pipeline", "tool": "presidio_regex (chained)",
         "blurb": "First runs the full regex track so structured PII (postcode/NINO/IBAN/...) is detected."},
        {"stage": "ner", "tool": "spacy.en_core_web_sm",
         "blurb": "Adds PERSON / ORGANISATION / LOCATION / DATE from spaCy NER. Falls back to regex-only if the model isn't installed."},
        {"stage": "merge + risk", "tool": "pii_v2.merger + pii_v2.risk",
         "blurb": "Same merge / risk passes as the regex track."},
    ],
    "gliner": [
        {"stage": "regex pipeline", "tool": "presidio_regex (chained)",
         "blurb": "Regex baseline runs first."},
        {"stage": "ml_detect", "tool": "GLiNER (subprocess)",
         "blurb": "Spawns a fresh subprocess per call, loads urchade/gliner_small-v2.1, runs predict_entities against ~17 labels (postcode, NINO, sort_code, IBAN, vulnerable customer info, etc)."},
        {"stage": "merge + risk", "tool": "pii_v2.merger + pii_v2.risk", "blurb": ""},
    ],
    "piiranha": [
        {"stage": "regex pipeline", "tool": "presidio_regex (chained)",
         "blurb": "Regex baseline runs first."},
        {"stage": "ml_detect", "tool": "iiiorg/piiranha-v1 (transformers subprocess)",
         "blurb": "HF token-classification pipeline with simple aggregation. Subprocess-isolated; reads from the HF cache (HF_HUB_OFFLINE=1 by default)."},
        {"stage": "label map", "tool": "pii_piiranha_worker._LABEL_TO_ENTITY_TYPE",
         "blurb": "Maps Piiranha's label space (TELEPHONENUM, ACCOUNTNUM, SOCIALNUM, ...) to the pii_v2 taxonomy."},
        {"stage": "merge + risk", "tool": "pii_v2.merger + pii_v2.risk", "blurb": ""},
    ],
    "hybrid": [
        {"stage": "regex pipeline", "tool": "presidio_regex (chained)", "blurb": "Structured-PII baseline."},
        {"stage": "contextual_picker", "tool": "GLiNER → Piiranha → spaCy → regex-only",
         "blurb": "Tries each contextual ML detector in order. The first one whose subprocess succeeds wins; subsequent runs skip the cached-unavailable ones."},
        {"stage": "merge + risk", "tool": "pii_v2.merger + pii_v2.risk",
         "blurb": "Structured-over-contextual merge rules; composite risk evaluation."},
    ],
    "presidio_legacy": [
        {"stage": "per-region detection", "tool": "Microsoft Presidio Analyzer",
         "blurb": "The legacy in-pipeline PII stage runs against each Region.text separately, not against the joined page text. Card values are read from the paired /runs result.json — no detection happens inside the pii_run."},
        {"stage": "universal mask sweep", "tool": "_find_extra_occurrences",
         "blurb": "Second pass spots the same PII values that appeared in regions where Presidio missed them."},
        {"stage": "token map", "tool": "Fernet-encrypted UUID tokens",
         "blurb": "Persists at runs/<id>/<sol>/artifacts/pii/token-map.fernet. Tokens look like `<PERSON>`/`***` masks (not same-length)."},
        {"stage": "mock variants", "tool": "pii_v2.redaction (newly bridged)",
         "blurb": "Same-length mock images are now emitted alongside the legacy red-overlay PNG; see the §6b.12 LLM loop."},
    ],
}


def _detector_customisation(name: str) -> list[dict]:
    """Knobs that actually affect THIS detector at runtime, with their
    currently-configured values from settings + USER_CUSTOM dictionary
    sizes so the user can audit what they're shipping to the LLM."""
    knobs: list[dict] = [
        {
            "name": "PII_V2_DEFAULT_JURISDICTIONS",
            "value": settings.pii_v2_default_jurisdictions,
            "purpose": "Which jurisdiction recogniser packs this detector loads",
        },
        {
            "name": "PII_V2_USER_CUSTOM_SCORE",
            "value": str(settings.pii_v2_user_custom_score),
            "purpose": "Confidence assigned to user-annotated text via USER_CUSTOM",
        },
    ]
    if name in {"gliner", "piiranha", "hybrid"}:
        knobs.append({
            "name": "PII_V2_HF_ONLINE",
            "value": str(getattr(settings, "pii_v2_hf_online", False)),
            "purpose": "Allow ML detectors to download HF models on first call",
        })
    if name == "gliner":
        knobs.append({
            "name": "PII_V2_GLINER_MODEL",
            "value": "urchade/gliner_small-v2.1",
            "purpose": "GLiNER HF model id",
        })
    if name == "piiranha":
        knobs.append({
            "name": "PII_V2_PIIRANHA_MODEL",
            "value": "iiiorg/piiranha-v1-detect-personal-information",
            "purpose": "Piiranha HF model id",
        })
    knobs.append({
        "name": "PII_V2_REDACTION_ENABLED",
        "value": str(getattr(settings, "pii_v2_redaction_enabled", True)),
        "purpose": "Auto-write same-length mock redaction artifacts",
    })
    return knobs


def _user_custom_dictionary_preview() -> dict:
    """Returns a {jurisdiction: [{entity_type, text}], ...} preview of the
    USER_CUSTOM dictionary so the Customisation section shows what's been
    promoted by manual annotations."""
    try:
        from app import pii_v2_manual_store as _ms
        out: dict[str, list[dict]] = {}
        for j in _ms.list_dictionaries():
            entries = _ms.read_custom_dictionary(j)
            out[j] = [
                {"entity_type": e.get("entity_type"), "text": e.get("text")}
                for e in entries[:50]
            ]
        return {
            "jurisdictions": out,
            "total_entries": sum(len(v) for v in out.values()),
        }
    except Exception:  # noqa: BLE001
        return {"jurisdictions": {}, "total_entries": 0}


_SYNTHETIC_DETECTORS: dict[str, dict] = {
    "presidio_legacy": {
        "display_name": "Presidio (legacy, from paired /runs)",
        "description": (
            "Surfaces the existing in-pipeline PresidioPII output — the same "
            "detector every OCR solution already runs — as a benchmark "
            "candidate alongside the new detectors. Entities are read from "
            "the paired /runs/<id>/<sol>/result.json. Token mapping and the "
            "red-overlay masked PNG live next to each OCR solution's "
            "artifacts; the same-length mock variants are bridged in via "
            "the §6b.12 redaction pipeline."
        ),
        "requires_models": [],
    },
}


@router.get("/detectors/{name}/capabilities")
def detector_capabilities(name: str):
    """Full capability descriptor for a detector — taxonomy + jurisdictions
    + knobs + HLD architecture + current customisation values.

    Powers the `🛈 Capabilities` tab on each PII benchmark card.
    """
    from app.pii_v2 import jurisdictions as juris
    from app.pii_v2.categories import category_for
    from app.pii_v2.registry import list_detectors as _list_detectors

    detectors = _list_detectors()
    if name in detectors:
        cls = detectors[name]
        display_name = cls.display_name or cls.name
        description = cls.description
        requires_models = list(cls.requires_models)
    elif name in _SYNTHETIC_DETECTORS:
        meta = _SYNTHETIC_DETECTORS[name]
        display_name = meta["display_name"]
        description = meta["description"]
        requires_models = list(meta["requires_models"])
    else:
        raise HTTPException(404, f"detector not registered: {name}")

    all_juris = sorted(juris.PLUGINS.keys())
    taxonomy: dict[str, dict] = {}
    for code, plugin in juris.PLUGINS.items():
        for spec in plugin.get_recognizers():
            taxonomy.setdefault(spec.entity_type, {
                "entity_type": spec.entity_type,
                "category": category_for(spec.entity_type),
                "jurisdictions": [],
                "has_validator": False,
            })
            taxonomy[spec.entity_type]["jurisdictions"].append(code)
            if spec.validator is not None:
                taxonomy[spec.entity_type]["has_validator"] = True

    return {
        "name": name,
        "display_name": display_name,
        "description": description,
        "requires_models": requires_models,
        "jurisdictions": all_juris,
        "entity_types": sorted(taxonomy.values(), key=lambda x: x["entity_type"]),
        "config_knobs": [
            {"name": "PII_V2_DEFAULT_DETECTORS", "purpose": "Which detectors to run by default"},
            {"name": "PII_V2_DEFAULT_JURISDICTIONS", "purpose": "Which jurisdiction packs to load"},
            {"name": "PII_V2_USER_CUSTOM_SCORE", "purpose": "Confidence assigned to user-annotated text"},
            {"name": "PII_V2_HF_ONLINE", "purpose": "Allow ML detectors to download HF models on first call"},
            {"name": "PII_V2_MAX_OVERLAYS", "purpose": "Cap on bbox overlays in the image modal"},
        ],
        # NEW — HLD + customisation surfaces for the Capabilities tab.
        "architecture": _DETECTOR_ARCHITECTURE.get(name, []),
        "customisation": _detector_customisation(name),
        "user_custom_dictionary": _user_custom_dictionary_preview(),
    }


@router.get("")
def list_pii_runs(limit: int = 50):
    return {"runs": pii_v2_store.list_runs(limit=limit)}


@router.post("/runs")
def create_pii_run(req: PiiRunRequest, background_tasks: BackgroundTasks):
    if not settings.pii_v2_enabled:
        raise HTTPException(503, "pii_v2 is disabled (PII_V2_ENABLED=false)")
    if not req.document_ids:
        raise HTTPException(400, "document_ids is required")

    detector_names = req.detector_names or settings.pii_v2_default_detectors_list
    available = set(list_detectors().keys())
    # ``presidio_legacy`` is a synthetic detector: there's no class for it in
    # the pii_v2 registry; pii_runner reads its entities from the paired
    # /runs/<id>/<sol>/result.json instead. Accept it whenever the request
    # is paired with a /runs.
    SYNTHETIC = {"presidio_legacy"}
    missing = [d for d in detector_names if d not in available and d not in SYNTHETIC]
    if missing:
        raise HTTPException(400, f"unknown detectors: {missing} (have: {sorted(available)})")

    ocr_producers = req.ocr_producers or settings.pii_v2_text_producers_list
    jurisdictions = req.jurisdictions or settings.pii_v2_default_jurisdictions_list
    dpi = req.dpi or settings.default_dpi

    pii_run_id = uuid.uuid4().hex[:12]
    docs_meta: list[dict] = []
    paired = list(req.paired_run_ids or [])
    # When paired with a /runs, include the legacy PresidioPII output as a
    # benchmark candidate so the dashboard compares it side-by-side with the
    # new detectors. Skipped silently when the request didn't include it.
    if paired and "presidio_legacy" not in detector_names:
        detector_names = list(detector_names) + ["presidio_legacy"]
    for idx, doc_id in enumerate(req.document_ids):
        try:
            meta = document_store.get_document_meta(doc_id)
        except FileNotFoundError:
            raise HTTPException(404, f"document not found: {doc_id}")
        docs_meta.append({
            "document_id": doc_id,
            "filename": meta.get("filename") or doc_id,
            "pdf_kind": meta.get("pdf_kind", "unknown"),
            "n_pages": meta.get("n_pages", 0),
            "path": meta["path"],
            "paired_run_id": paired[idx] if idx < len(paired) else None,
        })

    pii_v2_store.init_run(
        pii_run_id=pii_run_id,
        documents=[{k: v for k, v in d.items() if k != "path"} for d in docs_meta],
        ocr_producers=ocr_producers,
        detector_names=detector_names,
        jurisdictions=jurisdictions,
        paired_run_ids=paired,
        paired_batch_id=req.paired_batch_id,
    )
    # Stamp the cross-link onto each paired /runs row so its dashboard can
    # render the chip pointing here.
    for paired_run_id in paired:
        try:
            run_store.set_pii_v2_link(paired_run_id, pii_run_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to set pii_v2 link on run %s", paired_run_id)

    background_tasks.add_task(
        execute_pii_run,
        pii_run_id=pii_run_id,
        docs=docs_meta,
        ocr_producers=ocr_producers,
        detector_names=detector_names,
        jurisdictions=jurisdictions,
        dpi=dpi,
    )
    return {
        "pii_run_id": pii_run_id,
        "detector_names": detector_names,
        "ocr_producers": ocr_producers,
    }


@router.post("/{pii_run_id}/resume")
def resume_pii_run(pii_run_id: str, background_tasks: BackgroundTasks):
    """Re-run any documents in ``error`` state on the SAME ``pii_run_id``.

    Mirrors ``POST /runs/{run_id}/resume`` for the OCR track. Documents
    already ``done`` are left alone. Reset documents are wiped to ``queued``
    state and re-processed with the original producer / detector / juris
    configuration.
    """
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        raise HTTPException(404, f"pii_run not found: {pii_run_id}")

    failed_docs: List[dict] = []
    for doc in state.get("documents", []) or []:
        if doc.get("status") in ("error", "partial", "queued") or (
            doc.get("status") == "running" and doc.get("started_at") is None
        ):
            try:
                meta = document_store.get_document_meta(doc["document_id"])
            except FileNotFoundError:
                logger.warning("resume: document %s missing from store", doc["document_id"])
                continue
            failed_docs.append({
                **doc,
                "path": meta["path"],
                "pdf_kind": meta.get("pdf_kind", doc.get("pdf_kind", "unknown")),
                "n_pages": meta.get("n_pages", doc.get("n_pages", 0)),
            })
    if not failed_docs:
        raise HTTPException(400, "no failed or queued documents to resume")

    pii_v2_store.reset_documents_for_resume(
        pii_run_id, [d["document_id"] for d in failed_docs],
    )

    background_tasks.add_task(
        execute_pii_run,
        pii_run_id=pii_run_id,
        docs=failed_docs,
        ocr_producers=state.get("ocr_producers") or [],
        detector_names=state.get("detector_names") or [],
        jurisdictions=state.get("jurisdictions") or [],
        dpi=settings.default_dpi,
    )
    return {
        "pii_run_id": pii_run_id,
        "status": "running",
        "resumed_documents": [d["document_id"] for d in failed_docs],
    }


@router.get("/{pii_run_id}")
def get_pii_run(pii_run_id: str):
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        raise HTTPException(404, f"pii_run not found: {pii_run_id}")
    return state


@router.get("/{pii_run_id}/cell/{document_id}/{page_index}/{ocr}/{detector}")
def get_pii_cell(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
):
    cell = pii_v2_store.read_cell(pii_run_id, document_id, page_index, ocr, detector)
    if cell is None:
        raise HTTPException(404, "cell not found")
    return cell


class ManualAnnotationRequest(BaseModel):
    page_index: int
    entity_type: str
    text: str
    bbox_px: Optional[dict] = None
    jurisdiction: Optional[str] = None
    scope: str = "doc"  # "doc" (persistent, promoted to dictionary) | "run" (one-shot)


@router.get("/{pii_run_id}/manual-annotations/{document_id}")
def list_manual_annotations(pii_run_id: str, document_id: str):
    return {
        "doc_scope": pii_v2_manual_store.list_for_document(document_id),
        "run_scope": pii_v2_manual_store.list_for_run(pii_run_id, document_id),
    }


@router.post("/{pii_run_id}/manual-annotations/{document_id}")
def add_manual_annotation(
    pii_run_id: str,
    document_id: str,
    req: ManualAnnotationRequest,
):
    if req.scope not in ("doc", "run"):
        raise HTTPException(400, f"scope must be 'doc' or 'run', got {req.scope!r}")
    if not req.text.strip():
        raise HTTPException(400, "text must be non-empty")
    annotation = pii_v2_manual_store.add_annotation(
        document_id=document_id,
        pii_run_id=pii_run_id,
        page_index=req.page_index,
        entity_type=req.entity_type,
        text=req.text,
        bbox_px=req.bbox_px,
        jurisdiction=req.jurisdiction,
        scope=req.scope,
    )
    return annotation


class PendingAnnotation(BaseModel):
    bbox_px: dict


class ProcessAnnotationsRequest(BaseModel):
    document_id: str
    page_index: int
    annotations: List[PendingAnnotation]


@router.post("/{pii_run_id}/annotations/process")
def process_pending_annotations(pii_run_id: str, req: ProcessAnnotationsRequest):
    """Crop each pending bbox, run lightweight OCR + visual extraction, and
    return the cross-reference of existing detector spans that overlap.

    Drives the manual annotation review step on the frontend — the user sees
    auto-extracted text + matched-by chips per pending box and then saves.
    """
    from app.pii_v2.annotation_processor import process_annotation

    processed = []
    for ann in req.annotations:
        processed.append(
            process_annotation(
                pii_run_id=pii_run_id,
                document_id=req.document_id,
                page_index=req.page_index,
                bbox_px=ann.bbox_px,
            )
        )
    return {"processed_annotations": processed}


@router.delete("/{pii_run_id}/manual-annotations/{document_id}/{annotation_id}")
def delete_manual_annotation(pii_run_id: str, document_id: str, annotation_id: str):
    ok = pii_v2_manual_store.delete_annotation(
        document_id=document_id,
        pii_run_id=pii_run_id,
        annotation_id=annotation_id,
    )
    if not ok:
        raise HTTPException(404, "annotation not found")
    return {"ok": True}


@router.get("/{pii_run_id}/visual/{document_id}/{page_index}")
def get_visual_codes(pii_run_id: str, document_id: str, page_index: int):
    """QR + barcode list for a (doc, page). Returns {codes: [...], skipped: [...]}.

    Note: the runner stores per-document data under the *unmodified* document_id
    string, so the lookup uses ``document_id`` directly. Some doc_ids contain
    colons / spaces — the filesystem accepts those on macOS + Linux.
    """
    path = (
        pii_v2_store.run_dir(pii_run_id) / document_id / "visual" / f"page-{page_index:03d}.json"
    )
    if not path.exists():
        return {"codes": [], "skipped": ["not extracted yet"]}
    import json as _json
    return _json.loads(path.read_text())


@router.get("/{pii_run_id}/page-image/{document_id}/{page_index}")
def get_page_image(pii_run_id: str, document_id: str, page_index: int):
    """Return a page image (PNG) for the annotation modal.

    Files are written by ``rasterize_pdf`` (see ``app/core/rasterize.py``)
    using **0-based** names like ``page-000.png`` for page 0. The doc_id
    is used directly (no sanitisation) to match how the runner stores
    artifacts.

    Preference order:
      1. paired /runs/<paired_run_id>/<solution>/artifacts/pages/page-NNN.png
      2. pii_run-local producer rasters
      3. private visual-extractor raster cache
    """
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        raise HTTPException(404, "pii_run not found")
    filename = f"page-{page_index:03d}.png"

    # Use the SPECIFIC document's paired_run_id — not the global list — or
    # multi-doc runs end up serving doc-1's page image for every doc.
    paired_run_id = pii_v2_store.paired_run_id_for_doc(state, document_id)
    if paired_run_id:
        run_dir_path = run_store.run_dir(paired_run_id)
        for png in run_dir_path.glob(f"*/artifacts/pages/{filename}"):
            return FileResponse(png, media_type="image/png")

    pii_run_root = pii_v2_store.run_dir(pii_run_id) / document_id
    for png in pii_run_root.glob(f"_producers/*/*/artifacts/pages/{filename}"):
        return FileResponse(png, media_type="image/png")

    raster_cache = pii_run_root / "_visual_raster" / filename
    if raster_cache.exists():
        return FileResponse(raster_cache, media_type="image/png")

    raise HTTPException(404, f"page image not found ({filename})")


@router.post("/{pii_run_id}/redaction/rebuild")
def rebuild_redactions(pii_run_id: str, background_tasks: BackgroundTasks):
    """Re-run redaction for every cell in this pii_run.

    Heals the case where ``redacted_page*.png`` artifacts were written
    while the page-image lookup had the multi-doc paired-run bug — those
    PNGs had doc-1's image bytes baked underneath even for later docs.
    Doesn't re-detect: it reuses the existing entities + text in each
    cell and only re-runs ``redact_cell`` with the now-correct doc-
    specific source image lookup.
    """
    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        raise HTTPException(404, f"pii_run not found: {pii_run_id}")

    background_tasks.add_task(_rebuild_redactions_task, pii_run_id)
    return {"pii_run_id": pii_run_id, "status": "rebuilding"}


def _rebuild_redactions_task(pii_run_id: str) -> None:
    """Background worker for /redaction/rebuild — see route docstring."""
    from app.pii_runner import _find_page_image_for_redaction
    from app.pii_v2.redaction import redact_cell
    from app.pii_v2.schema import PIIEntity

    state = pii_v2_store.read_run(pii_run_id)
    if state is None:
        return
    total = 0
    rebuilt = 0
    for doc in state.get("documents") or []:
        doc_id = doc["document_id"]
        pages = doc.get("pages") or {}
        for page_key, ocr_map in pages.items():
            try:
                page_index = int(page_key)
            except ValueError:
                continue
            for ocr, det_map in ocr_map.items():
                for det in det_map.keys():
                    total += 1
                    cell = pii_v2_store.read_cell(pii_run_id, doc_id, page_index, ocr, det)
                    if cell is None:
                        continue
                    ents_raw = cell.get("entities") or []
                    if not ents_raw:
                        continue
                    text = cell.get("source_text") or ""
                    try:
                        ents = [PIIEntity(**{**e, "metadata": e.get("metadata") or {}}) for e in ents_raw]
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "rebuild_redactions: could not rehydrate entities for %s/%s/p%d/%s/%s",
                            pii_run_id, doc_id, page_index, ocr, det,
                        )
                        continue
                    page_image = _find_page_image_for_redaction(
                        pii_run_id=pii_run_id,
                        document_id=doc_id,
                        page_index=page_index,
                    )
                    try:
                        art = redact_cell(
                            pii_run_id=pii_run_id,
                            document_id=doc_id,
                            page_index=page_index,
                            ocr=ocr,
                            detector=det,
                            text=text,
                            entities=ents,
                            region_index=[],
                            page_image_path=page_image,
                            out_dir=pii_v2_store.cell_dir(pii_run_id, doc_id, page_index, ocr, det)
                                    / "redaction",
                        )
                        pii_v2_store.update_cell_summary(
                            pii_run_id=pii_run_id,
                            document_id=doc_id,
                            page_index=page_index,
                            ocr=ocr,
                            detector=det,
                            extra={"redaction": art.to_dict()},
                        )
                        rebuilt += 1
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "rebuild_redactions: cell failed %s/%s/p%d/%s/%s",
                            pii_run_id, doc_id, page_index, ocr, det,
                        )
    logger.info("rebuild_redactions: pii_run=%s rebuilt %d/%d cells", pii_run_id, rebuilt, total)


@router.get("/{pii_run_id}/redaction/{document_id}/{page_index}/{ocr}/{detector}")
def get_redaction(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
):
    """Return the side-by-side redaction payload for one cell.

    The encrypted mock→original mapping is NOT included — only its index
    (entity-type counts). Use the ``/mapping`` endpoint to retrieve the
    ciphertext when reverse-mapping is needed.
    """
    data = pii_v2_store.read_redaction(pii_run_id, document_id, page_index, ocr, detector)
    if data is None:
        raise HTTPException(404, "no redaction artifacts for this cell")
    return data


@router.get("/{pii_run_id}/redaction/{document_id}/{page_index}/{ocr}/{detector}/image")
def get_redacted_image(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
    annotated: bool = False,
):
    """The redacted page image (PNG bytes). Returns 404 when the cell didn't
    have an associated page image — text-only redaction is still useful.

    ``annotated=true`` serves the variant with green bbox outlines + entity
    labels so the UI can show *where* mock text was placed. The default
    (clean) variant is what you feed an LLM.
    """
    filename = "redacted_page_annotated.png" if annotated else "redacted_page.png"
    path = (
        pii_v2_store.redaction_dir(pii_run_id, document_id, page_index, ocr, detector)
        / filename
    )
    if not path.exists():
        raise HTTPException(404, "redacted image not available")
    return FileResponse(path, media_type="image/png")


@router.get("/{pii_run_id}/redaction/{document_id}/{page_index}/{ocr}/{detector}/mapping")
def get_redaction_mapping(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
    reveal: bool = False,
):
    """Return the mock→original mapping.

    Default (``reveal=false``) returns the plaintext-safe ``mapping_index``
    only (entity-type counts). With ``reveal=true`` it serves the raw
    Fernet ciphertext bytes — the caller must possess ``PII_MASK_KEY`` to
    decrypt. The server never decrypts; this keeps the key off the wire.
    """
    d = pii_v2_store.redaction_dir(pii_run_id, document_id, page_index, ocr, detector)
    if not d.exists():
        raise HTTPException(404, "no redaction for this cell")
    if not reveal:
        idx = d / "mapping.index.json"
        if not idx.exists():
            raise HTTPException(404, "mapping index missing")
        import json as _json
        return _json.loads(idx.read_text())
    cipher = d / "mapping.fernet"
    if not cipher.exists():
        raise HTTPException(404, "encrypted mapping missing")
    return FileResponse(cipher, media_type="application/octet-stream", filename="mapping.fernet")


@router.get("/{pii_run_id}/text-layout/{document_id}/{page_index}/{ocr}")
def get_text_layout(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
):
    """Char-range → source-region bbox mapping for the image annotation viewer.

    Used by the frontend to resolve char-offset PII spans (returned by
    detectors against the joined page text) into pixel bboxes to overlay
    on the page image.
    """
    layout = pii_v2_store.read_text_layout(pii_run_id, document_id, page_index, ocr)
    if layout is None:
        raise HTTPException(404, "text layout not found")
    return {"region_index": layout}
