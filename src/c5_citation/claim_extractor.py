"""
C5 — Citation Pipeline: Atomic Claim Extractor.
Splits a SummarySection's content into individual verifiable claims
and marks each as critical or non-critical.
"""

from __future__ import annotations
import re
from src.schemas import CitedClaim, SummarySection, is_structural_content

_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Patterns that signal a CRITICAL claim
# ---------------------------------------------------------------------------
# Drug name + dosage: "Metformin 1000 mg", "Amlodipine 5mg"
_DRUG_DOSE_RE = re.compile(r"\b\d+[\.,]?\d*\s*mg\b", re.IGNORECASE)

# Lab value + unit: "9.2 %", "3.4 mmol/L", "42 mg/g", "88 µmol/L", "48 U/L"
# Allows integer or decimal values (e.g. "88 µmol/L" as well as "9.2%")
_LAB_VALUE_RE = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s*(%|mmol/L|mg/g|µmol/L|umol/L|U/L|IU/L|g/dL|ng/mL)\b",
    re.IGNORECASE,
)

# ICD-10 codes: "E11", "I10", "E78.5", "N18.3"
_ICD_RE = re.compile(r"\b[A-Z]\d{2}(\.\d+)?\b")

# Allergy keywords in Vietnamese
_ALLERGY_RE = re.compile(r"dị ứng|phản ứng dị ứng|allerg", re.IGNORECASE)

# Abnormal vital signs: blood pressure, SpO2, heart rate with values
_VITAL_RE = re.compile(
    r"(huyết áp|HA|SpO2|mạch|nhịp tim|nhiệt độ)\s*[:\-]?\s*\d+",
    re.IGNORECASE,
)

# HbA1c with a numeric value (e.g. "HbA1c: 9.2%") — mention without value is not critical
_HBA1C_RE = re.compile(r"HbA1c\s*[:\-]?\s*\d+", re.IGNORECASE)


def _is_critical(text: str) -> bool:
    """Return True if the claim text contains a clinically critical data point."""
    return bool(
        _DRUG_DOSE_RE.search(text)
        or _LAB_VALUE_RE.search(text)
        or _ICD_RE.search(text)
        or _ALLERGY_RE.search(text)
        or _VITAL_RE.search(text)
        or _HBA1C_RE.search(text)
    )


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+"          # after sentence-ending punctuation
    r"|(?<=\n)\s*[-•]\s*"     # bullet list items
    r"|\n{2,}"                 # double newlines
)


def _split_sentences(text: str) -> list[str]:
    parts = _SPLIT_RE.split(text)
    cleaned = []
    for p in parts:
        p = p.strip().lstrip("-•").strip()
        if len(p) >= 10:
            cleaned.append(p)
    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EMPTY_MARKERS = (
    "Chưa thấy ghi nhận",
    "[LỖI",
    "Không có thông tin",
)


def extract_claims(section: SummarySection) -> list[CitedClaim]:
    """
    Split section.content into atomic CitedClaims.
    Each claim starts with status=NO_CITATION; evidence matching happens in C5b.
    Returns [] for empty / error sections.
    """
    content = (section.content or "").strip()
    if not content:
        return []
    # Only skip if the entire content is a single short line starting with an empty/error marker
    first_line = content.split("\n")[0].strip()
    if len(content.split("\n")) <= 1 or content.strip() == first_line:
        if any(first_line.startswith(m) for m in _EMPTY_MARKERS):
            return []

    sentences = _split_sentences(content)

    if not sentences:
        # Whole section as a single claim
        sentences = [content]

    # Drop exact duplicate sentences within the same section (e.g. the LLM
    # emitting "Uống buổi sáng." once per drug). Keep first occurrence, preserve order.
    seen: set[str] = set()
    unique_sentences: list[str] = []
    for s in sentences:
        key = _WS_RE.sub(" ", s.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique_sentences.append(s)

    return [
        CitedClaim(
            claim_text=s,
            is_critical=_is_critical(s),
            status="NO_CITATION",
            is_structural=is_structural_content(s),
        )
        for s in unique_sentences
    ]

