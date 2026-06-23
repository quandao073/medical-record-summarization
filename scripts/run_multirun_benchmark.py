"""Run benchmark N times and compute statistical summary."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from scripts.benchmark_models import run_benchmark

BENCHMARK_DIR = Path("data/benchmark/multirun")


def run_multirun(
    patient_ids: list[str],
    models: list[str],
    n_runs: int = 3,
    max_chunks: int = 60,
) -> dict:
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    all_patient_results = {}

    total_start = time.time()

    for pid in patient_ids:
        print(f"\n{'='*60}")
        print(f"  Patient {pid}")
        print(f"{'='*60}")
        all_runs = []
        for i in range(n_runs):
            print(f"\n--- Run {i+1}/{n_runs} ---")
            try:
                results = run_benchmark(pid, models, max_chunks)
                all_runs.append(results)
            except Exception as e:
                print(f"  Run {i+1} failed: {e}")

        patient_summary = {}
        for model_spec in models:
            model_runs = []
            for run in all_runs:
                if model_spec in run and run[model_spec].get("error") is None:
                    model_runs.append(run[model_spec]["summary"]["metrics"])

            if not model_runs:
                patient_summary[model_spec] = {"error": "all runs failed"}
                continue

            metric_stats = {}
            for metric_name in model_runs[0].keys():
                values = [r[metric_name] for r in model_runs if metric_name in r]
                if not values or not isinstance(values[0], (int, float)):
                    continue
                metric_stats[metric_name] = {
                    "mean": round(statistics.mean(values), 4),
                    "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
                    "min": round(min(values), 4),
                    "max": round(max(values), 4),
                    "n_runs": len(values),
                }

            patient_summary[model_spec] = {
                "metric_stats": metric_stats,
                "n_successful_runs": len(model_runs),
                "n_total_runs": n_runs,
            }

        all_patient_results[pid] = patient_summary

    total_elapsed = round(time.time() - total_start, 1)
    all_patient_results["_meta"] = {
        "n_patients": len(patient_ids),
        "patient_ids": patient_ids,
        "models": models,
        "n_runs": n_runs,
        "total_seconds": total_elapsed,
        "timestamp": datetime.now().isoformat(),
    }

    return all_patient_results


def print_report(results: dict, n_runs: int):
    meta = results.get("_meta", {})
    print(f"\n{'='*70}")
    print(f"  MULTI-RUN BENCHMARK RESULTS ({n_runs} runs)")
    print(f"{'='*70}")
    if meta:
        print(f"  Patients: {', '.join(meta.get('patient_ids', []))}")
        print(f"  Models: {', '.join(meta.get('models', []))}")
        print(f"  Total time: {meta.get('total_seconds', '?')}s")

    for pid, patient_data in results.items():
        if pid.startswith("_"):
            continue
        print(f"\n  Patient: {pid}")
        for model, data in patient_data.items():
            print(f"    Model: {model}")
            if "error" in data:
                print(f"      ERROR: {data['error']}")
                continue
            print(f"    Successful: {data['n_successful_runs']}/{data['n_total_runs']}")
            for metric, stats in data["metric_stats"].items():
                mean, std = stats["mean"], stats["std"]
                if isinstance(mean, float) and mean <= 1.0 and metric not in ("latency_seconds",):
                    print(f"      {metric:<35} {mean:.1%} ± {std:.1%}")
                else:
                    print(f"      {metric:<35} {mean:.1f} ± {std:.1f}")


def main():
    parser = argparse.ArgumentParser(description="Multi-run benchmark with statistical summary")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patients", nargs="+", help="Patient IDs to benchmark")
    group.add_argument("--all-patients", action="store_true", help="Benchmark all patients")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--n-runs", type=int, default=3)
    parser.add_argument("--max-chunks", type=int, default=60)
    args = parser.parse_args()

    if args.all_patients:
        assembled = Path("data/processed/assembled")
        patient_ids = sorted(p.stem for p in assembled.glob("*.json"))
    else:
        patient_ids = args.patients

    print(f"Multi-run benchmark: {len(patient_ids)} patients × {args.n_runs} runs")
    print(f"Models: {args.models}")

    results = run_multirun(patient_ids, args.models, args.n_runs, args.max_chunks)
    print_report(results, args.n_runs)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = BENCHMARK_DIR / f"multirun_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
