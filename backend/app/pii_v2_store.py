"""Filesystem-backed persistence for pii_v2 runs.

Layout (one directory per pii_run_id):

    storage/pii_runs/<pii_run_id>/
        pii_run.json                                # top-level state
        <doc_id>/<page_index>/<ocr>/text.txt        # text input
        <doc_id>/<page_index>/<ocr>/<detector>.json # DetectorResult payload

Keeps the run document small (state file) and pushes per-cell payloads to
disk so the dashboard can pull them lazily.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_LOCK = threading.Lock()


def _root() -> Path:
    p = settings.pii_v2_runs_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_dir(pii_run_id: str) -> Path:
    return _root() / pii_run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(pii_run_id: str) -> Path:
    return run_dir(pii_run_id) / "pii_run.json"


def _read(pii_run_id: str) -> Optional[Dict[str, Any]]:
    p = _state_path(pii_run_id)
    if not p.exists():
        return None
    text = p.read_text().strip()
    if not text:
        return None
    return json.loads(text)


def _write(pii_run_id: str, state: Dict[str, Any]) -> None:
    _state_path(pii_run_id).write_text(json.dumps(state, indent=2, default=str))


def init_run(
    pii_run_id: str,
    documents: List[Dict[str, Any]],
    ocr_producers: List[str],
    detector_names: List[str],
    jurisdictions: List[str],
    paired_run_ids: Optional[List[str]] = None,
    paired_batch_id: Optional[str] = None,
) -> None:
    d = run_dir(pii_run_id)
    d.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    state: Dict[str, Any] = {
        "pii_run_id": pii_run_id,
        "status": "running",
        "started_at": now,
        "updated_at": now,
        "ocr_producers": ocr_producers,
        "detector_names": detector_names,
        "jurisdictions": jurisdictions,
        "paired_run_ids": paired_run_ids or [],
        "paired_batch_id": paired_batch_id,
        "documents": [
            {
                "document_id": doc["document_id"],
                "filename": doc.get("filename") or doc["document_id"],
                "pdf_kind": doc.get("pdf_kind", "unknown"),
                "n_pages": doc.get("n_pages", 0),
                "paired_run_id": doc.get("paired_run_id"),
                "status": "queued",
                "started_at": None,
                "finished_at": None,
                "pages": {},  # page_index -> { ocr -> { detector -> summary } }
            }
            for doc in documents
        ],
        "stats": {
            "total_docs": len(documents),
            "done_docs": 0,
            "error_docs": 0,
        },
    }
    with _LOCK:
        _write(pii_run_id, state)


def reset_documents_for_resume(pii_run_id: str, document_ids: List[str]) -> None:
    """Wipe per-doc state (pages, status, timestamps) so a resume re-runs cleanly.

    Leaves the top-level pii_run config (producers, detectors, jurisdictions)
    intact so the resume picks up exactly where it left off.
    """
    with _LOCK:
        state = _read(pii_run_id)
        if state is None:
            return
        targets = set(document_ids)
        for doc in state.get("documents", []):
            if doc["document_id"] not in targets:
                continue
            doc["status"] = "queued"
            doc["started_at"] = None
            doc["finished_at"] = None
            doc["pages"] = {}
        state["status"] = "running"
        state["finished_at"] = None
        state["updated_at"] = _now_iso()
        docs = state.get("documents", [])
        state["stats"]["done_docs"] = sum(1 for d in docs if d["status"] == "done")
        state["stats"]["error_docs"] = sum(1 for d in docs if d["status"] == "error")
        _write(pii_run_id, state)


def update_document_status(pii_run_id: str, document_id: str, status: str) -> None:
    with _LOCK:
        state = _read(pii_run_id)
        if state is None:
            return
        for doc in state.get("documents", []):
            if doc["document_id"] == document_id:
                doc["status"] = status
                if status == "running" and not doc.get("started_at"):
                    doc["started_at"] = _now_iso()
                if status in ("done", "error", "partial"):
                    doc["finished_at"] = _now_iso()
                break
        docs = state.get("documents", [])
        state["stats"]["done_docs"] = sum(1 for d in docs if d["status"] == "done")
        state["stats"]["error_docs"] = sum(1 for d in docs if d["status"] == "error")
        state["stats"]["partial_docs"] = sum(1 for d in docs if d["status"] == "partial")
        if all(d["status"] in ("done", "error", "partial") for d in docs):
            # "partial" docs are terminal, so the run as a whole is terminal
            # too, but flag the top-level status so the dashboard can show
            # a Resume control alongside the OK badge.
            any_partial = any(d["status"] == "partial" for d in docs)
            any_error = any(d["status"] == "error" for d in docs)
            state["status"] = "partial" if (any_partial or any_error) else "done"
            state["finished_at"] = _now_iso()
        state["updated_at"] = _now_iso()
        _write(pii_run_id, state)


def update_cell_summary(
    *,
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
    extra: Dict[str, Any],
) -> None:
    """Merge ``extra`` into an already-written cell summary.

    Used by the redaction orchestrator to stamp ``redaction: {n_mocks, ...}``
    onto the cell after ``write_cell`` so the dashboard's polling sees it
    without a second round-trip.
    """
    with _LOCK:
        state = _read(pii_run_id)
        if state is None:
            return
        for doc in state.get("documents", []):
            if doc["document_id"] != document_id:
                continue
            page_key = str(page_index)
            cell = (
                doc.get("pages", {})
                .get(page_key, {})
                .get(ocr, {})
                .get(detector)
            )
            if cell is None:
                return
            cell.update(extra)
            state["updated_at"] = _now_iso()
            _write(pii_run_id, state)
            return


def paired_run_id_for_doc(
    state: Optional[Dict[str, Any]],
    document_id: str,
) -> Optional[str]:
    """Return the paired ``/runs/<id>`` for a specific document.

    Reading ``state["paired_run_ids"]`` globally (and grabbing the first) is
    a bug when a pii_run is paired with a multi-doc /batches — every
    document then resolves to the FIRST paired run's images. Each
    document entry carries its own ``paired_run_id`` set at init time;
    that's the one to use.
    """
    if not state:
        return None
    for doc in state.get("documents", []) or []:
        if doc.get("document_id") == document_id:
            return doc.get("paired_run_id")
    return None


def cell_dir(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str | None = None,
) -> Path:
    """Public helper used by the redaction orchestrator.

    The detector name is optional — when ``None`` the path points at the
    OCR-level directory (used to be shared across detectors for that OCR).
    """
    d = run_dir(pii_run_id) / document_id / f"page-{page_index:03d}" / ocr
    if detector is not None:
        d = d / detector
    return d


def write_cell(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
    text: str,
    result_payload: Dict[str, Any],
) -> None:
    cell_dir = run_dir(pii_run_id) / document_id / f"page-{page_index:03d}" / ocr
    cell_dir.mkdir(parents=True, exist_ok=True)
    (cell_dir / "text.txt").write_text(text)
    (cell_dir / f"{detector}.json").write_text(json.dumps(result_payload, indent=2, default=str))

    meta = result_payload.get("metadata") or {}
    ocr_status = meta.get("ocr_status")  # None when this is a real detection
    entities = result_payload.get("entities") or []
    summary = {
        "entity_count": len(entities),
        "latency_ms": result_payload.get("latency_ms", 0),
        "error": result_payload.get("error"),
        "entity_types": _entity_type_counts(entities),
        "category_counts": _category_counts(entities),
        "status": ocr_status or ("error" if result_payload.get("error") else "ok"),
        "reason": meta.get("ocr_reason"),
        "audit_step_count": len(meta.get("audit") or []),
        "occurrence_count": len(meta.get("occurrences") or {}),
        "manual_annotation_count": sum(
            1 for e in entities if (e.get("metadata") or {}).get("discovery") == "manual_only"
        ),
        "search_only_count": sum(
            1 for e in entities if (e.get("metadata") or {}).get("discovery") == "search_only"
        ),
    }
    with _LOCK:
        state = _read(pii_run_id)
        if state is None:
            return
        for doc in state["documents"]:
            if doc["document_id"] != document_id:
                continue
            pages = doc["pages"]
            page_key = str(page_index)
            pages.setdefault(page_key, {})
            pages[page_key].setdefault(ocr, {})
            pages[page_key][ocr][detector] = summary
            break
        state["updated_at"] = _now_iso()
        _write(pii_run_id, state)


def _entity_type_counts(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for e in entities:
        t = e.get("entity_type", "?")
        counts[t] = counts.get(t, 0) + 1
    return counts


def _category_counts(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    from app.pii_v2.categories import category_for

    counts: Dict[str, int] = {}
    for e in entities:
        c = category_for(str(e.get("entity_type", "")))
        counts[c] = counts.get(c, 0) + 1
    return counts


def read_run(pii_run_id: str) -> Optional[Dict[str, Any]]:
    return _read(pii_run_id)


def read_cell(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
) -> Optional[Dict[str, Any]]:
    cell_dir = run_dir(pii_run_id) / document_id / f"page-{page_index:03d}" / ocr
    p = cell_dir / f"{detector}.json"
    if not p.exists():
        return None
    payload = json.loads(p.read_text())
    text_path = cell_dir / "text.txt"
    if text_path.exists():
        payload["source_text"] = text_path.read_text()
    return payload


def redaction_dir(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
) -> Path:
    return cell_dir(pii_run_id, document_id, page_index, ocr, detector) / "redaction"


def read_redaction(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
    detector: str,
) -> Optional[Dict[str, Any]]:
    """Return ``{redacted_text, diff_spans, mapping_index, has_image}`` or ``None``."""
    d = redaction_dir(pii_run_id, document_id, page_index, ocr, detector)
    if not d.exists():
        return None
    out: Dict[str, Any] = {}
    text_p = d / "redacted_text.txt"
    diff_p = d / "diff.json"
    index_p = d / "mapping.index.json"
    image_p = d / "redacted_page.png"
    out["redacted_text"] = text_p.read_text() if text_p.exists() else ""
    out["diff_spans"] = json.loads(diff_p.read_text()) if diff_p.exists() else []
    out["mapping_index"] = json.loads(index_p.read_text()) if index_p.exists() else None
    out["has_image"] = image_p.exists()
    return out


def read_text_layout(
    pii_run_id: str,
    document_id: str,
    page_index: int,
    ocr: str,
) -> Optional[List[Dict[str, Any]]]:
    """Char-range → region bbox mapping for a (doc, page, ocr) tuple."""
    p = (
        run_dir(pii_run_id)
        / document_id
        / "text_layout"
        / ocr
        / f"page-{page_index:03d}.json"
    )
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(_root().glob("*/pii_run.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            state = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "pii_run_id": state.get("pii_run_id"),
            "status": state.get("status"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "updated_at": state.get("updated_at"),
            "ocr_producers": state.get("ocr_producers", []),
            "detector_names": state.get("detector_names", []),
            "paired_run_ids": state.get("paired_run_ids", []),
            "paired_batch_id": state.get("paired_batch_id"),
            "stats": state.get("stats", {}),
            "n_documents": len(state.get("documents", [])),
        })
        if len(out) >= limit:
            break
    return out
