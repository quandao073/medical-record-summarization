"""
Checkpoint script Tuan 3 — Citation & Hallucination Mitigation.
Usage: python scripts/week3_status.py
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent

checks = [
    # C3 Retrieval
    ("src/c3_retrieval/retriever.py exists",       (ROOT / "src/c3_retrieval/retriever.py").exists()),
    # C5 Citation
    ("src/c5_citation/claim_extractor.py exists",  (ROOT / "src/c5_citation/claim_extractor.py").exists()),
    ("src/c5_citation/evidence_matcher.py exists", (ROOT / "src/c5_citation/evidence_matcher.py").exists()),
    # C6 Verifier
    ("src/c6_verifier/verifier.py exists",         (ROOT / "src/c6_verifier/verifier.py").exists()),
    # Tests
    ("tests/test_c3_retrieval.py exists",          (ROOT / "tests/test_c3_retrieval.py").exists()),
    ("tests/test_c5_citation.py exists",           (ROOT / "tests/test_c5_citation.py").exists()),
    ("tests/test_c6_verifier.py exists",           (ROOT / "tests/test_c6_verifier.py").exists()),
]

# Runtime checks — only run if files exist
try:
    import sys; sys.path.insert(0, str(ROOT))
    from src.c3_retrieval.retriever import retrieve_for_section
    from src.c1_emr.pipeline import load_and_process
    from src.c2_chunking.chunker import chunk_ehr

    ehr = load_and_process(ROOT / "data/processed/assembled/P001.json")
    chunks = chunk_ehr(ehr)

    med_chunks = retrieve_for_section(chunks, "current_medications", max_chunks=15)
    checks.append(("C3: current_medications only med chunks",
                   all(c.source_type == "medications" for c in med_chunks)))

    lab_chunks = retrieve_for_section(chunks, "abnormal_labs", max_chunks=15)
    checks.append(("C3: abnormal_labs only abnormal=True",
                   all(c.metadata.get("is_abnormal") for c in lab_chunks)))

    tl_chunks = retrieve_for_section(chunks, "treatment_timeline", max_chunks=15)
    checks.append(("C3: treatment_timeline has ≤15 chunks", len(tl_chunks) <= 15))

except ImportError as e:
    checks.append((f"C3 import error (not yet implemented): {e}", False))
except Exception as e:
    checks.append((f"C3 runtime error: {e}", False))

# Check pipeline has 9 sections
try:
    from poc.poc_pipeline import SECTIONS
    checks.append((f"PoC SECTIONS == 9 (got {len(SECTIONS)})", len(SECTIONS) == 9))
    checks.append(("PoC has treatment_timeline section", "treatment_timeline" in SECTIONS))
except Exception as e:
    checks.append((f"SECTIONS import error: {e}", False))

# Check PoC uses Claude API
try:
    import ast
    poc_src = (ROOT / "poc/poc_pipeline.py").read_text(encoding="utf-8")
    checks.append(("PoC imports anthropic (not openai)",
                   "from anthropic import" in poc_src and "from openai import" not in poc_src))
except Exception as e:
    checks.append((f"API check error: {e}", False))

print("\n" + "="*60)
print("  WEEK 3 CHECKPOINT")
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
    print("ALL PASSED — Week 3 deliverables complete!")
else:
    print("Some checks failed — see above.")
