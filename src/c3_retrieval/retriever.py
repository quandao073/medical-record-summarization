"""
C3 — Section-wise Retrieval.
Filters SourceChunks to only the types relevant for each summary section,
then applies special filters (is_abnormal, is_current, recency) and sort order.

Key principle:
  - Sections showing *current state* (clinical_alerts, abnormal_labs,
    current_medications, reason_for_visit, diagnoses) → latest encounter only.
  - Sections showing *history* (treatment_timeline, medical_history) → all encounters.
  - Overview: latest vitals + diagnoses; patient_info always.
"""

from __future__ import annotations
from src.schemas import SourceChunk


# ---------------------------------------------------------------------------
# Section → allowed source types
# ---------------------------------------------------------------------------

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

# Sections requiring latest-encounter-only filter (current state view).
# Note: abnormal_labs uses _filter_latest_n_encounters(n=2) instead (for trend)
_LATEST_ENCOUNTER_SECTIONS = {
    "current_medications",
    "reason_for_visit",
    "diagnoses",
    "overview",
}

# Sections where chronological order matters (oldest → newest)
_CHRONOLOGICAL = {"treatment_timeline", "medical_history"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_encounter_ids(chunks: list[SourceChunk]) -> set[str]:
    """
    Return the set of encounter_ids that belong to the most recent encounter.
    Ties (same date) are all included.
    Falls back to all encounter_ids if no date info available.
    """
    if not chunks:
        return set()

    enc_max_date: dict[str, str] = {}
    for c in chunks:
        if _is_patient_level(c):
            continue
        d = c.date or ""
        if c.encounter_id not in enc_max_date or d > enc_max_date[c.encounter_id]:
            enc_max_date[c.encounter_id] = d

    if not enc_max_date:
        return set()

    latest_date = max(enc_max_date.values())
    return {eid for eid, d in enc_max_date.items() if d == latest_date}


_PATIENT_LEVEL_ENC = "PATIENT_LEVEL"


def _is_patient_level(chunk: SourceChunk) -> bool:
    return chunk.encounter_id is None or chunk.encounter_id == _PATIENT_LEVEL_ENC


def _filter_latest_encounter(chunks: list[SourceChunk]) -> list[SourceChunk]:
    """
    Keep only chunks whose encounter_id belongs to the most recent encounter.
    Patient-level chunks (encounter_id is None or "PATIENT_LEVEL") are always kept.
    """
    latest = _latest_encounter_ids(chunks)
    if not latest:
        return chunks
    result = [c for c in chunks if _is_patient_level(c) or c.encounter_id in latest]
    return result if result else chunks


def _filter_latest_n_encounters(chunks: list[SourceChunk], n: int = 2) -> list[SourceChunk]:
    """
    Keep chunks from the n most recent distinct encounters.
    Used for abnormal_labs to include current value + previous value for trend.
    Patient-level chunks are always kept.
    """
    if not chunks:
        return chunks

    enc_max_date: dict[str, str] = {}
    for c in chunks:
        if _is_patient_level(c):
            continue
        d = c.date or ""
        if c.encounter_id not in enc_max_date or d > enc_max_date[c.encounter_id]:
            enc_max_date[c.encounter_id] = d

    if not enc_max_date:
        return chunks

    latest_n = set(
        sorted(enc_max_date, key=enc_max_date.__getitem__, reverse=True)[:n]
    )
    result = [c for c in chunks if _is_patient_level(c) or c.encounter_id in latest_n]
    return result if result else chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_for_section(
    chunks: list[SourceChunk],
    section_id: str,
    max_chunks: int = 15,
) -> list[SourceChunk]:
    """
    Return up to max_chunks SourceChunks relevant for section_id.

    Filters applied in order:
      1. source_type whitelist per section
      2. Domain-specific filters (is_abnormal, is_current)
      3. Latest-encounter filter for current-state sections
      4. Sort (recency-first or chronological)
    """
    allowed = SECTION_SOURCE_TYPES.get(section_id)
    if allowed is None:
        return chunks[:max_chunks]

    filtered = [c for c in chunks if c.source_type in allowed]

    # ── Domain-specific filters ────────────────────────────────────────────
    if section_id == "abnormal_labs":
        abnormal = [
            c for c in filtered
            if c.metadata.get("is_abnormal") or c.metadata.get("is_critical")
        ]
        if abnormal:
            filtered = abnormal
        # Include last 2 encounters so LabsTable can show trend (current vs previous)
        filtered = _filter_latest_n_encounters(filtered, n=2)

    elif section_id == "current_medications":
        current = [c for c in filtered if c.metadata.get("is_current")]
        if current:
            filtered = current

    # ── Latest-encounter filter (current-state sections) ───────────────────
    if section_id in _LATEST_ENCOUNTER_SECTIONS:
        filtered = _filter_latest_encounter(filtered)

    elif section_id == "clinical_alerts":
        # Labs and vitals → latest encounter only (current state)
        # Allergies and diagnoses → all (always clinically relevant)
        time_sensitive = [c for c in filtered if c.source_type in ("labs", "vitals")]
        always_relevant = [c for c in filtered if c.source_type in ("allergies", "diagnoses")]

        time_sensitive = _filter_latest_encounter(time_sensitive)

        # For labs in clinical_alerts: keep only abnormal ones from latest encounter
        time_sensitive = [
            c for c in time_sensitive
            if c.source_type != "labs"
            or c.metadata.get("is_abnormal")
            or c.metadata.get("is_critical")
        ]
        filtered = time_sensitive + always_relevant

    # ── Sort ───────────────────────────────────────────────────────────────
    if section_id in _CHRONOLOGICAL:
        filtered = sorted(filtered, key=lambda c: c.date or "")
    elif section_id == "allergies":
        # Allergy-type chunks first (primary source), then clinical_notes by recency
        allergy_chunks = [c for c in filtered if c.source_type == "allergies"]
        other_chunks = sorted(
            [c for c in filtered if c.source_type != "allergies"],
            key=lambda c: c.date or "", reverse=True,
        )
        filtered = allergy_chunks + other_chunks
    else:
        # Default: most-recent first, but patient-level chunks always first
        filtered = sorted(
            filtered,
            key=lambda c: ("0" if _is_patient_level(c) else "1", c.date or ""),
            reverse=True,
        )

    return filtered[:max_chunks]
