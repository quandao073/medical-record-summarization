"""Guardrail orchestrator — runs output guard + judge and assembles GuardrailResult."""
from __future__ import annotations

from pathlib import Path

import yaml

from src.schemas import SummarySection, SourceChunk, InjectionAlert, GuardrailResult
from src.guardrails.output_guard import check_role_drift
from src.guardrails.llm_judge import judge_sections

_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "config.yaml"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_guardrails(
    sections: list[SummarySection],
    chunks: list[SourceChunk],
    injection_alerts: list[InjectionAlert],
) -> GuardrailResult:
    """Run output guard + LLM judge; combine with pre-collected injection_alerts."""
    config = _load_config()
    guardrail_cfg = config.get("guardrails", {})

    safety_violations = []
    if guardrail_cfg.get("output", {}).get("enabled", True):
        safety_violations = check_role_drift(sections)

    judge_results = []
    if guardrail_cfg.get("llm_judge", {}).get("enabled", True):
        judge_results = judge_sections(sections, chunks, config)

    return GuardrailResult(
        injection_alerts=injection_alerts,
        safety_violations=safety_violations,
        judge_results=judge_results,
    )
