"""Build the LLM prompt for a cross-document benchmark + parse the response.

A benchmark analysis pulls together:
- per-document, per-page review state (with ordered solutions + comments)
- per-(doc, run, page, solution) metric snapshot

…and asks Claude for a structured JSON summary of which solution wins per
category, with the *limitations* surfaced (drawn from reviewer comments).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from json_repair import repair_json  # type: ignore

from app import benchmark_store, review_store, run_store
from app.config import settings
from app.llm_io import logged_messages_create
from app.pipeline.ssl_env import ssl_env_overrides  # noqa: F401 — env applied at module import implicitly

logger = logging.getLogger("ote.benchmark.analyzer")


SYSTEM_PROMPT = (
    "You are an expert reviewer of OCR / document-parsing solutions. "
    "Given a set of documents, multiple solutions run over them, reviewer "
    "comments, and per-page acceptance ordering, summarize which solution is "
    "best per category (tables, text, pii, layout) with concrete LIMITATIONS "
    "drawn from the reviewer comments. Output JSON only — no markdown, no "
    "commentary."
)

OUTPUT_SCHEMA = """{
  "by_category": {
    "tables": { "winner": "<solution name>", "runners_up": ["..."], "limitations": ["..."] },
    "text":   { "winner": "...",             "runners_up": ["..."], "limitations": ["..."] },
    "pii":    { "winner": "...",             "runners_up": ["..."], "limitations": ["..."] },
    "layout": { "winner": "...",             "runners_up": ["..."], "limitations": ["..."] }
  },
  "overall":  { "winner": "...", "rationale": "..." },
  "per_document_notes": [
    { "document_id": "...", "filename": "...", "notes": "..." }
  ]
}"""


def build_payload(selections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collect per-doc snapshot of reviews + per-(run, page, solution) metrics."""
    review_snapshot: Dict[str, Any] = {}
    metrics_snapshot: Dict[str, Any] = {}

    for sel in selections:
        doc_id = sel["document_id"]
        run_id = sel["run_id"]
        pages = sel.get("page_indices") or []

        review = review_store.load(doc_id) or {"pages": {}}
        review_snapshot[doc_id] = {
            "filename": review.get("filename") or doc_id,
            "selected_pages": [
                {
                    "page_index": pi,
                    "categories": (review.get("pages", {}).get(str(pi)) or {}).get("categories") or {},
                    "rejections": (review.get("pages", {}).get(str(pi)) or {}).get("rejections") or {},
                    "page_solution": (review.get("pages", {}).get(str(pi)) or {}).get("solution"),
                }
                for pi in pages
            ],
        }

        state = run_store.read_run(run_id)
        if state is None:
            metrics_snapshot[run_id] = {"error": "run not found"}
            continue
        metrics_snapshot[run_id] = {
            "document_id": doc_id,
            "filename": (state.get("document") or {}).get("filename"),
            "per_solution": {},
        }
        for sol in state.get("solution_results") or []:
            per_page = []
            for p in sol.get("pages") or []:
                if pages and p.get("page_index") not in pages:
                    continue
                per_page.append({
                    "page_index": p.get("page_index"),
                    "regions": len(p.get("regions") or []),
                    "tables": len(p.get("tables") or []),
                    "custom_tables": len(p.get("custom_tables") or []),
                    "custom_table_status": p.get("custom_table_status"),
                    "pii_spans": sum(len(r.get("pii_spans") or []) for r in p.get("regions") or []),
                })
            metrics_snapshot[run_id]["per_solution"][sol.get("solution_name")] = {
                "status": sol.get("status"),
                "overall_confidence": sol.get("overall_confidence"),
                "duration_ms": (sol.get("timings") or {}).get("total_ms"),
                "pages": per_page,
            }

    return {"reviews": review_snapshot, "metrics": metrics_snapshot}


def build_prompt(payload: Dict[str, Any]) -> str:
    return (
        "Analyze these documents and their solution comparisons.\n\n"
        "Data (JSON):\n"
        f"```json\n{json.dumps(payload, indent=2, default=str)[:80000]}\n```\n\n"
        "Output JSON matching this schema exactly:\n"
        f"```json\n{OUTPUT_SCHEMA}\n```\n\n"
        "Rules:\n"
        "- Pick winners by combining reviewer acceptance order (lower = better), comments, and metrics.\n"
        "- Limitations should QUOTE reviewer comments where useful (e.g. 'mangled multiline cells').\n"
        "- runners_up is a list of solution names in preference order, excluding the winner.\n"
        "- If a category has no acceptance data, set winner to the highest-metric solution and add a limitation noting it.\n"
        "- REJECTED solutions (in 'rejections' per page) MUST NOT appear as winner or runner-up for that category; quote the rejection reason in limitations.\n"
        "- Output JSON only."
    )


async def _call_claude(prompt: str) -> str:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await logged_messages_create(
        client,
        "benchmark.analyzer",
        model=settings.anthropic_model,
        max_tokens=min(max(settings.anthropic_max_tokens, 4096), 8192),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    )
    blocks = getattr(response, "content", None) or []
    if not blocks or getattr(blocks[0], "type", None) != "text":
        return ""
    return (getattr(blocks[0], "text", None) or "").strip()


def _parse(raw: str) -> Dict[str, Any]:
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        pass
    try:
        repaired = repair_json(txt, return_objects=False)
        return json.loads(repaired)
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError("could not parse LLM JSON")


def run_analysis(analysis_id: str) -> None:
    """Run synchronously (intended to be called from a background thread)."""
    rec = benchmark_store.load(analysis_id)
    if rec is None:
        logger.warning("analysis %s missing", analysis_id)
        return
    try:
        payload = build_payload(rec["selections"])
        rec["review_snapshot"] = payload["reviews"]
        rec["metrics_snapshot"] = payload["metrics"]
        prompt = build_prompt(payload)
        rec["llm_input_preview"] = prompt[:4000]
        benchmark_store.save(rec)

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        raw = asyncio.run(_call_claude(prompt))
        rec["llm_raw"] = raw
        parsed = _parse(raw) if raw else {}
        rec["llm_summary"] = parsed
        rec["status"] = "done"
        benchmark_store.save(rec)
    except Exception as exc:  # noqa: BLE001
        logger.exception("benchmark analysis %s failed", analysis_id)
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"
        benchmark_store.save(rec)
