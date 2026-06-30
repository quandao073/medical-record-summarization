"""Tests for output guardrail — role-drift detection."""
import pytest
from src.schemas import SummarySection
from src.guardrails.output_guard import check_role_drift


def _section(section_id: str, content: str) -> SummarySection:
    return SummarySection(section_id=section_id, content=content)


def test_clean_summary_has_no_violations():
    sections = [_section("diagnoses", "Đái tháo đường type 2 (E11). Tăng huyết áp (I10).")]
    assert check_role_drift(sections) == []


def test_detects_nen_dung():
    sections = [_section("clinical_alerts", "Bệnh nhân nên dùng thêm Aspirin.")]
    violations = check_role_drift(sections)
    assert len(violations) == 1
    assert violations[0].section_id == "clinical_alerts"
    assert violations[0].severity == "HIGH"
    assert "nên dùng" in violations[0].matched_text


def test_detects_nen_tang():
    sections = [_section("clinical_alerts", "Bác sĩ nên tăng liều Metformin.")]
    violations = check_role_drift(sections)
    assert len(violations) >= 1


def test_detects_khuyen_cao():
    sections = [_section("current_medications", "Khuyến cáo bổ sung vitamin D.")]
    violations = check_role_drift(sections)
    assert len(violations) >= 1


def test_detects_english_recommend():
    sections = [_section("diagnoses", "It is recommended to increase Metformin dosage.")]
    violations = check_role_drift(sections)
    assert len(violations) >= 1


def test_detects_consider_adding():
    sections = [_section("clinical_alerts", "Consider adding Aspirin for cardiovascular protection.")]
    violations = check_role_drift(sections)
    assert len(violations) >= 1


def test_violation_records_section_id():
    sections = [_section("current_medications", "Nên bổ sung thêm Omega-3.")]
    violations = check_role_drift(sections)
    assert violations[0].section_id == "current_medications"


def test_multiple_sections_only_flags_offending():
    sections = [
        _section("diagnoses", "Đái tháo đường type 2 (E11)."),
        _section("clinical_alerts", "Nên dùng thêm Aspirin."),
        _section("overview", "Nam, 55 tuổi, bệnh nền ĐTĐ."),
    ]
    violations = check_role_drift(sections)
    assert len(violations) == 1
    assert violations[0].section_id == "clinical_alerts"


def test_empty_sections_returns_empty():
    assert check_role_drift([]) == []
