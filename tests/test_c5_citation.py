"""Tests for C5 — Claim Extractor and Evidence Matcher."""

import pytest
from src.schemas import CitedClaim, SummarySection, SourceChunk
from src.c5_citation.claim_extractor import extract_claims, _is_critical
from src.c5_citation.evidence_matcher import match_claim, match_claims


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _section(content: str, section_id: str = "current_medications") -> SummarySection:
    return SummarySection(section_id=section_id, content=content)


def _chunk(source_id: str, source_type: str, content: str, **meta) -> SourceChunk:
    return SourceChunk(
        source_id=source_id, source_type=source_type,
        patient_id="P001", date="2024-01-10",
        content=content, metadata=meta,
    )


# ---------------------------------------------------------------------------
# Claim Extractor
# ---------------------------------------------------------------------------

class TestClaimExtractor:

    def test_returns_list(self):
        s = _section("HbA1c 9.2%. Glucose đói 9.8 mmol/L.")
        claims = extract_claims(s)
        assert isinstance(claims, list)

    def test_splits_into_multiple_claims(self):
        s = _section("HbA1c 9.2%. Glucose đói 9.8 mmol/L. LDL 3.4 mmol/L.")
        claims = extract_claims(s)
        assert len(claims) >= 2

    def test_empty_section_returns_empty(self):
        assert extract_claims(_section("")) == []

    def test_empty_marker_returns_empty(self):
        s = _section("Chưa thấy ghi nhận trong dữ liệu được cung cấp.")
        assert extract_claims(s) == []

    def test_error_section_returns_empty(self):
        s = _section("[LỖI: Không thể tạo section này]")
        assert extract_claims(s) == []

    def test_all_claims_start_as_no_citation(self):
        s = _section("HbA1c 9.2%. Metformin 1000 mg x2/ngày.")
        for claim in extract_claims(s):
            assert claim.status == "NO_CITATION"

    def test_single_sentence_one_claim(self):
        s = _section("Bệnh nhân dị ứng Penicillin — nổi mề đay toàn thân.")
        claims = extract_claims(s)
        assert len(claims) == 1

    def test_bullet_list_splits_correctly(self):
        content = "- HbA1c 9.2%\n- Glucose 9.8 mmol/L\n- LDL 3.4 mmol/L"
        claims = extract_claims(_section(content))
        assert len(claims) >= 3


class TestIsCritical:
    def test_drug_with_dose_is_critical(self):
        assert _is_critical("Metformin 1000 mg uống sau ăn")

    def test_lab_value_with_unit_is_critical(self):
        assert _is_critical("HbA1c: 9.2%")
        assert _is_critical("LDL-Cholesterol: 3.4 mmol/L")
        assert _is_critical("Creatinine: 88 µmol/L")

    def test_icd_code_is_critical(self):
        assert _is_critical("Chẩn đoán: E11 - Đái tháo đường type 2")
        assert _is_critical("Mã ICD: I10")

    def test_allergy_is_critical(self):
        assert _is_critical("Dị ứng Penicillin — nổi mề đay")
        assert _is_critical("Phản ứng dị ứng với Sulfonamide")

    def test_vital_with_value_is_critical(self):
        assert _is_critical("Huyết áp: 148/92 mmHg")
        assert _is_critical("Mạch: 82 lần/phút")

    def test_non_clinical_text_not_critical(self):
        assert not _is_critical("Bệnh nhân tuân thủ điều trị tốt")
        assert not _is_critical("Tái khám sau 3 tháng")

    def test_medication_without_dose_not_critical(self):
        assert not _is_critical("Bệnh nhân đang dùng Metformin")

    def test_hba1c_without_value_not_critical(self):
        # HbA1c mention without value
        assert not _is_critical("Kiểm tra HbA1c tại lần khám tiếp theo")


# ---------------------------------------------------------------------------
# Evidence Matcher
# ---------------------------------------------------------------------------

@pytest.fixture
def med_chunks():
    return [
        _chunk("MED-MET", "medications",
               "Metformin 1000 mg uống sau ăn sáng và tối",
               drug_name="Metformin", strength="1000 mg", is_current=True),
        _chunk("MED-AML", "medications",
               "Amlodipine 5 mg uống buổi sáng",
               drug_name="Amlodipine", strength="5 mg", is_current=True),
    ]


@pytest.fixture
def lab_chunks():
    return [
        _chunk("LAB-HBA1C", "labs",
               "HbA1c (Hemoglobin glycated): 9.2 % [tham chiếu: 4.0-5.6]",
               test_name="HbA1c", value=9.2, unit="%", is_abnormal=True),
        _chunk("LAB-LDL", "labs",
               "LDL-Cholesterol: 3.4 mmol/L [tham chiếu: <2.6]",
               test_name="LDL-Cholesterol", value=3.4, unit="mmol/L", is_abnormal=True),
    ]


@pytest.fixture
def dx_chunks():
    return [
        _chunk("DX-E11", "diagnoses",
               "Đái tháo đường type 2 (E11)",
               icd10_code="E11", diagnosis_name="Đái tháo đường type 2"),
    ]


@pytest.fixture
def allergy_chunks():
    return [
        _chunk("ALLERGY-PEN", "allergies",
               "Dị ứng Penicillin — nổi mề đay toàn thân",
               substance="Penicillin"),
    ]


class TestEvidenceMatcher:

    def test_returns_cited_claim(self, med_chunks):
        claim = CitedClaim(claim_text="Metformin 1000 mg uống sau ăn", is_critical=True)
        result = match_claim(claim, med_chunks)
        assert isinstance(result, CitedClaim)

    def test_exact_med_match_supported(self, med_chunks):
        claim = CitedClaim(claim_text="Metformin 1000 mg 2 lần/ngày", is_critical=True)
        result = match_claim(claim, med_chunks)
        assert result.status == "SUPPORTED"
        assert "MED-MET" in result.citations

    def test_exact_lab_match_supported(self, lab_chunks):
        claim = CitedClaim(claim_text="HbA1c: 9.2% (tăng cao)", is_critical=True)
        result = match_claim(claim, lab_chunks)
        assert result.status == "SUPPORTED"
        assert "LAB-HBA1C" in result.citations

    def test_exact_dx_match_by_icd_code(self, dx_chunks):
        claim = CitedClaim(claim_text="Chẩn đoán: E11 Đái tháo đường", is_critical=True)
        result = match_claim(claim, dx_chunks)
        assert result.status == "SUPPORTED"

    def test_exact_dx_match_by_name(self, dx_chunks):
        claim = CitedClaim(claim_text="Bệnh nhân mắc Đái tháo đường type 2", is_critical=True)
        result = match_claim(claim, dx_chunks)
        assert result.status in ("SUPPORTED", "PARTIALLY_SUPPORTED")

    def test_exact_allergy_match_supported(self, allergy_chunks):
        claim = CitedClaim(claim_text="Dị ứng Penicillin gây nổi mề đay", is_critical=True)
        result = match_claim(claim, allergy_chunks)
        assert result.status == "SUPPORTED"

    def test_keyword_match_partially_supported(self, lab_chunks):
        claim = CitedClaim(
            claim_text="Mức LDL cholesterol bất thường, cần điều trị",
            is_critical=False,
        )
        result = match_claim(claim, lab_chunks)
        assert result.status in ("PARTIALLY_SUPPORTED", "LOW_CONFIDENCE", "UNSUPPORTED")

    def test_no_match_critical_claim_no_citation(self, med_chunks):
        claim = CitedClaim(
            claim_text="Insulin glargine 20 units tiêm dưới da mỗi tối",
            is_critical=True,
        )
        result = match_claim(claim, med_chunks)
        assert result.status == "NO_CITATION"
        assert result.citations == []

    def test_no_match_noncritical_claim_unsupported(self, med_chunks):
        claim = CitedClaim(
            claim_text="Bệnh nhân hoàn toàn khỏe mạnh không cần thuốc",
            is_critical=False,
        )
        result = match_claim(claim, med_chunks)
        assert result.status == "UNSUPPORTED"

    def test_citations_populated_on_match(self, med_chunks):
        claim = CitedClaim(claim_text="Metformin 1000 mg sau ăn", is_critical=True)
        result = match_claim(claim, med_chunks)
        if result.status == "SUPPORTED":
            assert len(result.citations) >= 1

    def test_input_claim_not_mutated(self, med_chunks):
        claim = CitedClaim(claim_text="Metformin 1000 mg", is_critical=True, status="NO_CITATION")
        _ = match_claim(claim, med_chunks)
        assert claim.status == "NO_CITATION"  # original unchanged

    def test_match_claims_batch(self, med_chunks, lab_chunks):
        claims = [
            CitedClaim(claim_text="Metformin 1000 mg", is_critical=True),
            CitedClaim(claim_text="HbA1c: 9.2%",       is_critical=True),
        ]
        results = match_claims(claims, med_chunks + lab_chunks)
        assert len(results) == 2
        assert all(isinstance(r, CitedClaim) for r in results)
