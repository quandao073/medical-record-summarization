"""
Checkpoint script Tuan 2 — in trang thai cac deliverable.
Usage: python scripts/week2_status.py
"""

from pathlib import Path
import json

ROOT = Path(__file__).parent.parent

checks = [
    ("data/processed/assembled/P001.json exists",    (ROOT / "data/processed/assembled/P001.json").exists()),
    ("data/processed/assembled/P002.json exists",    (ROOT / "data/processed/assembled/P002.json").exists()),
    ("data/processed/assembled/P003.json exists",    (ROOT / "data/processed/assembled/P003.json").exists()),
    ("data/processed/assembled/P004.json exists",    (ROOT / "data/processed/assembled/P004.json").exists()),
    ("data/processed/stores/P001_store.json exists", (ROOT / "data/processed/stores/P001_store.json").exists()),
    ("src/schemas.py exists",                (ROOT / "src/schemas.py").exists()),
    ("src/c1_emr/validator.py exists",       (ROOT / "src/c1_emr/validator.py").exists()),
    ("src/c1_emr/deidentifier.py exists",    (ROOT / "src/c1_emr/deidentifier.py").exists()),
    ("src/c1_emr/normalizer.py exists",      (ROOT / "src/c1_emr/normalizer.py").exists()),
    ("src/c2_chunking/chunker.py exists",    (ROOT / "src/c2_chunking/chunker.py").exists()),
    ("src/c2_chunking/store_builder.py",     (ROOT / "src/c2_chunking/store_builder.py").exists()),
    ("poc/poc_pipeline.py exists",           (ROOT / "poc/poc_pipeline.py").exists()),
    ("poc/dry_run.py exists",                (ROOT / "poc/dry_run.py").exists()),
    ("tests/test_c1_emr.py exists",          (ROOT / "tests/test_c1_emr.py").exists()),
    ("tests/test_c2_chunking.py exists",     (ROOT / "tests/test_c2_chunking.py").exists()),
    ("requirements.txt exists",              (ROOT / "requirements.txt").exists()),
]

# Check chunk counts
try:
    import sys; sys.path.insert(0, str(ROOT))
    from src.c1_emr.pipeline import load_and_process
    from src.c2_chunking.chunker import chunk_ehr
    ehr = load_and_process(ROOT / "data/processed/assembled/P001.json")
    chunks = chunk_ehr(ehr)
    ids = [c.source_id for c in chunks]
    checks.append((f"P001 chunks >= 20 (got {len(chunks)})", len(chunks) >= 20))
    checks.append(("P001 source_ids all unique", len(ids) == len(set(ids))))
    checks.append(("P001 has allergy chunk",
                   any(c.source_type == "allergies" for c in chunks)))
except Exception as e:
    checks.append((f"Pipeline import error: {e}", False))

# Check PoC output exists
poc_out = ROOT / "data/processed/outputs/P001_summary.json"
checks.append(("PoC output P001 exists (needs API run)", poc_out.exists()))
if poc_out.exists():
    with open(poc_out, encoding="utf-8") as f:
        summary = json.load(f)
    coverage = summary.get("metrics", {}).get("citation_coverage", 0)
    latency  = summary.get("metrics", {}).get("latency_seconds", 0)
    sections = len(summary.get("sections", []))
    checks.append((f"PoC sections == 8 (got {sections})", sections == 8))  # Week 3: update to 9 after treatment_timeline added
    checks.append((f"PoC citation coverage >= 30% (got {coverage:.0%})", coverage >= 0.30))
    checks.append((f"PoC latency <= 120s (got {latency:.1f}s)", latency <= 120))

print("\n" + "="*60)
print("  WEEK 2 CHECKPOINT")
print("="*60)
passed = 0
for label, ok in checks:
    status = "[OK]  " if ok else "[FAIL]"
    print(f"  {status} {label}")
    if ok:
        passed += 1

print(f"\nResult: {passed}/{len(checks)} checks passed")
print("="*60)

if passed == len(checks):
    print("ALL PASSED — Week 2 deliverables complete!")
else:
    print("Some checks failed — see above.")
