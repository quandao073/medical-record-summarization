"""Tests for review API endpoints."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

REVIEW_DIR = Path(__file__).parent.parent / "data" / "reviews"


@pytest.fixture(autouse=True)
def clean_reviews():
    """Remove test review files before/after each test."""
    test_file = REVIEW_DIR / "P001_review.json"
    if test_file.exists():
        test_file.unlink()
    yield
    if test_file.exists():
        test_file.unlink()


def test_get_review_creates_default():
    resp = client.get("/api/v1/review/P001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_id"] == "P001"
    assert data["summary_status"] == "draft"
    assert data["claim_reviews"] == {}
    assert data["feedback"] == []


def test_get_review_rejects_invalid_patient_id():
    resp = client.get("/api/v1/review/../../secret")
    assert resp.status_code in (404, 422)


def test_get_review_rejects_bad_format():
    resp = client.get("/api/v1/review/INVALID")
    assert resp.status_code == 422


def test_post_claim_review_approved():
    resp = client.post("/api/v1/review/P001/claim", json={
        "claim_id": "P001-overview-001-abc12",
        "section_id": "overview",
        "claim_text": "Test claim",
        "action": "approved",
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    state = client.get("/api/v1/review/P001").json()
    assert "P001-overview-001-abc12" in state["claim_reviews"]
    assert state["claim_reviews"]["P001-overview-001-abc12"]["action"] == "approved"


def test_post_claim_review_edited():
    resp = client.post("/api/v1/review/P001/claim", json={
        "claim_id": "P001-overview-001-abc12",
        "section_id": "overview",
        "claim_text": "Original text",
        "action": "edited",
        "new_text": "Corrected text",
    })
    assert resp.status_code == 200
    state = client.get("/api/v1/review/P001").json()
    review = state["claim_reviews"]["P001-overview-001-abc12"]
    assert review["action"] == "edited"
    assert review["new_text"] == "Corrected text"


def test_post_claim_review_rejects_invalid_action():
    resp = client.post("/api/v1/review/P001/claim", json={
        "claim_id": "P001-overview-001-abc12",
        "section_id": "overview",
        "claim_text": "Test",
        "action": "invalid_action",
    })
    assert resp.status_code == 422


def test_post_summary_status_draft():
    resp = client.post("/api/v1/review/P001/summary", json={
        "status": "draft",
    })
    assert resp.status_code == 200
    state = client.get("/api/v1/review/P001").json()
    assert state["summary_status"] == "draft"
    assert state["confirmed_at"] is None


def test_post_summary_status_confirmed():
    resp = client.post("/api/v1/review/P001/summary", json={
        "status": "confirmed",
        "reviewer": "BS. Nguyễn Văn A",
    })
    assert resp.status_code == 200
    state = client.get("/api/v1/review/P001").json()
    assert state["summary_status"] == "confirmed"
    assert state["confirmed_at"] is not None
    assert state["reviewer"] == "BS. Nguyễn Văn A"


def test_post_feedback_appends():
    client.post("/api/v1/review/P001/feedback", json={"text": "Feedback 1"})
    client.post("/api/v1/review/P001/feedback", json={"text": "Feedback 2"})
    state = client.get("/api/v1/review/P001").json()
    assert len(state["feedback"]) == 2
    assert state["feedback"][0]["text"] == "Feedback 1"
    assert state["feedback"][1]["text"] == "Feedback 2"


def test_reject_path_traversal():
    resp = client.get("/api/v1/review/..%2F..%2Fsecret")
    assert resp.status_code in (404, 422)
