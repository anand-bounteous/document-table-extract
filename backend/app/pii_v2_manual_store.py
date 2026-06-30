"""Manual PII annotations + USER_CUSTOM dictionary store.

Two scopes:

- ``doc``  (default): persisted at
  ``storage/pii_runs/_manual_annotations/<document_id>.json``. Survives
  across pii_runs and is promoted into the global USER_CUSTOM dictionary
  so the regex detector can pick it up next time.
- ``run`` (opt-out): persisted at
  ``storage/pii_runs/<pii_run_id>/<doc_id>/manual_annotations.json``.
  Treated as one-shot context — not promoted to the dictionary.

The merged ``read_for(document_id, pii_run_id)`` view is what
``pii_runner._run_detectors`` consumes for the manual_overlay post-process.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_LOCK = threading.Lock()


def _doc_annotations_path(document_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in document_id)
    p = settings.pii_v2_runs_path / "_manual_annotations"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.json"


def _run_annotations_path(pii_run_id: str, document_id: str) -> Path:
    from app import pii_v2_store

    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in document_id)
    d = pii_v2_store.run_dir(pii_run_id) / safe
    d.mkdir(parents=True, exist_ok=True)
    return d / "manual_annotations.json"


def _custom_dictionary_path(jurisdiction: str) -> Path:
    p = settings.pii_v2_runs_path / "_custom_dictionary"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{jurisdiction}.json"


def _load(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return []


def _save(path: Path, items: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, indent=2, default=str))


def list_for_document(document_id: str) -> List[Dict[str, Any]]:
    return _load(_doc_annotations_path(document_id))


def list_for_run(pii_run_id: str, document_id: str) -> List[Dict[str, Any]]:
    return _load(_run_annotations_path(pii_run_id, document_id))


def read_for(document_id: str, pii_run_id: Optional[str]) -> List[Dict[str, Any]]:
    """Union of doc-scoped (always) + run-scoped (when pii_run_id is set)."""
    out: List[Dict[str, Any]] = list_for_document(document_id)
    if pii_run_id:
        out += list_for_run(pii_run_id, document_id)
    return out


def add_annotation(
    *,
    document_id: str,
    pii_run_id: Optional[str],
    page_index: int,
    entity_type: str,
    text: str,
    bbox_px: Optional[Dict[str, Any]] = None,
    jurisdiction: Optional[str] = None,
    scope: str = "doc",
) -> Dict[str, Any]:
    annotation = {
        "annotation_id": uuid.uuid4().hex[:12],
        "scope": scope,
        "page_index": int(page_index),
        "entity_type": entity_type,
        "text": text,
        "bbox_px": bbox_px,
        "jurisdiction": jurisdiction,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        if scope == "run":
            if not pii_run_id:
                raise ValueError("scope=run requires pii_run_id")
            path = _run_annotations_path(pii_run_id, document_id)
            items = _load(path)
            items.append(annotation)
            _save(path, items)
        else:
            path = _doc_annotations_path(document_id)
            items = _load(path)
            items.append(annotation)
            _save(path, items)
            _promote_to_dictionary(annotation)
    return annotation


def delete_annotation(
    *,
    document_id: str,
    pii_run_id: Optional[str],
    annotation_id: str,
) -> bool:
    """Removes the annotation from whichever scope it lives in. Does NOT
    retract a promotion to the global dictionary (intentional — user can
    edit the dictionary file directly if they want to recall)."""
    deleted = False
    with _LOCK:
        for path in (
            _doc_annotations_path(document_id),
            _run_annotations_path(pii_run_id, document_id) if pii_run_id else None,
        ):
            if path is None or not path.exists():
                continue
            items = _load(path)
            new_items = [a for a in items if a.get("annotation_id") != annotation_id]
            if len(new_items) != len(items):
                _save(path, new_items)
                deleted = True
    return deleted


def _promote_to_dictionary(annotation: Dict[str, Any]) -> None:
    """Append a doc-scoped annotation to the global USER_CUSTOM dictionary."""
    jurisdiction = annotation.get("jurisdiction") or "USER_CUSTOM"
    path = _custom_dictionary_path(jurisdiction)
    items = _load(path)
    # Dedup on (entity_type, text) — promotion is idempotent.
    key = (annotation["entity_type"], annotation["text"])
    if not any((it.get("entity_type"), it.get("text")) == key for it in items):
        items.append({
            "entity_type": annotation["entity_type"],
            "text": annotation["text"],
            "added_from": annotation.get("annotation_id"),
            "created_at": annotation.get("created_at"),
        })
        _save(path, items)


def read_custom_dictionary(jurisdiction: str) -> List[Dict[str, Any]]:
    return _load(_custom_dictionary_path(jurisdiction))


def list_dictionaries() -> List[str]:
    root = settings.pii_v2_runs_path / "_custom_dictionary"
    if not root.exists():
        return []
    return [p.stem for p in root.glob("*.json")]
