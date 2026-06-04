"""Tests for C1 EMR Integration (validator, deidentifier, normalizer)."""

import json
import pytest
from pathlib import Path

from src.c1_emr.validator import validate_ehr
from src.c1_emr.deidentifier import deidentify, is_deidentified
from src.c1_emr.normalizer import normalize_text, normalize_ehr

ROOT = Path(__file__).parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"


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


@pytest.fixture
def pii_ehr():
    """EHR with all PII field types populated — used for deidentifier tests."""
    return {
        "patient_id": "P_TEST",
        "patient": {
            "patient_id": "P_TEST",
            "full_name": "Nguyen Van Test",
            "date_of_birth": "1969-01-15",
            "age": 55,
            "gender": "male",
            "citizen_id": "001069123456",
            "insurance_id": "0123456789",
            "phone": "0912345678",
            "address": "Số 5 Nguyễn Trãi, Phường Bến Thành, Quận 1, Thành phố Hồ Chí Minh",
            "occupation": "Công chức",
        },
        "allergies": [
            {
                "allergy_id": "A1",
                "patient_id": "P_TEST",
                "substance": "Penicillin",
                "data_note": "EC-03: test annotation for synthetic data",
            }
        ],
        "encounters": [
            {
                "encounter_id": "P_TEST-E001",
                "patient_id": "P_TEST",
                "encounter_date": "2024-01-10",
                "labs": [],
                "medications": [
                    {
                        "medication_id": "M1",
                        "drug_name": "Metformin",
                        "data_note": "EC-01: dose intentionally missing",
                    }
                ],
                "diagnoses": [],
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
        assert ok
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

    # --- Full-redact fields ---

    def test_citizen_id_redacted(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["citizen_id"] == "[REDACTED]"

    def test_insurance_id_redacted(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["insurance_id"] == "[REDACTED]"

    def test_phone_redacted(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["phone"] == "[REDACTED]"

    def test_citizen_id_inline(self):
        ehr = {"patient_id": "P1", "patient": {"citizen_id": "012345678901"}}
        assert deidentify(ehr)["patient"]["citizen_id"] == "[REDACTED]"

    def test_insurance_id_inline(self):
        ehr = {"patient_id": "P1", "patient": {"insurance_id": "GD4030000012345"}}
        assert deidentify(ehr)["patient"]["insurance_id"] == "[REDACTED]"

    def test_phone_inline(self):
        ehr = {"patient_id": "P1", "patient": {"phone": "0912345678"}}
        assert deidentify(ehr)["patient"]["phone"] == "[REDACTED]"

    # --- Year-only masking ---

    def test_date_of_birth_year_only(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["date_of_birth"] == "1969"

    def test_date_of_birth_various_formats(self):
        for dob, expected in [
            ("1969-01-15", "1969"),
            ("1974-03-20", "1974"),
            ("1962/05/10", "1962"),
            ("2001",       "2001"),
        ]:
            ehr = {"patient_id": "P1", "patient": {"date_of_birth": dob}}
            assert deidentify(ehr)["patient"]["date_of_birth"] == expected, f"Failed for {dob}"

    def test_date_of_birth_none_handled(self):
        ehr = {"patient_id": "P1", "patient": {"date_of_birth": None}}
        result = deidentify(ehr)
        assert result["patient"]["date_of_birth"] == "[REDACTED]"

    # --- Partial address masking ---

    def test_address_keeps_district_province(self, pii_ehr):
        result = deidentify(pii_ehr)
        addr = result["patient"]["address"]
        assert "Quận 1" in addr
        assert "Thành phố Hồ Chí Minh" in addr
        assert "Số 5" not in addr
        assert "Nguyễn Trãi" not in addr

    def test_address_single_token_fallback(self):
        ehr = {"patient_id": "P1", "patient": {"address": "Hà Nội"}}
        result = deidentify(ehr)
        assert result["patient"]["address"] == "Hà Nội"

    def test_address_two_tokens(self):
        ehr = {"patient_id": "P1", "patient": {"address": "Quận Cầu Giấy, Hà Nội"}}
        result = deidentify(ehr)
        assert result["patient"]["address"] == "Quận Cầu Giấy, Hà Nội"

    # --- Strip metadata fields ---

    def test_data_note_stripped_from_allergy(self, pii_ehr):
        result = deidentify(pii_ehr)
        allergy = result["allergies"][0]
        assert "data_note" not in allergy

    def test_data_note_stripped_from_medication(self, pii_ehr):
        result = deidentify(pii_ehr)
        med = result["encounters"][0]["medications"][0]
        assert "data_note" not in med

    def test_data_note_key_absent_not_error(self):
        """data_note key doesn't exist → should not raise."""
        ehr = {"patient_id": "P1", "patient": {"full_name": "Test"}, "allergies": [], "encounters": []}
        result = deidentify(ehr)
        assert result["patient"]["full_name"] == "Test"

    # --- Preserved fields ---

    def test_full_name_preserved(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["full_name"] == "Nguyen Van Test"

    def test_age_preserved(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["age"] == 55

    def test_gender_preserved(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["patient"]["gender"] == "male"

    def test_clinical_substance_preserved(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["allergies"][0]["substance"] == "Penicillin"

    def test_drug_name_preserved(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert result["encounters"][0]["medications"][0]["drug_name"] == "Metformin"

    # --- Immutability ---

    def test_does_not_mutate_input(self, pii_ehr):
        original_cid = pii_ehr["patient"]["citizen_id"]
        _ = deidentify(pii_ehr)
        assert pii_ehr["patient"]["citizen_id"] == original_cid

    # --- Nested PII ---

    def test_nested_pii_in_encounter_patient_object(self):
        ehr = {
            "patient_id": "P1",
            "patient": {"citizen_id": "111111111111"},
            "encounters": [{"encounter_id": "E1", "patient": {"insurance_id": "GD123"}}],
            "allergies": [],
        }
        result = deidentify(ehr)
        assert result["patient"]["citizen_id"] == "[REDACTED]"
        assert result["encounters"][0]["patient"]["insurance_id"] == "[REDACTED]"

    # --- Real data: P001 assembled file ---

    def test_p001_all_pii_fields_deidentified(self, valid_ehr):
        result = deidentify(valid_ehr)
        patient = result["patient"]
        assert patient.get("citizen_id") == "[REDACTED]"
        assert patient.get("insurance_id") == "[REDACTED]"
        assert patient.get("phone") == "[REDACTED]"
        # date_of_birth should be year only
        dob = patient.get("date_of_birth")
        if dob:
            assert len(dob) == 4 and dob.isdigit(), f"Expected YYYY got: {dob}"

    def test_p001_address_partially_masked(self, valid_ehr):
        result = deidentify(valid_ehr)
        addr = result["patient"].get("address", "")
        # Should keep province/city-level info
        assert addr != ""
        # Should not contain house numbers (single digits at start of address)
        raw_addr = valid_ehr["patient"].get("address", "")
        if raw_addr and "," in raw_addr:
            assert result["patient"]["address"] != raw_addr

    def test_p001_patient_id_unchanged(self, valid_ehr):
        result = deidentify(valid_ehr)
        assert result["patient_id"] == valid_ehr["patient_id"]

    def test_p001_data_notes_stripped(self, valid_ehr):
        result = deidentify(valid_ehr)
        text = str(result)
        assert "data_note" not in text


# ---------------------------------------------------------------------------
# is_deidentified() tests
# ---------------------------------------------------------------------------

class TestIsDeidentified:
    def test_false_when_cccd_present(self):
        ehr = {"patient": {"citizen_id": "001069123456"}}
        assert is_deidentified(ehr) is False

    def test_false_when_phone_present(self):
        ehr = {"patient": {"phone": "0912345678"}}
        assert is_deidentified(ehr) is False

    def test_false_when_bhyt_present(self):
        ehr = {"patient": {"insurance_id": "GD4030000012345"}}
        assert is_deidentified(ehr) is False

    def test_true_after_deidentify(self, pii_ehr):
        result = deidentify(pii_ehr)
        assert is_deidentified(result) is True

    def test_true_for_minimal_ehr(self, minimal_ehr):
        result = deidentify(minimal_ehr)
        assert is_deidentified(result) is True

    def test_true_for_p001_after_deidentify(self, valid_ehr):
        result = deidentify(valid_ehr)
        assert is_deidentified(result) is True

    def test_false_for_p001_raw(self, valid_ehr):
        assert is_deidentified(valid_ehr) is False


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
        text = "THAY the thuoc"
        result = normalize_text(text)
        assert "THAY" in result
        assert "tăng huyết áp" not in result

    def test_multiple_abbrevs_in_one_text(self):
        text = "BN THA + ĐTĐ, RLLPM"
        result = normalize_text(text)
        assert result != text

    def test_normalize_ehr_does_not_crash(self, valid_ehr):
        result = normalize_ehr(valid_ehr)
        assert "encounters" in result
        assert len(result["encounters"]) == len(valid_ehr["encounters"])

    def test_icd10_not_expanded(self):
        text = "Chan doan: E11 - DTD type 2"
        result = normalize_text(text)
        assert "E11" in result

    def test_empty_text_returns_empty(self):
        assert normalize_text("") == ""
        assert normalize_text(None) is None
