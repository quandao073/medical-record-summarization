"""Sources router: look up individual SourceChunks by source_id."""

from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.c2_chunking.store_builder import load_structured_store, get_chunk

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
STORE_DIR = ROOT / "data" / "processed" / "stores"


def _patient_from_source_id(source_id: str) -> str:
    """
    Extract patient_id from source_id.
    Source IDs follow: {encounter_id}-{TYPE}-{ID}
    where encounter_id is {patient_id}-E{n}.
    So split("-")[0] gives the patient_id.
    """
    return source_id.split("-")[0]


@router.get("/source/{source_id}")
def get_source(source_id: str):
    """
    Look up a single SourceChunk by source_id.
    Patient store must exist (run dry_run.py or poc_pipeline first).
    """
    patient_id = _patient_from_source_id(source_id)
    store_path = STORE_DIR / f"{patient_id}_store.json"

    if not store_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Store not found for patient {patient_id}. "
                "Run `python poc/dry_run.py` first to build the chunk store."
            ),
        )

    store = load_structured_store(store_path)
    chunk = get_chunk(store, source_id)

    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source ID '{source_id}' not found in store for {patient_id}",
        )

    return chunk.model_dump()
