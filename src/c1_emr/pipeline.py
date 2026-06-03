"""
C1 — EMR Integration: end-to-end processor.
validate -> deidentify -> normalize -> return safe EHR
"""

from __future__ import annotations
import json
from pathlib import Path

from src.c1_emr.validator import validate_ehr
from src.c1_emr.deidentifier import deidentify
from src.c1_emr.normalizer import normalize_ehr
from src.schemas import ValidationError


class C1ProcessingError(Exception):
    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s): {[e.message for e in errors]}")


def process_ehr(raw_ehr: dict) -> dict:
    """
    Full C1 pipeline:
      1. Validate schema
      2. De-identify PII
      3. Normalize abbreviations
    Returns safe, normalized EHR dict.
    Raises C1ProcessingError on blocking validation errors.
    """
    ok, errors = validate_ehr(raw_ehr)
    if not ok:
        raise C1ProcessingError([e for e in errors if e.severity == "error"])

    safe = deidentify(raw_ehr)
    normalized = normalize_ehr(safe)
    return normalized


def load_and_process(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return process_ehr(raw)
