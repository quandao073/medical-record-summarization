"""
C1 — EMR Integration: Schema Validator.
Validates assembled EHR JSON before it enters the pipeline.
"""

from __future__ import annotations
import sys
import json
from pathlib import Path
from src.schemas import ValidationError


REQUIRED_PATIENT_FIELDS = ["patient_id", "full_name", "gender"]
REQUIRED_ENCOUNTER_FIELDS = ["encounter_id", "patient_id", "encounter_date"]


def validate_ehr(ehr: dict) -> tuple[bool, list[ValidationError]]:
    """
    Validate assembled EHR dict.
    Returns (is_valid, errors). Errors with severity='error' block the pipeline.
    """
    errors: list[ValidationError] = []

    # Top-level structure
    if "patient_id" not in ehr:
        errors.append(ValidationError(field="patient_id", message="Missing patient_id at root"))
    if "patient" not in ehr:
        errors.append(ValidationError(field="patient", message="Missing patient block"))
    if "encounters" not in ehr:
        errors.append(ValidationError(field="encounters", message="Missing encounters array"))

    if errors:
        return False, errors

    # Patient fields
    patient = ehr["patient"]
    for field in REQUIRED_PATIENT_FIELDS:
        if not patient.get(field):
            errors.append(ValidationError(
                field=f"patient.{field}",
                message=f"Missing or empty required field: {field}",
            ))

    # Encounters
    encounters = ehr.get("encounters", [])
    if not encounters:
        errors.append(ValidationError(
            field="encounters",
            message="No encounters found — cannot generate summary",
        ))

    seen_encounter_ids: set[str] = set()
    for i, enc in enumerate(encounters):
        prefix = f"encounters[{i}]"

        for field in REQUIRED_ENCOUNTER_FIELDS:
            if not enc.get(field):
                errors.append(ValidationError(
                    field=f"{prefix}.{field}",
                    message=f"Missing required field in encounter: {field}",
                ))

        eid = enc.get("encounter_id", "")
        if eid in seen_encounter_ids:
            errors.append(ValidationError(
                field=f"{prefix}.encounter_id",
                message=f"Duplicate encounter_id: {eid}",
            ))
        seen_encounter_ids.add(eid)

        # Warn on encounters with no clinical data at all
        has_data = any([
            enc.get("labs"), enc.get("medications"), enc.get("diagnoses"),
            enc.get("clinical_notes"), enc.get("vitals"),
        ])
        if not has_data:
            errors.append(ValidationError(
                field=f"{prefix}",
                message="Encounter has no clinical data (labs/meds/diagnoses/notes/vitals)",
                severity="warning",
            ))

        # Warn on medications missing dose
        for j, med in enumerate(enc.get("medications", [])):
            if not med.get("dose") and not med.get("strength"):
                errors.append(ValidationError(
                    field=f"{prefix}.medications[{j}]",
                    message=f"Medication '{med.get('drug_name', '?')}' missing dose and strength",
                    severity="warning",
                ))

        # Warn on labs missing unit
        for j, lab in enumerate(enc.get("labs", [])):
            if not lab.get("unit"):
                errors.append(ValidationError(
                    field=f"{prefix}.labs[{j}]",
                    message=f"Lab '{lab.get('test_name', '?')}' missing unit",
                    severity="warning",
                ))

    blocking_errors = [e for e in errors if e.severity == "error"]
    return len(blocking_errors) == 0, errors


def validate_ehr_file(path: str | Path) -> tuple[bool, list[ValidationError]]:
    with open(path, encoding="utf-8") as f:
        ehr = json.load(f)
    return validate_ehr(ehr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.c1_emr.validator <ehr.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    ok, errs = validate_ehr_file(path)
    blocking = [e for e in errs if e.severity == "error"]
    warnings = [e for e in errs if e.severity == "warning"]

    print(f"Valid: {ok} | Errors: {len(blocking)} | Warnings: {len(warnings)}")
    for e in errs:
        tag = "[ERR ]" if e.severity == "error" else "[WARN]"
        print(f"  {tag} {e.field}: {e.message}")
