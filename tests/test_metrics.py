"""Tests for Prometheus metrics endpoint and instrumentation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, client):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200

    def test_metrics_content_type_is_text(self, client):
        response = client.get("/api/v1/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_process_metrics(self, client):
        response = client.get("/api/v1/metrics")
        assert "process_" in response.text or "# HELP" in response.text

    def test_metrics_contains_custom_counters(self, client):
        response = client.get("/api/v1/metrics")
        text = response.text
        assert "summary_requests_total" in text or "summary_requests" in text

    def test_metrics_contains_histogram(self, client):
        response = client.get("/api/v1/metrics")
        text = response.text
        assert "summary_request_duration_seconds" in text

    def test_metrics_contains_cache_operations(self, client):
        response = client.get("/api/v1/metrics")
        text = response.text
        assert "cache_operations_total" in text or "cache_operations" in text

    def test_metrics_contains_active_requests_gauge(self, client):
        response = client.get("/api/v1/metrics")
        text = response.text
        assert "active_summary_requests" in text


class TestMetricsModule:
    def test_counters_importable(self):
        from src.monitoring.metrics import (
            SUMMARY_REQUESTS,
            SUMMARY_DURATION,
            CACHE_OPERATIONS,
            LLM_CALLS,
            LLM_DURATION,
            ACTIVE_REQUESTS,
        )
        assert SUMMARY_REQUESTS is not None
        assert SUMMARY_DURATION is not None
        assert CACHE_OPERATIONS is not None
        assert LLM_CALLS is not None
        assert LLM_DURATION is not None
        assert ACTIVE_REQUESTS is not None

    def test_counter_labels(self):
        from src.monitoring.metrics import SUMMARY_REQUESTS
        labeled = SUMMARY_REQUESTS.labels(patient_id="P001", status="success", cache_source="redis")
        labeled.inc()
        assert labeled._value.get() >= 1

    def test_histogram_observe(self):
        from src.monitoring.metrics import SUMMARY_DURATION
        labeled = SUMMARY_DURATION.labels(patient_id="P001", from_cache="true")
        labeled.observe(0.05)

    def test_gauge_inc_dec(self):
        from src.monitoring.metrics import ACTIVE_REQUESTS
        ACTIVE_REQUESTS.inc()
        val = ACTIVE_REQUESTS._value.get()
        ACTIVE_REQUESTS.dec()
        assert ACTIVE_REQUESTS._value.get() == val - 1
