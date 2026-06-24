"""Tests for EMR CRUD API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.db.engine import init_db, close_db


@pytest_asyncio.fixture
async def client():
    await init_db("sqlite+aiosqlite:///:memory:")
    from api.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await close_db()


class TestEMREndpoints:
    @pytest.mark.asyncio
    async def test_list_emr_patients_empty(self, client):
        response = await client.get("/api/v1/emr/patients")
        assert response.status_code == 200
        data = response.json()
        assert "patients" in data
        assert data["source"] == "database"

    @pytest.mark.asyncio
    async def test_get_emr_patient_not_found(self, client):
        response = await client.get("/api/v1/emr/patients/P999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_emr_stats_empty(self, client):
        response = await client.get("/api/v1/emr/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["patients"] == 0
        assert data["total"] == 0
