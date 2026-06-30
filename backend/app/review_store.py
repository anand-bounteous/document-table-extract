"""Per-document review state.

A review records which solution the user accepted as the best result for each
page — both at page level ("overall best") and per-category (Tables / Text /
PII / Layout). One file per document at
``storage/reviews/<sanitized_doc_id>.json``::

    {
      "document_id": "sample:Foo.pdf",
      "filename": "Foo.pdf",
      "pages": {
        "0": {
          "solution": "claude_vision",                 # optional page-level pick
          "run_id": "abc123",
          "accepted_at": "...",
          "categories": {                              # independent per-area picks
            "tables": {"solution": "img2table",     "run_id": "abc123", "accepted_at": "..."},
            "text":   {"solution": "claude_vision", "run_id": "abc123", "accepted_at": "..."},
            "pii":    {"solution": "claude_vision", "run_id": "abc123", "accepted_at": "..."},
            "layout": {"solution": "opencv_tesseract","run_id":"abc123","accepted_at":"..."}
          }
        }
      },
      "updated_at": "..."
    }
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from app import run_store
from app.config import settings

Category = Literal["tables", "text", "pii", "layout"]
CATEGORIES: tuple[Category, ...] = ("tables", "text", "pii", "layout")

_LOCK = threading.Lock()


def _root() -> Path:
    p = settings.runs_path.parent / "reviews"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(doc_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", doc_id)


def _path(doc_id: str) -> Path:
    return _root() / f"{_safe(doc_id)}.json"


def load(doc_id: str) -> Optional[Dict[str, Any]]:
    p = _path(doc_id)
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    return _normalize_record(rec)


def _normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade legacy {category: {solution,...}} to {category: [{...,order,comment}]}.

    Idempotent — running on an already-normalized record is a no-op.
    """
    for _idx, page in (rec.get("pages") or {}).items():
        if not page:
            continue
        cats = page.get("categories")
        if not cats:
            continue
        for c, value in list(cats.items()):
            if isinstance(value, dict):
                # legacy single-accept shape
                cats[c] = [{
                    "solution": value.get("solution"),
                    "run_id": value.get("run_id"),
                    "accepted_at": value.get("accepted_at"),
                    "order": 1,
                    "comment": value.get("comment", ""),
                }]
    return rec


def _category_list(page: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    cats = page.setdefault("categories", {})
    entries = cats.get(category)
    if entries is None:
        cats[category] = []
        return cats[category]
    if isinstance(entries, dict):
        entries = [{
            "solution": entries.get("solution"),
            "run_id": entries.get("run_id"),
            "accepted_at": entries.get("accepted_at"),
            "order": 1,
            "comment": entries.get("comment", ""),
        }]
        cats[category] = entries
    return entries


def _renumber(entries: List[Dict[str, Any]]) -> None:
    """Re-assign order 1..N to entries IN-PLACE in their current list order."""
    for i, e in enumerate(entries, start=1):
        e["order"] = i


def _sort_by_order(entries: List[Dict[str, Any]]) -> None:
    entries.sort(key=lambda e: e.get("order") or 999999)


def save(record: Dict[str, Any]) -> None:
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    p = _path(record["document_id"])
    with _LOCK:
        p.write_text(json.dumps(record, indent=2, default=str))


def accept_page(*, document_id: str, filename: str, page_index: int, solution: str, run_id: str) -> Dict[str, Any]:
    """Page-level accept (the 'overall' winner). Does NOT touch per-category accepts."""
    rec = load(document_id) or {"document_id": document_id, "filename": filename, "pages": {}}
    rec["filename"] = filename
    page_entry = rec["pages"].get(str(page_index)) or {}
    page_entry.update({
        "solution": solution,
        "run_id": run_id,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    })
    rec["pages"][str(page_index)] = page_entry
    save(rec)
    return rec


def revoke_page(*, document_id: str, page_index: int) -> Optional[Dict[str, Any]]:
    """Drop the page-level pick; per-category picks are kept."""
    rec = load(document_id)
    if rec is None:
        return None
    page_entry = rec["pages"].get(str(page_index)) or {}
    for k in ("solution", "run_id", "accepted_at"):
        page_entry.pop(k, None)
    if page_entry:
        rec["pages"][str(page_index)] = page_entry
    else:
        rec["pages"].pop(str(page_index), None)
    save(rec)
    return rec


def accept_category(
    *,
    document_id: str,
    filename: str,
    page_index: int,
    category: Category,
    solution: str,
    run_id: str,
    order: Optional[int] = None,
    comment: str = "",
) -> Dict[str, Any]:
    """Add or update an accept for (page, category, solution).

    If the solution already has an entry: update order (if provided) + comment.
    Otherwise insert at the given order (defaults to next-available).
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    rec = load(document_id) or {"document_id": document_id, "filename": filename, "pages": {}}
    rec["filename"] = filename
    page_entry = rec["pages"].setdefault(str(page_index), {})
    entries = _category_list(page_entry, category)

    existing = next((e for e in entries if e["solution"] == solution), None)
    if existing is not None:
        if order is not None:
            existing["order"] = int(order)
        existing["comment"] = comment
        existing["run_id"] = run_id
        existing["accepted_at"] = datetime.now(timezone.utc).isoformat()
    else:
        new_order = int(order) if order is not None else (len(entries) + 1)
        entries.append({
            "solution": solution,
            "run_id": run_id,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "order": new_order,
            "comment": comment,
        })

    _sort_by_order(entries)
    _renumber(entries)
    save(rec)
    return rec


def reorder_category(
    *, document_id: str, page_index: int, category: Category, ordered_solutions: List[str]
) -> Optional[Dict[str, Any]]:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    rec = load(document_id)
    if rec is None:
        return None
    page_entry = rec["pages"].get(str(page_index)) or {}
    entries = _category_list(page_entry, category)
    by_name = {e["solution"]: e for e in entries}
    ordered: List[Dict[str, Any]] = []
    for name in ordered_solutions:
        if name in by_name:
            ordered.append(by_name.pop(name))
    # tack on remaining entries in their existing order
    ordered.extend(sorted(by_name.values(), key=lambda e: e.get("order") or 999999))
    page_entry.setdefault("categories", {})[category] = ordered
    rec["pages"][str(page_index)] = page_entry
    _renumber(ordered)
    save(rec)
    return rec


def comment_category(
    *, document_id: str, page_index: int, category: Category, solution: str, comment: str
) -> Optional[Dict[str, Any]]:
    rec = load(document_id)
    if rec is None:
        return None
    page_entry = rec["pages"].get(str(page_index)) or {}
    entries = _category_list(page_entry, category)
    target = next((e for e in entries if e["solution"] == solution), None)
    if target is None:
        return None
    target["comment"] = comment
    rec["pages"][str(page_index)] = page_entry
    save(rec)
    return rec


def reject_category(
    *,
    document_id: str,
    filename: str,
    page_index: int,
    category: Category,
    solution: str,
    run_id: str,
    reason: str = "",
) -> Dict[str, Any]:
    """Record a negative verdict for (page, category, solution). Upserts if already present."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    rec = load(document_id) or {"document_id": document_id, "filename": filename, "pages": {}}
    rec["filename"] = filename
    page_entry = rec["pages"].setdefault(str(page_index), {})
    entries = _rejection_list(page_entry, category)
    existing = next((e for e in entries if e["solution"] == solution), None)
    if existing is not None:
        existing["reason"] = reason
        existing["run_id"] = run_id
        existing["rejected_at"] = datetime.now(timezone.utc).isoformat()
    else:
        entries.append({
            "solution": solution,
            "run_id": run_id,
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
        })
    save(rec)
    return rec


def unreject_category(
    *, document_id: str, page_index: int, category: Category, solution: str
) -> Optional[Dict[str, Any]]:
    """Remove a negative verdict for one solution in a category."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    rec = load(document_id)
    if rec is None:
        return None
    page_entry = rec["pages"].get(str(page_index)) or {}
    rejections = page_entry.get("rejections") or {}
    entries = rejections.get(category) or []
    entries = [e for e in entries if e["solution"] != solution]
    if entries:
        rejections[category] = entries
    else:
        rejections.pop(category, None)
    if rejections:
        page_entry["rejections"] = rejections
    else:
        page_entry.pop("rejections", None)
    if page_entry:
        rec["pages"][str(page_index)] = page_entry
    else:
        rec["pages"].pop(str(page_index), None)
    save(rec)
    return rec


def _rejection_list(page: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    rejections = page.setdefault("rejections", {})
    if category not in rejections:
        rejections[category] = []
    return rejections[category]


def revoke_category(
    *, document_id: str, page_index: int, category: Category, solution: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Drop one solution's entry (if `solution` given) or clear the whole category list."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    rec = load(document_id)
    if rec is None:
        return None
    page_entry = rec["pages"].get(str(page_index)) or {}
    cats = page_entry.get("categories") or {}
    if solution is None:
        cats.pop(category, None)
    else:
        entries = _category_list(page_entry, category)
        entries[:] = [e for e in entries if e["solution"] != solution]
        if not entries:
            cats.pop(category, None)
        else:
            _renumber(entries)
            cats[category] = entries
    if not cats:
        page_entry.pop("categories", None)
    if page_entry:
        rec["pages"][str(page_index)] = page_entry
    else:
        rec["pages"].pop(str(page_index), None)
    save(rec)
    return rec


def compose(document_id: str) -> Dict[str, Any]:
    """Build the per-page composite from current category accepts.

    For each page, each category's content (tables / text+regions / PII / layout)
    is pulled from the solution accepted for THAT category, looking up the
    correct run via `run_id`. Where no per-category accept exists, fall back to
    the page-level `solution`, then to the highest-confidence solution from the
    most-recent run that has `status == "done"` for this doc.
    """
    rec = load(document_id) or {"document_id": document_id, "filename": "", "pages": {}}
    doc_runs = [r for r in run_store.list_runs(limit=500) if (r.get("document") or {}).get("document_id") == document_id]
    # newest first
    doc_runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)

    composite_pages: List[Dict[str, Any]] = []
    page_keys = sorted(rec.get("pages", {}).keys(), key=int) if rec.get("pages") else []

    # If no reviews exist yet, still emit composites for each page using "best available".
    if not page_keys and doc_runs:
        n_pages = (doc_runs[0].get("document") or {}).get("n_pages") or 0
        page_keys = [str(i) for i in range(n_pages)]

    for k in page_keys:
        idx = int(k)
        entry = rec["pages"].get(k) or {}
        cats = entry.get("categories") or {}
        page_level = entry.get("solution")
        page_level_run = entry.get("run_id")

        sources: Dict[str, Optional[str]] = {}
        ordered_sources: Dict[str, List[Dict[str, Any]]] = {}
        page_data = {"page_index": idx, "tables": [], "regions": [], "pii": []}

        for category in CATEGORIES:
            entries = cats.get(category)
            if isinstance(entries, dict):
                entries = [entries]  # legacy
            chosen = None
            if isinstance(entries, list) and entries:
                ordered = sorted(entries, key=lambda e: e.get("order") or 999999)
                ordered_sources[category] = ordered
                chosen = ordered[0]
            if chosen:
                solution = chosen["solution"]
                run_id = chosen["run_id"]
            elif page_level and page_level_run:
                solution = page_level
                run_id = page_level_run
            else:
                solution, run_id = _best_available(doc_runs, idx)
            sources[category] = solution
            if not solution or not run_id:
                continue
            page_payload = _page_from_run(run_id, solution, idx)
            if page_payload is None:
                continue
            if category == "tables":
                page_data["tables"] = page_payload.get("tables") or []
            elif category == "text":
                page_data["regions"] = page_payload.get("regions") or []
            elif category == "pii":
                # PII spans live on regions — collect them
                spans: List[Dict[str, Any]] = []
                for r in page_payload.get("regions") or []:
                    for s in r.get("pii_spans") or []:
                        spans.append(s)
                page_data["pii"] = spans
            elif category == "layout":
                # Region types / annotated_image_ref reflect layout
                page_data["layout_regions"] = page_payload.get("regions") or []
                page_data["annotated_image_ref"] = page_payload.get("annotated_image_ref")

        composite_pages.append({**page_data, "sources": sources, "ordered_sources": ordered_sources})

    return {
        "document_id": document_id,
        "filename": rec.get("filename") or (doc_runs[0].get("document") or {}).get("filename", document_id) if doc_runs else rec.get("filename", ""),
        "pages": composite_pages,
    }


def _best_available(doc_runs: List[Dict[str, Any]], page_index: int) -> tuple[Optional[str], Optional[str]]:
    """Highest overall_confidence solution from the most recent completed run."""
    for r in doc_runs:
        run_id = r.get("run_id")
        state = run_store.read_run(run_id) if run_id else None
        if state is None:
            continue
        best = None
        for sol in state.get("solution_results") or []:
            if sol.get("status") != "ok":
                continue
            if best is None or (sol.get("overall_confidence") or 0) > (best.get("overall_confidence") or 0):
                best = sol
        if best is not None:
            return best.get("solution_name"), run_id
    return None, None


def _page_from_run(run_id: str, solution: str, page_index: int) -> Optional[Dict[str, Any]]:
    state = run_store.read_run(run_id)
    if state is None:
        return None
    sol = next((s for s in state.get("solution_results") or [] if s.get("solution_name") == solution), None)
    if sol is None:
        return None
    return next((p for p in sol.get("pages") or [] if p.get("page_index") == page_index), None)


def list_reviews() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in sorted(_root().glob("*.json")):
        out.append(json.loads(f.read_text()))
    return out


def stats() -> Dict[str, Any]:
    """Dashboard aggregate: per-solution accept counts + reviewed/total docs.

    Counts both page-level accepts (`solution`) and per-category accepts as
    contributions to the chosen solution's tally.
    """
    reviews = list_reviews()
    per_solution: Dict[str, int] = {}
    docs_with_any = 0
    pages_accepted = 0
    for r in reviews:
        if r["pages"]:
            docs_with_any += 1
        for _idx, p in r["pages"].items():
            if not p:
                continue
            pages_accepted += 1
            if p.get("solution"):
                per_solution[p["solution"]] = per_solution.get(p["solution"], 0) + 1
            for _cat, c in (p.get("categories") or {}).items():
                if isinstance(c, dict):
                    per_solution[c["solution"]] = per_solution.get(c["solution"], 0) + 1
                elif isinstance(c, list):
                    for entry in c:
                        per_solution[entry["solution"]] = per_solution.get(entry["solution"], 0) + 1
    return {
        "docs_reviewed": docs_with_any,
        "pages_accepted": pages_accepted,
        "per_solution": [
            {"solution": s, "accepts": c}
            for s, c in sorted(per_solution.items(), key=lambda kv: -kv[1])
        ],
        "recent": [
            {
                "document_id": r["document_id"],
                "filename": r["filename"],
                "n_pages_accepted": len(r["pages"]),
                "updated_at": r.get("updated_at"),
            }
            for r in sorted(reviews, key=lambda r: r.get("updated_at") or "", reverse=True)[:10]
        ],
    }
