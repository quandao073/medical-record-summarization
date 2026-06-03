"""Tests for C1 EMR Integration (validator, deidentifier, normalizer)."""

import json
import pytest
from pathlib import Path

from src.c1_emr.validator import validate_ehr
from src.c1_emr.deidentifier import deidentify, is_deidentified
from src.c1_emr.normalizer import normalize_text, normalize_ehr

ROOT = Path(__file__).parent.parent
ASSEMBLED_DIR = ROOT / "data" / "medical_summarization" / "assembled"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_ehr():
    path = ASSEMBLED_DIR / "P001.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def minimal_ehr():
    return {
        "patient_id": "TEST001",
        "patient": {
            "patient_id": "TEST001",
            "full_name": "Nguyen Van Test",
            "gender": "Nam",
        },
        "allergies": [],
        "encounters": [
            {
                "encounter_id": "TEST001-E001",
                "patient_id": "TEST001",
                "encounter_date": "2024-01-01",
                "encounter_type": "outpatient",
                "labs": [{"lab_id": "L1", "patient_id": "TEST001", "encounter_id": "TEST001-E001",
                           "test_code": "HBA1C", "test_name": "HbA1c", "value": 8.5, "unit": "%",
                           "abnormal": True}],
                "medications": [],
                "diagnoses": [{"diagnosis_id": "D1", "patient_id": "TEST001",
                               "encounter_id": "TEST001-E001", "icd10_code": "E11",
                               "diagnosis_name": "DTD type 2"}],
                "vitals": [],
                "clinical_notes": [],
                "imaging": [],
                "procedures": [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_p001_passes(self, valid_ehr):
        ok, errors = validate_ehr(valid_ehr)
        blocking = [e for e in errors if e.severity == "error"]
        assert ok, f"P001 should be valid but got: {blocking}"

    def test_missing_patient_id_fails(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        del ehr["patient_id"]
        ok, errors = validate_ehr(ehr)
        assert not ok
        assert any("patient_id" in e.field for e in errors)

    def test_missing_encounters_fails(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        del ehr["encounters"]
        ok, errors = validate_ehr(ehr)
        assert not ok

    def test_empty_encounters_fails(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        ehr["encounters"] = []
        ok, errors = validate_ehr(ehr)
        assert not ok
        assert any("encounters" in e.field for e in errors)

    def test_missing_encounter_date_fails(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        ehr["encounters"][0] = {k: v for k, v in ehr["encounters"][0].items()
                                if k != "encounter_date"}
        ok, errors = validate_ehr(ehr)
        assert not ok

    def test_duplicate_encounter_id_fails(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        ehr["encounters"] = [ehr["encounters"][0], dict(ehr["encounters"][0])]
        ok, errors = validate_ehr(ehr)
        # Should produce a blocking error for duplicate encounter_id
        blocking = [e for e in errors if e.severity == "error"]
        assert any("Duplicate" in e.message for e in blocking)

    def test_medication_missing_dose_is_warning(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        ehr["encounters"][0]["medications"] = [{
            "medication_id": "M1", "patient_id": "TEST001",
            "encounter_id": "TEST001-E001", "drug_name": "Metformin",
            "dose": None, "strength": None,
        }]
        ok, errors = validate_ehr(ehr)
        warnings = [e for e in errors if e.severity == "warning"]
        assert ok  # warnings don't block
        assert any("dose" in e.message.lower() or "strength" in e.message.lower()
                   for e in warnings)

    def test_lab_missing_unit_is_warning(self, minimal_ehr):
        ehr = dict(minimal_ehr)
        ehr["encounters"][0]["labs"][0]["unit"] = None
        ok, errors = validate_ehr(ehr)
        warnings = [e for e in errors if e.severity == "warning"]
        assert any("unit" in e.message.lower() for e in warnings)


# ---------------------------------------------------------------------------
# Deidentifier tests
# ---------------------------------------------------------------------------

class TestDeidentifier:
    def test_citizen_id_redacted(self):
        ehr = {"patient_id": "P1", "patient": {"citizen_id": "012345678901"}}
        result = deidentify(ehr)
        assert result["patient"]["citizen_id"] == "[REDACTED]"

    def test_insurance_id_redacted(self):
        ehr = {"patient_id": "P1", "patient": {"insurance_id": "GD4030000012345"}}
        result = deidentify(ehr)
        assert result["patient"]["insurance_id"] == "[REDACTED]"

    def test_phone_redacted(self):
        ehr = {"patient_id": "P1", "patient": {"phone": "0912345678"}}
        result = deidentify(ehr)
        assert result["patient"]["phone"] == "[REDACTED]"

    def test_full_name_preserved(self):
        ehr = {"patient_id": "P1", "patient": {"full_name": "Nguyen Van A"}}
        result = deidentify(ehr)
        assert result["patient"]["full_name"] == "Nguyen Van A"

    def test_does_not_mutate_input(self):
        ehr = {"patient_id": "P1", "patient": {"citizen_id": "123456789012"}}
        _ = deidentify(ehr)
        assert ehr["patient"]["citizen_id"] == "123456789012"

    def test_p001_already_redacted_passes(self, valid_ehr):
        # Seed data already has REDACTED — deidentifier should not break it
        result = deidentify(valid_ehr)
        assert result["patient_id"] == valid_ehr["patient_id"]

    def test_nested_pii_redacted(self):
        ehr = {
            "patient_id": "P1",
            "patient": {"citizen_id": "111111111111"},
            "encounters": [{"encounter_id": "E1", "patient": {"insurance_id": "GD123"}}],
        }
        result = deidentify(ehr)
        assert result["patient"]["citizen_id"] == "[REDACTED]"
        assert result["encounters"][0]["patient"]["insurance_id"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------

class TestNormalizer:
    def test_tha_expanded(self):
        result = normalize_text("BN bị THA 5 năm")
        assert "tăng huyết áp" in result or "tang huyet ap" in result.lower()

    def test_dtd_expanded(self):
        result = normalize_text("ĐTĐ type 2 phát hiện 2021")
        assert "đái tháo đường" in result or "dai thao duong" in result.lower()

    def test_partial_word_not_replaced(self):
        # 'THA' inside 'THAY' should not be replaced
        text = "THAY the thuoc"
        result = normalize_text(text)
        assert "THAY" in result  # unchanged
        assert "tăng huyết áp" not in result

    def test_multiple_abbrevs_in_one_text(self):
        text = "BN THA + ĐTĐ, RLLPM"
        result = normalize_text(text)
        # At least some abbreviations should be expanded
        assert result != text

    def test_normalize_ehr_does_not_crash(self, valid_ehr):
        result = normalize_ehr(valid_ehr)
        assert "encounters" in result
        assert len(result["encounters"]) == len(valid_ehr["encounters"])

    def test_icd10_not_expanded(self):
        # ICD-10 codes should NOT be in text fields that get normalized
        # This tests that the chunker (not normalizer) preserves ICD-10
        text = "Chan doan: E11 - DTD type 2"
        result = normalize_text(text)
        assert "E11" in result  # ICD-10 code preserved

    def test_empty_text_returns_empty(self):
        assert normalize_text("") == ""
        assert normalize_text(None) is None
