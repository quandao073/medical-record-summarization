"""Tests for guardrail schema types."""
from src.schemas import (
    InjectionAlert, SafetyViolation, JudgeResult, GuardrailResult, FinalSummary,
)


def test_injection_alert_fields():
    alert = InjectionAlert(source_id="P001-C1", matched_pattern="ignore previous")
    assert alert.source_id == "P001-C1"
    assert alert.matched_pattern == "ignore previous"


def test_safety_violation_fields():
    v = SafetyViolation(section_id="diagnoses", matched_text="nên dùng", severity="HIGH")
    assert v.section_id == "diagnoses"
    assert v.severity == "HIGH"


def test_judge_result_verdicts():
    for verdict in ("PASS", "FAIL", "UNKNOWN"):
        jr = JudgeResult(section_id="diagnoses", verdict=verdict, reason="ok")
        assert jr.verdict == verdict


def test_guardrail_result_defaults_to_empty_lists():
    gr = GuardrailResult()
    assert gr.injection_alerts == []
    assert gr.safety_violations == []
    assert gr.judge_results == []


def test_final_summary_has_guardrail_field():
    fs = FinalSummary(patient_id="P001")
    assert hasattr(fs, "guardrail")
    assert isinstance(fs.guardrail, GuardrailResult)
    assert fs.guardrail.injection_alerts == []
