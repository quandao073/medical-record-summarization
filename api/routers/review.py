"""Review router: persist doctor review state (claim reviews, summary status, feedback)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
REVIEW_DIR = ROOT / "data" / "reviews"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

PATIENT_ID_PATTERN = re.compile(r"^P\d{3}$")


def _validate_patient_id(patient_id: str) -> str:
    if not PATIENT_ID_PATTERN.match(patient_id):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid patient_id format: '{patient_id}'. Expected P001, P002, etc.",
        )
    return patient_id


def _review_path(patient_id: str) -> Path:
    return REVIEW_DIR / f"{patient_id}_review.json"


def _load_review(patient_id: str) -> dict:
    path = _review_path(patient_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "patient_id": patient_id,
        "summary_status": "draft",
        "confirmed_at": None,
        "reviewer": None,
        "claim_reviews": {},
        "feedback": [],
    }


def _save_review(patient_id: str, data: dict) -> None:
    path = _review_path(patient_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ClaimReviewRequest(BaseModel):
    claim_id: str
    section_id: str
    claim_text: str
    action: Literal["approved", "edited", "needs_review"]
    new_text: str | None = None


class SummaryStatusRequest(BaseModel):
    status: Literal["draft", "confirmed"]
    reviewer: str | None = None


class FeedbackRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Feedback text must not be empty")
        return v.strip()


@router.get("/review/{patient_id}")
def get_review(patient_id: str):
    _validate_patient_id(patient_id)
    data = _load_review(patient_id)
    _save_review(patient_id, data)
    return data


@router.post("/review/{patient_id}/claim")
def post_claim_review(patient_id: str, body: ClaimReviewRequest):
    _validate_patient_id(patient_id)
    data = _load_review(patient_id)
    data["claim_reviews"][body.claim_id] = {
        "claim_id": body.claim_id,
        "section_id": body.section_id,
        "claim_text": body.claim_text,
        "action": body.action,
        "new_text": body.new_text,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_review(patient_id, data)
    return {"ok": True}


@router.post("/review/{patient_id}/summary")
def post_summary_status(patient_id: str, body: SummaryStatusRequest):
    _validate_patient_id(patient_id)
    data = _load_review(patient_id)
    data["summary_status"] = body.status
    if body.status == "confirmed":
        data["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        data["reviewer"] = body.reviewer
    else:
        data["confirmed_at"] = None
    _save_review(patient_id, data)
    return {"ok": True, "status": body.status, "confirmed_at": data["confirmed_at"]}


@router.post("/review/{patient_id}/feedback")
def post_feedback(patient_id: str, body: FeedbackRequest):
    _validate_patient_id(patient_id)
    data = _load_review(patient_id)
    data["feedback"].append({
        "text": body.text,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    _save_review(patient_id, data)
    return {"ok": True}
