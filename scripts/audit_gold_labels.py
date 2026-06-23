"""Audit gold labels against eval results to find coverage gaps."""
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT / "eval" / "results"
GOLD_DIR = PROJECT / "eval" / "gold"


def audit_patient(patient_id: str) -> dict:
    eval_path = EVAL_DIR / f"{patient_id}_gold_eval.json"
    gold_path = GOLD_DIR / f"{patient_id}_gold.json"

    if not eval_path.exists():
        return {"patient_id": patient_id, "error": "no eval results"}

    with open(eval_path, encoding="utf-8") as f:
        eval_data = json.load(f)
    with open(gold_path, encoding="utf-8") as f:
        gold_data = json.load(f)

    gaps = {
        "patient_id": patient_id,
        "generated_without_gold_match": [],
        "gold_not_matched_by_output": [],
    }

    # Type 1: generated claims without gold match
    for sec in eval_data.get("sections", []):
        sid = sec["section_id"]
        for claim in sec.get("claim_evals", []):
            if not claim.get("matched_gold_pattern"):
                gaps["generated_without_gold_match"].append({
                    "section": sid,
                    "claim": claim["claim_text"],
                    "status": claim.get("status"),
                    "citations": claim.get("citations", []),
                })

    # Type 2: gold claims not matched by output
    for gsec in gold_data.get("sections", []):
        sid = gsec["section_id"]
        for gc in gsec.get("expected_claims", []):
            matched = False
            for esec in eval_data.get("sections", []):
                if esec["section_id"] != sid:
                    continue
                for ce in esec.get("claim_evals", []):
                    if ce.get("matched_gold_pattern") == gc["claim_pattern"]:
                        matched = True
                        break
            if not matched:
                gaps["gold_not_matched_by_output"].append({
                    "section": sid,
                    "pattern": gc["claim_pattern"],
                    "is_critical": gc.get("is_critical", False),
                })

    return gaps


def main():
    patients = sorted(p.stem.split("_")[0] for p in EVAL_DIR.glob("*_gold_eval.json"))

    all_gaps = []
    total_gen_gaps = 0
    total_gold_gaps = 0
    total_critical_gold_gaps = 0

    for pid in patients:
        gaps = audit_patient(pid)
        all_gaps.append(gaps)
        n_gen = len(gaps.get("generated_without_gold_match", []))
        n_gold = len(gaps.get("gold_not_matched_by_output", []))
        n_critical = sum(
            1 for g in gaps.get("gold_not_matched_by_output", [])
            if g.get("is_critical")
        )
        total_gen_gaps += n_gen
        total_gold_gaps += n_gold
        total_critical_gold_gaps += n_critical
        print(f"{pid}: {n_gen} generated-without-gold, {n_gold} gold-not-in-output ({n_critical} critical)")

    print(f"\n--- TOTALS ---")
    print(f"Generated claims without gold match: {total_gen_gaps} (precision gap)")
    print(f"Gold claims not matched by output:   {total_gold_gaps} (recall gap, {total_critical_gold_gaps} critical)")

    out_path = PROJECT / "eval" / "gold_audit_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_gaps, f, ensure_ascii=False, indent=2)
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
