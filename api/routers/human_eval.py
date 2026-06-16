"""Human evaluation rubric API — store per-patient rubric scores with summary metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter()

ROOT = Path(__file__).parent.parent.parent
HUMAN_EVAL_DIR = ROOT / "data" / "human_eval"
HUMAN_EVAL_DIR.mkdir(parents=True, exist_ok=True)

PATIENT_ID_PATTERN = re.compile(r"^P\d{3}$")

CRITERIA = [
    "clinical_correctness",
    "completeness",
    "citation_faithfulness",
    "safety",
    "temporal_correctness",
    "readability",
]

WEIGHTS: dict[str, float] = {
    "clinical_correctness": 0.25,
    "completeness": 0.20,
    "citation_faithfulness": 0.20,
    "safety": 0.20,
    "temporal_correctness": 0.10,
    "readability": 0.05,
}

VALID_ERROR_CATEGORIES = {
    "omission",
    "commission",
    "wrong_source",
    "partial_citation",
    "no_source",
    "temporal_error",
    "safety_error",
    "readability_issue",
}


def _validate_patient_id(patient_id: str) -> str:
    if not PATIENT_ID_PATTERN.match(patient_id):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid patient_id: '{patient_id}'. Expected P001..P999.",
        )
    return patient_id


def _eval_path(patient_id: str) -> Path:
    return HUMAN_EVAL_DIR / f"{patient_id}_human_eval.json"


def _default_eval(patient_id: str) -> dict:
    return {
        "patient_id": patient_id,
        "summary_generated_at": None,
        "model": None,
        "prompt_version": None,
        "evaluator": None,
        "evaluated_at": None,
        "scores": {c: {"score": None, "notes": ""} for c in CRITERIA},
        "overall_notes": "",
        "error_categories": [],
        "weighted_score": None,
    }


def _load_eval(patient_id: str) -> dict:
    path = _eval_path(patient_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return _default_eval(patient_id)


def _save_eval(patient_id: str, data: dict) -> None:
    path = _eval_path(patient_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _compute_weighted_score(scores: dict) -> float | None:
    total = 0.0
    for criterion, weight in WEIGHTS.items():
        s = scores.get(criterion, {}).get("score")
        if s is None:
            return None
        total += float(s) * weight
    return round(total, 3)


class CriterionScore(BaseModel):
    score: int = Field(ge=1, le=5)
    notes: str = ""


class HumanEvalSubmit(BaseModel):
    evaluator: str
    summary_generated_at: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    scores: dict[str, CriterionScore]
    overall_notes: str = ""
    error_categories: list[str] = Field(default_factory=list)

    @field_validator("evaluator")
    @classmethod
    def evaluator_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Evaluator must not be empty")
        return v.strip()

    @field_validator("scores")
    @classmethod
    def validate_criteria_exact(cls, v: dict) -> dict:
        missing = [c for c in CRITERIA if c not in v]
        extra = [c for c in v if c not in CRITERIA]
        if missing:
            raise ValueError(f"Missing criteria: {missing}")
        if extra:
            raise ValueError(f"Unknown criteria: {extra}. Expected exactly: {CRITERIA}")
        return v

    @field_validator("error_categories")
    @classmethod
    def validate_error_categories(cls, v: list[str]) -> list[str]:
        invalid = [c for c in v if c not in VALID_ERROR_CATEGORIES]
        if invalid:
            raise ValueError(
                f"Invalid error categories: {invalid}. "
                f"Allowed: {sorted(VALID_ERROR_CATEGORIES)}"
            )
        return v


@router.get("/human-eval")
def list_human_evals():
    """Summary of all completed evaluations."""
    results = []
    for path in sorted(HUMAN_EVAL_DIR.glob("*_human_eval.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        results.append({
            "patient_id": data["patient_id"],
            "evaluator": data["evaluator"],
            "evaluated_at": data["evaluated_at"],
            "weighted_score": data["weighted_score"],
            "model": data.get("model"),
            "prompt_version": data.get("prompt_version"),
        })
    return {"evals": results}


@router.get("/human-eval/{patient_id}")
def get_human_eval(patient_id: str):
    _validate_patient_id(patient_id)
    return _load_eval(patient_id)


@router.post("/human-eval/{patient_id}")
def submit_human_eval(patient_id: str, body: HumanEvalSubmit):
    _validate_patient_id(patient_id)
    data = _default_eval(patient_id)
    data["summary_generated_at"] = body.summary_generated_at
    data["model"] = body.model
    data["prompt_version"] = body.prompt_version
    data["evaluator"] = body.evaluator
    data["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    data["scores"] = {k: v.model_dump() for k, v in body.scores.items()}
    data["overall_notes"] = body.overall_notes
    data["error_categories"] = body.error_categories
    data["weighted_score"] = _compute_weighted_score(data["scores"])
    _save_eval(patient_id, data)
    return {"ok": True, "weighted_score": data["weighted_score"]}
