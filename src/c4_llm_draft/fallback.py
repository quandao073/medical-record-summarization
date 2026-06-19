"""Rule-based fallback generators for when LLM is unavailable."""

from __future__ import annotations

from enum import Enum

from src.schemas import SourceChunk


class FallbackStrategy(Enum):
    RULE_BASED = "rule_based"
    EMPTY = "empty"
    FAIL_FAST = "fail_fast"


class FallbackGenerator:

    @staticmethod
    def generate_overview(chunks: list[SourceChunk]) -> str:
        if not chunks:
            return "Chưa thấy ghi nhận trong dữ liệu được cung cấp."

        lines: list[str] = []
        patient_info = next((c for c in chunks if c.source_type == "patient_info"), None)
        diagnoses = [c for c in chunks if c.source_type == "diagnoses"][:3]

        if patient_info:
            lines.append(patient_info.content)
        if diagnoses:
            dx_text = ", ".join(c.content for c in diagnoses)
            lines.append(f"Chẩn đoán: {dx_text}")

        return ". ".join(lines) if lines else "Chưa có thông tin tổng quan."

    @staticmethod
    def generate_medications(chunks: list[SourceChunk]) -> str:
        meds = [c for c in chunks if c.source_type == "medications"]
        if not meds:
            return "Chưa có thông tin về thuốc."
        return "\n".join(f"- {c.content}" for c in meds[:10])

    @staticmethod
    def generate_labs(chunks: list[SourceChunk]) -> str:
        labs = [c for c in chunks if c.source_type == "labs" and c.metadata.get("is_abnormal")]
        if not labs:
            labs = [c for c in chunks if c.source_type == "labs"]
        if not labs:
            return "Chưa có xét nghiệm bất thường."
        return "\n".join(f"- {c.content}" for c in labs[:15])

    @staticmethod
    def generate_allergies(chunks: list[SourceChunk]) -> str:
        allergies = [c for c in chunks if c.source_type == "allergies"]
        if not allergies:
            return "Chưa có dị ứng ghi nhận."
        return "\n".join(f"- {c.content}" for c in allergies)


FALLBACK_GENERATORS: dict[str, object] = {
    "overview": FallbackGenerator.generate_overview,
    "current_medications": FallbackGenerator.generate_medications,
    "abnormal_labs": FallbackGenerator.generate_labs,
    "allergies": FallbackGenerator.generate_allergies,
    "reason_for_visit": lambda chunks: chunks[0].content if chunks else "Chưa rõ lý do khám.",
}


def generate_fallback_content(section_id: str, chunks: list[SourceChunk]) -> str:
    generator = FALLBACK_GENERATORS.get(section_id)
    if generator:
        return generator(chunks)

    if not chunks:
        return "Chưa thấy ghi nhận trong dữ liệu được cung cấp."

    return "\n".join(f"- {c.content}" for c in chunks[:10])
