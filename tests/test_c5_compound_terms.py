"""Tests for Vietnamese compound term matching in evidence matcher."""

import pytest
from src.c5_citation.evidence_matcher import _tokens, _keyword_overlap


class TestVietnameseCompoundTerms:
    def test_dai_thao_duong_is_single_token(self):
        tokens = _tokens("Bệnh nhân mắc đái tháo đường type 2")
        assert "đái_tháo_đường" in tokens

    def test_tang_huyet_ap_is_single_token(self):
        tokens = _tokens("Tăng huyết áp nguyên phát")
        assert "tăng_huyết_áp" in tokens

    def test_suy_than_man_is_single_token(self):
        tokens = _tokens("Suy thận mạn giai đoạn 3")
        assert "suy_thận_mạn" in tokens

    def test_benh_phoi_tac_nghen_is_single_token(self):
        tokens = _tokens("Bệnh phổi tắc nghẽn mạn tính")
        assert "bệnh_phổi_tắc_nghẽn_mạn_tính" in tokens

    def test_compound_overlap_matches_claim_to_chunk(self):
        claim = "Bệnh nhân được chẩn đoán đái tháo đường type 2"
        chunk = "Chẩn đoán: Đái tháo đường type 2 (E11)"
        assert _keyword_overlap(claim, chunk, min_overlap=2)

    def test_numeric_spacing_tolerance(self):
        claim = "HbA1c 9.2%"
        chunk = "HbA1c: 9.2 %"
        assert _keyword_overlap(claim, chunk, min_overlap=2)

    def test_numeric_comma_dot_equivalence(self):
        claim = "Creatinine 1,5 mg/dL"
        chunk = "Creatinine: 1.5 mg/dL"
        assert _keyword_overlap(claim, chunk, min_overlap=2)


class TestNegativeCases:
    """Verify compound term matching does NOT increase false positives."""

    def test_compound_term_does_not_match_wrong_disease(self):
        claim = "Chẩn đoán tăng huyết áp nguyên phát"
        chunk = "Phát hiện đái tháo đường type 2"
        assert not _keyword_overlap(claim, chunk, min_overlap=2)

    def test_diabetes_same_family_has_keyword_overlap(self):
        """C5 keyword overlap matches same disease family.
        Type 1 vs type 2 conflict is handled by C6 verifier, not C5."""
        claim = "Đái tháo đường type 1"
        chunk = "Đái tháo đường type 2"
        assert _keyword_overlap(claim, chunk, min_overlap=2)

    def test_unrelated_claims_do_not_match(self):
        claim = "Bệnh nhân dị ứng Penicillin"
        chunk = "Xét nghiệm HbA1c 9.2%"
        assert not _keyword_overlap(claim, chunk, min_overlap=2)

    def test_unrelated_diseases_do_not_match(self):
        claim = "Thiếu máu mạn tính"
        chunk = "Tăng huyết áp nguyên phát"
        result = _keyword_overlap(claim, chunk, min_overlap=2)
        assert not result
