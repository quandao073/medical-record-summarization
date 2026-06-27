"""Summary router: list patients, run pipeline, manage cache."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Annotated

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from dotenv import load_dotenv

from poc.poc_pipeline import run_poc
from api.dependencies import LLMClientDep, DBSessionDep
from src.c1_emr.assembler import assemble_from_db
from src.c2_chunking.store_builder import load_structured_store
from src.c6_verifier.verifier import verify_summary
from src.cache.redis_cache import SummaryCache, compute_ehr_hash
from src.llm.circuit_breaker import CircuitOpenError
from src.llm.errors import LLMError
from src.monitoring.metrics import (
    SUMMARY_REQUESTS, SUMMARY_DURATION, CACHE_OPERATIONS, ACTIVE_REQUESTS,
)
from src.schemas import SourceChunk
from src.tasks.store import TaskStore, TaskStatus

load_dotenv()

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"
STORE_DIR = ROOT / "data" / "processed" / "stores"

_cache = SummaryCache()
_task_store = TaskStore()


@router.get("/patients")
async def list_patients():
    """Return list of available patient IDs — from DB first, fallback to files."""
    try:
        from src.db.engine import get_db
        from src.db.repositories.emr_repo import EMRRepository
        async for session in get_db():
            repo = EMRRepository(session)
            patients = await repo.list_patients()
            if patients:
                return {"patients": patients, "source": "database"}
    except Exception:
        pass
    if not ASSEMBLED_DIR.exists():
        return {"patients": [], "source": "none"}
    patients = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
    return {"patients": patients, "source": "filesystem"}


@router.post("/summarize/{patient_id}")
async def summarize(
    patient_id: str,
    client: LLMClientDep,
    db: DBSessionDep,
    background_tasks: BackgroundTasks,
    force_refresh: Annotated[bool, Query(description="Skip cache")] = False,
    background: Annotated[bool, Query(description="Run in background")] = False,
):
    """
    Run the full pipeline: C1 → C2 → C3 → C4 → C5/C6 verification.
    EHR is read from the database (source of truth). Results are cached
    in Redis (L1) with file fallback (L2).
    Pass background=true to get a task_id and poll GET /tasks/{task_id}.
    """
    start = time.perf_counter()
    ACTIVE_REQUESTS.inc()
    try:
        raw_ehr = await assemble_from_db(db, patient_id)
        if raw_ehr is None:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        ehr_hash = compute_ehr_hash(raw_ehr)
        model = getattr(client, "model", "unknown")

        if not force_refresh:
            cached = await _cache.get(patient_id, ehr_hash, model)
            if cached:
                duration = time.perf_counter() - start
                cache_source = cached.get("_cache_source", "unknown")
                SUMMARY_REQUESTS.labels(patient_id=patient_id, status="success", cache_source=cache_source).inc()
                SUMMARY_DURATION.labels(patient_id=patient_id, from_cache="true").observe(duration)
                CACHE_OPERATIONS.labels(operation="get", result="hit").inc()
                return cached

        CACHE_OPERATIONS.labels(operation="get", result="miss").inc()

        if background:
            task = _task_store.create(patient_id)
            if task.status == TaskStatus.PENDING:
                background_tasks.add_task(
                    _run_pipeline_background,
                    task.task_id, patient_id, client, raw_ehr, ehr_hash, model,
                )
            return {"status": task.status, "task_id": task.task_id, "patient_id": patient_id}

        try:
            summary = await asyncio.to_thread(
                run_poc, patient_id, client, None, 60, False, False, raw_ehr
            )
        except (LLMError, CircuitOpenError):
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

        result = summary.model_dump()
        result["_from_cache"] = False
        result["_cache_source"] = "none"

        await _cache.set(patient_id, ehr_hash, model, result)

        duration = time.perf_counter() - start
        SUMMARY_REQUESTS.labels(patient_id=patient_id, status="success", cache_source="none").inc()
        SUMMARY_DURATION.labels(patient_id=patient_id, from_cache="false").observe(duration)
        return result
    except Exception:
        SUMMARY_REQUESTS.labels(patient_id=patient_id, status="error", cache_source="none").inc()
        raise
    finally:
        ACTIVE_REQUESTS.dec()


async def _run_pipeline_background(
    task_id: str, patient_id: str, client, raw_ehr: dict, ehr_hash: str, model: str,
):
    _task_store.update(task_id, status=TaskStatus.PROCESSING)
    try:
        summary = await asyncio.to_thread(
            run_poc, patient_id, client, None, 60, False, False, raw_ehr
        )
        result = summary.model_dump()
        result["_from_cache"] = False
        result["_cache_source"] = "none"
        await _cache.set(patient_id, ehr_hash, model, result)
        _task_store.update(
            task_id, status=TaskStatus.READY, result=result,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        _task_store.update(
            task_id, status=TaskStatus.FAILED, error=str(exc),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


@router.get("/cache/stats")
async def cache_stats():
    """Return cache hit/miss statistics and Redis health."""
    redis_healthy = await _cache.is_redis_healthy()
    return {
        "redis_healthy": redis_healthy,
        "stats": _cache.stats,
    }


@router.post("/cache/invalidate-all")
async def invalidate_all_cache():
    """Invalidate all cached summaries across Redis and file."""
    deleted = await _cache.invalidate_all()
    return {"deleted_keys": deleted}


@router.get("/cache/{patient_id}")
def get_cache(patient_id: str):
    """Return cached summary if it exists (file-based lookup)."""
    cache_dir = _cache._cache_dir
    cache_path = cache_dir / f"{patient_id}_latest.json"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="No cached result for this patient")
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    data["_from_cache"] = True
    return data


@router.delete("/cache/{patient_id}")
async def clear_cache(patient_id: str):
    """Delete cached summary to force re-generation."""
    deleted = await _cache.invalidate(patient_id)
    return {"cleared": patient_id, "deleted_keys": deleted}
