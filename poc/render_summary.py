"""
Render a FinalSummary JSON into a readable text report.

Usage:
    python poc/render_summary.py data/poc_outputs/P001_poc_summary.json
    python poc/render_summary.py data/poc_outputs/P001_poc_summary.json --save
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


SECTION_LABELS = {
    "overview":            "TỔNG QUAN BỆNH NHÂN",
    "reason_for_visit":    "LÝ DO KHÁM / TRIỆU CHỨNG CHÍNH",
    "medical_history":     "TIỀN SỬ BỆNH",
    "current_medications": "THUỐC ĐANG SỬ DỤNG",
    "allergies":           "DỊ ỨNG",
    "abnormal_labs":       "KẾT QUẢ XÉT NGHIỆM BẤT THƯỜNG",
    "diagnoses":           "CHẨN ĐOÁN",
    "clinical_alerts":     "ĐIỂM CẦN LƯU Ý / CẢNH BÁO",
}


def render(summary: dict) -> str:
    lines = []
    pid = summary.get("patient_id", "?")
    model = summary.get("model_version", "?")
    prompt = summary.get("prompt_version", "?")
    created = summary.get("created_at", summary.get("ngay_tao", "?"))[:19]
    metrics = summary.get("metrics", {})

    lines.append("=" * 68)
    lines.append(f"  TOM TAT BENH AN --- {pid}")
    lines.append(f"  Ngay tao: {created} | Model: {model} | Prompt: {prompt}")
    lines.append("=" * 68)

    for section in summary.get("sections", []):
        sid = section.get("section_id", "?")
        label = SECTION_LABELS.get(sid, sid.upper())
        content = section.get("content", "").strip()

        # Collect all citation source_ids across claims
        all_citations = []
        for claim in section.get("cited_claims", []):
            all_citations.extend(claim.get("citations", []))
        all_citations = list(dict.fromkeys(all_citations))  # dedup, preserve order

        lines.append("")
        lines.append(f"[{label}]")
        if content:
            for line in content.split(". "):
                line = line.strip()
                if line:
                    lines.append(f"  {line}.")
        else:
            lines.append("  Chua thay ghi nhan trong du lieu duoc cung cap.")

        if all_citations:
            lines.append(f"  Citations: {', '.join(all_citations)}")

    lines.append("")
    lines.append("-" * 68)
    lines.append("METRICS:")
    lines.append(f"  Citation Coverage:      {metrics.get('citation_coverage', 0):.0%}")
    lines.append(f"  Unsupported Claim Rate: {metrics.get('unsupported_claim_rate', 0):.0%}")
    lines.append(f"  Latency:                {metrics.get('latency_seconds', 0):.1f}s")
    lines.append(f"  Token Count:            {metrics.get('token_count', 0):,}")
    lines.append("-" * 68)
    lines.append("AI-GENERATED DRAFT — CHUA DUOC BAC SI DUYET. CHI DUNG DE THAM KHAO.")
    lines.append("=" * 68)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_path", help="Path to summary JSON")
    parser.add_argument("--save", action="store_true", help="Save rendered .txt next to JSON")
    args = parser.parse_args()

    path = Path(args.summary_path)
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)

    rendered = render(summary)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(rendered)

    if args.save:
        out = path.with_suffix(".txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"\nSaved to: {out}")


if __name__ == "__main__":
    main()
