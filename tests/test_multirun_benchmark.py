"""Tests for multi-run benchmark statistical aggregation."""

from unittest.mock import patch
from scripts.run_multirun_benchmark import run_multirun


def _fake_benchmark(patient_id, model_specs, max_chunks):
    return {
        "anthropic:test": {
            "error": None,
            "summary": {
                "metrics": {
                    "citation_coverage": 0.85,
                    "hallucination_rate": 0.05,
                    "total_claims": 20,
                    "latency_seconds": 3.5,
                }
            },
        }
    }


def _fake_benchmark_varying(patient_id, model_specs, max_chunks):
    import random
    base = 0.80 + random.random() * 0.15
    return {
        "anthropic:test": {
            "error": None,
            "summary": {
                "metrics": {
                    "citation_coverage": round(base, 4),
                    "hallucination_rate": round(0.1 - base * 0.05, 4),
                    "total_claims": 20,
                }
            },
        }
    }


@patch("scripts.run_multirun_benchmark.run_benchmark", side_effect=_fake_benchmark)
def test_multirun_returns_stats(mock_bench):
    results = run_multirun(["P001"], ["anthropic:test"], n_runs=3)

    assert "P001" in results
    model_data = results["P001"]["anthropic:test"]
    assert model_data["n_successful_runs"] == 3
    assert model_data["n_total_runs"] == 3

    stats = model_data["metric_stats"]
    assert "citation_coverage" in stats
    assert stats["citation_coverage"]["mean"] == 0.85
    assert stats["citation_coverage"]["std"] == 0
    assert stats["citation_coverage"]["n_runs"] == 3


@patch("scripts.run_multirun_benchmark.run_benchmark", side_effect=_fake_benchmark)
def test_multirun_meta(mock_bench):
    results = run_multirun(["P001", "P002"], ["anthropic:test"], n_runs=2)

    meta = results["_meta"]
    assert meta["n_patients"] == 2
    assert meta["n_runs"] == 2
    assert "timestamp" in meta


@patch("scripts.run_multirun_benchmark.run_benchmark", side_effect=Exception("boom"))
def test_multirun_handles_all_failures(mock_bench):
    results = run_multirun(["P001"], ["anthropic:test"], n_runs=2)

    model_data = results["P001"]["anthropic:test"]
    assert model_data["error"] == "all runs failed"


@patch("scripts.run_multirun_benchmark.run_benchmark", side_effect=_fake_benchmark_varying)
def test_multirun_std_nonzero_with_varying_data(mock_bench):
    results = run_multirun(["P001"], ["anthropic:test"], n_runs=5)

    stats = results["P001"]["anthropic:test"]["metric_stats"]
    assert stats["citation_coverage"]["n_runs"] == 5
    assert stats["citation_coverage"]["mean"] > 0
