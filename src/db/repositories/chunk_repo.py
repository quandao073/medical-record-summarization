"""
ChunkRepository — persists and retrieves SourceChunk objects from the DB.

Usage:
    repo = ChunkRepository(session)
    await repo.save_chunks(chunks)                      # upsert all chunks for patient
    chunks = await repo.get_chunks_for_patient("P001")  # load for pipeline
    chunk  = await repo.get_chunk_by_id("P001-E001-LAB-HBA1C")  # citation lookup
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChunkDB
from src.schemas import SourceChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_chunks(self, chunks: list[SourceChunk]) -> None:
        """Upsert: delete all existing chunks for the patient, then insert new ones."""
        if not chunks:
            return
        patient_id = chunks[0].patient_id
        await self._session.execute(
            delete(ChunkDB).where(ChunkDB.patient_id == patient_id)
        )
        self._session.add_all([
            ChunkDB(
                source_id=c.source_id,
                patient_id=c.patient_id,
                source_type=c.source_type,
                encounter_id=c.encounter_id,
                date=c.date,
                content=c.content,
                metadata_json=c.metadata,
            )
            for c in chunks
        ])
        await self._session.flush()

    async def get_chunks_for_patient(self, patient_id: str) -> list[SourceChunk]:
        result = await self._session.execute(
            select(ChunkDB).where(ChunkDB.patient_id == patient_id)
        )
        return [_to_source_chunk(row) for row in result.scalars().all()]

    async def get_chunk_by_id(self, source_id: str) -> SourceChunk | None:
        result = await self._session.execute(
            select(ChunkDB).where(ChunkDB.source_id == source_id)
        )
        row = result.scalar_one_or_none()
        return _to_source_chunk(row) if row else None


def _to_source_chunk(row: ChunkDB) -> SourceChunk:
    return SourceChunk(
        source_id=row.source_id,
        patient_id=row.patient_id,
        source_type=row.source_type,
        encounter_id=row.encounter_id,
        date=row.date,
        content=row.content,
        metadata=row.metadata_json or {},
    )
