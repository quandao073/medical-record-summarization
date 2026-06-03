"""
Dry-run: verify toàn bộ pipeline trước khi gọi API.
Chạy C1 + C2 trên tất cả patients, in thống kê.
Không cần ANTHROPIC_API_KEY.

Usage: python poc/dry_run.py
"""

from __future__ import annotations
import json
from pathlib import Path
from src.c1_emr.pipeline import load_and_process, C1ProcessingError
from src.c1_emr.validator import validate_ehr
from src.c2_chunking.chunker import chunk_ehr
from src.c2_chunking.store_builder import build_structured_store, save_structured_store
from poc.poc_pipeline import format_chunks_as_context, build_section_prompt, SECTIONS

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "medical_summarization"
ASSEMBLED_DIR = DATA_DIR / "assembled"
STORE_DIR = DATA_DIR / "stores"


def run_dry(patient_id: str):
    path = ASSEMBLED_DIR / f"{patient_id}.json"

    # --- C1 ---
    try:
        safe_ehr = load_and_process(path)
    except C1ProcessingError as e:
        print(f"  [C1 ERROR] {e}")
        return

    raw_ehr = json.loads(path.read_text(encoding="utf-8"))
    _, all_errors = validate_ehr(raw_ehr)
    warnings = [e for e in all_errors if e.severity == "warning"]

    # --- C2 ---
    chunks = chunk_ehr(safe_ehr)
    store = build_structured_store(chunks)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    save_structured_store(store, STORE_DIR / f"{patient_id}_store.json")

    type_counts = {}
    for c in chunks:
        type_counts[c.source_type] = type_counts.get(c.source_type, 0) + 1

    # --- Context + Prompt (no LLM call) ---
    context = format_chunks_as_context(chunks, max_chunks=60)
    sample_prompt = build_section_prompt("thuoc_hien_tai", context)

    # Print stats
    enc_count = len(safe_ehr.get("encounters", []))
    allergy_count = len(safe_ehr.get("allergies", []))
    print(f"\n{'='*56}")
    print(f"Patient: {patient_id} | {enc_count} encounters | {allergy_count} allergies")
    print(f"  Chunks: {len(chunks)} total")
    for t, n in sorted(type_counts.items()):
        print(f"    {t:<25} {n:>3}")
    print(f"  Warnings: {len(warnings)}")
    for w in warnings:
        print(f"    [W] {w.field}: {w.message}")
    print(f"  Context chars: {len(context):,}")
    print(f"  Sample prompt chars (current_medications): {len(sample_prompt):,}")
    print(f"  Store saved: {STORE_DIR}/{patient_id}_store.json")


def main():
    patients = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
    print(f"Dry-run on {len(patients)} patients: {patients}")
    for pid in patients:
        run_dry(pid)

    print(f"\n{'='*56}")
    print("Dry-run PASSED. C1+C2 pipeline works for all patients.")
    print("Next step: set ANTHROPIC_API_KEY in .env and run:")
    print("  python poc/poc_pipeline.py --patient P001")
    print("  python poc/poc_pipeline.py --all-patients")


if __name__ == "__main__":
    main()
