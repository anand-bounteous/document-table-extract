"""Span-level precision/recall + per-entity-type confusion stats.

Used by the JSONL benchmark runner. Two match modes:

- ``exact``: start and end must match.
- ``partial``: any overlap counts.

Entity-type must match in both modes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from app.pii_v2.schema import PIIEntity


@dataclass
class EvalCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class EvalReport:
    overall_exact: EvalCounts = field(default_factory=EvalCounts)
    overall_partial: EvalCounts = field(default_factory=EvalCounts)
    by_entity_exact: Dict[str, EvalCounts] = field(default_factory=lambda: defaultdict(EvalCounts))
    by_entity_partial: Dict[str, EvalCounts] = field(default_factory=lambda: defaultdict(EvalCounts))
    false_positives: List[PIIEntity] = field(default_factory=list)
    false_negatives: List[PIIEntity] = field(default_factory=list)


def _overlaps(a: PIIEntity, b: PIIEntity) -> bool:
    return a.entity_type == b.entity_type and not (a.end <= b.start or b.end <= a.start)


def _exact(a: PIIEntity, b: PIIEntity) -> bool:
    return a.entity_type == b.entity_type and a.start == b.start and a.end == b.end


def evaluate(predicted: Iterable[PIIEntity], gold: Iterable[PIIEntity]) -> EvalReport:
    """Compare a single record's predicted spans against gold."""
    pred = list(predicted)
    truth = list(gold)
    report = EvalReport()

    used_truth_exact: set[int] = set()
    used_pred_exact: set[int] = set()
    for i, p in enumerate(pred):
        for j, g in enumerate(truth):
            if j in used_truth_exact:
                continue
            if _exact(p, g):
                report.overall_exact.tp += 1
                report.by_entity_exact[p.entity_type].tp += 1
                used_truth_exact.add(j)
                used_pred_exact.add(i)
                break
    for i, p in enumerate(pred):
        if i not in used_pred_exact:
            report.overall_exact.fp += 1
            report.by_entity_exact[p.entity_type].fp += 1
    for j, g in enumerate(truth):
        if j not in used_truth_exact:
            report.overall_exact.fn += 1
            report.by_entity_exact[g.entity_type].fn += 1

    used_truth_partial: set[int] = set()
    used_pred_partial: set[int] = set()
    for i, p in enumerate(pred):
        for j, g in enumerate(truth):
            if j in used_truth_partial:
                continue
            if _overlaps(p, g):
                report.overall_partial.tp += 1
                report.by_entity_partial[p.entity_type].tp += 1
                used_truth_partial.add(j)
                used_pred_partial.add(i)
                break
    for i, p in enumerate(pred):
        if i not in used_pred_partial:
            report.overall_partial.fp += 1
            report.by_entity_partial[p.entity_type].fp += 1
            report.false_positives.append(p)
    for j, g in enumerate(truth):
        if j not in used_truth_partial:
            report.overall_partial.fn += 1
            report.by_entity_partial[g.entity_type].fn += 1
            report.false_negatives.append(g)

    return report


def aggregate(reports: Iterable[EvalReport]) -> EvalReport:
    out = EvalReport()
    for r in reports:
        out.overall_exact.tp += r.overall_exact.tp
        out.overall_exact.fp += r.overall_exact.fp
        out.overall_exact.fn += r.overall_exact.fn
        out.overall_partial.tp += r.overall_partial.tp
        out.overall_partial.fp += r.overall_partial.fp
        out.overall_partial.fn += r.overall_partial.fn
        for k, c in r.by_entity_exact.items():
            out.by_entity_exact[k].tp += c.tp
            out.by_entity_exact[k].fp += c.fp
            out.by_entity_exact[k].fn += c.fn
        for k, c in r.by_entity_partial.items():
            out.by_entity_partial[k].tp += c.tp
            out.by_entity_partial[k].fp += c.fp
            out.by_entity_partial[k].fn += c.fn
        out.false_positives.extend(r.false_positives)
        out.false_negatives.extend(r.false_negatives)
    return out
