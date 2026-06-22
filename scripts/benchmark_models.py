"""Benchmark: compare LLM model outputs on the same patient(s).

Usage:
    python -m scripts.benchmark_models --patient P001
    python -m scripts.benchmark_models --patient P001 --models openai:gpt-4o-mini lmstudio:meta-llama-3.1-8b-instruct
    python -m scripts.benchmark_models --all-patients
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from src.llm import create_llm_client
from poc.poc_pipeline import run_poc

load_dotenv()

ROOT = Path(__file__).parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"
BENCHMARK_DIR = ROOT / "data" / "benchmark"


def run_benchmark(
    patient_id: str,
    model_specs: list[str],
    max_chunks: int = 60,
) -> dict:
    """Run pipeline for each model_spec and return comparison data."""
    results = {}

    for spec in model_specs:
        parts = spec.split(":", 1)
        provider = parts[0]
        model = parts[1] if len(parts) > 1 else None

        print(f"\n{'='*60}")
        print(f"  BENCHMARK: {patient_id} | {spec}")
        print(f"{'='*60}")

        try:
            client = create_llm_client(provider=provider, model=model)
        except Exception as e:
            print(f"  [SKIP] Cannot create client for {spec}: {e}")
            results[spec] = {"error": str(e)}
            continue

        t0 = time.time()
        try:
            summary = run_poc(patient_id, client, model, max_chunks, verbose=True)
            elapsed = round(time.time() - t0, 2)
            results[spec] = {
                "summary": summary.model_dump(),
                "latency": elapsed,
                "error": None,
            }
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"  [ERROR] {spec}: {e}")
            results[spec] = {"error": str(e), "latency": elapsed}

    return results


def compare_results(patient_id: str, results: dict) -> str:
    """Generate a comparison report."""
    lines = []
    lines.append(f"\n{'#'*70}")
    lines.append(f"  COMPARISON REPORT: {patient_id}")
    lines.append(f"{'#'*70}\n")

    specs = [s for s in results if results[s].get("error") is None]
    if len(specs) < 2:
        lines.append("Not enough successful runs to compare.")
        return "\n".join(lines)

    # Metrics comparison table
    lines.append(f"{'Metric':<35}", )
    header = f"{'Metric':<35}"
    for s in specs:
        header += f" | {s:<30}"
    lines = [header, "-" * len(header)]

    for metric_name in [
        "citation_coverage",
        "critical_citation_coverage",
        "unsupported_claim_rate",
        "low_confidence_rate",
        "need_review_rate",
        "hallucination_rate",
        "missing_section_rate",
        "total_claims",
        "total_critical_claims",
        "contradiction_count",
        "latency_seconds",
        "token_count",
    ]:
        row = f"{metric_name:<35}"
        for s in specs:
            m = results[s]["summary"]["metrics"]
            val = m.get(metric_name, "N/A")
            if isinstance(val, float) and val <= 1.0 and metric_name != "latency_seconds":
                row += f" | {val:<30.1%}"
            else:
                row += f" | {str(val):<30}"
        lines.append(row)

    # Per-section content comparison
    lines.append(f"\n{'='*70}")
    lines.append("PER-SECTION CONTENT COMPARISON")
    lines.append(f"{'='*70}")

    sections_by_model = {}
    for s in specs:
        sections_by_model[s] = {
            sec["section_id"]: sec
            for sec in results[s]["summary"]["sections"]
        }

    all_section_ids = list(sections_by_model[specs[0]].keys())

    for sid in all_section_ids:
        lines.append(f"\n--- {sid} ---")
        for s in specs:
            sec = sections_by_model[s].get(sid, {})
            content = sec.get("content", "(missing)")
            claims = sec.get("cited_claims", [])
            n_claims = len(claims)
            n_supported = sum(1 for c in claims if c.get("status") == "SUPPORTED")
            n_unsupported = sum(1 for c in claims if c.get("status") in ("UNSUPPORTED", "NO_CITATION"))
            lines.append(f"\n  [{s}] ({n_claims} claims, {n_supported} supported, {n_unsupported} unsupported)")
            for line in content.split("\n"):
                lines.append(f"    {line}")

    return "\n".join(lines)


def aggregate_results(all_results: dict[str, dict]) -> str:
    """Aggregate metrics across all patients for each model."""
    lines = []
    lines.append(f"\n{'#'*70}")
    lines.append("  AGGREGATE BENCHMARK RESULTS")
    lines.append(f"{'#'*70}\n")

    model_metrics: dict[str, list[dict]] = {}
    for pid, results in all_results.items():
        for spec, data in results.items():
            if data.get("error") is not None:
                continue
            if spec not in model_metrics:
                model_metrics[spec] = []
            model_metrics[spec].append(data["summary"]["metrics"])

    if not model_metrics:
        lines.append("No successful results to aggregate.")
        return "\n".join(lines)

    specs = list(model_metrics.keys())
    header = f"{'Metric':<35}"
    for s in specs:
        header += f" | {s:<30}"
    lines.append(header)
    lines.append("-" * len(header))

    metric_names = [
        "citation_coverage",
        "critical_citation_coverage",
        "unsupported_claim_rate",
        "hallucination_rate",
        "total_claims",
        "latency_seconds",
        "token_count",
    ]

    for metric_name in metric_names:
        row = f"{metric_name:<35}"
        for s in specs:
            values = [m.get(metric_name, 0) for m in model_metrics[s]]
            avg = sum(values) / len(values) if values else 0
            if isinstance(avg, float) and avg <= 1.0 and metric_name not in ("latency_seconds",):
                row += f" | {avg:<30.1%}"
            else:
                row += f" | {avg:<30.1f}"
        lines.append(row)

    row = f"{'patients_tested':<35}"
    for s in specs:
        row += f" | {len(model_metrics[s]):<30}"
    lines.append(row)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Benchmark model comparison")
    parser.add_argument("--patient", default="P001")
    parser.add_argument("--all-patients", action="store_true")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["openai:gpt-4o-mini", "lmstudio:meta-llama-3.1-8b-instruct"],
    )
    parser.add_argument("--max-chunks", type=int, default=60)
    args = parser.parse_args()

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    if args.all_patients:
        patient_ids = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
        print(f"Running benchmark for {len(patient_ids)} patients...")
        all_results = {}
        for pid in patient_ids:
            results = run_benchmark(pid, args.models, args.max_chunks)
            all_results[pid] = results

            out_path = BENCHMARK_DIR / f"{pid}_benchmark.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            report = compare_results(pid, results)
            report_path = BENCHMARK_DIR / f"{pid}_comparison.txt"
            report_path.write_text(report, encoding="utf-8")

        agg_report = aggregate_results(all_results)
        print(agg_report)

        agg_path = BENCHMARK_DIR / "aggregate_comparison.txt"
        agg_path.write_text(agg_report, encoding="utf-8")
        print(f"\nAggregate report saved to: {agg_path}")

        all_path = BENCHMARK_DIR / "all_benchmark.json"
        with open(all_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"All results saved to: {all_path}")
    else:
        pid = args.patient
        results = run_benchmark(pid, args.models, args.max_chunks)
        report = compare_results(pid, results)
        print(report)

        out_path = BENCHMARK_DIR / f"{pid}_benchmark.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nRaw data saved to: {out_path}")

        report_path = BENCHMARK_DIR / f"{pid}_comparison.txt"
        report_path.write_text(report, encoding="utf-8")
        print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
