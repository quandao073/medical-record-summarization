"""Tests for the LLM fallback strategy."""

import pytest

from src.c4_llm_draft.fallback import (
    FallbackStrategy,
    FallbackGenerator,
    generate_fallback_content,
)
from src.schemas import SourceChunk


def _make_chunk(source_type: str, content: str, **kwargs) -> SourceChunk:
    return SourceChunk(
        source_id=f"TEST-{source_type.upper()}-001",
        source_type=source_type,
        patient_id="P999",
        content=content,
        **kwargs,
    )


class TestFallbackGenerator:
    def test_overview_with_diagnoses(self):
        chunks = [
            _make_chunk("patient_info", "Nguyễn Văn A, nam, 55 tuổi"),
            _make_chunk("diagnoses", "Đái tháo đường type 2"),
            _make_chunk("diagnoses", "Tăng huyết áp"),
        ]
        result = FallbackGenerator.generate_overview(chunks)
        assert "Nguyễn Văn A" in result
        assert "Đái tháo đường" in result

    def test_overview_empty(self):
        result = FallbackGenerator.generate_overview([])
        assert result == "Chưa thấy ghi nhận trong dữ liệu được cung cấp."

    def test_medications(self):
        chunks = [
            _make_chunk("medications", "Metformin 500mg 2 lần/ngày"),
            _make_chunk("medications", "Amlodipine 5mg 1 lần/ngày"),
        ]
        result = FallbackGenerator.generate_medications(chunks)
        assert "Metformin" in result
        assert "Amlodipine" in result
        assert result.startswith("- ")

    def test_medications_empty(self):
        result = FallbackGenerator.generate_medications([])
        assert "Chưa có" in result

    def test_labs_with_abnormal(self):
        chunks = [
            _make_chunk("labs", "HbA1c: 8.5% (cao)", metadata={"is_abnormal": True}),
            _make_chunk("labs", "Glucose: 5.0 mmol/L", metadata={"is_abnormal": False}),
        ]
        result = FallbackGenerator.generate_labs(chunks)
        assert "HbA1c" in result

    def test_labs_no_abnormal_falls_back(self):
        chunks = [
            _make_chunk("labs", "Glucose: 5.0 mmol/L", metadata={"is_abnormal": False}),
        ]
        result = FallbackGenerator.generate_labs(chunks)
        assert "Glucose" in result

    def test_allergies(self):
        chunks = [
            _make_chunk("allergies", "Penicillin — phát ban"),
        ]
        result = FallbackGenerator.generate_allergies(chunks)
        assert "Penicillin" in result

    def test_allergies_empty(self):
        result = FallbackGenerator.generate_allergies([])
        assert "Chưa có" in result


class TestGenerateFallbackContent:
    def test_known_section(self):
        chunks = [_make_chunk("medications", "Aspirin 81mg")]
        result = generate_fallback_content("current_medications", chunks)
        assert "Aspirin" in result

    def test_unknown_section_uses_bullet_list(self):
        chunks = [
            _make_chunk("misc", "Line 1"),
            _make_chunk("misc", "Line 2"),
        ]
        result = generate_fallback_content("some_unknown_section", chunks)
        assert "- Line 1" in result
        assert "- Line 2" in result

    def test_unknown_section_empty(self):
        result = generate_fallback_content("some_unknown_section", [])
        assert "Chưa thấy" in result
