"""Prometheus metrics for the summarization API."""

from prometheus_client import Counter, Histogram, Gauge

SUMMARY_REQUESTS = Counter(
    "summary_requests_total",
    "Total summary requests",
    ["patient_id", "status", "cache_source"],
)

SUMMARY_DURATION = Histogram(
    "summary_request_duration_seconds",
    "Time spent processing summary requests",
    ["patient_id", "from_cache"],
    buckets=[0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

CACHE_OPERATIONS = Counter(
    "cache_operations_total",
    "Cache operations",
    ["operation", "result"],
)

LLM_CALLS = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["provider", "model", "status"],
)

LLM_DURATION = Histogram(
    "llm_call_duration_seconds",
    "Time spent on LLM calls",
    ["provider", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30],
)

ACTIVE_REQUESTS = Gauge(
    "active_summary_requests",
    "Currently processing summary requests",
)
