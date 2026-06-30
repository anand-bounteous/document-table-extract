"""CLI wrapper for the JSONL PII benchmark runner.

Equivalent to clicking through `/pii-benchmarks/dataset` in the UI, but
suitable for CI / scripted regression runs. Prints a single summary table
and exits non-zero if any detector errored.

Usage:

    uv run python -m scripts.run_pii_benchmark \\
        --dataset ../data/pii_v2/synthetic_50.jsonl \\
        --detectors presidio_regex,presidio_spacy,gliner,piiranha,hybrid
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app import pii_v2_dataset_store as ds
from app.pii_dataset_runner import execute_dataset_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a PII benchmark from the CLI")
    parser.add_argument("--dataset", type=Path, required=True, help="annotated JSONL file")
    parser.add_argument(
        "--detectors",
        default="presidio_regex,presidio_spacy,gliner,piiranha,hybrid",
        help="comma-separated detector names",
    )
    parser.add_argument(
        "--jurisdictions",
        default="GLOBAL_COMMON,UK",
        help="comma-separated jurisdiction codes",
    )
    args = parser.parse_args()

    if not args.dataset.exists():
        print(f"dataset not found: {args.dataset}", file=sys.stderr)
        return 2

    detector_names = [d.strip() for d in args.detectors.split(",") if d.strip()]
    jurisdictions = [j.strip() for j in args.jurisdictions.split(",") if j.strip()]

    meta = ds.save_dataset(content=args.dataset.read_bytes(), filename=args.dataset.name)
    dataset_run_id = ds.init_dataset_run(
        dataset_id=meta["dataset_id"],
        detector_names=detector_names,
        jurisdictions=jurisdictions,
    )
    print(f"dataset:        {args.dataset.name} ({meta['n_records']} records)")
    print(f"dataset_run_id: {dataset_run_id}")
    print(f"detectors:      {', '.join(detector_names)}")
    print("running ...")

    t0 = time.time()
    execute_dataset_run(
        dataset_run_id=dataset_run_id,
        dataset_id=meta["dataset_id"],
        detector_names=detector_names,
        jurisdictions=jurisdictions,
    )
    elapsed = time.time() - t0

    state = ds.read_dataset_run(dataset_run_id) or {}
    summary = (state.get("summary") or {})
    per_detector = summary.get("per_detector") or {}

    print()
    print(f"done in {elapsed:.1f}s")
    print()
    print(f"{'detector':18} {'P':>6} {'R':>6} {'F1':>6} {'FP':>4} {'FN':>4} {'p50':>8} {'p95':>8}")
    print("-" * 72)
    any_error = False
    for det in detector_names:
        data = per_detector.get(det) or {}
        m = (data.get("metrics") or {}).get("overall_exact") or {}
        lat = data.get("latency_ms") or {}
        if data.get("status") == "error":
            any_error = True
            print(f"{det:18} ERROR: {data.get('error')}")
            continue
        print(
            f"{det:18} {m.get('precision', 0):>6.3f} {m.get('recall', 0):>6.3f} "
            f"{m.get('f1', 0):>6.3f} {data.get('false_positive_count', 0):>4} "
            f"{data.get('false_negative_count', 0):>4} "
            f"{lat.get('p50', 0):>8.1f} {lat.get('p95', 0):>8.1f}"
        )

    rec = summary.get("recommendation") or {}
    print()
    print(f"winner_f1:        {rec.get('winner_overall_f1')}")
    print(f"winner_recall:    {rec.get('winner_recall')}")
    print(f"winner_precision: {rec.get('winner_precision')}")
    print(f"winner_latency:   {rec.get('winner_latency_p95')}")

    report_path = ds.report_path(dataset_run_id, "report.md")
    print()
    print(f"full report: {report_path}")
    print(f"raw JSON:    {ds.report_path(dataset_run_id, 'report.json')}")
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
