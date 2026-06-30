"""Document upload + catalog endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import document_store, run_store
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_docs():
    return {"documents": document_store.list_documents()}


@router.post("")
async def upload_doc(file: UploadFile):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf accepted")
    return document_store.save_upload(file)


# ----- SPECIFIC SUB-PATHS FIRST (path-converter is greedy) ------------------


@router.get("/file/{doc_id:path}")
def get_doc_file(doc_id: str):
    try:
        path = document_store.resolve_path(doc_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"document file missing: {doc_id}")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@router.get("/page/{page_index}/{doc_id:path}")
def get_page_png(doc_id: str, page_index: int, dpi: int | None = None):
    try:
        png = document_store.page_png(doc_id, page_index, dpi or settings.default_dpi)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(png, media_type="image/png")


@router.get("/runs/{doc_id:path}")
def list_doc_runs(doc_id: str):
    """All runs that processed this document, newest first."""
    matched = [r for r in run_store.list_runs(limit=500) if (r.get("document") or {}).get("document_id") == doc_id]
    return {"document_id": doc_id, "runs": matched}


class MergeRunsRequest(BaseModel):
    run_ids: List[str]


@router.post("/merge/{doc_id:path}")
def merge_runs(doc_id: str, req: MergeRunsRequest):
    """Merge results from multiple runs targeting the same document.

    For each ``(solution_name, page_index)`` we pick the best version across
    the selected runs:

      1. Reject ``error`` / ``skipped`` solutions per-run (unless every run
         has them in that state, in which case the latest wins so the
         dashboard still shows the failure reason).
      2. Among ``ok`` / ``partial`` results, pick the page with the highest
         ``overall_confidence``; ties broken by most recent ``updated_at``.

    Returns a synthetic ``RunState``-shaped object so existing
    ``SolutionCompareGrid`` rendering Just Works on the frontend.
    """
    if len(req.run_ids) < 2:
        raise HTTPException(400, "merge needs at least 2 run_ids")
    runs = []
    for rid in req.run_ids:
        state = run_store.read_run(rid)
        if state is None:
            raise HTTPException(404, f"run not found: {rid}")
        runs.append(state)
    by_solution: Dict[str, Dict[int, Tuple[str, Dict[str, Any]]]] = {}
    solution_results_by_name: Dict[str, Dict[str, Any]] = {}
    for state in runs:
        rid = state["run_id"]
        updated_at = state.get("updated_at", "")
        for sol in state.get("solution_results", []) or []:
            name = sol["solution_name"]
            sol_status = sol.get("status")
            existing = solution_results_by_name.get(name)
            if existing is None:
                solution_results_by_name[name] = {
                    **sol,
                    "_merged_from": [rid],
                }
            else:
                existing["_merged_from"].append(rid)
                if sol_status in ("ok", "partial") and (
                    existing.get("status") in ("error", "skipped")
                    or (sol.get("overall_confidence", 0) or 0)
                    > (existing.get("overall_confidence", 0) or 0)
                ):
                    existing.update({k: v for k, v in sol.items() if k != "pages"})
            # Per-page winner across runs
            page_index_map = by_solution.setdefault(name, {})
            for p in sol.get("pages") or []:
                idx = int(p["page_index"])
                cur = page_index_map.get(idx)
                if cur is None:
                    page_index_map[idx] = (rid, p)
                    continue
                cur_page = cur[1]
                cur_runs_at = next((s for s in runs if s["run_id"] == cur[0]), {}).get("updated_at", "")
                # Prefer non-error / non-empty pages first.
                cur_has_data = bool(cur_page.get("regions") or cur_page.get("tables"))
                new_has_data = bool(p.get("regions") or p.get("tables"))
                if new_has_data and not cur_has_data:
                    page_index_map[idx] = (rid, p)
                    continue
                if not new_has_data:
                    continue
                # Both have data — confidence then recency.
                cur_conf = cur_page.get("confidence", 0) or 0
                new_conf = p.get("confidence", 0) or 0
                if new_conf > cur_conf or (new_conf == cur_conf and updated_at > cur_runs_at):
                    page_index_map[idx] = (rid, p)

    # Compile merged synthetic SolutionResults
    merged_solutions = []
    sources_by_solution: Dict[str, Dict[int, str]] = {}
    for name, sol in solution_results_by_name.items():
        pages_map = by_solution.get(name, {})
        ordered = [pages_map[i][1] for i in sorted(pages_map.keys())]
        sources_by_solution[name] = {i: pages_map[i][0] for i in sorted(pages_map.keys())}
        merged_solutions.append({
            **sol,
            "pages": ordered,
            "merged_from": sol.get("_merged_from", []),
        })

    base = runs[0]
    return {
        "merged": True,
        "document_id": doc_id,
        "merged_from_runs": req.run_ids,
        "run_id": f"merged:{'+'.join(req.run_ids)}",
        "document": base.get("document"),
        "status": "done",
        "solution_names": list(solution_results_by_name.keys()),
        "completed": list(solution_results_by_name.keys()),
        "solution_results": merged_solutions,
        "page_sources_by_solution": sources_by_solution,
    }


@router.get("/diff/{doc_id:path}")
def diff_runs(doc_id: str, run_a: str, run_b: str):
    """Compute per-solution metric deltas between two runs of this document."""
    a = run_store.read_run(run_a)
    b = run_store.read_run(run_b)
    if a is None or b is None:
        raise HTTPException(404, "run not found")
    out = []
    for name in sorted({s["solution_name"] for s in a["solution_results"]} | {s["solution_name"] for s in b["solution_results"]}):
        sa = next((s for s in a["solution_results"] if s["solution_name"] == name), None)
        sb = next((s for s in b["solution_results"] if s["solution_name"] == name), None)
        out.append({
            "name": name,
            "a": _metric_snapshot(sa),
            "b": _metric_snapshot(sb),
            "delta": _delta(sa, sb),
        })
    return {
        "document_id": doc_id,
        "run_a": run_a,
        "run_b": run_b,
        "solutions": out,
    }


def _metric_snapshot(sol):
    if sol is None:
        return None
    regions = sum(len(p.get("regions") or []) for p in sol.get("pages") or [])
    tables = sum(len(p.get("tables") or []) for p in sol.get("pages") or [])
    pii = sum(len(r.get("pii_spans") or []) for p in sol.get("pages") or [] for r in p.get("regions") or [])
    return {
        "regions": regions,
        "tables": tables,
        "pii": pii,
        "overall_confidence": sol.get("overall_confidence", 0.0),
        "duration_ms": (sol.get("timings") or {}).get("total_ms", 0.0),
        "status": sol.get("status"),
    }


def _delta(a, b):
    if a is None or b is None:
        return None
    sa, sb = _metric_snapshot(a), _metric_snapshot(b)
    return {
        "regions": sb["regions"] - sa["regions"],
        "tables": sb["tables"] - sa["tables"],
        "pii": sb["pii"] - sa["pii"],
        "overall_confidence": sb["overall_confidence"] - sa["overall_confidence"],
        "duration_ms": sb["duration_ms"] - sa["duration_ms"],
    }


# ----- CATCH-ALL LAST -------------------------------------------------------


@router.get("/{doc_id:path}")
def get_doc(doc_id: str):
    try:
        return document_store.get_document_meta(doc_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
