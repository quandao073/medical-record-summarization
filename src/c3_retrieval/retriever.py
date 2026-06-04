"""
C3 — Section-wise Retrieval.
Filters SourceChunks to only the types relevant for each summary section,
then applies special filters (is_abnormal, is_current) and sort order.
"""

from __future__ import annotations
from src.schemas import SourceChunk


# Map: section_id -> allowed source_types
SECTION_SOURCE_TYPES: dict[str, list[str]] = {
    "overview":            ["patient_info", "diagnoses", "vitals"],
    "reason_for_visit":    ["clinical_notes"],
    "medical_history":     ["clinical_notes", "diagnoses", "allergies"],
    "current_medications": ["medications"],
    "allergies":           ["allergies", "clinical_notes"],
    "abnormal_labs":       ["labs"],
    "diagnoses":           ["diagnoses"],
    "treatment_timeline":  ["labs", "medications", "diagnoses", "clinical_notes"],
    "clinical_alerts":     ["labs", "vitals", "allergies", "diagnoses"],
}

# Sections where we want most-recent encounter first
_RECENCY_FIRST = {"diagnoses", "current_medications"}

# Sections where chronological order matters (oldest→newest)
_CHRONOLOGICAL = {"treatment_timeline"}


def retrieve_for_section(
    chunks: list[SourceChunk],
    section_id: str,
    max_chunks: int = 15,
) -> list[SourceChunk]:
    """
    Return up to max_chunks SourceChunks relevant for section_id.

    Filters applied in order:
      1. source_type whitelist per section
      2. For abnormal_labs:       only is_abnormal=True or is_critical=True
      3. For current_medications: prefer is_current=True (fall back to all if none)
      4. Sort: recency-first for diagnoses/medications; chronological for timeline
    """
    allowed = SECTION_SOURCE_TYPES.get(section_id)
    if allowed is None:
        # Unknown section: return up to max_chunks from all chunks
        return chunks[:max_chunks]

    filtered = [c for c in chunks if c.source_type in allowed]

    # --- Special filters ---
    if section_id == "abnormal_labs":
        abnormal = [
            c for c in filtered
            if c.metadata.get("is_abnormal") or c.metadata.get("is_critical")
        ]
        if abnormal:
            filtered = abnormal

    if section_id == "current_medications":
        current = [c for c in filtered if c.metadata.get("is_current")]
        if current:
            filtered = current

    # --- Sort ---
    if section_id in _RECENCY_FIRST:
        filtered = sorted(filtered, key=lambda c: c.date or "", reverse=True)
    elif section_id in _CHRONOLOGICAL:
        filtered = sorted(filtered, key=lambda c: c.date or "")

    return filtered[:max_chunks]
