"""Tests for C3 — Section-wise Retrieval."""

import pytest
from src.schemas import SourceChunk
from src.c3_retrieval.retriever import (
    retrieve_for_section,
    SECTION_SOURCE_TYPES,
    _latest_encounter_ids,
    _filter_latest_encounter,
    _filter_latest_n_encounters,
    _dedup_diagnoses,
    _dedup_labs_with_unique,
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
# Deduplication helpers
# ---------------------------------------------------------------------------

class TestDedupDiagnoses:
    def test_dedup_by_icd_keeps_latest(self):
        chunks = [
            _chunk("E001-DX-E11", "diagnoses", date="2024-01-10", icd10_code="E11"),
            _chunk("E003-DX-E11", "diagnoses", date="2024-10-10", icd10_code="E11"),
        ]
        result = _dedup_diagnoses(chunks)
        assert len(result) == 1
        assert result[0].source_id == "E003-DX-E11"

    def test_dedup_preserves_unique_old_diagnoses(self):
        chunks = [
            _chunk("E001-DX-E05", "diagnoses", date="2024-02-05", icd10_code="E05.0"),
            _chunk("E001-DX-H06", "diagnoses", date="2024-02-05", icd10_code="H06.2"),
            _chunk("E001-DX-R00", "diagnoses", date="2024-02-05", icd10_code="R00.0"),
            _chunk("E003-DX-E05", "diagnoses", date="2024-08-05", icd10_code="E05.0"),
        ]
        result = _dedup_diagnoses(chunks)
        icds = {c.metadata["icd10_code"] for c in result}
        assert icds == {"E05.0", "H06.2", "R00.0"}
        # E05.0 should be the latest version
        e05 = [c for c in result if c.metadata["icd10_code"] == "E05.0"][0]
        assert e05.source_id == "E003-DX-E05"

    def test_dedup_empty(self):
        assert _dedup_diagnoses([]) == []


class TestDedupLabsWithUnique:
    def test_keeps_latest_2_encounters(self):
        chunks = [
            _chunk("E001-TSH", "labs", date="2024-02-05", test_name="TSH", is_abnormal=True),
            _chunk("E002-TSH", "labs", date="2024-05-05", test_name="TSH", is_abnormal=True),
            _chunk("E003-TSH", "labs", date="2024-08-05", test_name="TSH", is_abnormal=True),
        ]
        for i, enc in enumerate(["E001", "E002", "E003"]):
            chunks[i] = chunks[i].model_copy(update={"encounter_id": enc})

        result = _dedup_labs_with_unique(chunks, n_encounters=2)
        enc_ids = {c.encounter_id for c in result}
        assert "E002" in enc_ids
        assert "E003" in enc_ids
        assert "E001" not in enc_ids  # TSH already in E002/E003

    def test_preserves_unique_old_test(self):
        """TRAb only at E001 — must be preserved even with n=2."""
        chunks = [
            _chunk("E001-TRAB", "labs", date="2024-02-05", test_name="TRAb", is_abnormal=True),
            _chunk("E002-TSH", "labs", date="2024-05-05", test_name="TSH", is_abnormal=True),
            _chunk("E003-TSH", "labs", date="2024-08-05", test_name="TSH", is_abnormal=True),
        ]
        for i, enc in enumerate(["E001", "E002", "E003"]):
            chunks[i] = chunks[i].model_copy(update={"encounter_id": enc})

        result = _dedup_labs_with_unique(chunks, n_encounters=2)
        ids = {c.source_id for c in result}
        assert "E001-TRAB" in ids, "TRAb from E001 must be preserved"
        assert "E003-TSH" in ids
        assert "E002-TSH" in ids

    def test_does_not_preserve_normal_old_unique(self):
        """Old unique test that is NOT abnormal should NOT be preserved."""
        chunks = [
            _chunk("E001-TRAB", "labs", date="2024-02-05", test_name="TRAb", is_abnormal=False),
            _chunk("E002-TSH", "labs", date="2024-05-05", test_name="TSH", is_abnormal=True),
            _chunk("E003-TSH", "labs", date="2024-08-05", test_name="TSH", is_abnormal=True),
        ]
        for i, enc in enumerate(["E001", "E002", "E003"]):
            chunks[i] = chunks[i].model_copy(update={"encounter_id": enc})

        result = _dedup_labs_with_unique(chunks, n_encounters=2)
        ids = {c.source_id for c in result}
        assert "E001-TRAB" not in ids, "Normal TRAb should not be preserved"

    def test_empty(self):
        assert _dedup_labs_with_unique([]) == []


# ---------------------------------------------------------------------------
# Section-level encounter filtering
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

    def test_abnormal_labs_trend_plus_unique(self):
        """abnormal_labs: n=2 encounters for trend + unique tests from older encounters."""
        chunks = self._multi_enc_labs()
        result = retrieve_for_section(chunks, "abnormal_labs")
        enc_ids = {c.encounter_id for c in result}
        # HbA1c at all 3 encounters → only latest 2 (E002, E003)
        assert "E003" in enc_ids, "Latest encounter must be included"
        assert "E002" in enc_ids, "Previous encounter for trend"
        assert "E001" not in enc_ids, "Oldest HbA1c excluded (already in E002/E003)"

    def test_abnormal_labs_includes_one_time_diagnostic_test(self):
        """One-time diagnostic labs (e.g. TRAb at E001 only) must be retrieved."""
        chunks = [
            _chunk("E001-LAB-TRAB", "labs", date="2024-02-05",
                   test_name="TRAb", value=8.5, is_abnormal=True, is_critical=False),
            _chunk("E002-LAB-TSH", "labs", date="2024-05-05",
                   test_name="TSH", value=0.01, is_abnormal=True, is_critical=False),
            _chunk("E003-LAB-TSH", "labs", date="2024-08-05",
                   test_name="TSH", value=0.3, is_abnormal=True, is_critical=False),
        ]
        for i, enc in enumerate(["E001", "E002", "E003"]):
            chunks[i] = chunks[i].model_copy(update={"encounter_id": enc})

        result = retrieve_for_section(chunks, "abnormal_labs")
        ids = [c.source_id for c in result]
        assert "E001-LAB-TRAB" in ids, "One-time TRAb from E001 must be retrieved"

    def test_diagnoses_includes_all_unique_icd(self):
        """Diagnoses are cumulative — deduplicated by ICD, includes all unique codes."""
        chunks = [
            _chunk("E001-DX-E05", "diagnoses", date="2024-02-05",
                   icd10_code="E05.0", diagnosis_name="Basedow"),
            _chunk("E001-DX-H06", "diagnoses", date="2024-02-05",
                   icd10_code="H06.2", diagnosis_name="Exophthalmos"),
            _chunk("E001-DX-R00", "diagnoses", date="2024-02-05",
                   icd10_code="R00.0", diagnosis_name="Nhịp nhanh xoang"),
            _chunk("E003-DX-E05", "diagnoses", date="2024-08-05",
                   icd10_code="E05.0", diagnosis_name="Basedow"),
        ]
        result = retrieve_for_section(chunks, "diagnoses")
        icds = {c.metadata["icd10_code"] for c in result}
        assert icds == {"E05.0", "H06.2", "R00.0"}, f"All unique ICD codes, got {icds}"
        assert len(result) == 3, "No duplicates"

    def test_diagnoses_dedup_keeps_latest_version(self):
        """When same ICD appears in multiple encounters, keep the latest."""
        chunks = [
            _chunk("E001-DX-E11", "diagnoses", date="2024-01-10", icd10_code="E11"),
            _chunk("E003-DX-E11", "diagnoses", date="2024-10-10", icd10_code="E11"),
        ]
        for i, enc in enumerate(["E001", "E003"]):
            chunks[i] = chunks[i].model_copy(update={"encounter_id": enc})
        result = retrieve_for_section(chunks, "diagnoses")
        assert len(result) == 1
        assert result[0].date == "2024-10-10"

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

    def test_overview_vitals_latest_only_diagnoses_all_deduped(self):
        """Overview: vitals from latest encounter, diagnoses deduplicated."""
        chunks = []
        for enc, date in [("E001", "2024-01-10"), ("E003", "2024-10-10")]:
            c = _chunk(f"P001-{enc}-VIT", "vitals", date=date)
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        for enc, date in [("E001", "2024-01-10"), ("E003", "2024-10-10")]:
            c = _chunk(f"P001-{enc}-DX-E11", "diagnoses", date=date, icd10_code="E11")
            c = c.model_copy(update={"encounter_id": enc})
            chunks.append(c)
        # Add a unique old diagnosis
        old_dx = _chunk("P001-E001-DX-H06", "diagnoses", date="2024-01-10", icd10_code="H06.2")
        old_dx = old_dx.model_copy(update={"encounter_id": "E001"})
        chunks.append(old_dx)
        # Patient info
        pi = _chunk("P001-PAT", "patient_info", date="2024-01-10")
        pi = pi.model_copy(update={"encounter_id": None})
        chunks.append(pi)

        result = retrieve_for_section(chunks, "overview")
        vitals = [c for c in result if c.source_type == "vitals"]
        diags = [c for c in result if c.source_type == "diagnoses"]
        pinfo = [c for c in result if c.source_type == "patient_info"]
        assert {c.encounter_id for c in vitals} == {"E003"}
        # E11 deduplicated (latest wins) + H06.2 unique → 2 diagnoses
        assert len(diags) == 2
        diag_icds = {c.metadata["icd10_code"] for c in diags}
        assert diag_icds == {"E11", "H06.2"}
        assert len(pinfo) == 1

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


# ---------------------------------------------------------------------------
# Integration tests using real patient data
# ---------------------------------------------------------------------------

class TestRetrievalIntegration:
    """Verify retrieval quality against known recall gaps from evaluation."""

    @staticmethod
    def _load_patient_chunks(patient_id: str) -> list[SourceChunk]:
        import json
        from pathlib import Path
        store_path = Path(__file__).parent.parent / "data" / "processed" / "stores" / f"{patient_id}_store.json"
        if not store_path.exists():
            pytest.skip(f"Store file {store_path} not found")
        raw = json.loads(store_path.read_text(encoding="utf-8"))
        return [SourceChunk(**v) for v in raw.values()]

    def test_p007_diagnoses_includes_secondary(self):
        """P007 has H06.2 and R00.0 only at E001 — diagnoses must retrieve them."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "diagnoses")
        ids = {c.source_id for c in result}
        assert "P007-E001-DX-H06.2" in ids, "Secondary: Exophthalmos from E001"
        assert "P007-E001-DX-R00.0" in ids, "Secondary: Sinus tachycardia from E001"
        assert "P007-E003-DX-E05.0" in ids, "Primary: Basedow from latest encounter"

    def test_p007_diagnoses_deduped(self):
        """P007 E05.0 appears in E001 and E003 — should be deduplicated."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "diagnoses")
        e05_chunks = [c for c in result if "E05" in c.source_id]
        assert len(e05_chunks) == 1, f"E05.0 should appear once, got {[c.source_id for c in e05_chunks]}"
        assert "E003" in e05_chunks[0].source_id, "Should keep latest E003 version"

    def test_p007_abnormal_labs_includes_trab(self):
        """P007 TRAb was only measured at E001 — must not be filtered out."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "abnormal_labs")
        ids = {c.source_id for c in result}
        assert "P007-E001-LAB-TRAB" in ids, "TRAb from E001 must be retrieved"

    def test_p007_abnormal_labs_still_has_trend_data(self):
        """TSH/FT4/FT3 from E002 and E003 must still be present for trend display."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "abnormal_labs")
        ids = {c.source_id for c in result}
        assert "P007-E003-LAB-TSH" in ids
        assert "P007-E002-LAB-TSH" in ids

    def test_p007_abnormal_labs_not_flooded(self):
        """Should not include TSH/FT4/FT3 from E001 since they exist in E002/E003."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "abnormal_labs")
        ids = {c.source_id for c in result}
        assert "P007-E001-LAB-TSH" not in ids, "TSH from E001 redundant (exists in E002/E003)"
        assert "P007-E001-LAB-FT4" not in ids, "FT4 from E001 redundant"

    def test_p008_diagnoses_includes_hpylori(self):
        """P008 has B98.0 (H.pylori) only at E001 — diagnoses must retrieve it."""
        chunks = self._load_patient_chunks("P008")
        result = retrieve_for_section(chunks, "diagnoses")
        ids = {c.source_id for c in result}
        assert "P008-E001-DX-B98.0" in ids, "H.pylori diagnosis from E001"
        assert "P008-E002-DX-K25.7" in ids, "Primary diagnosis from latest"
        assert "P008-E002-DX-K21.0" in ids, "Comorbid from latest"

    def test_p007_overview_has_latest_vitals_and_all_diagnoses(self):
        """Overview: vitals from E003, diagnoses from all encounters deduped."""
        chunks = self._load_patient_chunks("P007")
        result = retrieve_for_section(chunks, "overview")
        vitals = [c for c in result if c.source_type == "vitals"]
        diags = [c for c in result if c.source_type == "diagnoses"]
        assert all("E003" in c.encounter_id for c in vitals), \
            f"Vitals should be from E003 only, got {[c.encounter_id for c in vitals]}"
        diag_encounters = {c.encounter_id for c in diags}
        assert "P007-E001" in diag_encounters, "E001 diagnoses should be in overview"
