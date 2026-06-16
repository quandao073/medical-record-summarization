"""Tests for human evaluation API."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
HUMAN_EVAL_DIR = Path(__file__).parent.parent / "data" / "human_eval"

VALID_SCORES = {
    "clinical_correctness": {"score": 4, "notes": "Chính xác"},
    "completeness": {"score": 3, "notes": ""},
    "citation_faithfulness": {"score": 5, "notes": ""},
    "safety": {"score": 5, "notes": ""},
    "temporal_correctness": {"score": 4, "notes": ""},
    "readability": {"score": 4, "notes": ""},
}

VALID_PAYLOAD = {
    "evaluator": "Đào Anh Quân",
    "summary_generated_at": "2026-06-16T15:30:00Z",
    "model": "claude-haiku-4-5-20251001",
    "prompt_version": "poc_v4",
    "scores": VALID_SCORES,
    "overall_notes": "Bản tóm tắt tốt",
    "error_categories": [],
}


@pytest.fixture(autouse=True)
def clean_eval():
    path = HUMAN_EVAL_DIR / "P999_human_eval.json"
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


def test_get_human_eval_default():
    resp = client.get("/api/v1/human-eval/P999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_id"] == "P999"
    assert data["evaluated_at"] is None
    assert data["weighted_score"] is None
    assert data["summary_generated_at"] is None


def test_submit_stores_summary_metadata():
    resp = client.post("/api/v1/human-eval/P999", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    data = client.get("/api/v1/human-eval/P999").json()
    assert data["summary_generated_at"] == "2026-06-16T15:30:00Z"
    assert data["model"] == "claude-haiku-4-5-20251001"
    assert data["prompt_version"] == "poc_v4"


def test_submit_computes_weighted_score():
    resp = client.post("/api/v1/human-eval/P999", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["weighted_score"] is not None


def test_weighted_score_all_fours():
    """Tất cả tiêu chí cho điểm 4 → weighted_score == 4.0."""
    all_four = {k: {"score": 4, "notes": ""} for k in VALID_SCORES}
    payload = {**VALID_PAYLOAD, "scores": all_four}
    data = client.post("/api/v1/human-eval/P999", json=payload).json()
    assert abs(data["weighted_score"] - 4.0) < 0.001


def test_submit_rejects_empty_evaluator():
    payload = {**VALID_PAYLOAD, "evaluator": "   "}
    resp = client.post("/api/v1/human-eval/P999", json=payload)
    assert resp.status_code == 422


def test_submit_rejects_score_out_of_range():
    bad_scores = {**VALID_SCORES, "clinical_correctness": {"score": 6, "notes": ""}}
    resp = client.post("/api/v1/human-eval/P999", json={**VALID_PAYLOAD, "scores": bad_scores})
    assert resp.status_code == 422


def test_submit_rejects_missing_criterion():
    incomplete = {k: v for k, v in VALID_SCORES.items() if k != "safety"}
    resp = client.post("/api/v1/human-eval/P999", json={**VALID_PAYLOAD, "scores": incomplete})
    assert resp.status_code == 422


def test_submit_rejects_extra_criterion():
    extra_scores = {**VALID_SCORES, "random_metric": {"score": 5, "notes": ""}}
    resp = client.post("/api/v1/human-eval/P999", json={**VALID_PAYLOAD, "scores": extra_scores})
    assert resp.status_code == 422


def test_submit_rejects_invalid_error_category():
    payload = {**VALID_PAYLOAD, "error_categories": ["citation_error"]}  # old key, now invalid
    resp = client.post("/api/v1/human-eval/P999", json=payload)
    assert resp.status_code == 422


def test_submit_accepts_valid_citation_error_categories():
    for cat in ["wrong_source", "partial_citation", "no_source"]:
        payload = {**VALID_PAYLOAD, "error_categories": [cat]}
        resp = client.post("/api/v1/human-eval/P999", json=payload)
        assert resp.status_code == 200, f"Should accept '{cat}'"


def test_get_after_submit_returns_all_fields():
    client.post("/api/v1/human-eval/P999", json=VALID_PAYLOAD)
    data = client.get("/api/v1/human-eval/P999").json()
    assert data["evaluator"] == "Đào Anh Quân"
    assert data["evaluated_at"] is not None
    assert data["overall_notes"] == "Bản tóm tắt tốt"
    assert data["model"] == "claude-haiku-4-5-20251001"


def test_submit_twice_overwrites():
    client.post("/api/v1/human-eval/P999", json=VALID_PAYLOAD)
    v2 = {**VALID_PAYLOAD, "evaluator": "BS. Khác", "overall_notes": "Lần 2"}
    client.post("/api/v1/human-eval/P999", json=v2)
    data = client.get("/api/v1/human-eval/P999").json()
    assert data["evaluator"] == "BS. Khác"
    assert data["overall_notes"] == "Lần 2"


def test_reject_invalid_patient_id():
    resp = client.get("/api/v1/human-eval/INVALID")
    assert resp.status_code == 422


def test_reject_path_traversal():
    resp = client.get("/api/v1/human-eval/..%2F..%2Fsecret")
    assert resp.status_code in (404, 422)


def test_list_evals_returns_list():
    resp = client.get("/api/v1/human-eval")
    assert resp.status_code == 200
    assert "evals" in resp.json()
