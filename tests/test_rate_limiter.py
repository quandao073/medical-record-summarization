import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.rate_limiter import RateLimitMiddleware


def test_rate_limit_allows_within_limit():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=10)

    @app.post("/api/v1/summarize/P001")
    async def endpoint():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(10):
        resp = client.post("/api/v1/summarize/P001")
        assert resp.status_code == 200


def test_rate_limit_rejects_over_limit():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=3)

    @app.post("/api/v1/summarize/P001")
    async def endpoint():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(3):
        resp = client.post("/api/v1/summarize/P001")
        assert resp.status_code == 200

    resp = client.post("/api/v1/summarize/P001")
    assert resp.status_code == 429
    assert "rate_limit" in resp.json()["error"]


def test_non_summarize_endpoint_not_limited():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=1)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/review/P001")
    async def review():
        return {"data": "..."}

    client = TestClient(app)
    # Both should pass even after limit is "exhausted"
    for _ in range(5):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        resp = client.get("/api/v1/review/P001")
        assert resp.status_code == 200
