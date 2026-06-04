"""Tests for C3 — Section-wise Retrieval."""

import pytest
from src.schemas import SourceChunk
from src.c3_retrieval.retriever import (
    retrieve_for_section,
    SECTION_SOURCE_TYPES,
    _latest_encounter_ids,
    _filter_latest_encounter,
)


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


# ---------------------------------------------------------------------------
# Latest-encounter filtering helpers
# ---------------------------------------------------------------------------

class TestLatestEncounterIds:
    def test_returns_latest_encounter_id(self):
        chunks = [
            _chunk("E001-LAB", "labs", date="2024-01-10", encounter_id="E001"),
            _chunk("E002-LAB", "labs", date="2024-04-10", encounter_id="E002"),
            _chunk("E003-LAB", "labs", date="2024-10-10", encounter_id="E003"),
        ]
        # Patch encounter_id directly
        chunks[0] = chunks[0].model_copy(update={"encounter_id": "E001"})
        chunks[1] = chunks[1].model_copy(update={"encounter_id": "E002"})
        chunks[2] = chunks[2].model_copy(update={"encounter_id": "E003"})
        result = _latest_encounter_ids(chunks)
        assert result == {"E003"}

    def test_ties_include_all_same_date_encounters(self):
        chunks = [
            _chunk("A", "labs", date="2024-10-10"),
            _chunk("B", "labs", date="2024-10-10"),
        ]
        chunks[0] = chunks[0].model_copy(update={"encounter_id": "E001"})
        chunks[1] = chunks[1].model_copy(update={"encounter_id": "E002"})
        result = _latest_encounter_ids(chunks)
        assert result == {"E001", "E002"}

    def test_returns_empty_for_no_chunks(self):
        assert _latest_encounter_ids([]) == set()

    def test_chunks_without_encounter_id_ignored(self):
        chunks = [_chunk("X", "labs", date="2024-01-10")]
        chunks[0] = chunks[0].model_copy(update={"encounter_id": None})
        result = _latest_encounter_ids(chunks)
        assert result == set()


class TestFilterLatestEncounter:
    def _make_multi_encounter_chunks(self):
        e1 = _chunk("E001-MED", "medications", date="2024-01-10")
        e2 = _chunk("E002-MED", "medications", date="2024-04-10")
        e3 = _chunk("E003-MED", "medications", date="2024-10-10")
        e1 = e1.model_copy(update={"encounter_id": "E001"})
        e2 = e2.model_copy(update={"encounter_id": "E002"})
        e3 = e3.model_copy(update={"encounter_id": "E003"})
        return [e1, e2, e3]

    def test_keeps_only_latest_encounter(self):
        chunks = self._make_multi_encounter_chunks()
        result = _filter_latest_encounter(chunks)
        assert all(c.encounter_id == "E003" for c in result)
        assert len(result) == 1

    def test_fallback_to_all_when_no_encounter_id(self):
        chunks = [
            _chunk("A", "allergies", date="2021-01-01"),
            _chunk("B", "allergies", date="2022-01-01"),
        ]
        for i, c in enumerate(chunks):
            chunks[i] = c.model_copy(update={"encounter_id": None})
        result = _filter_latest_encounter(chunks)
        assert len(result) == 2

    def test_chunks_without_encounter_id_always_kept(self):
        """patient_info and allergy chunks (no encounter_id) survive the filter."""
        enc_chunk = _chunk("E003-MED", "medications", date="2024-10-10")
        enc_chunk = enc_chunk.model_copy(update={"encounter_id": "E003"})
        no_enc = _chunk("ALLERGY-X", "allergies", date="2020-01-01")
        no_enc = no_enc.model_copy(update={"encounter_id": None})

        result = _filter_latest_encounter([enc_chunk, no_enc])
        ids = [c.source_id for c in result]
        assert "ALLERGY-X" in ids

    def test_empty_returns_empty(self):
        assert _filter_latest_encounter([]) == []


# ---------------------------------------------------------------------------
# Latest-encounter applied to sections
# ---------------------------------------------------------------------------

class TestLatestEncounterSections:

    def _multi_enc_meds(self):
        """3 encounters, each with Metformin is_current=True."""
        chunks = []
        for enc, date in [("E001", "2024-01-10"), ("E002", "2024-04-10"), ("E003", "2024-10-10")]:
            c = _chunk(f"P001-{enc}-MED-MET", "medications", date=date,
                       drug_name="Metformin", is_current=True)
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        return chunks

    def _multi_enc_labs(self):
        """HbA1c across 3 encounters: 9.2% (E001), 8.1% (E002), 7.1% (E003)."""
        chunks = []
        for enc, date, val in [("E001", "2024-01-10", 9.2),
                                ("E002", "2024-04-10", 8.1),
                                ("E003", "2024-10-10", 7.1)]:
            c = _chunk(f"P001-{enc}-LAB-HBA1C", "labs", date=date,
                       test_name="HbA1c", value=val, is_abnormal=True, is_critical=False)
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        return chunks

    def test_current_medications_only_latest_encounter(self):
        chunks = self._multi_enc_meds()
        result = retrieve_for_section(chunks, "current_medications")
        enc_ids = {c.encounter_id for c in result}
        assert enc_ids == {"E003"}, f"Expected only E003, got {enc_ids}"

    def test_abnormal_labs_includes_last_2_encounters_for_trend(self):
        """abnormal_labs uses n=2 encounters so LabsTable can show trend."""
        chunks = self._multi_enc_labs()
        result = retrieve_for_section(chunks, "abnormal_labs")
        enc_ids = {c.encounter_id for c in result}
        # Should include latest 2 (E002, E003), not the oldest (E001)
        assert "E001" not in enc_ids, "Oldest encounter should be excluded"
        assert "E003" in enc_ids, "Latest encounter must be included"
        assert len(enc_ids) <= 2, f"At most 2 encounters, got {enc_ids}"

    def test_diagnoses_only_latest_encounter(self):
        chunks = []
        for enc, date in [("E001", "2024-01-10"), ("E003", "2024-10-10")]:
            c = _chunk(f"P001-{enc}-DX-E11", "diagnoses", date=date,
                       icd10_code="E11", diagnosis_name="ĐTĐ type 2")
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        result = retrieve_for_section(chunks, "diagnoses")
        enc_ids = {c.encounter_id for c in result}
        assert enc_ids == {"E003"}

    def test_treatment_timeline_keeps_all_encounters(self):
        """treatment_timeline must have ALL encounters for historical view."""
        chunks = []
        for enc, date in [("E001", "2024-01-10"), ("E002", "2024-04-10"), ("E003", "2024-10-10")]:
            c = _chunk(f"P001-{enc}-LAB-HBA1C", "labs", date=date,
                       test_name="HbA1c", is_abnormal=True)
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        result = retrieve_for_section(chunks, "treatment_timeline")
        enc_ids = {c.encounter_id for c in result}
        assert enc_ids == {"E001", "E002", "E003"}

    def test_clinical_alerts_labs_latest_only(self):
        """clinical_alerts: lab chunks should come from latest encounter only."""
        chunks = []
        for enc, date, val in [("E001", "2024-01-10", 9.2),
                                ("E003", "2024-10-10", 7.1)]:
            c = _chunk(f"P001-{enc}-LAB-HBA1C", "labs", date=date,
                       test_name="HbA1c", value=val, is_abnormal=True)
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        result = retrieve_for_section(chunks, "clinical_alerts")
        lab_chunks = [c for c in result if c.source_type == "labs"]
        enc_ids = {c.encounter_id for c in lab_chunks}
        assert "E001" not in enc_ids, "Old lab from E001 should not be in clinical_alerts"
        assert "E003" in enc_ids

    def test_clinical_alerts_allergies_always_included(self):
        """Allergies in clinical_alerts must survive regardless of encounter date."""
        allergy = _chunk("ALLERGY-PEN", "allergies", date="2021-01-01")
        allergy = allergy.model_copy(update={"encounter_id": None})
        lab_old = _chunk("E001-LAB", "labs", date="2024-01-10", is_abnormal=True)
        lab_old = lab_old.model_copy(update={"encounter_id": "E001"})
        lab_new = _chunk("E003-LAB", "labs", date="2024-10-10", is_abnormal=True)
        lab_new = lab_new.model_copy(update={"encounter_id": "E003"})

        result = retrieve_for_section([allergy, lab_old, lab_new], "clinical_alerts")
        ids = [c.source_id for c in result]
        assert "ALLERGY-PEN" in ids
