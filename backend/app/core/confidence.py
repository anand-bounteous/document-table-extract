"""Normalize per-tool confidence scores into a comparable [0, 1] range.

Confidence is a within-solution quality signal, not a cross-solution ranker.
"""

from __future__ import annotations

from typing import Iterable, List

from app.core.schemas import PageResult, Region, SolutionResult, TableModel


def from_tesseract_word_conf(conf: float) -> float:
    """tesseract returns 0..100 (or -1 for no-value)."""
    if conf is None or conf < 0:
        return 0.0
    return max(0.0, min(1.0, conf / 100.0))


def from_paddle_score(score: float) -> float:
    return max(0.0, min(1.0, float(score)))


def from_camelot_accuracy(accuracy: float, whitespace: float = 0.0) -> float:
    base = max(0.0, min(1.0, accuracy / 100.0))
    return max(0.0, base * (1.0 - 0.5 * max(0.0, min(1.0, whitespace / 100.0))))


def structural_fill(n_empty_cells: int, n_total_cells: int) -> float:
    if n_total_cells <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - n_empty_cells / n_total_cells))


def length_weighted(regions: Iterable[Region]) -> float:
    total_w = 0.0
    weighted = 0.0
    for r in regions:
        w = max(1, len(r.text))
        total_w += w
        weighted += r.confidence * w
    return weighted / total_w if total_w else 0.0


def page_confidence(page: PageResult) -> float:
    """Region-area-weighted mean across the page, with a structural penalty when
    table-bearing pages emit zero tables."""
    if not page.regions:
        return 0.0
    total_area = 0.0
    weighted = 0.0
    table_like = 0
    for r in page.regions:
        area = max(1.0, r.bbox.w * r.bbox.h)
        total_area += area
        weighted += r.confidence * area
        if r.type.value in {"table", "table_row", "table_cell"}:
            table_like += 1
    base = weighted / total_area if total_area else 0.0
    if table_like and not page.tables:
        base *= 0.7
    return base


def solution_confidence(pages: List[PageResult]) -> float:
    if not pages:
        return 0.0
    scores = [page_confidence(p) for p in pages]
    return sum(scores) / len(scores)


def attach_overall(result: SolutionResult) -> SolutionResult:
    result.overall_confidence = solution_confidence(result.pages)
    return result


def table_structural_confidence(t: TableModel) -> float:
    if t.n_rows == 0 or t.n_cols == 0:
        return 0.0
    empty = sum(1 for c in t.cells if not (c.text or "").strip())
    return structural_fill(empty, len(t.cells) or t.n_rows * t.n_cols)
