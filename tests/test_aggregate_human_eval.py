"""Tests for human eval aggregation script."""

import csv
import json
from pathlib import Path

import pytest

HUMAN_EVAL_DIR = Path(__file__).parent.parent / "data" / "human_eval"

SAMPLE_EVAL = {
    "patient_id": "P999",
    "summary_generated_at": "2026-06-16T15:30:00Z",
    "model": "claude-haiku-4-5-20251001",
    "prompt_version": "poc_v4",
    "evaluator": "Đào Anh Quân",
    "evaluated_at": "2026-06-16T16:00:00Z",
    "scores": {
        "clinical_correctness": {"score": 4, "notes": ""},
        "completeness": {"score": 4, "notes": ""},
        "citation_faithfulness": {"score": 4, "notes": ""},
        "safety": {"score": 4, "notes": ""},
        "temporal_correctness": {"score": 4, "notes": ""},
        "readability": {"score": 4, "notes": ""},
    },
    "overall_notes": "Tốt",
    "error_categories": ["partial_citation"],
    "weighted_score": 4.0,
}


@pytest.fixture()
def sample_eval_file():
    HUMAN_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = HUMAN_EVAL_DIR / "P999_human_eval.json"
    path.write_text(json.dumps(SAMPLE_EVAL, ensure_ascii=False), encoding="utf-8")
    yield path
    if path.exists():
        path.unlink()


def test_load_human_evals(sample_eval_file):
    from scripts.aggregate_human_eval import load_human_evals
    evals = load_human_evals()
    p999_evals = [e for e in evals if e["patient_id"] == "P999"]
    assert len(p999_evals) == 1
    assert p999_evals[0]["weighted_score"] == 4.0


def test_format_report_empty():
    from scripts.aggregate_human_eval import format_report
    report = format_report([])
    assert "Chưa có đánh giá" in report


def test_format_report_shows_patient_id(sample_eval_file):
    from scripts.aggregate_human_eval import load_human_evals, format_report
    evals = [e for e in load_human_evals() if e["patient_id"] == "P999"]
    report = format_report(evals)
    assert "P999" in report
    assert "4.000" in report


def test_format_report_shows_missing_patients(sample_eval_file):
    from scripts.aggregate_human_eval import load_human_evals, format_report
    evals = [e for e in load_human_evals() if e["patient_id"] == "P999"]
    report = format_report(evals)
    assert "P001" in report or "Chưa đánh giá" in report


def test_format_csv(sample_eval_file):
    from scripts.aggregate_human_eval import load_human_evals, format_csv
    evals = [e for e in load_human_evals() if e["patient_id"] == "P999"]
    csv_str = format_csv(evals)
    rows = list(csv.reader(csv_str.splitlines()))
    assert rows[0][0] == "patient_id"
    assert rows[1][0] == "P999"
    assert "4" in rows[1]  # score 4 appears


def test_load_auto_eval_robust():
    """load_auto_eval returns None (not crash) when file missing."""
    from scripts.aggregate_human_eval import load_auto_eval
    result = load_auto_eval("P999")
    assert result is None
