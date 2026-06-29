"""Tests for ChunkRepository — async SQLAlchemy chunk persistence."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.db.models import Base, ChunkDB
from src.db.repositories.chunk_repo import ChunkRepository
from src.schemas import SourceChunk


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_chunk(source_id: str, patient_id: str = "P001",
                source_type: str = "labs", **meta) -> SourceChunk:
    return SourceChunk(
        source_id=source_id,
        patient_id=patient_id,
        source_type=source_type,
        encounter_id="P001-E001",
        date="2024-01-10",
        content=f"Content for {source_id}",
        metadata=meta,
    )


class TestSaveChunks:
    @pytest.mark.asyncio
    async def test_save_inserts_rows(self, async_session):
        repo = ChunkRepository(async_session)
        chunks = [
            _make_chunk("P001-E001-LAB-HBA1C", is_abnormal=True),
            _make_chunk("P001-E001-LAB-GLUC"),
        ]
        await repo.save_chunks(chunks)
        await async_session.flush()

        from sqlalchemy import select
        result = await async_session.execute(
            select(ChunkDB).where(ChunkDB.patient_id == "P001")
        )
        rows = result.scalars().all()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_save_upserts_existing_patient(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([_make_chunk("P001-OLD")])
        await repo.save_chunks([_make_chunk("P001-NEW-A"), _make_chunk("P001-NEW-B")])
        await async_session.flush()

        result = await repo.get_chunks_for_patient("P001")
        ids = {c.source_id for c in result}
        assert "P001-OLD" not in ids
        assert "P001-NEW-A" in ids
        assert "P001-NEW-B" in ids

    @pytest.mark.asyncio
    async def test_save_empty_list_is_noop(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([])  # must not raise

    @pytest.mark.asyncio
    async def test_save_preserves_metadata(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([_make_chunk("P001-LAB-X", is_abnormal=True, test_name="HbA1c")])
        await async_session.flush()

        chunks = await repo.get_chunks_for_patient("P001")
        assert chunks[0].metadata["is_abnormal"] is True
        assert chunks[0].metadata["test_name"] == "HbA1c"


class TestGetChunksForPatient:
    @pytest.mark.asyncio
    async def test_returns_only_matching_patient(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([_make_chunk("P001-LAB", patient_id="P001")])
        await repo.save_chunks([_make_chunk("P002-LAB", patient_id="P002")])
        await async_session.flush()

        result = await repo.get_chunks_for_patient("P001")
        assert all(c.patient_id == "P001" for c in result)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_patient(self, async_session):
        repo = ChunkRepository(async_session)
        result = await repo.get_chunks_for_patient("P999")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_sourcechunk_objects(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([_make_chunk("P001-LAB")])
        await async_session.flush()

        result = await repo.get_chunks_for_patient("P001")
        assert isinstance(result[0], SourceChunk)
        assert result[0].source_id == "P001-LAB"


class TestGetChunkById:
    @pytest.mark.asyncio
    async def test_returns_chunk_when_found(self, async_session):
        repo = ChunkRepository(async_session)
        await repo.save_chunks([_make_chunk("P001-E001-MED-X", is_current=True)])
        await async_session.flush()

        chunk = await repo.get_chunk_by_id("P001-E001-MED-X")
        assert chunk is not None
        assert chunk.source_id == "P001-E001-MED-X"
        assert chunk.metadata["is_current"] is True

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, async_session):
        repo = ChunkRepository(async_session)
        result = await repo.get_chunk_by_id("NONEXISTENT-ID")
        assert result is None
