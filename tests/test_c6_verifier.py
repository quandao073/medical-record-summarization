"""Tests for C6 — Hallucination Verifier."""

import pytest
from src.schemas import CitedClaim, SummarySection, SourceChunk
from src.c6_verifier.verifier import decide, verify_section, verify_summary


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

    def test_flagged_claims_marked_with_status_prefix(self):
        """Flagged claims should have a status-specific prefix, not a blanket [CẦN XÁC NHẬN]."""
        chunks = []  # no matching chunks → NO_CITATION
        section = _section("Bệnh nhân dùng thuốc bí mật 5000 mg.")
        vsec, actions = verify_section(section, chunks, conservative=True)
        # Conservative mode: NO_CITATION critical → FLAG with [Chưa có nguồn] prefix
        if any(a == "FLAG" for a in actions):
            # Status-specific label, not the old blanket label
            assert "[Chưa có nguồn]" in vsec.content or "[Cần xác minh]" in vsec.content

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
        
        # Test verify_section does not add prefixes to structural claims
        vsec, actions = verify_section(section, [])
        assert "[Cần xác minh] Cảnh báo hiện tại:" not in vsec.content
        assert "[Cần xác minh] Không ghi nhận." not in vsec.content
        # Non-structural critical claim "Metformin 1000 mg" with no source is flagged
        assert "[Chưa có nguồn] Metformin 1000 mg" in vsec.content or "[Cần xác minh] Metformin 1000 mg" in vsec.content

        # Test verify_summary excludes structural claims from metrics counts
        vsections, metrics = verify_summary([section], [])
        # The section has 3 claims, 2 are structural. So total_claims should be 1 (only Metformin)
        assert metrics.total_claims == 1

