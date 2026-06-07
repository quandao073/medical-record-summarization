"""Tests for C6 — Hallucination Verifier."""

import pytest
from src.schemas import CitedClaim, SummarySection, SourceChunk
from src.c6_verifier.verifier import (
    decide, verify_section, verify_summary, check_internal_consistency,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _claim(status: str, is_critical: bool = False) -> CitedClaim:
    return CitedClaim(
        claim_text=f"Claim [{status} critical={is_critical}]",
        status=status,
        is_critical=is_critical,
        citations=["SRC-001"] if status == "SUPPORTED" else [],
    )


def _section(content: str, sid: str = "current_medications") -> SummarySection:
    return SummarySection(section_id=sid, content=content)


def _chunk(source_id: str, source_type: str = "medications", **meta) -> SourceChunk:
    return SourceChunk(
        source_id=source_id, source_type=source_type,
        patient_id="P001", date="2024-01-10",
        content=f"Content {source_id}",
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Decision matrix (decide function)
# ---------------------------------------------------------------------------

class TestDecide:

    def test_supported_any_keep(self):
        assert decide(_claim("SUPPORTED", True))  == "KEEP"
        assert decide(_claim("SUPPORTED", False)) == "KEEP"

    def test_partially_supported_flag(self):
        assert decide(_claim("PARTIALLY_SUPPORTED", True))  == "FLAG"
        assert decide(_claim("PARTIALLY_SUPPORTED", False)) == "FLAG"

    def test_low_confidence_flag(self):
        assert decide(_claim("LOW_CONFIDENCE", True))  == "FLAG"
        assert decide(_claim("LOW_CONFIDENCE", False)) == "FLAG"

    def test_unsupported_critical_conservative_flag(self):
        # conservative=True → REMOVE becomes FLAG
        assert decide(_claim("UNSUPPORTED", True), conservative=True)  == "FLAG"

    def test_unsupported_critical_strict_remove(self):
        assert decide(_claim("UNSUPPORTED", True), conservative=False) == "REMOVE"

    def test_unsupported_noncritical_flag(self):
        assert decide(_claim("UNSUPPORTED", False)) == "FLAG"

    def test_no_citation_critical_conservative_flag(self):
        assert decide(_claim("NO_CITATION", True), conservative=True)  == "FLAG"

    def test_no_citation_critical_strict_remove(self):
        assert decide(_claim("NO_CITATION", True), conservative=False) == "REMOVE"

    def test_no_citation_noncritical_flag(self):
        assert decide(_claim("NO_CITATION", False)) == "FLAG"

    def test_contradicted_always_remove(self):
        assert decide(_claim("CONTRADICTED", True),  conservative=False) == "REMOVE"
        assert decide(_claim("CONTRADICTED", False), conservative=False) == "REMOVE"

    def test_contradicted_conservative_flag(self):
        assert decide(_claim("CONTRADICTED", True),  conservative=True) == "FLAG"

    def test_need_review_flag(self):
        assert decide(_claim("NEED_REVIEW", True))  == "FLAG"
        assert decide(_claim("NEED_REVIEW", False)) == "FLAG"


# ---------------------------------------------------------------------------
# verify_section
# ---------------------------------------------------------------------------

@pytest.fixture
def med_chunks():
    return [
        _chunk("MED-MET", "medications",
               drug_name="Metformin", strength="1000 mg", is_current=True),
        _chunk("MED-AML", "medications",
               drug_name="Amlodipine", strength="5 mg", is_current=True),
    ]


class TestVerifySection:

    def test_returns_section_and_actions(self, med_chunks):
        section = _section("Metformin 1000 mg uống sau ăn. Amlodipine 5 mg sáng.")
        vsec, actions = verify_section(section, med_chunks)
        assert isinstance(vsec, SummarySection)
        assert isinstance(actions, list)

    def test_supported_claims_preserved_in_content(self, med_chunks):
        section = _section("Metformin 1000 mg uống sau ăn sáng và tối.")
        vsec, _ = verify_section(section, med_chunks)
        assert vsec.content != ""
        assert "[CẦN XÁC NHẬN]" not in vsec.content or "Metformin" in vsec.content

    def test_flagged_claims_content_stays_clean(self):
        """Flagged claims should NOT have status prefixes in content — status is in CitedClaim.status only."""
        chunks = []  # no matching chunks → NO_CITATION
        section = _section("Bệnh nhân dùng thuốc bí mật 5000 mg.")
        vsec, actions = verify_section(section, chunks, conservative=True)
        if any(a == "FLAG" for a in actions):
            assert "[Chưa có nguồn]" not in vsec.content
            assert "[Cần xác minh]" not in vsec.content
            assert "[CẦN XÁC NHẬN]" not in vsec.content
            assert "thuốc bí mật 5000 mg" in vsec.content

    def test_empty_section_unchanged(self, med_chunks):
        section = _section("Chưa thấy ghi nhận trong dữ liệu được cung cấp.")
        vsec, actions = verify_section(section, med_chunks)
        assert actions == []
        assert vsec.content == section.content

    def test_section_id_preserved(self, med_chunks):
        section = _section("Metformin 1000 mg.", "current_medications")
        vsec, _ = verify_section(section, med_chunks)
        assert vsec.section_id == "current_medications"

    def test_all_removed_gives_empty_marker(self):
        chunks = []
        # strict mode: unsupported critical claims removed
        section = _section("Insulin glargine 5000 mg tiêm mỗi ngày.")
        vsec, actions = verify_section(section, chunks, conservative=False)
        if all(a == "REMOVE" for a in actions):
            assert "Chưa thấy ghi nhận" in vsec.content

    def test_cited_claims_populated(self, med_chunks):
        section = _section("Metformin 1000 mg sau ăn. Amlodipine 5 mg sáng.")
        vsec, _ = verify_section(section, med_chunks)
        assert isinstance(vsec.cited_claims, list)


# ---------------------------------------------------------------------------
# verify_summary
# ---------------------------------------------------------------------------

class TestVerifySummary:

    def test_returns_sections_and_metrics(self, med_chunks):
        sections = [
            _section("Metformin 1000 mg uống sau ăn.", "current_medications"),
            _section("Chưa thấy ghi nhận dị ứng.", "allergies"),
        ]
        vsections, metrics = verify_summary(sections, med_chunks)
        assert len(vsections) == len(sections)
        assert metrics.total_claims >= 0

    def test_metrics_citation_coverage_range(self, med_chunks):
        sections = [_section("Metformin 1000 mg.", "current_medications")]
        _, metrics = verify_summary(sections, med_chunks)
        assert 0.0 <= metrics.citation_coverage <= 1.0

    def test_metrics_hallucination_rate_zero_when_no_contradictions(self, med_chunks):
        sections = [_section("Metformin 1000 mg.", "current_medications")]
        _, metrics = verify_summary(sections, med_chunks)
        assert metrics.hallucination_rate == 0.0

    def test_metrics_missing_section_rate_range(self, med_chunks):
        sections = [
            _section("Metformin 1000 mg.", "current_medications"),
            _section("Chưa thấy ghi nhận dị ứng.", "allergies"),
        ]
        _, metrics = verify_summary(sections, med_chunks)
        assert 0.0 <= metrics.missing_section_rate <= 1.0

    def test_unsupported_critical_claim_conservative_flagged(self):
        chunks = []  # nothing to match
        sections = [_section("Insulin 5000 mg tiêm mỗi ngày.", "current_medications")]
        vsections, metrics = verify_summary(sections, chunks, conservative=True)
        # Conservative: not removed, flagged
        assert vsections[0].content != ""

    def test_section_count_unchanged(self, med_chunks):
        sections = [
            _section("Metformin 1000 mg.", "current_medications"),
            _section("Dị ứng Penicillin.", "allergies"),
            _section("HbA1c: 9.2%.", "abnormal_labs"),
        ]
        vsections, _ = verify_summary(sections, med_chunks)
        assert len(vsections) == 3

    def test_allergy_section_not_silenced(self):
        chunks = [_chunk("ALLERGY-PEN", "allergies", substance="Penicillin")]
        sections = [_section("Dị ứng Penicillin — nổi mề đay.", "allergies")]
        vsections, _ = verify_summary(sections, chunks)
        assert vsections[0].content != ""
        assert "Chưa thấy ghi nhận được xác minh" not in vsections[0].content

    def test_metrics_computed_correctly(self, med_chunks):
        sections = [
            _section("Metformin 1000 mg uống sau ăn.", "current_medications"),
        ]
        _, metrics = verify_summary(sections, med_chunks)
        assert metrics.total_claims >= 1
        # All these fields should be in [0,1]
        for field in ("citation_coverage", "unsupported_claim_rate",
                      "hallucination_rate", "missing_section_rate"):
            val = getattr(metrics, field)
            assert 0.0 <= val <= 1.0, f"{field}={val} out of range"

    def test_structural_claims_behavior(self):
        from src.schemas import is_structural_content
        from src.c5_citation.claim_extractor import extract_claims
        from src.c5_citation.evidence_matcher import match_claims

        # Test helper function
        assert is_structural_content("Cảnh báo hiện tại:") is True
        assert is_structural_content("Không ghi nhận.") is True
        assert is_structural_content("Metformin 1000 mg.") is False

        # Test extraction sets is_structural
        section = _section("Cảnh báo hiện tại:\n- Không ghi nhận.\n- Metformin 1000 mg.")
        claims = extract_claims(section)
        assert len(claims) == 3
        assert claims[0].is_structural is True
        assert claims[1].is_structural is True
        assert claims[2].is_structural is False

        # Test match_claims marks structural claims as SUPPORTED with no prefix
        matched = match_claims(claims, [])
        assert matched[0].status == "SUPPORTED"
        assert matched[0].citations == []
        assert matched[1].status == "SUPPORTED"
        
        # Test verify_section does not add prefixes to any claims (content stays clean)
        vsec, actions = verify_section(section, [])
        assert "[Cần xác minh]" not in vsec.content
        assert "[Chưa có nguồn]" not in vsec.content
        # Non-structural critical claim "Metformin 1000 mg" is kept in content (flagged, not removed)
        assert "Metformin 1000 mg" in vsec.content

        # Test verify_summary excludes structural claims from metrics counts
        vsections, metrics = verify_summary([section], [])
        # The section has 3 claims, 2 are structural. So total_claims should be 1 (only Metformin)
        assert metrics.total_claims == 1


# ---------------------------------------------------------------------------
# Week 3 quality fixes
# ---------------------------------------------------------------------------

class TestVerifierActionWritten:
    """Q8 — every kept claim carries its KEEP/FLAG decision."""

    def test_verifier_action_set_on_claims(self, med_chunks):
        section = _section("Metformin 1000 mg uống sau ăn. Thuốc bí mật 9999 mg.")
        vsec, _ = verify_section(section, med_chunks, conservative=True)
        assert vsec.cited_claims  # non-empty
        for c in vsec.cited_claims:
            assert c.verifier_action in ("KEEP", "FLAG")

    def test_supported_claim_is_keep(self, med_chunks):
        section = _section("Metformin 1000 mg uống sau ăn sáng và tối.")
        vsec, _ = verify_section(section, med_chunks)
        met = [c for c in vsec.cited_claims if "Metformin" in c.claim_text]
        assert met and met[0].verifier_action == "KEEP"


class TestRemovedClaimsAudit:
    """Q8 — REMOVE'd claims are captured for audit in strict mode."""

    def test_removed_claims_logged(self):
        removed: list = []
        section = _section("Insulin glargine 9999 mg tiêm mỗi tối.")
        vsec, actions = verify_section(section, [], conservative=False, removed_out=removed)
        if "REMOVE" in actions:
            assert len(removed) >= 1
            assert all(c.verifier_action == "REMOVE" for c in removed)

    def test_conservative_mode_removes_nothing(self):
        removed: list = []
        section = _section("Insulin glargine 9999 mg tiêm mỗi tối.")
        verify_section(section, [], conservative=True, removed_out=removed)
        assert removed == []


class TestInternalConsistency:
    """Q1 — cross-section diabetes-type disagreement is flagged."""

    def test_minority_type_marked_contradicted(self):
        sections = [
            SummarySection(section_id="overview", cited_claims=[
                CitedClaim(claim_text="Đái tháo đường type 2 nhiều năm", status="SUPPORTED"),
            ]),
            SummarySection(section_id="diagnoses", cited_claims=[
                CitedClaim(claim_text="Chẩn đoán: Đái tháo đường type 2 (E11.9)", status="SUPPORTED"),
            ]),
            SummarySection(section_id="reason_for_visit", cited_claims=[
                CitedClaim(claim_text="Bệnh nhân đái tháo đường type 1 tái khám", status="SUPPORTED"),
            ]),
        ]
        updated, count = check_internal_consistency(sections)
        assert count == 1
        minority = updated[2].cited_claims[0]
        assert minority.status == "CONTRADICTED"

    def test_no_conflict_when_consistent(self):
        sections = [
            SummarySection(section_id="overview", cited_claims=[
                CitedClaim(claim_text="Đái tháo đường type 2", status="SUPPORTED"),
            ]),
            SummarySection(section_id="diagnoses", cited_claims=[
                CitedClaim(claim_text="Đái tháo đường type 2 (E11.9)", status="SUPPORTED"),
            ]),
        ]
        updated, count = check_internal_consistency(sections)
        assert count == 0


class TestNewMetrics:
    """New quality counters are present and consistent."""

    def test_metrics_have_new_counters(self, med_chunks):
        sections = [_section("Metformin 1000 mg uống sau ăn.", "current_medications")]
        _, metrics = verify_summary(sections, med_chunks)
        assert hasattr(metrics, "contradiction_count")
        assert hasattr(metrics, "need_review_count")
        assert hasattr(metrics, "duplicate_claim_count")
        assert metrics.contradiction_count >= 0

