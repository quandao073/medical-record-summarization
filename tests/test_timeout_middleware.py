import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.timeout import TimeoutMiddleware


def test_timeout_returns_504():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.1)

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(5)
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/slow")
    assert resp.status_code == 504
    assert resp.json()["error"] == "timeout"


def test_fast_request_succeeds():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=5)

    @app.get("/fast")
    async def fast():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/fast")
    assert resp.status_code == 200
