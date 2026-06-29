"""
PoC Pipeline — Tuan 3+.
Full C1→C2→C3→C4→C5→C6 pipeline with atomic claim verification.
Provider: configurable via --provider (openai | anthropic | ollama).
Section IDs: English. Summary content: Vietnamese.

Usage:
    python -m poc.poc_pipeline --patient P001
    python -m poc.poc_pipeline --patient P001 --provider openai --model gpt-4o-mini
    python -m poc.poc_pipeline --patient P001 --provider anthropic --model claude-haiku-4-5-20251001
    python -m poc.poc_pipeline --patient P001 --provider ollama --model llama3
    python -m poc.poc_pipeline --all-patients
    python -m poc.poc_pipeline --patient P001 --vector
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from src.llm import BaseLLMClient, create_llm_client
from src.c1_emr.pipeline import load_and_process, process_ehr, C1ProcessingError
from src.c2_chunking.chunker import chunk_ehr
from src.c3_retrieval.retriever import retrieve_for_section
from src.c3_retrieval.vector_store import VectorStore
from src.c4_llm_draft import SECTIONS, SECTION_LABELS
from src.c4_llm_draft.prompts import TOP_K_PER_SECTION, build_section_prompt
from src.c4_llm_draft.summarizer import (
    format_chunks_as_context,
    format_chunks_by_encounter,
    generate_section_drafts,
)
from src.c6_verifier.verifier import verify_section, check_internal_consistency
from src.schemas import SourceChunk, CitedClaim, FinalSummary, SummarySection, SummaryMetrics

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR      = ROOT / "data" / "processed"
ASSEMBLED_DIR = DATA_DIR / "assembled"
OUTPUT_DIR    = DATA_DIR / "outputs"
VECTOR_DIR    = DATA_DIR / "vector_store"


def run_poc(
    patient_id: str,
    client: BaseLLMClient,
    model: str | None = None,
    max_context_chunks: int = 60,
    verbose: bool = True,
    use_vector_store: bool = False,
    raw_ehr: dict | None = None,
) -> tuple[FinalSummary, list[SourceChunk]]:
    t_start = time.time()
    if verbose:
        print(f"\n{'='*60}")
        print(f"PoC Pipeline | Patient: {patient_id} | {client.provider_name}/{client.model}")
        print(f"{'='*60}")

    # C1: Validate + De-identify + Normalize
    if raw_ehr is not None:
        if verbose:
            print("[C1] Processing EHR (source: database)...")
        try:
            safe_ehr = process_ehr(raw_ehr)
        except C1ProcessingError as e:
            print(f"[C1] VALIDATION FAILED: {e}")
            raise
    else:
        ehr_path = ASSEMBLED_DIR / f"{patient_id}.json"
        if not ehr_path.exists():
            raise FileNotFoundError(f"EHR not found: {ehr_path}")

        if verbose:
            print("[C1] Processing EHR (source: file)...")
        try:
            safe_ehr = load_and_process(ehr_path)
        except C1ProcessingError as e:
            print(f"[C1] VALIDATION FAILED: {e}")
            raise

    # C2: Chunk + Build Store
    if verbose:
        print("[C2] Chunking...")
    chunks = chunk_ehr(safe_ehr)

    if verbose:
        type_counts = {}
        for c in chunks:
            type_counts[c.source_type] = type_counts.get(c.source_type, 0) + 1
        print(f"[C2] {len(chunks)} chunks: {type_counts}")

    # C3-prep: Build or load vector store for hybrid retrieval
    vs: VectorStore | None = None
    if use_vector_store:
        vs_path = VECTOR_DIR / patient_id
        if vs_path.exists() and (vs_path / "index.faiss").exists():
            if verbose:
                print(f"[C3] Loading vector store from {vs_path}...")
            vs = VectorStore()
            vs.load(vs_path)
        else:
            if verbose:
                print(f"[C3] Building vector store ({len(chunks)} chunks)...", end=" ", flush=True)
            vs = VectorStore()
            vs.build(chunks)
            vs.save(vs_path)
            if verbose:
                print("OK")

    # ──────────────────────────────────────────────────────────────────────────
    # C3: retrieve chunks + build prompts for all sections (local, fast)
    # ──────────────────────────────────────────────────────────────────────────
    section_chunks_map: dict[str, list[SourceChunk]] = {}
    section_prompts: dict[str, str] = {}
    is_local = client.provider_name in ("lmstudio", "ollama")

    for section_id in SECTIONS:
        top_k = TOP_K_PER_SECTION.get(section_id, 15)
        section_chunks = retrieve_for_section(chunks, section_id, max_chunks=top_k, vector_store=vs)
        section_chunks_map[section_id] = section_chunks

        if section_id == "treatment_timeline":
            context = format_chunks_by_encounter(section_chunks, top_k)
        else:
            context = format_chunks_as_context(section_chunks, top_k)

        section_prompts[section_id] = build_section_prompt(section_id, context, local_model=is_local)

    # ──────────────────────────────────────────────────────────────────────────
    # C4 (LLM): Generate all section drafts concurrently
    # ──────────────────────────────────────────────────────────────────────────
    draft_sections, total_tokens = generate_section_drafts(
        section_ids=SECTIONS,
        section_prompts=section_prompts,
        section_chunks_map=section_chunks_map,
        client=client,
        verbose=verbose,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # C5 (Claim Extraction + Evidence Matching) + C6 (Hallucination Verifier)
    # Run per section with its specific chunks for highest precision
    # ──────────────────────────────────────────────────────────────────────────
    if verbose:
        print("[C5/C6] Verifying claims per section...")

    verified_sections: list[SummarySection] = []
    removed_claims: list[CitedClaim] = []
    for draft in draft_sections:
        sc = section_chunks_map.get(draft.section_id, chunks)
        v_section, _ = verify_section(draft, sc, conservative=True, removed_out=removed_claims)
        verified_sections.append(v_section)

    # Metrics — computed from verified atomic claims (not blob-per-section)
    # ──────────────────────────────────────────────────────────────────────────
    all_claims     = [c for s in verified_sections for c in s.cited_claims if not c.is_structural]
    total_claims   = len(all_claims)
    critical_claims = [c for c in all_claims if c.is_critical]
    total_critical  = len(critical_claims)

    supported       = sum(1 for c in all_claims if c.status == "SUPPORTED")
    crit_supported  = sum(1 for c in critical_claims if c.status == "SUPPORTED")
    unsupported_n   = sum(1 for c in all_claims if c.status in ("UNSUPPORTED", "NO_CITATION"))
    low_conf        = sum(1 for c in all_claims if c.status in ("PARTIALLY_SUPPORTED", "LOW_CONFIDENCE"))
    need_rev        = sum(1 for c in all_claims if c.status == "NEED_REVIEW")
    contradicted    = sum(1 for c in all_claims if c.status == "CONTRADICTED")
    empty_sections  = sum(1 for s in verified_sections
                         if s.content and "Chưa thấy ghi nhận" in s.content)
    complete_sections = len(SECTIONS) - empty_sections

    latency = round(time.time() - t_start, 2)

    metrics = SummaryMetrics(
        citation_coverage          = round(supported / total_claims, 3)        if total_claims   else 0.0,
        critical_citation_coverage = round(crit_supported / total_critical, 3) if total_critical else 0.0,
        total_critical_claims      = total_critical,
        unsupported_claim_rate     = round(unsupported_n / total_claims, 3)    if total_claims   else 0.0,
        low_confidence_rate        = round(low_conf / total_claims, 3)         if total_claims   else 0.0,
        need_review_rate           = round(need_rev / total_claims, 3)         if total_claims   else 0.0,
        hallucination_rate         = round(contradicted / total_claims, 3)     if total_claims   else 0.0,
        missing_section_rate       = round(empty_sections / len(SECTIONS), 3)  if SECTIONS       else 0.0,
        total_claims               = total_claims,
        contradiction_count        = contradicted,
        need_review_count          = need_rev,
        duplicate_claim_count      = 0,
        latency_seconds            = latency,
        token_count                = total_tokens,
    )

    sections = verified_sections

    final = FinalSummary(
        patient_id=patient_id,
        prompt_version="poc_v4",
        model_version=f"{client.provider_name}/{client.model}",
        sections=sections,
        metrics=metrics,
        removed_claims=removed_claims,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{patient_id}_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final.model_dump(), f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n{'='*60}")
        print(f"DONE | {patient_id}")
        print(f"  Latency:          {latency}s")
        print(f"  Tokens:           {total_tokens:,}")
        print(f"  Total claims:     {total_claims}")
        print(f"  Critical claims:  {total_critical}")
        print(f"  Coverage:         {metrics.citation_coverage:.0%} overall  "
              f"| {metrics.critical_citation_coverage:.0%} critical")
        print(f"  Low confidence:   {metrics.low_confidence_rate:.0%}")
        print(f"  Need review:      {metrics.need_review_rate:.0%}")
        print(f"  Sections:         {complete_sections}/{len(SECTIONS)}")
        print(f"  Output:           {out_path}")
        print(f"{'='*60}")

    return final, chunks


async def _async_main() -> None:
    parser = argparse.ArgumentParser(description="PoC Pipeline — Medical Record Summarization")
    parser.add_argument("--patient", default="P001")
    parser.add_argument("--all-patients", action="store_true")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-chunks", type=int, default=60)
    parser.add_argument("--vector", action="store_true")
    args = parser.parse_args()

    try:
        client = create_llm_client(provider=args.provider, model=args.model)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print(f"LLM: {client.provider_name} / {client.model}")
    use_vs = args.vector

    from src.db.engine import init_db, get_db
    from src.db.repositories.chunk_repo import ChunkRepository
    await init_db()

    if args.all_patients:
        patient_ids = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
        print(f"Running PoC | {len(patient_ids)} patients | vector: {use_vs}")
        for pid in patient_ids:
            try:
                final, chunks = run_poc(pid, client, args.model, args.max_chunks, use_vector_store=use_vs)
                async for session in get_db():
                    repo = ChunkRepository(session)
                    await repo.save_chunks(chunks)
            except Exception as e:
                print(f"[ERROR] {pid}: {e}")
    else:
        final, chunks = run_poc(args.patient, client, args.model, args.max_chunks, use_vector_store=use_vs)
        async for session in get_db():
            repo = ChunkRepository(session)
            await repo.save_chunks(chunks)


def main() -> None:
    import asyncio
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
