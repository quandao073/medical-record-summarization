"""Tests for C3 — Vector Store + Hybrid Retrieval."""

import time
import pytest
from pathlib import Path

from src.schemas import SourceChunk
from src.c3_retrieval.vector_store import VectorStore
from src.c3_retrieval.retriever import retrieve_for_section, SECTION_QUERY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(source_id: str, source_type: str, content: str,
           date: str = "2024-01-10", **meta) -> SourceChunk:
    return SourceChunk(
        source_id=source_id,
        source_type=source_type,
        patient_id="P001",
        date=date,
        content=content,
        metadata=meta,
    )


@pytest.fixture
def clinical_chunks():
    """Realistic clinical chunks in Vietnamese covering multiple source types."""
    return [
        _chunk("LAB-HBA1C-1", "labs", "HbA1c 9.2% - cao, kiểm soát đường huyết kém",
               date="2024-01-10", test_name="HbA1c", is_abnormal=True),
        _chunk("LAB-HBA1C-2", "labs", "HbA1c 7.5% - cải thiện so với lần trước",
               date="2024-06-10", test_name="HbA1c", is_abnormal=True),
        _chunk("LAB-CREAT", "labs", "Creatinine 0.9 mg/dL - bình thường",
               date="2024-01-10", test_name="Creatinine", is_abnormal=False),
        _chunk("LAB-CHOL", "labs", "Cholesterol toàn phần 6.5 mmol/L - cao",
               date="2024-01-10", test_name="Cholesterol", is_abnormal=True),
        _chunk("MED-MET", "medications", "Metformin 850mg uống 2 lần/ngày sau ăn",
               date="2024-01-10", drug_name="Metformin", is_current=True),
        _chunk("MED-AML", "medications", "Amlodipine 5mg uống 1 lần/ngày buổi sáng",
               date="2024-01-10", drug_name="Amlodipine", is_current=True),
        _chunk("MED-ATOR", "medications", "Atorvastatin 20mg uống 1 lần/ngày buổi tối",
               date="2024-01-10", drug_name="Atorvastatin", is_current=True),
        _chunk("DX-E11", "diagnoses", "Đái tháo đường type 2 - E11 - chẩn đoán chính",
               date="2024-01-10", icd10_code="E11"),
        _chunk("DX-I10", "diagnoses", "Tăng huyết áp - I10 - bệnh kèm",
               date="2024-01-10", icd10_code="I10"),
        _chunk("ALLERGY-PEN", "allergies", "Dị ứng Penicillin - phản ứng: phát ban, mức độ: trung bình",
               date="2021-03-15"),
        _chunk("NOTE-HISTORY", "clinical_notes", "Bệnh nhân có tiền sử gia đình: mẹ bị đái tháo đường type 2",
               date="2024-01-10"),
        _chunk("NOTE-EXAM", "clinical_notes", "Khám thực thể: huyết áp 142/90 mmHg, BMI 27.3",
               date="2024-01-10"),
        _chunk("VIT-001", "vitals", "Huyết áp 142/90, mạch 82, SpO2 97%, nhiệt độ 36.8°C",
               date="2024-01-10"),
        _chunk("PAT-INFO", "patient_info", "Nguyễn Văn A, nam, 58 tuổi, nghề nghiệp: kế toán",
               date="2024-01-10"),
    ]


@pytest.fixture
def vector_store(clinical_chunks):
    vs = VectorStore()
    vs.build(clinical_chunks)
    return vs


# ---------------------------------------------------------------------------
# VectorStore.build
# ---------------------------------------------------------------------------

class TestBuild:
    def test_build_sets_size(self, vector_store, clinical_chunks):
        assert vector_store.size == len(clinical_chunks)

    def test_build_empty_chunks(self):
        vs = VectorStore()
        vs.build([])
        assert vs.size == 0

    def test_build_single_chunk(self):
        vs = VectorStore()
        c = _chunk("SINGLE", "labs", "xét nghiệm glucose 8.5 mmol/L")
        vs.build([c])
        assert vs.size == 1

    def test_build_overwrites_previous(self, clinical_chunks):
        vs = VectorStore()
        vs.build(clinical_chunks[:3])
        assert vs.size == 3
        vs.build(clinical_chunks)
        assert vs.size == len(clinical_chunks)

    def test_build_performance_under_5s(self, vector_store):
        """Build index for 83 chunks (typical patient) should take < 5 seconds.
        Uses pre-warmed model to exclude one-time model loading from timing."""
        chunks = [
            _chunk(f"CHUNK-{i:03}", "labs", f"Xét nghiệm {i}: giá trị {i * 0.5} mg/dL")
            for i in range(83)
        ]
        vs = VectorStore()
        vs._model = vector_store.model  # reuse already-loaded model
        start = time.time()
        vs.build(chunks)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Build took {elapsed:.1f}s, expected < 5s"


# ---------------------------------------------------------------------------
# VectorStore.search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_results(self, vector_store):
        results = vector_store.search("đường huyết HbA1c", top_k=5)
        assert len(results) > 0

    def test_search_returns_tuples_of_chunk_and_score(self, vector_store):
        results = vector_store.search("thuốc đang dùng")
        for chunk, score in results:
            assert isinstance(chunk, SourceChunk)
            assert isinstance(score, float)

    def test_search_respects_top_k(self, vector_store):
        results = vector_store.search("xét nghiệm", top_k=3)
        assert len(results) <= 3

    def test_search_empty_store_returns_empty(self):
        vs = VectorStore()
        vs.build([])
        assert vs.search("anything") == []

    def test_search_unbuilt_store_returns_empty(self):
        vs = VectorStore()
        assert vs.search("anything") == []

    def test_search_hba1c_ranks_lab_chunks_high(self, vector_store):
        results = vector_store.search("HbA1c đường huyết xét nghiệm", top_k=5)
        top_ids = [c.source_id for c, _ in results[:3]]
        hba1c_in_top = any("HBA1C" in sid for sid in top_ids)
        assert hba1c_in_top, f"Expected HbA1c chunk in top 3, got {top_ids}"

    def test_search_medication_ranks_med_chunks_high(self, vector_store):
        results = vector_store.search("thuốc điều trị đái tháo đường Metformin", top_k=5)
        top_ids = [c.source_id for c, _ in results[:3]]
        med_in_top = any("MED" in sid for sid in top_ids)
        assert med_in_top, f"Expected medication chunk in top 3, got {top_ids}"

    def test_search_scores_are_descending(self, vector_store):
        results = vector_store.search("chẩn đoán bệnh", top_k=10)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# VectorStore.search with allowed_source_types (hard filter)
# ---------------------------------------------------------------------------

class TestSearchHardFilter:
    def test_filter_returns_only_allowed_types(self, vector_store):
        results = vector_store.search("đường huyết", top_k=10, allowed_source_types=["labs"])
        for chunk, _ in results:
            assert chunk.source_type == "labs", f"Expected 'labs', got '{chunk.source_type}'"

    def test_filter_medications_only(self, vector_store):
        results = vector_store.search("thuốc", top_k=10, allowed_source_types=["medications"])
        for chunk, _ in results:
            assert chunk.source_type == "medications"

    def test_filter_multiple_types(self, vector_store):
        results = vector_store.search("bệnh", top_k=10,
                                      allowed_source_types=["diagnoses", "clinical_notes"])
        for chunk, _ in results:
            assert chunk.source_type in ("diagnoses", "clinical_notes")

    def test_filter_no_matching_type_returns_empty(self, vector_store):
        results = vector_store.search("thuốc", top_k=5, allowed_source_types=["imaging"])
        assert results == []

    def test_abnormal_labs_hard_filter(self, vector_store):
        """Even if query is about medications, hard filter should block non-lab results."""
        results = vector_store.search("Metformin thuốc", top_k=10, allowed_source_types=["labs"])
        for chunk, _ in results:
            assert chunk.source_type == "labs"


# ---------------------------------------------------------------------------
# VectorStore.save / load
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_creates_files(self, vector_store, tmp_path):
        vector_store.save(tmp_path / "test_index")
        assert (tmp_path / "test_index" / "index.faiss").exists()
        assert (tmp_path / "test_index" / "meta.json").exists()

    def test_load_restores_state(self, vector_store, clinical_chunks, tmp_path):
        vector_store.save(tmp_path / "test_index")
        loaded = VectorStore()
        loaded.load(tmp_path / "test_index")
        assert loaded.size == len(clinical_chunks)

    def test_loaded_store_can_search(self, vector_store, tmp_path):
        vector_store.save(tmp_path / "test_index")
        loaded = VectorStore()
        loaded.load(tmp_path / "test_index")
        results = loaded.search("HbA1c", top_k=3)
        assert len(results) > 0

    def test_loaded_search_matches_original(self, vector_store, tmp_path):
        original_results = vector_store.search("thuốc đái tháo đường", top_k=5)
        vector_store.save(tmp_path / "test_index")
        loaded = VectorStore()
        loaded.load(tmp_path / "test_index")
        loaded_results = loaded.search("thuốc đái tháo đường", top_k=5)
        orig_ids = [c.source_id for c, _ in original_results]
        load_ids = [c.source_id for c, _ in loaded_results]
        assert orig_ids == load_ids

    def test_save_without_build_raises(self, tmp_path):
        vs = VectorStore()
        with pytest.raises(ValueError):
            vs.save(tmp_path / "empty")

    def test_save_creates_nested_dirs(self, tmp_path):
        vs = VectorStore()
        c = _chunk("X", "labs", "test content")
        vs.build([c])
        deep_path = tmp_path / "a" / "b" / "c"
        vs.save(deep_path)
        assert (deep_path / "index.faiss").exists()


# ---------------------------------------------------------------------------
# Hybrid retrieval — retrieve_for_section with vector_store
# ---------------------------------------------------------------------------

class TestHybridRetrieval:
    def test_hybrid_returns_same_types_as_rule_based(self, clinical_chunks, vector_store):
        """Hybrid should not introduce chunks that rule-based would exclude."""
        for section_id in SECTION_QUERY:
            rule_result = retrieve_for_section(clinical_chunks, section_id)
            hybrid_result = retrieve_for_section(clinical_chunks, section_id,
                                                  vector_store=vector_store)
            rule_types = {c.source_type for c in rule_result}
            hybrid_types = {c.source_type for c in hybrid_result}
            assert hybrid_types.issubset(rule_types), \
                f"Section {section_id}: hybrid types {hybrid_types} not subset of rule {rule_types}"

    def test_hybrid_same_chunk_set_as_rule_based(self, clinical_chunks, vector_store):
        """Hybrid may reorder, but must contain the same chunks as rule-based."""
        for section_id in SECTION_QUERY:
            rule_ids = {c.source_id for c in retrieve_for_section(clinical_chunks, section_id)}
            hybrid_ids = {c.source_id for c in retrieve_for_section(
                clinical_chunks, section_id, vector_store=vector_store)}
            assert hybrid_ids == rule_ids, \
                f"Section {section_id}: hybrid {hybrid_ids} != rule {rule_ids}"

    def test_hybrid_respects_max_chunks(self, clinical_chunks, vector_store):
        result = retrieve_for_section(clinical_chunks, "treatment_timeline",
                                       max_chunks=3, vector_store=vector_store)
        assert len(result) <= 3

    def test_hybrid_abnormal_labs_still_excludes_normal(self, clinical_chunks, vector_store):
        result = retrieve_for_section(clinical_chunks, "abnormal_labs",
                                       vector_store=vector_store)
        for c in result:
            assert c.metadata.get("is_abnormal") or c.metadata.get("is_critical")

    def test_hybrid_current_medications_still_filters_current(self, clinical_chunks, vector_store):
        result = retrieve_for_section(clinical_chunks, "current_medications",
                                       vector_store=vector_store)
        for c in result:
            assert c.source_type == "medications"
            assert c.metadata.get("is_current")

    def test_hybrid_treatment_timeline_chronological(self, clinical_chunks, vector_store):
        """Chronological sections should maintain date order even with vector re-rank."""
        result = retrieve_for_section(clinical_chunks, "treatment_timeline",
                                       vector_store=vector_store)
        dates = [c.date for c in result if c.date]
        assert dates == sorted(dates), f"Timeline should be chronological, got {dates}"

    def test_hybrid_overview_patient_info_first(self, clinical_chunks, vector_store):
        result = retrieve_for_section(clinical_chunks, "overview",
                                       vector_store=vector_store)
        if result:
            patient_info = [c for c in result if c.source_type == "patient_info"]
            if patient_info:
                assert result[0].source_type == "patient_info"

    def test_no_vector_store_falls_back_to_rule_based(self, clinical_chunks):
        """When vector_store=None (default), behavior is identical to before."""
        result = retrieve_for_section(clinical_chunks, "current_medications")
        assert all(c.source_type == "medications" for c in result)

    def test_hybrid_allergies_section(self, clinical_chunks, vector_store):
        result = retrieve_for_section(clinical_chunks, "allergies",
                                       vector_store=vector_store)
        types = {c.source_type for c in result}
        assert "allergies" in types

    def test_section_query_covers_all_sections(self):
        """Every section in SECTION_SOURCE_TYPES should have a query for hybrid retrieval."""
        from src.c3_retrieval.retriever import SECTION_SOURCE_TYPES
        for section_id in SECTION_SOURCE_TYPES:
            assert section_id in SECTION_QUERY, \
                f"Missing SECTION_QUERY for '{section_id}'"
