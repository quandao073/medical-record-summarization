"""Tests for C3 — Section-wise Retrieval."""

import pytest
from src.schemas import SourceChunk
from src.c3_retrieval.retriever import retrieve_for_section, SECTION_SOURCE_TYPES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _chunk(source_id: str, source_type: str, date: str = "2024-01-10", **meta) -> SourceChunk:
    return SourceChunk(
        source_id=source_id,
        source_type=source_type,
        patient_id="P001",
        date=date,
        content=f"Content for {source_id}",
        metadata=meta,
    )


@pytest.fixture
def mixed_chunks():
    return [
        _chunk("P001-E001-MED-A", "medications", "2024-01-10", drug_name="Metformin",  is_current=True),
        _chunk("P001-E001-MED-B", "medications", "2024-01-10", drug_name="Amlodipine", is_current=True),
        _chunk("P001-E002-MED-A", "medications", "2024-04-10", drug_name="Metformin",  is_current=False),
        _chunk("P001-E001-LAB-HBA1C",  "labs", "2024-01-10", test_name="HbA1c",       is_abnormal=True,  is_critical=False),
        _chunk("P001-E001-LAB-CREAT",  "labs", "2024-01-10", test_name="Creatinine",   is_abnormal=False, is_critical=False),
        _chunk("P001-E003-LAB-GLUC",   "labs", "2024-09-05", test_name="Glucose",      is_abnormal=True,  is_critical=True),
        _chunk("P001-E001-DX-E11",     "diagnoses", "2024-01-10", icd10_code="E11"),
        _chunk("P001-E002-DX-I10",     "diagnoses", "2024-04-10", icd10_code="I10"),
        _chunk("P001-E001-VIT001",     "vitals",    "2024-01-10"),
        _chunk("P001-ALLERGY-PEN",     "allergies", "2021-03-15"),
        _chunk("P001-NOTE-001",        "clinical_notes", "2024-01-10"),
        _chunk("P001-PAT-INFO",        "patient_info",   "2024-01-10"),
    ]


# ---------------------------------------------------------------------------
# Basic type filtering
# ---------------------------------------------------------------------------

class TestTypeFiltering:
    def test_current_medications_only_med_chunks(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "current_medications")
        assert all(c.source_type == "medications" for c in result)

    def test_abnormal_labs_only_lab_chunks(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "abnormal_labs")
        assert all(c.source_type == "labs" for c in result)

    def test_diagnoses_only_dx_chunks(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "diagnoses")
        assert all(c.source_type == "diagnoses" for c in result)

    def test_allergies_includes_allergy_chunks(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "allergies")
        types = {c.source_type for c in result}
        assert "allergies" in types

    def test_overview_includes_patient_info(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "overview")
        types = {c.source_type for c in result}
        assert "patient_info" in types

    def test_treatment_timeline_multi_type(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "treatment_timeline")
        types = {c.source_type for c in result}
        assert len(types) >= 2


# ---------------------------------------------------------------------------
# Special filters
# ---------------------------------------------------------------------------

class TestSpecialFilters:
    def test_abnormal_labs_excludes_normal(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "abnormal_labs")
        for c in result:
            assert c.metadata.get("is_abnormal") or c.metadata.get("is_critical"), \
                f"Normal lab {c.source_id} should be excluded"

    def test_abnormal_labs_includes_critical(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "abnormal_labs")
        ids = [c.source_id for c in result]
        assert "P001-E003-LAB-GLUC" in ids

    def test_current_medications_prefers_is_current_true(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "current_medications")
        for c in result:
            assert c.metadata.get("is_current") is True, \
                f"Non-current med {c.source_id} should be excluded when current ones exist"

    def test_current_medications_fallback_when_no_current(self):
        chunks = [
            _chunk("M1", "medications", is_current=False, drug_name="DrugA"),
            _chunk("M2", "medications", is_current=False, drug_name="DrugB"),
        ]
        result = retrieve_for_section(chunks, "current_medications")
        assert len(result) == 2  # fallback to all meds


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------

class TestSortOrder:
    def test_diagnoses_most_recent_first(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "diagnoses")
        dates = [c.date for c in result if c.date]
        assert dates == sorted(dates, reverse=True), "Diagnoses should be newest first"

    def test_treatment_timeline_chronological(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "treatment_timeline")
        dates = [c.date for c in result if c.date]
        assert dates == sorted(dates), "Timeline should be oldest first"

    def test_current_medications_most_recent_first(self):
        chunks = [
            _chunk("M_OLD", "medications", date="2024-01-10", is_current=True, drug_name="A"),
            _chunk("M_NEW", "medications", date="2024-10-10", is_current=True, drug_name="A"),
        ]
        result = retrieve_for_section(chunks, "current_medications")
        assert result[0].source_id == "M_NEW"


# ---------------------------------------------------------------------------
# Max chunks cap
# ---------------------------------------------------------------------------

class TestMaxChunks:
    def test_max_chunks_respected(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "treatment_timeline", max_chunks=3)
        assert len(result) <= 3

    def test_default_max_15(self):
        chunks = [_chunk(f"LAB-{i:02}", "labs", is_abnormal=True) for i in range(30)]
        result = retrieve_for_section(chunks, "abnormal_labs")
        assert len(result) <= 15

    def test_returns_all_when_below_max(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "allergies", max_chunks=15)
        # allergies section allows "allergies" + "clinical_notes"
        expected = [c for c in mixed_chunks if c.source_type in ("allergies", "clinical_notes")]
        assert len(result) == len(expected)


# ---------------------------------------------------------------------------
# Unknown section ID
# ---------------------------------------------------------------------------

class TestUnknownSection:
    def test_unknown_section_returns_all_up_to_max(self, mixed_chunks):
        result = retrieve_for_section(mixed_chunks, "unknown_section_xyz", max_chunks=5)
        assert len(result) == 5

    def test_known_sections_all_defined(self):
        for section_id in SECTION_SOURCE_TYPES:
            types = SECTION_SOURCE_TYPES[section_id]
            assert isinstance(types, list) and len(types) >= 1
