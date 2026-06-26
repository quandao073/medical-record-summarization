"""Integration test: full pipeline C1->C6 with mock LLM."""

import json
import pytest
from unittest.mock import MagicMock
from pathlib import Path

ROOT = Path(__file__).parent.parent
ASSEMBLED_DIR = ROOT / "data" / "processed" / "assembled"

_MOCK_SECTION_RESPONSE = json.dumps({
    "content": "- Bệnh nhân nam, 55 tuổi [P001-PATIENT-INFO]",
    "source_ids": ["P001-PATIENT-INFO"],
})


class MockLLMClient:
    """Minimal mock implementing BaseLLMClient interface."""

    def __init__(self):
        self.model = "mock-model"

    @property
    def provider_name(self) -> str:
        return "mock"

    def complete(self, system_prompt, user_prompt, **kwargs):
        from src.llm.types import LLMResponse
        return LLMResponse(text=_MOCK_SECTION_RESPONSE, total_tokens=50)


@pytest.fixture
def mock_llm_client():
    return MockLLMClient()


class TestPipelineIntegration:
    @pytest.mark.skipif(
        not (ASSEMBLED_DIR / "P001.json").exists(),
        reason="Assembled data not available",
    )
    def test_full_pipeline_produces_valid_summary(self, mock_llm_client):
        from poc.poc_pipeline import run_poc
        from src.schemas import FinalSummary

        result = run_poc(
            patient_id="P001",
            client=mock_llm_client,
            max_context_chunks=10,
            verbose=False,
        )

        assert isinstance(result, FinalSummary)
        assert result.patient_id == "P001"
        assert len(result.sections) == 9
        assert result.metrics is not None
        assert result.metrics.latency_seconds > 0

    @pytest.mark.skipif(
        not (ASSEMBLED_DIR / "P001.json").exists(),
        reason="Assembled data not available",
    )
    def test_all_sections_have_expected_ids(self, mock_llm_client):
        from poc.poc_pipeline import run_poc
        from src.c4_llm_draft import SECTIONS

        result = run_poc("P001", mock_llm_client, verbose=False)

        section_ids = {s.section_id for s in result.sections}
        for expected_id in SECTIONS:
            assert expected_id in section_ids, f"Missing section: {expected_id}"

    @pytest.mark.skipif(
        not (ASSEMBLED_DIR / "P001.json").exists(),
        reason="Assembled data not available",
    )
    def test_pipeline_with_raw_ehr_dict(self, mock_llm_client):
        """Test pipeline when given raw_ehr dict (DB path) instead of file."""
        from poc.poc_pipeline import run_poc

        ehr_path = ASSEMBLED_DIR / "P001.json"
        raw_ehr = json.loads(ehr_path.read_text(encoding="utf-8"))

        result = run_poc(
            patient_id="P001",
            client=mock_llm_client,
            verbose=False,
            raw_ehr=raw_ehr,
        )

        assert result.patient_id == "P001"
        assert len(result.sections) == 9

    @pytest.mark.skipif(
        not (ASSEMBLED_DIR / "P001.json").exists(),
        reason="Assembled data not available",
    )
    def test_metrics_have_valid_values(self, mock_llm_client):
        from poc.poc_pipeline import run_poc

        result = run_poc("P001", mock_llm_client, verbose=False)

        m = result.metrics
        assert m.total_claims >= 0
        assert m.token_count >= 0
        assert 0 <= m.citation_coverage <= 1.0
        assert m.latency_seconds > 0
