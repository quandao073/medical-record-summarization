"""
C1 — EMR Integration: end-to-end processor.
validate -> deidentify -> normalize -> return safe EHR
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from src.c1_emr.validator import validate_ehr
from src.c1_emr.deidentifier import deidentify
from src.c1_emr.normalizer import normalize_ehr
from src.schemas import ValidationError


class C1ProcessingError(Exception):
    def __init__(self, errors: list[ValidationError], context: dict | None = None):
        self.errors = errors
        self.context = context or {}

        error_msgs = [f"{e.field}: {e.message}" for e in errors]
        msg = f"{len(errors)} validation error(s):\n" + "\n".join(error_msgs)

        if self.context:
            msg += f"\nContext: {self.context}"

        super().__init__(msg)


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
    """Load EHR file with comprehensive error handling."""
    path = Path(path)
    context = {"file": str(path)}

    if not path.exists():
        raise C1ProcessingError(
            [ValidationError(
                field="file",
                message="EHR file not found",
                severity="error",
            )],
            context={"path": str(path), "cwd": str(Path.cwd())},
        )

    if not os.access(path, os.R_OK):
        raise C1ProcessingError(
            [ValidationError(
                field="file",
                message="Permission denied",
                severity="error",
            )],
            context={"path": str(path)},
        )

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise C1ProcessingError(
            [ValidationError(
                field="json",
                message=f"Invalid JSON at line {e.lineno}, col {e.colno}",
                severity="error",
            )],
            context={"path": str(path), "line": e.lineno, "column": e.colno, "error": str(e)},
        )
    except UnicodeDecodeError as e:
        raise C1ProcessingError(
            [ValidationError(
                field="encoding",
                message="File encoding is not UTF-8",
                severity="error",
            )],
            context={"path": str(path), "error": str(e)},
        )

    try:
        return process_ehr(raw)
    except C1ProcessingError as e:
        e.context.update(context)
        raise


async def process_ehr_from_db(session, patient_id: str) -> dict:
    """
    Full C1 pipeline reading from database:
      1. Assemble from DB
      2. Validate
      3. De-identify
      4. Normalize
    Returns safe, normalized EHR dict.
    """
    from src.c1_emr.assembler import assemble_from_db

    raw_ehr = await assemble_from_db(session, patient_id)
    if raw_ehr is None:
        raise C1ProcessingError(
            [ValidationError(field="patient_id", message=f"Patient {patient_id} not found in database")],
            context={"patient_id": patient_id, "source": "database"},
        )

    return process_ehr(raw_ehr)
