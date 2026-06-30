"""Tests for guardrail orchestrator."""
from unittest.mock import patch
from src.schemas import SummarySection, SourceChunk, InjectionAlert, GuardrailResult, SafetyViolation
from src.guardrails import run_guardrails


def _section(sid: str, content: str = "ok") -> SummarySection:
    return SummarySection(section_id=sid, content=content)


def test_returns_guardrail_result_instance():
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": False}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails([], [], [])
    assert isinstance(result, GuardrailResult)


def test_injection_alerts_passed_through():
    alerts = [InjectionAlert(source_id="C1", matched_pattern="ignore previous")]
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": False}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails([], [], alerts)
    assert len(result.injection_alerts) == 1
    assert result.injection_alerts[0].source_id == "C1"


def test_output_disabled_no_violations():
    sections = [_section("clinical_alerts", "Nên dùng thêm Aspirin.")]
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": False}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails(sections, [], [])
    assert result.safety_violations == []


def test_output_enabled_detects_violation():
    sections = [_section("clinical_alerts", "Nên dùng thêm Aspirin.")]
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": True}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails(sections, [], [])
    assert len(result.safety_violations) >= 1


def test_all_disabled_returns_empty_lists():
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": False}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails([], [], [])
    assert result.injection_alerts == []
    assert result.safety_violations == []
    assert result.judge_results == []


def test_judge_disabled_no_judge_results():
    with patch("src.guardrails.orchestrator._load_config", return_value={
        "guardrails": {"output": {"enabled": False}, "llm_judge": {"enabled": False}}
    }):
        result = run_guardrails([_section("diagnoses")], [], [])
    assert result.judge_results == []


def test_importable_from_package():
    from src.guardrails import run_guardrails as rg
    assert callable(rg)
