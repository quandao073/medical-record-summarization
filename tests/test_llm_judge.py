"""Tests for LLM-as-judge guardrail."""
from unittest.mock import patch, MagicMock
import pytest
from src.schemas import SummarySection, SourceChunk, JudgeResult
from src.guardrails.llm_judge import judge_sections


def _section(sid: str, content: str = "content") -> SummarySection:
    return SummarySection(section_id=sid, content=content)


def _chunk(sid: str, content: str = "ctx") -> SourceChunk:
    return SourceChunk(source_id=sid, source_type="labs", patient_id="P1", content=content)


_CFG_ENABLED = {
    "guardrails": {
        "llm_judge": {
            "enabled": True,
            "model": "gpt-4o-mini",
            "mode": "critical",
            "sections": ["diagnoses", "current_medications", "clinical_alerts"],
        }
    }
}

_CFG_DISABLED = {"guardrails": {"llm_judge": {"enabled": False}}}


def test_disabled_returns_empty():
    result = judge_sections([_section("diagnoses")], [], _CFG_DISABLED)
    assert result == []


def test_section_not_in_configured_list_skipped():
    cfg = {"guardrails": {"llm_judge": {
        "enabled": True, "model": "gpt-4o-mini",
        "mode": "critical", "sections": ["diagnoses"],
    }}}
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(text='{"verdict": "PASS", "reason": "ok"}')
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections([_section("diagnoses"), _section("overview")], [], cfg)
    assert len(results) == 1
    assert results[0].section_id == "diagnoses"


def test_pass_verdict_returned():
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(
        text='{"verdict": "PASS", "reason": "All claims supported by source"}'
    )
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections([_section("diagnoses")], [], _CFG_ENABLED)
    assert results[0].verdict == "PASS"
    assert results[0].reason == "All claims supported by source"


def test_fail_verdict_returned():
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(
        text='{"verdict": "FAIL", "reason": "Invented drug not in EHR"}'
    )
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections([_section("diagnoses")], [], _CFG_ENABLED)
    assert results[0].verdict == "FAIL"


def test_openai_error_returns_unknown_not_pass():
    with patch("src.guardrails.llm_judge.create_llm_client", side_effect=Exception("timeout")):
        results = judge_sections([_section("diagnoses")], [], _CFG_ENABLED)
    assert results[0].verdict == "UNKNOWN"
    assert results[0].reason == "judge_unavailable"


def test_invalid_json_from_llm_returns_unknown():
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(text="not valid json at all")
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections([_section("diagnoses")], [], _CFG_ENABLED)
    assert results[0].verdict == "UNKNOWN"


def test_mode_all_judges_all_sections():
    cfg = {"guardrails": {"llm_judge": {
        "enabled": True, "model": "gpt-4o-mini", "mode": "all",
        "sections": ["diagnoses"],
    }}}
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(text='{"verdict": "PASS", "reason": "ok"}')
    sections = [_section("diagnoses"), _section("overview"), _section("allergies")]
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections(sections, [], cfg)
    assert len(results) == 3


def test_result_section_id_matches_input():
    mock_client = MagicMock()
    mock_client.complete.return_value = MagicMock(text='{"verdict": "PASS", "reason": "ok"}')
    with patch("src.guardrails.llm_judge.create_llm_client", return_value=mock_client):
        results = judge_sections([_section("current_medications")], [], _CFG_ENABLED)
    assert results[0].section_id == "current_medications"
