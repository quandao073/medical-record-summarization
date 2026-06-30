"""LLM-as-judge guardrail — gpt-4o-mini reviews critical sections post-C6."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.logging_config import get_logger
from src.schemas import SummarySection, SourceChunk, JudgeResult
from src.llm import create_llm_client
from src.c4_llm_draft.summarizer import format_chunks_as_context
from src.c4_llm_draft.prompts import SECTION_LABELS

_logger = get_logger("guardrails.judge")

_DEFAULT_SECTIONS = ["diagnoses", "current_medications", "clinical_alerts"]

_JUDGE_SYSTEM = (
    "You are a clinical safety reviewer. "
    "Evaluate whether a Vietnamese clinical summary stays within its defined role."
)


def _build_judge_prompt(section: SummarySection, chunks: list[SourceChunk]) -> str:
    label = SECTION_LABELS.get(section.section_id, section.section_id)
    context = format_chunks_as_context(chunks, max_chunks=20)
    return f"""Đánh giá đoạn tóm tắt lâm sàng bên dưới.

[SUMMARY — {label}]
{section.content}

[SOURCE EHR CHUNKS]
{context}

Trả về JSON: {{"verdict": "PASS" hoặc "FAIL", "reason": "một câu giải thích ngắn"}}

Trả về FAIL nếu summary:
1. Chứa thông tin không có trong source chunks
2. Đưa ra khuyến nghị điều trị (nên dùng, cần tăng liều, khuyến cáo...)
3. Tự thêm ICD-10 hoặc tên thuốc không xuất hiện trong chunks
"""


def _judge_one(
    section: SummarySection,
    chunks: list[SourceChunk],
    model: str,
) -> JudgeResult:
    try:
        client = create_llm_client(provider="openai", model=model)
        prompt = _build_judge_prompt(section, chunks)
        resp = client.complete(
            system_prompt=_JUDGE_SYSTEM,
            user_prompt=prompt,
            json_mode=True,
        )
        data = json.loads(resp.text)
        verdict = str(data.get("verdict", "UNKNOWN")).upper()
        if verdict not in ("PASS", "FAIL"):
            verdict = "UNKNOWN"
        return JudgeResult(
            section_id=section.section_id,
            verdict=verdict,
            reason=data.get("reason", ""),
        )
    except Exception as exc:
        _logger.info(
            "Judge unavailable",
            extra={"section_id": section.section_id, "error": str(exc)},
        )
        return JudgeResult(
            section_id=section.section_id,
            verdict="UNKNOWN",
            reason="judge_unavailable",
        )


def judge_sections(
    sections: list[SummarySection],
    chunks: list[SourceChunk],
    config: dict,
) -> list[JudgeResult]:
    """Run gpt-4o-mini judge on configured sections. Returns empty list if disabled."""
    judge_cfg = config.get("guardrails", {}).get("llm_judge", {})
    if not judge_cfg.get("enabled", True):
        return []

    model = judge_cfg.get("model", "gpt-4o-mini")
    mode = judge_cfg.get("mode", "critical")

    if mode == "all":
        target_ids = {s.section_id for s in sections}
    else:
        target_ids = set(judge_cfg.get("sections", _DEFAULT_SECTIONS))

    targets = [s for s in sections if s.section_id in target_ids]
    if not targets:
        return []

    results: list[JudgeResult | None] = [None] * len(targets)
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        future_to_idx = {
            pool.submit(_judge_one, sec, chunks, model): i
            for i, sec in enumerate(targets)
        }
        for future in as_completed(future_to_idx):
            results[future_to_idx[future]] = future.result()

    return results  # type: ignore[return-value]
