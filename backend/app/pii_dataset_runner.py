"""Run every selected detector over an annotated JSONL dataset.

Produces:
  - <dataset_run_id>/<detector>/predictions.jsonl
  - <dataset_run_id>/<detector>/false_positives.csv
  - <dataset_run_id>/<detector>/false_negatives.csv
  - <dataset_run_id>/report.json
  - <dataset_run_id>/report.md
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app import pii_v2_dataset_store as ds
from app.pii_v2.evaluators import EvalReport, aggregate, evaluate
from app.pii_v2.registry import get_detector
from app.pii_v2.schema import PIIEntity

logger = logging.getLogger("ote.pii_dataset")


def _load_gold(record: Dict[str, Any]) -> List[PIIEntity]:
    out: List[PIIEntity] = []
    for e in record.get("entities", []) or []:
        try:
            out.append(PIIEntity(
                entity_type=e["entity_type"],
                text=e.get("text", ""),
                start=int(e["start"]),
                end=int(e["end"]),
                score=1.0,
                source="gold",
                detection_method="annotation",
            ))
        except (KeyError, ValueError):
            continue
    return out


def _serialise_report(report: EvalReport) -> Dict[str, Any]:
    def counts(c) -> Dict[str, float]:  # type: ignore[no-untyped-def]
        return {
            "tp": c.tp, "fp": c.fp, "fn": c.fn,
            "precision": round(c.precision, 4),
            "recall": round(c.recall, 4),
            "f1": round(c.f1, 4),
        }
    return {
        "overall_exact": counts(report.overall_exact),
        "overall_partial": counts(report.overall_partial),
        "by_entity_exact": {k: counts(v) for k, v in report.by_entity_exact.items()},
        "by_entity_partial": {k: counts(v) for k, v in report.by_entity_partial.items()},
    }


def execute_dataset_run(
    *,
    dataset_run_id: str,
    dataset_id: str,
    detector_names: List[str],
    jurisdictions: List[str],
) -> None:
    summary: Dict[str, Any] = {"per_detector": {}}
    records = list(ds.iter_records(dataset_id))
    n_records = len(records)
    logger.info("dataset_run %s: %d records, %d detectors", dataset_run_id, n_records, len(detector_names))

    for det_name in detector_names:
        ds.mark_detector(dataset_run_id, det_name, status="running")
        try:
            detector_cls = get_detector(det_name)
        except KeyError:
            ds.mark_detector(dataset_run_id, det_name, status="error", error="unknown detector")
            continue
        detector = detector_cls(jurisdictions=jurisdictions)
        det_dir = ds.detector_dir(dataset_run_id, det_name)
        preds_path = det_dir / "predictions.jsonl"
        per_record_reports: List[EvalReport] = []
        latencies: List[float] = []
        false_positives: List[Dict[str, Any]] = []
        false_negatives: List[Dict[str, Any]] = []
        load_time_ms: float | None = None

        with preds_path.open("w") as preds_out:
            for i, rec in enumerate(records):
                t0 = time.perf_counter()
                try:
                    result = detector.detect_with_timing(rec.get("text", ""))
                    if load_time_ms is None and i == 0:
                        load_time_ms = result.latency_ms
                except Exception as exc:  # noqa: BLE001
                    logger.exception("detector %s failed on record %s", det_name, rec.get("id"))
                    result = None
                latencies.append((time.perf_counter() - t0) * 1000.0)
                gold = _load_gold(rec)
                preds = result.entities if result else []
                preds_out.write(json.dumps({
                    "id": rec.get("id"),
                    "predictions": [p.to_dict() for p in preds],
                    "latency_ms": result.latency_ms if result else None,
                }) + "\n")
                report = evaluate(preds, gold)
                per_record_reports.append(report)
                for fp in report.false_positives:
                    false_positives.append({
                        "record_id": rec.get("id"),
                        "entity_type": fp.entity_type,
                        "text": fp.text,
                        "start": fp.start,
                        "end": fp.end,
                        "score": fp.score,
                    })
                for fn in report.false_negatives:
                    false_negatives.append({
                        "record_id": rec.get("id"),
                        "entity_type": fn.entity_type,
                        "text": fn.text,
                        "start": fn.start,
                        "end": fn.end,
                    })
                ds.mark_detector(dataset_run_id, det_name, records_done=i + 1)

        agg = aggregate(per_record_reports)
        ds.write_csv(
            det_dir / "false_positives.csv",
            false_positives,
            columns=["record_id", "entity_type", "text", "start", "end", "score"],
        )
        ds.write_csv(
            det_dir / "false_negatives.csv",
            false_negatives,
            columns=["record_id", "entity_type", "text", "start", "end"],
        )

        per_detector_summary = {
            "n_records": n_records,
            "load_time_ms": round(load_time_ms or 0.0, 2),
            "latency_ms": _latency_summary(latencies),
            "metrics": _serialise_report(agg),
            "false_positive_count": len(false_positives),
            "false_negative_count": len(false_negatives),
        }
        summary["per_detector"][det_name] = per_detector_summary
        ds.mark_detector(dataset_run_id, det_name, status="done", **per_detector_summary)

    summary["recommendation"] = _recommendation_matrix(summary["per_detector"])
    (ds.report_path(dataset_run_id, "report.json")).write_text(
        json.dumps(summary, indent=2, default=str)
    )
    (ds.report_path(dataset_run_id, "report.md")).write_text(_markdown_summary(summary))
    ds.finalize_dataset_run(dataset_run_id, summary)


def _latency_summary(latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        return {"p50": 0, "p95": 0, "p99": 0, "mean": 0}
    sorted_l = sorted(latencies)
    def pct(p: float) -> float:
        k = max(0, min(len(sorted_l) - 1, int(round((p / 100) * (len(sorted_l) - 1)))))
        return round(sorted_l[k], 2)
    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": round(statistics.mean(latencies), 2),
    }


def _recommendation_matrix(per_detector: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Per .prompt/009 §17 — pick a winner per category using the metrics."""
    if not per_detector:
        return {}

    def f1(det: str) -> float:
        return per_detector[det]["metrics"]["overall_exact"]["f1"]

    def recall(det: str) -> float:
        return per_detector[det]["metrics"]["overall_exact"]["recall"]

    def precision(det: str) -> float:
        return per_detector[det]["metrics"]["overall_exact"]["precision"]

    def p95(det: str) -> float:
        return per_detector[det]["latency_ms"]["p95"]

    detectors = list(per_detector.keys())
    by_f1 = sorted(detectors, key=f1, reverse=True)
    by_recall = sorted(detectors, key=recall, reverse=True)
    by_precision = sorted(detectors, key=precision, reverse=True)
    by_latency = sorted(detectors, key=p95)

    return {
        "winner_overall_f1": by_f1[0] if by_f1 else None,
        "winner_recall": by_recall[0] if by_recall else None,
        "winner_precision": by_precision[0] if by_precision else None,
        "winner_latency_p95": by_latency[0] if by_latency else None,
        "ranking": [
            {
                "detector": d,
                "f1": f1(d),
                "recall": recall(d),
                "precision": precision(d),
                "p95_ms": p95(d),
            }
            for d in by_f1
        ],
    }


def _markdown_summary(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# PII benchmark — production recommendation matrix\n")
    rec = summary.get("recommendation", {}) or {}
    lines.append(f"- **Overall F1 winner**: `{rec.get('winner_overall_f1') or '—'}`")
    lines.append(f"- **Highest recall**: `{rec.get('winner_recall') or '—'}`")
    lines.append(f"- **Highest precision**: `{rec.get('winner_precision') or '—'}`")
    lines.append(f"- **Lowest p95 latency**: `{rec.get('winner_latency_p95') or '—'}`\n")

    lines.append("## Ranking\n")
    lines.append("| Detector | F1 | Recall | Precision | p95 ms |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in rec.get("ranking", []):
        lines.append(
            f"| `{r['detector']}` | {r['f1']:.3f} | {r['recall']:.3f} | "
            f"{r['precision']:.3f} | {r['p95_ms']:.0f} |"
        )
    lines.append("")

    lines.append("## Per-detector detail\n")
    for det, data in summary.get("per_detector", {}).items():
        lines.append(f"### `{det}`\n")
        m = data["metrics"]["overall_exact"]
        lines.append(f"- records: {data['n_records']}")
        lines.append(f"- exact precision/recall/F1: {m['precision']:.3f} / {m['recall']:.3f} / {m['f1']:.3f}")
        lat = data["latency_ms"]
        lines.append(
            f"- latency mean/p50/p95/p99: {lat['mean']:.1f} / {lat['p50']:.1f} / {lat['p95']:.1f} / {lat['p99']:.1f} ms"
        )
        lines.append(f"- false positives: {data['false_positive_count']}")
        lines.append(f"- false negatives: {data['false_negative_count']}\n")
    return "\n".join(lines)
