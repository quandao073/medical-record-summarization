"""
C2 — Chunking Service: Store Builder.
Builds a structured store (dict lookup by source_id) from SourceChunks.
The vector store (FAISS) will be added in Week 3 for full RAG.
"""

from __future__ import annotations
import json
from pathlib import Path
from src.schemas import SourceChunk


def build_structured_store(chunks: list[SourceChunk]) -> dict[str, dict]:
    """
    {source_id: chunk_dict} — O(1) citation lookup.
    Used by citation viewer and evidence matcher.
    """
    return {chunk.source_id: chunk.model_dump() for chunk in chunks}


def save_structured_store(store: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def load_structured_store(path: str | Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_chunks_for_patient(store: dict, patient_id: str) -> list[SourceChunk]:
    """Filter store by patient_id and return as SourceChunk objects."""
    return [
        SourceChunk(**v)
        for v in store.values()
        if v.get("patient_id") == patient_id
    ]


def get_chunk(store: dict, source_id: str) -> SourceChunk | None:
    data = store.get(source_id)
    return SourceChunk(**data) if data else None


def filter_by_type(chunks: list[SourceChunk], source_type: str) -> list[SourceChunk]:
    return [c for c in chunks if c.source_type == source_type]


def filter_by_encounter(chunks: list[SourceChunk], encounter_id: str) -> list[SourceChunk]:
    return [c for c in chunks if c.encounter_id == encounter_id]
