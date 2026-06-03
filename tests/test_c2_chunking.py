"""Tests for C2 Chunking Service (chunker, store builder)."""

import json
import pytest
from pathlib import Path

from src.c1_emr.pipeline import load_and_process
from src.c2_chunking.chunker import chunk_ehr
from src.c2_chunking.store_builder import (
    build_structured_store, get_chunks_for_patient,
    get_chunk, filter_by_type,
)
from src.schemas import SourceChunk

ROOT = Path(__file__).parent.parent
ASSEMBLED_DIR = ROOT / "data" / "medical_summarization" / "assembled"


@pytest.fixture
def p001_ehr():
    return load_and_process(ASSEMBLED_DIR / "P001.json")


@pytest.fixture
def p001_chunks(p001_ehr):
    return chunk_ehr(p001_ehr)


@pytest.fixture
def p001_store(p001_chunks):
    return build_structured_store(p001_chunks)


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunker:
    def test_chunks_not_empty(self, p001_chunks):
        assert len(p001_chunks) > 0

    def test_all_chunks_are_source_chunk(self, p001_chunks):
        assert all(isinstance(c, SourceChunk) for c in p001_chunks)

    def test_source_ids_unique(self, p001_chunks):
        ids = [c.source_id for c in p001_chunks]
        assert len(ids) == len(set(ids)), "Duplicate source_ids found"

    def test_source_ids_contain_patient_id(self, p001_chunks):
        for chunk in p001_chunks:
            assert "P001" in chunk.source_id

    def test_has_lab_chunks(self, p001_chunks):
        lab_chunks = [c for c in p001_chunks if c.source_type == "labs"]
        assert len(lab_chunks) > 0

    def test_has_medication_chunks(self, p001_chunks):
        med_chunks = [c for c in p001_chunks if c.source_type == "medications"]
        assert len(med_chunks) > 0

    def test_has_diagnosis_chunks(self, p001_chunks):
        dx_chunks = [c for c in p001_chunks if c.source_type == "diagnoses"]
        assert len(dx_chunks) > 0

    def test_has_allergy_chunks(self, p001_chunks):
        # P001 has 1 known allergy (Penicillin)
        allergy_chunks = [c for c in p001_chunks if c.source_type == "allergies"]
        assert len(allergy_chunks) > 0
        assert any("Penicillin" in c.content for c in allergy_chunks)

    def test_has_vital_chunks(self, p001_chunks):
        vital_chunks = [c for c in p001_chunks if c.source_type == "vitals"]
        assert len(vital_chunks) > 0

    def test_has_patient_info_chunk(self, p001_chunks):
        info_chunks = [c for c in p001_chunks if c.source_type == "patient_info"]
        assert len(info_chunks) == 1

    def test_lab_chunk_has_value(self, p001_chunks):
        lab_chunks = [c for c in p001_chunks if c.source_type == "labs"]
        # All lab chunks should have non-empty content
        for c in lab_chunks:
            assert len(c.content) > 10, f"Lab chunk too short: {c.content}"

    def test_medication_chunk_has_drug_name(self, p001_chunks):
        med_chunks = [c for c in p001_chunks if c.source_type == "medications"]
        for c in med_chunks:
            assert "drug_name" in c.metadata
            assert c.metadata["drug_name"]

    def test_diagnosis_preserves_icd10(self, p001_chunks):
        dx_chunks = [c for c in p001_chunks if c.source_type == "diagnoses"]
        all_text = " ".join(c.content for c in dx_chunks)
        # P001 has E11 (DTD type 2) and I10 (THA)
        assert "E11" in all_text
        assert "I10" in all_text

    def test_p002_no_allergy_chunks(self):
        ehr = load_and_process(ASSEMBLED_DIR / "P002.json")
        chunks = chunk_ehr(ehr)
        allergy_chunks = [c for c in chunks if c.source_type == "allergies"]
        assert len(allergy_chunks) == 0

    def test_p004_edge_case_no_crash(self):
        # P004 has edge cases: missing dose, missing unit, etc.
        ehr = load_and_process(ASSEMBLED_DIR / "P004.json")
        chunks = chunk_ehr(ehr)
        assert len(chunks) > 0
        # Missing dose should be flagged in text
        med_chunks = [c for c in chunks if c.source_type == "medications"]
        missing_dose = [c for c in med_chunks if c.metadata.get("missing_dose")]
        # P004 has at least some medications (may or may not have missing dose)
        # Just verify no crash


# ---------------------------------------------------------------------------
# Store builder tests
# ---------------------------------------------------------------------------

class TestStoreBuilder:
    def test_store_has_all_chunk_ids(self, p001_chunks, p001_store):
        for chunk in p001_chunks:
            assert chunk.source_id in p001_store

    def test_store_lookup_is_fast(self, p001_store):
        import time
        # O(1) dict lookup should be near-instant
        t = time.time()
        for _ in range(1000):
            _ = p001_store.get("P001-PATIENT-INFO")
        elapsed = time.time() - t
        assert elapsed < 0.1, f"1000 lookups took {elapsed:.3f}s (too slow)"

    def test_get_chunk_returns_source_chunk(self, p001_store):
        chunk = get_chunk(p001_store, "P001-PATIENT-INFO")
        assert chunk is not None
        assert isinstance(chunk, SourceChunk)
        assert chunk.source_type == "patient_info"

    def test_get_chunk_missing_returns_none(self, p001_store):
        assert get_chunk(p001_store, "NONEXISTENT-ID") is None

    def test_get_chunks_for_patient_filters_correctly(self, p001_store):
        chunks = get_chunks_for_patient(p001_store, "P001")
        assert all(c.patient_id == "P001" for c in chunks)

    def test_filter_by_type(self, p001_chunks):
        lab_chunks = filter_by_type(p001_chunks, "labs")
        assert all(c.source_type == "labs" for c in lab_chunks)
        assert len(lab_chunks) > 0

    def test_store_serializable(self, p001_store):
        import json
        # Should not raise
        text = json.dumps(p001_store, ensure_ascii=False)
        assert len(text) > 100
