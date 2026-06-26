"""Analyze precision/recall gaps for specific patients to identify root causes."""

from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent


def analyze_patient_gaps(patient_id: str) -> dict:
    """Categorize precision/recall failures by root cause."""
    eval_path = ROOT / "eval" / "results" / f"{patient_id}_gold_eval.json"

    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))

    precision_gaps = []
    recall_gaps = []

    for section in eval_data.get("sections", []):
        sid = section.get("section_id", "unknown")

        for claim in section.get("claim_evals", []):
            if not claim.get("has_correct_citation", False):
                precision_gaps.append({
                    "section": sid,
                    "claim_text": claim.get("claim_text", ""),
                    "status": claim.get("status", ""),
                    "citations": claim.get("citations", []),
                    "is_critical": claim.get("is_critical", False),
                    "reason": "generated_without_gold_match",
                })

        gold_total = section.get("gold_total", 0)
        gold_matched = section.get("gold_matched", 0)
        if gold_matched < gold_total:
            recall_gaps.append({
                "section": sid,
                "gold_total": gold_total,
                "gold_matched": gold_matched,
                "missing_count": gold_total - gold_matched,
            })

    categorized = defaultdict(list)
    for gap in precision_gaps:
        claim_text = gap["claim_text"].lower()
        if any(term in claim_text for term in [
            "đái tháo đường", "tăng huyết áp", "suy thận",
            "dị ứng", "rối loạn", "nhồi máu", "phì đại",
            "gan nhiễm mỡ", "bệnh phổi", "viêm gan",
        ]):
            categorized["compound_term_mismatch"].append(gap)
        elif any(c.isdigit() for c in claim_text):
            categorized["numeric_value_mismatch"].append(gap)
        else:
            categorized["other"].append(gap)

    return {
        "patient_id": patient_id,
        "citation_precision": eval_data.get("citation_precision"),
        "citation_recall": eval_data.get("citation_recall"),
        "critical_precision": eval_data.get("critical_precision"),
        "total_precision_gaps": len(precision_gaps),
        "total_recall_gaps": sum(g["missing_count"] for g in recall_gaps),
        "precision_by_category": {k: len(v) for k, v in categorized.items()},
        "precision_gaps_detail": dict(categorized),
        "recall_gaps_by_section": recall_gaps,
    }


if __name__ == "__main__":
    out_dir = ROOT / "eval" / "gap_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    for pid in ["P003", "P005"]:
        result = analyze_patient_gaps(pid)
        out_path = out_dir / f"{pid}_gap_analysis.json"
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n=== {pid} ===")
        print(f"Precision: {result['citation_precision']}")
        print(f"Recall:    {result['citation_recall']}")
        print(f"Critical:  {result['critical_precision']}")
        print(f"Precision gaps: {result['total_precision_gaps']}")
        for cat, count in result["precision_by_category"].items():
            print(f"  - {cat}: {count}")
        print(f"Recall gaps: {result['total_recall_gaps']}")
