"""Re-run C5 evidence matching on existing summaries and re-evaluate."""

from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.schemas import FinalSummary, CitedClaim, SourceChunk
from src.c5_citation.evidence_matcher import match_claims
from src.c7_evaluation.evaluator import evaluate_summary

OUTPUT_DIR = ROOT / "data" / "processed" / "outputs"
STORE_DIR = ROOT / "data" / "processed" / "stores"
GOLD_DIR = ROOT / "eval" / "gold"
EVAL_DIR = ROOT / "eval" / "results"


def recite_patient(patient_id: str) -> dict | None:
    summary_path = OUTPUT_DIR / f"{patient_id}_summary.json"
    store_path = STORE_DIR / f"{patient_id}_store.json"
    gold_path = GOLD_DIR / f"{patient_id}_gold.json"

    if not all(p.exists() for p in [summary_path, store_path, gold_path]):
        print(f"  [SKIP] {patient_id}: missing files")
        return None

    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    store_data = json.loads(store_path.read_text(encoding="utf-8"))

    if isinstance(store_data, dict) and "chunks" not in store_data:
        chunks = [SourceChunk(**v) for v in store_data.values() if isinstance(v, dict)]
    else:
        chunks = [SourceChunk(**c) for c in store_data.get("chunks", [])]

    for section in summary_data.get("sections", []):
        claims = [CitedClaim(**c) for c in section.get("cited_claims", [])]
        rematched = match_claims(claims, chunks)
        section["cited_claims"] = [c.model_dump() for c in rematched]

    summary_path.write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = FinalSummary(**summary_data)
    report = evaluate_summary(summary, gold_path)

    report_dict = report.model_dump()
    eval_path = EVAL_DIR / f"{patient_id}_gold_eval.json"
    eval_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return report_dict


if __name__ == "__main__":
    patients = sys.argv[1:] if len(sys.argv) > 1 else [
        f"P{i:03d}" for i in range(1, 9)
    ]

    print("Re-running C5 evidence matching and evaluation...")
    results = {}
    for pid in patients:
        print(f"\n=== {pid} ===")
        report = recite_patient(pid)
        if report:
            results[pid] = {
                "precision": report["citation_precision"],
                "recall": report["citation_recall"],
                "critical": report["critical_precision"],
            }
            print(f"  Precision: {report['citation_precision']:.1%}")
            print(f"  Recall:    {report['citation_recall']:.1%}")
            print(f"  Critical:  {report['critical_precision']:.1%}")

    if results:
        print("\n=== SUMMARY ===")
        avg_p = sum(r["precision"] for r in results.values()) / len(results)
        avg_r = sum(r["recall"] for r in results.values()) / len(results)
        avg_c = sum(r["critical"] for r in results.values()) / len(results)
        print(f"Avg Precision: {avg_p:.1%}")
        print(f"Avg Recall:    {avg_r:.1%}")
        print(f"Avg Critical:  {avg_c:.1%}")
