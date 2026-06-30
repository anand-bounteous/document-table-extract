"""Render the side-by-side comparison report as standalone HTML.

When ``embed_images=True``, every annotated PNG is inlined as a data URL so the
HTML/PDF works without needing any URL resolution.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import run_store

_TPL_DIR = Path(__file__).resolve().parent / "templates"
_ENV = Environment(
    loader=FileSystemLoader(str(_TPL_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _data_url(path: Path) -> str:
    media = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media};base64,{b64}"


def _embed_solution_images(run_id: str, sol: Dict[str, Any]) -> Dict[str, Any]:
    for page in sol.get("pages", []):
        ref = page.get("annotated_image_ref")
        if ref:
            path = run_store.list_artifact(run_id, ref)
            page["annotated_image_data_url"] = _data_url(path) if path else None
    return sol


def build_report_html(state: Dict[str, Any], *, embed_images: bool = False) -> str:
    run_id = state["run_id"]
    if embed_images:
        for sol in state["solution_results"]:
            _embed_solution_images(run_id, sol)
    template = _ENV.get_template("report.html.j2")
    return template.render(state=state)
