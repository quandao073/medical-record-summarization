import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestSourceEndpoint:
    def test_get_source_returns_chunk(self, client):
        resp = client.get("/api/v1/source/P001-PATIENT-INFO")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_id"] == "P001-PATIENT-INFO"
        assert data["patient_id"] == "P001"
        assert "content" in data

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
