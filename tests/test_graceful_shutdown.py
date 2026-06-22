import pytest
from fastapi.testclient import TestClient

from api.main import app


def test_health_returns_alive():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_startup_event_sets_ready():
    """After startup, readiness endpoint should return 200."""
    client = TestClient(app)
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200


def test_request_id_header_present():
    """Requests should get an X-Request-ID header in response."""
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) == 8
