"""Document catalog: 16 ./data samples + user uploads."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Dict, List

from fastapi import UploadFile

from app.config import settings
from app.core.pdf_kind import classify
from app.core.rasterize import rasterize_pdf
from app.core.schemas import DocumentResult


SAMPLE_PREFIX = "sample"
UPLOAD_PREFIX = "upload"


def _uploads_dir() -> Path:
    p = settings.runs_path.parent / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _id_for_sample(name: str) -> str:
    return f"{SAMPLE_PREFIX}:{name}"


def _path_for(doc_id: str) -> Path:
    if doc_id.startswith(f"{SAMPLE_PREFIX}:"):
        return settings.data_path / doc_id.split(":", 1)[1]
    if doc_id.startswith(f"{UPLOAD_PREFIX}:"):
        return _uploads_dir() / doc_id.split(":", 1)[1]
    raise ValueError(f"unknown document id: {doc_id}")


def list_documents() -> List[Dict]:
    out: List[Dict] = []
    if settings.data_path.exists():
        for p in sorted(settings.data_path.glob("*.pdf")):
            out.append(
                {
                    "id": _id_for_sample(p.name),
                    "filename": p.name,
                    "source": "sample",
                    "size_bytes": p.stat().st_size,
                }
            )
    up = _uploads_dir()
    for p in sorted(up.glob("*.pdf")):
        out.append(
            {
                "id": f"{UPLOAD_PREFIX}:{p.name}",
                "filename": p.name,
                "source": "upload",
                "size_bytes": p.stat().st_size,
            }
        )
    return out


def save_upload(file: UploadFile) -> Dict:
    name = f"{uuid.uuid4().hex[:8]}_{file.filename or 'upload.pdf'}"
    dest = _uploads_dir() / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return get_document_meta(f"{UPLOAD_PREFIX}:{name}")


def get_document_meta(doc_id: str) -> Dict:
    path = _path_for(doc_id)
    if not path.exists():
        raise FileNotFoundError(doc_id)
    kind, n_pages = classify(path)
    return {
        "id": doc_id,
        "filename": path.name,
        "pdf_kind": kind,
        "n_pages": n_pages,
        "path": str(path),
    }


def page_png(doc_id: str, page_index: int, dpi: int) -> Path:
    """Rasterize on demand (cached in storage/runs/_preview/<doc>/<dpi>)."""
    path = _path_for(doc_id)
    cache_dir = settings.runs_path / "_preview" / doc_id.replace(":", "_") / str(dpi)
    target = cache_dir / f"page-{page_index:03d}.png"
    if target.exists():
        return target
    pages = rasterize_pdf(path, cache_dir, dpi=dpi)
    for p in pages:
        if p.page_index == page_index:
            return p.png_path
    raise FileNotFoundError(f"page {page_index} not found in {doc_id}")


def empty_document_result(doc_id: str) -> DocumentResult:
    meta = get_document_meta(doc_id)
    return DocumentResult(
        document_id=doc_id,
        filename=meta["filename"],
        pdf_kind=meta["pdf_kind"],
        n_pages=meta["n_pages"],
    )


def resolve_path(doc_id: str) -> Path:
    return _path_for(doc_id)
