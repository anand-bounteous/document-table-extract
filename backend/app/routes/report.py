"""HTML / PDF report rendering. WeasyPrint is lazy-imported (heavy)."""

from __future__ import annotations

import logging
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from app import run_store
from app.report.builder import build_report_html

logger = logging.getLogger("ote.report")
router = APIRouter(prefix="/runs", tags=["report"])


@router.get("/{run_id}/report.html", response_class=HTMLResponse)
def get_report_html(run_id: str):
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    return HTMLResponse(build_report_html(state, embed_images=True))


@router.get("/{run_id}/report.pdf")
def get_report_pdf(run_id: str):
    state = run_store.read_run(run_id)
    if state is None:
        raise HTTPException(404, f"run not found: {run_id}")
    html = build_report_html(state, embed_images=True)
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"WeasyPrint not available: {exc}")
    buf = BytesIO()
    HTML(string=html, base_url=str(run_store.run_dir(run_id))).write_pdf(buf)
    return Response(buf.getvalue(), media_type="application/pdf")
