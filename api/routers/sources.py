"""Sources router: look up individual SourceChunks and raw encounter data."""

from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.dependencies import DBSessionDep
from src.db.repositories.chunk_repo import ChunkRepository

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"


def _patient_from_source_id(source_id: str) -> str:
    return source_id.split("-")[0]


@router.get("/source/{source_id}")
async def get_source(source_id: str, db: DBSessionDep):
    """Look up a single SourceChunk by source_id from the database."""
    repo = ChunkRepository(db)
    chunk = await repo.get_chunk_by_id(source_id)
    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source ID '{source_id}' not found. Run the pipeline first to populate chunk store.",
        )
    return chunk.model_dump()


@router.get("/raw-encounter/{patient_id}/{encounter_id}")
def get_raw_encounter(patient_id: str, encounter_id: str):
    """Return raw encounter data from the assembled JSON for doctor verification."""
    assembled_path = ASSEMBLED_DIR / f"{patient_id}.json"
    if not assembled_path.exists():
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

    data = json.loads(assembled_path.read_text(encoding="utf-8"))

    for enc in data.get("encounters", []):
        if enc.get("encounter_id") == encounter_id:
            return {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "encounter": enc,
                "patient_info": data.get("patient", {}),
                "allergies": data.get("allergies", []),
            }

    raise HTTPException(
        status_code=404,
        detail=f"Encounter '{encounter_id}' not found for {patient_id}",
    )
