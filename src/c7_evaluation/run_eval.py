"""
CLI runner for C7 citation evaluation.

Usage:
    python -m src.c7_evaluation.run_eval --patient P001
    python -m src.c7_evaluation.run_eval --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
GOLD_DIR = PROJECT / "eval" / "gold"
OUTPUT_DIR = PROJECT / "data" / "processed" / "outputs"
EVAL_DIR = PROJECT / "eval" / "results"


def run_one(patient_id: str, gold_suffix: str = "gold") -> dict | None:
    from src.schemas import FinalSummary
    from src.c7_evaluation.evaluator import evaluate_summary

    summary_path = OUTPUT_DIR / f"{patient_id}_summary.json"
    gold_path = GOLD_DIR / f"{patient_id}_{gold_suffix}.json"

    if not summary_path.exists():
        print(f"  [SKIP] {patient_id}: no summary at {summary_path}")
        return None
    if not gold_path.exists():
        print(f"  [SKIP] {patient_id}: no gold labels at {gold_path}")
        return None

    summary = FinalSummary(**json.loads(summary_path.read_text(encoding="utf-8")))
    report = evaluate_summary(summary, gold_path)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"{patient_id}_{gold_suffix}_eval.json"
    out_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mode_tag = f"[{report.evaluation_mode}] " if report.evaluation_mode != "loose" else ""
    print(f"  {patient_id} {mode_tag}: precision={report.citation_precision:.1%}  "
          f"recall={report.citation_recall:.1%}  "
          f"critical_prec={report.critical_precision:.1%}  "
          f"({report.precision_correct}/{report.total_supported} SUPPORTED correct, "
          f"{report.gold_matched}/{report.total_gold} gold matched)")
    return report.model_dump()


def main():
    parser = argparse.ArgumentParser(description="C7 Citation Evaluator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patient", type=str, help="Single patient ID")
    group.add_argument("--all", action="store_true", help="Evaluate all patients with gold labels")
    parser.add_argument(
        "--gold-suffix", type=str, default="gold",
        help="Gold file suffix (default: 'gold' → {pid}_gold.json; use 'gold_store_aware' for strict mode)"
    )
    args = parser.parse_args()

    suffix = args.gold_suffix

    if args.patient:
        patients = [args.patient]
    else:
        # Find all patients that have a gold file with this suffix
        patients = sorted(
            p.stem.replace(f"_{suffix}", "")
            for p in GOLD_DIR.glob(f"*_{suffix}.json")
        )

    if not patients:
        print(f"No gold label files found in {GOLD_DIR} with suffix '{suffix}'")
        sys.exit(1)

    print(f"Evaluating {len(patients)} patient(s) with gold suffix '{suffix}'...\n")
    results = {}
    for pid in patients:
        r = run_one(pid, gold_suffix=suffix)
        if r:
            results[pid] = r

    if len(results) > 1:
        avg_prec = sum(r["citation_precision"] for r in results.values()) / len(results)
        avg_rec = sum(r["citation_recall"] for r in results.values()) / len(results)
        avg_crit = sum(r["critical_precision"] for r in results.values()) / len(results)
        print(f"\n  AVG: precision={avg_prec:.1%}  recall={avg_rec:.1%}  critical_prec={avg_crit:.1%}")


if __name__ == "__main__":
    main()
