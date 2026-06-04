"""Summary router: list patients, run pipeline, manage cache."""

from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from openai import OpenAI
from dotenv import load_dotenv

from poc.poc_pipeline import run_poc
from src.c2_chunking.store_builder import load_structured_store
from src.c6_verifier.verifier import verify_summary
from src.schemas import SourceChunk

load_dotenv()

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"
STORE_DIR     = ROOT / "data" / "processed" / "stores"
CACHE_DIR     = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

VALID_MODELS = ["gpt-4o-mini", "gpt-4o"]


def _openai_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured. Add it to .env and restart the server.",
        )
    return OpenAI(api_key=key)


@router.get("/patients")
def list_patients():
    """Return list of available patient IDs."""
    if not ASSEMBLED_DIR.exists():
        return {"patients": []}
    patients = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
    return {"patients": patients}


@router.post("/summarize/{patient_id}")
async def summarize(
    patient_id: str,
    model: Annotated[str, Query(description="OpenAI model")] = "gpt-4o-mini",
    force_refresh: Annotated[bool, Query(description="Skip cache")] = False,
):
    """
    Run the full pipeline: C1 → C2 → C3 → LLM → C5/C6 verification.
    Returns FinalSummary JSON.  Results are cached per patient.
    """
    if model not in VALID_MODELS:
        raise HTTPException(status_code=400, detail=f"Model must be one of {VALID_MODELS}")

    cache_path = CACHE_DIR / f"{patient_id}_latest.json"

    if cache_path.exists() and not force_refresh:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["_from_cache"] = True
        return data

    ehr_path = ASSEMBLED_DIR / f"{patient_id}.json"
    if not ehr_path.exists():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    client = _openai_client()

    try:
        summary = await asyncio.to_thread(
            run_poc, patient_id, client, model, 60, False
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    # Apply C5+C6 verification on top of LLM-generated sections
    store_path = STORE_DIR / f"{patient_id}_store.json"
    if store_path.exists():
        store = load_structured_store(store_path)
        chunks = [SourceChunk(**v) for v in store.values()]
        verified_sections, v_metrics = verify_summary(summary.sections, chunks)
        final = summary.model_copy(update={
            "sections": verified_sections,
            "metrics": v_metrics.model_copy(update={
                "latency_seconds": summary.metrics.latency_seconds,
                "token_count":     summary.metrics.token_count,
            }),
        })
    else:
        final = summary

    result = final.model_dump()
    result["_from_cache"] = False

    cache_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


@router.get("/cache/{patient_id}")
def get_cache(patient_id: str):
    """Return cached summary if it exists."""
    cache_path = CACHE_DIR / f"{patient_id}_latest.json"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="No cached result for this patient")
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    data["_from_cache"] = True
    return data


@router.delete("/cache/{patient_id}")
def clear_cache(patient_id: str):
    """Delete cached summary to force re-generation."""
    cache_path = CACHE_DIR / f"{patient_id}_latest.json"
    if cache_path.exists():
        cache_path.unlink()
    return {"cleared": patient_id}
