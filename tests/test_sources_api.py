"""Tests for sources API — reads SourceChunks from DB, not JSON files."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from api.main import app
from src.db.engine import get_db
from src.db.models import Base, ChunkDB


@pytest_asyncio.fixture(scope="module")
async def seeded_engine():
    """In-memory SQLite DB seeded with minimal chunk data for all tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            ChunkDB(
                source_id="P001-PATIENT-INFO",
                patient_id="P001",
                source_type="patient_info",
                encounter_id=None,
                date=None,
                content="Nguyễn Văn An, 55 tuổi",
                metadata_json={},
            ),
            ChunkDB(
                source_id="P001-E001-LAB-HBA1C",
                patient_id="P001",
                source_type="labs",
                encounter_id="P001-E001",
                date="2024-01-10",
                content="HbA1c = 8.5%",
                metadata_json={"is_abnormal": True},
            ),
        ])
        await session.commit()
    yield engine
    await engine.dispose()


@pytest.fixture
def client(seeded_engine):
    """TestClient with DB dependency overridden to use in-memory SQLite."""
    factory = async_sessionmaker(seeded_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSourceEndpoint:
    def test_get_source_returns_chunk(self, client):
        resp = client.get("/api/v1/source/P001-PATIENT-INFO")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_id"] == "P001-PATIENT-INFO"
        assert data["patient_id"] == "P001"
        assert "content" in data

    def test_get_source_lab_chunk(self, client):
        resp = client.get("/api/v1/source/P001-E001-LAB-HBA1C")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "labs"
        assert data["metadata"]["is_abnormal"] is True

    def test_get_source_not_found(self, client):
        resp = client.get("/api/v1/source/P001-NONEXISTENT-999")
        assert resp.status_code == 404


class TestRawEncounterEndpoint:
    def test_get_raw_encounter_success(self, client):
        resp = client.get("/api/v1/raw-encounter/P001/P001-E001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_id"] == "P001"
        assert data["encounter_id"] == "P001-E001"
        enc = data["encounter"]
        assert "encounter_date" in enc
        assert "labs" in enc
        assert "medications" in enc
        assert isinstance(data["patient_info"], dict)
        assert isinstance(data["allergies"], list)

    def test_get_raw_encounter_patient_not_found(self, client):
        resp = client.get("/api/v1/raw-encounter/P999/P999-E001")
        assert resp.status_code == 404

    def test_get_raw_encounter_encounter_not_found(self, client):
        resp = client.get("/api/v1/raw-encounter/P001/P001-E999")
        assert resp.status_code == 404
