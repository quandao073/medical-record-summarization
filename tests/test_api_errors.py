import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_llm_client


def _mock_client():
    client = MagicMock()
    client.provider_name = "anthropic"
    client.model = "test-model"
    return client


def test_404_patient_not_found():
    mock_client = _mock_client()
    app.dependency_overrides[get_llm_client] = lambda: mock_client
    try:
        client = TestClient(app)
        resp = client.post("/api/v1/summarize/P999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_health_returns_200():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_llm_error_returns_502():
    from src.llm.errors import LLMConnectionError

    mock_client = _mock_client()
    app.dependency_overrides[get_llm_client] = lambda: mock_client
    try:
        client = TestClient(app, raise_server_exceptions=False)
        with patch("api.routers.summary.run_poc") as mock_run:
            mock_run.side_effect = LLMConnectionError("Cannot reach API")
            resp = client.post("/api/v1/summarize/P001?force_refresh=true")

        assert resp.status_code == 502
        body = resp.json()
        assert body["error"] == "llm_error"
    finally:
        app.dependency_overrides.clear()


def test_circuit_open_returns_503():
    from src.llm.circuit_breaker import CircuitOpenError

    mock_client = _mock_client()
    app.dependency_overrides[get_llm_client] = lambda: mock_client
    try:
        client = TestClient(app, raise_server_exceptions=False)
        with patch("api.routers.summary.run_poc") as mock_run:
            mock_run.side_effect = CircuitOpenError("Circuit is OPEN")
            resp = client.post("/api/v1/summarize/P001?force_refresh=true")

        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "service_unavailable"
    finally:
        app.dependency_overrides.clear()
