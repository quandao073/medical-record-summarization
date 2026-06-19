"""C4 — LLM draft generation for clinical sections."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.llm import BaseLLMClient
from src.llm.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.schemas import SourceChunk, SummarySection

from .fallback import FallbackStrategy, generate_fallback_content
from .prompts import SYSTEM_PROMPT, SECTION_LABELS, SECTION_GUIDELINES, build_section_prompt

_llm_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=60,
    success_threshold=2,
    name="c4_llm_draft",
)


def get_circuit_breaker() -> CircuitBreaker:
    return _llm_circuit_breaker


def format_chunks_as_context(chunks: list[SourceChunk], max_chunks: int = 60) -> str:
    lines = []
    for chunk in chunks[:max_chunks]:
        date_str = f" [{chunk.date}]" if chunk.date else ""
        lines.append(f"[{chunk.source_id}]{date_str} ({chunk.source_type}): {chunk.content}")
    return "\n".join(lines)


def format_chunks_by_encounter(chunks: list[SourceChunk], max_chunks: int = 60) -> str:
    by_enc: dict[str, list[SourceChunk]] = defaultdict(list)
    for c in chunks[:max_chunks]:
        key = c.encounter_id or "UNKNOWN"
        by_enc[key].append(c)

    sorted_enc_ids = sorted(
        by_enc.keys(),
        key=lambda eid: min(c.date or "9999-99-99" for c in by_enc[eid]),
    )

    lines = []
    for enc_id in sorted_enc_ids:
        enc_chunks = by_enc[enc_id]
        dates = [c.date for c in enc_chunks if c.date]
        enc_date = min(dates) if dates else "?"
        lines.append(f"\n=== Encounter {enc_id} [{enc_date}] ===")
        for c in enc_chunks:
            lines.append(f"[{c.source_id}] ({c.source_type}): {c.content}")

    return "\n".join(lines)


def _call_llm(
    prompt: str,
    client: BaseLLMClient,
    max_tokens: int = 1200,
    retries: int = 3,
) -> tuple[str, int]:
    def _do_call():
        resp = client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return resp.text, resp.total_tokens

    for attempt in range(retries):
        try:
            return _llm_circuit_breaker.call(_do_call)
        except CircuitOpenError:
            raise
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"    [RETRY {attempt+1}/{retries}] {e}")
            time.sleep(2 ** attempt)

    return "", 0


def _extract_json_object(text: str) -> str:
    text = text.strip()

    if "```" in text:
        lines = text.splitlines()
        fenced_lines: list[str] = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                fenced_lines.append(line)
        if fenced_lines:
            text = "\n".join(fenced_lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return text[start : end + 1]


def _normalise_content(value: object) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            s = str(item).strip()
            if s and not s.startswith(("- ", "* ")):
                s = "- " + s
            if s:
                parts.append(s)
        return "\n".join(parts)
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def _clean_content(content: str) -> str:
    """Remove source_id references and raw field names that leak into content."""
    import re
    content = re.sub(r'\s*\[P\d+-[A-Z0-9\-]+\]', '', content)
    content = content.replace("overweight_bmi", "thừa cân")
    content = content.replace("underweight_bmi", "thiếu cân")
    content = content.replace("normal_bmi", "BMI bình thường")
    content = content.replace("obese_bmi", "béo phì")
    return content.strip()


def _unwrap_nested_json(content: str, section_id: str) -> str:
    """If content is itself a JSON string containing the section structure, extract the inner content."""
    stripped = content.strip()
    if not stripped.startswith("{"):
        return content
    try:
        inner = json.loads(stripped)
        if isinstance(inner, dict):
            if section_id in inner and isinstance(inner[section_id], dict):
                return inner[section_id].get("content", content)
            if "content" in inner:
                return inner["content"]
    except (json.JSONDecodeError, ValueError):
        pass
    return content


def parse_section_response(text: str, section_id: str) -> dict:
    try:
        raw = _extract_json_object(text)
        data = json.loads(raw)

        if section_id in data and isinstance(data[section_id], dict):
            result = data[section_id]
        elif section_id in data and isinstance(data[section_id], str):
            result = {"content": data[section_id], "source_ids": []}
        elif "content" in data:
            result = data
        else:
            inner = next(
                (v for v in data.values() if isinstance(v, dict) and "content" in v),
                None,
            )
            if inner:
                result = inner
            else:
                result = {"content": str(data), "source_ids": []}
    except (json.JSONDecodeError, ValueError):
        result = {"content": text.strip(), "source_ids": []}

    content = _normalise_content(result.get("content", ""))
    content = _unwrap_nested_json(content, section_id)
    result["content"] = _clean_content(content)
    if not result["content"]:
        result["content"] = "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
    return result


LOCAL_PROVIDERS = {"lmstudio", "ollama"}


def generate_section_drafts(
    section_ids: list[str],
    section_prompts: dict[str, str],
    section_chunks_map: dict[str, list[SourceChunk]],
    client: BaseLLMClient,
    fallback_strategy: FallbackStrategy = FallbackStrategy.RULE_BASED,
    verbose: bool = True,
) -> tuple[list[SummarySection], int]:
    """Generate LLM drafts for all sections concurrently.

    On LLM failure the *fallback_strategy* determines behaviour:
      RULE_BASED  – generate content from raw chunks (no LLM)
      EMPTY       – return a placeholder message
      FAIL_FAST   – raise immediately
    """
    is_local = client.provider_name in LOCAL_PROVIDERS
    max_workers = min(3, len(section_ids)) if is_local else len(section_ids)

    if verbose:
        extra = f" (local mode, {max_workers} workers)" if is_local else ""
        print(f"[C4→LLM] Generating {len(section_ids)} sections in parallel...{extra}")

    llm_results: dict[str, tuple[str | None, int, Exception | None]] = {}
    failed_sections: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_section = {
            pool.submit(_call_llm, section_prompts[sid], client): sid
            for sid in section_ids
        }
        for future in as_completed(future_to_section):
            section_id = future_to_section[future]
            try:
                raw_text, tokens = future.result(timeout=120)
                llm_results[section_id] = (raw_text, tokens, None)
            except Exception as e:
                failed_sections.append(section_id)
                llm_results[section_id] = (None, 0, e)
                if verbose:
                    print(f"[C4→LLM] {section_id} FAILED: {e}")

    draft_sections: list[SummarySection] = []
    total_tokens = 0

    for section_id in section_ids:
        raw_text, tokens, err = llm_results[section_id]

        if err is None:
            total_tokens += tokens
            parsed = parse_section_response(raw_text, section_id)
            content = parsed.get("content", "Chưa thấy ghi nhận trong dữ liệu được cung cấp.")
        else:
            if fallback_strategy == FallbackStrategy.FAIL_FAST:
                raise type(err)(f"Section {section_id} failed: {err}") from err

            if fallback_strategy == FallbackStrategy.RULE_BASED:
                content = generate_fallback_content(
                    section_id,
                    section_chunks_map.get(section_id, []),
                )
                if verbose:
                    print(f"[C4→FALLBACK] {section_id}: Rule-based generation")
            else:
                content = "Chưa thể tạo section này do lỗi hệ thống."

        draft_sections.append(SummarySection(
            section_id=section_id,
            content=content,
            cited_claims=[],
        ))

        if err is None and verbose:
            print(f"[C4→LLM] {section_id}: OK ({tokens} tok, {len(section_chunks_map.get(section_id, []))} chunks)")

    if failed_sections and verbose:
        print(f"[C4] {len(failed_sections)}/{len(section_ids)} sections used fallback: {failed_sections}")

    return draft_sections, total_tokens
