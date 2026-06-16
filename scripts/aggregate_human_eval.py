#!/usr/bin/env python3
"""
Aggregate human evaluation results across all patients.

Usage:
    python scripts/aggregate_human_eval.py
    python scripts/aggregate_human_eval.py --output reports/human_eval_results.md
    python scripts/aggregate_human_eval.py --csv reports/human_eval_results.csv
    python scripts/aggregate_human_eval.py --output reports/out.md --csv reports/out.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
HUMAN_EVAL_DIR = PROJECT / "data" / "human_eval"
AUTO_EVAL_DIR = PROJECT / "eval" / "results"

EXPECTED_PATIENTS = [f"P{i:03d}" for i in range(1, 9)]  # P001–P008

WEIGHTS: dict[str, float] = {
    "clinical_correctness": 0.25,
    "completeness": 0.20,
    "citation_faithfulness": 0.20,
    "safety": 0.20,
    "temporal_correctness": 0.10,
    "readability": 0.05,
}

CRITERIA_LABELS: dict[str, str] = {
    "clinical_correctness": "Độ chính xác lâm sàng",
    "completeness": "Tính đầy đủ",
    "citation_faithfulness": "Trích dẫn trung thực",
    "safety": "An toàn",
    "temporal_correctness": "Đúng thứ tự thời gian",
    "readability": "Dễ đọc",
}

ERROR_LABELS: dict[str, str] = {
    "omission": "Bỏ sót thông tin",
    "commission": "Thêm thông tin ngoài hồ sơ",
    "wrong_source": "Citation sai nguồn",
    "partial_citation": "Citation hỗ trợ một phần",
    "no_source": "Không có citation",
    "temporal_error": "Sai thứ tự thời gian",
    "safety_error": "Thông tin nguy hiểm",
    "readability_issue": "Ngôn ngữ khó đọc",
}


def load_human_evals() -> list[dict]:
    results = []
    for path in sorted(HUMAN_EVAL_DIR.glob("*_human_eval.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("weighted_score") is not None:
            results.append(data)
    return results


def load_auto_eval(patient_id: str) -> dict | None:
    """Try multiple filename patterns — robust to naming variations."""
    candidates = [
        AUTO_EVAL_DIR / f"{patient_id}_gold_eval.json",
        AUTO_EVAL_DIR / f"{patient_id}_eval.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def format_report(evals: list[dict]) -> str:
    if not evals:
        return "# Kết quả Human Evaluation\n\nChưa có đánh giá nào hoàn thành.\n"

    lines: list[str] = ["# Kết quả Human Evaluation\n"]

    completed_ids = {e["patient_id"] for e in evals}
    missing = [p for p in EXPECTED_PATIENTS if p not in completed_ids]
    lines.append(f"**Tiến độ:** {len(evals)}/8 bệnh nhân đã đánh giá\n")
    if missing:
        lines.append(f"**Chưa đánh giá:** {', '.join(missing)}\n")

    criterion_scores: dict[str, list[float]] = {c: [] for c in WEIGHTS}
    for e in evals:
        for c in WEIGHTS:
            s = e["scores"].get(c, {}).get("score")
            if s is not None:
                criterion_scores[c].append(float(s))

    lines.append("## Điểm trung bình theo tiêu chí\n")
    lines.append("| Tiêu chí | Trọng số | Trung bình | vs Target ≥4.0 |")
    lines.append("|---|---|---|---|")
    for c, weight in WEIGHTS.items():
        scrs = criterion_scores[c]
        avg = sum(scrs) / len(scrs) if scrs else 0.0
        status = "✓ Đạt" if avg >= 4.0 else "✗ Chưa đạt"
        lines.append(
            f"| {CRITERIA_LABELS[c]} | {weight * 100:.0f}% | **{avg:.2f}** | {status} |"
        )

    all_ws = [e["weighted_score"] for e in evals if e["weighted_score"] is not None]
    avg_overall = sum(all_ws) / len(all_ws) if all_ws else 0.0
    overall_status = "✓ Đạt" if avg_overall >= 4.0 else "✗ Chưa đạt"
    lines.append(
        f"\n**Điểm tổng hợp (weighted average): {avg_overall:.3f}/5.0 — {overall_status}**\n"
    )

    lines.append("## Kết quả từng bệnh nhân\n")
    lines.append(
        "| Bệnh nhân | Điểm | Citation Precision | Citation Recall | Model | Prompt | Người đánh giá |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for e in evals:
        pid = e["patient_id"]
        ws = e.get("weighted_score") or 0
        auto = load_auto_eval(pid)
        prec = f"{auto['citation_precision']:.1%}" if auto else "N/A"
        rec = f"{auto['citation_recall']:.1%}" if auto else "N/A"
        model = e.get("model") or "—"
        prompt_v = e.get("prompt_version") or "—"
        evaluator = e.get("evaluator") or "—"
        lines.append(f"| {pid} | {ws:.3f} | {prec} | {rec} | {model} | {prompt_v} | {evaluator} |")

    all_errors: list[str] = []
    for e in evals:
        all_errors.extend(e.get("error_categories", []))
    if all_errors:
        error_counts = Counter(all_errors)
        lines.append("\n## Phân tích lỗi\n")
        lines.append("| Loại lỗi | Số lần |")
        lines.append("|---|---|")
        for err, count in error_counts.most_common():
            label = ERROR_LABELS.get(err, err)
            lines.append(f"| {label} | {count} |")

    notes_list = [
        (e["patient_id"], e["overall_notes"])
        for e in evals
        if e.get("overall_notes")
    ]
    if notes_list:
        lines.append("\n## Nhận xét tổng thể\n")
        for pid, note in notes_list:
            lines.append(f"**{pid}:** {note}\n")

    return "\n".join(lines) + "\n"


def format_csv(evals: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "patient_id", "evaluator", "model", "prompt_version",
        "summary_generated_at", "evaluated_at",
        "clinical_correctness", "completeness", "citation_faithfulness",
        "safety", "temporal_correctness", "readability",
        "weighted_score", "error_categories", "overall_notes",
    ])
    for e in evals:
        scrs = e.get("scores", {})
        writer.writerow([
            e["patient_id"],
            e.get("evaluator", ""),
            e.get("model", ""),
            e.get("prompt_version", ""),
            e.get("summary_generated_at", ""),
            e.get("evaluated_at", ""),
            scrs.get("clinical_correctness", {}).get("score", ""),
            scrs.get("completeness", {}).get("score", ""),
            scrs.get("citation_faithfulness", {}).get("score", ""),
            scrs.get("safety", {}).get("score", ""),
            scrs.get("temporal_correctness", {}).get("score", ""),
            scrs.get("readability", {}).get("score", ""),
            e.get("weighted_score", ""),
            "|".join(e.get("error_categories", [])),
            e.get("overall_notes", ""),
        ])
    return output.getvalue()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description="Aggregate human evaluation results")
    parser.add_argument("--output", type=str, help="Save markdown report to file")
    parser.add_argument("--csv", type=str, help="Save CSV to file")
    args = parser.parse_args()

    evals = load_human_evals()
    completed_ids = {e["patient_id"] for e in evals}
    missing = [p for p in EXPECTED_PATIENTS if p not in completed_ids]

    print(f"Đánh giá hoàn thành: {len(evals)}/8 bệnh nhân")
    if missing:
        print(f"Chưa đánh giá: {', '.join(missing)}")

    report = format_report(evals)
    print("\n" + report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Markdown đã lưu: {out_path}")

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(format_csv(evals), encoding="utf-8-sig")
        print(f"CSV đã lưu: {csv_path}")


if __name__ == "__main__":
    main()
