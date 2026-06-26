"""
C3 — Section-wise Retrieval.
Filters SourceChunks to only the types relevant for each summary section,
then applies special filters (is_abnormal, is_current, recency) and sort order.

Supports two modes:
  - Rule-based only (default, no vector store needed)
  - Hybrid: rule-based hard filter → vector re-rank (when VectorStore provided)

Key principles:
  - Sections showing *current state* (current_medications, reason_for_visit)
    → latest encounter only.
  - Sections showing *cumulative clinical picture* (diagnoses, overview)
    → all encounters, deduplicated by key.
  - Sections showing *trends* (abnormal_labs)
    → latest n encounters + one-time diagnostics.
  - Sections showing *history* (treatment_timeline, medical_history) → all encounters.
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from src.schemas import SourceChunk

if TYPE_CHECKING:
    from src.c3_retrieval.vector_store import VectorStore


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
_LATEST_ENCOUNTER_SECTIONS = {
    "current_medications",
    "reason_for_visit",
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


def _dedup_diagnoses(chunks: list[SourceChunk]) -> list[SourceChunk]:
    """
    Deduplicate diagnosis chunks by ICD-10 code, keeping the latest encounter's
    version of each diagnosis. Diagnoses only present in older encounters are
    preserved (e.g. H06.2 from E001 when E003 only has E05.0).
    """
    if not chunks:
        return chunks

    by_icd: dict[str, SourceChunk] = {}
    for c in sorted(chunks, key=lambda x: x.date or ""):
        icd = c.metadata.get("icd10_code", c.source_id)
        by_icd[icd] = c
    return list(by_icd.values())


def _dedup_labs_with_unique(
    chunks: list[SourceChunk], n_encounters: int = 2,
) -> list[SourceChunk]:
    """
    Keep labs from the latest n encounters for trend display, PLUS any abnormal
    lab from older encounters whose test_name is not represented in the n set.
    This catches one-time diagnostic tests (e.g. TRAb only at E001).
    """
    if not chunks:
        return chunks

    recent = _filter_latest_n_encounters(chunks, n=n_encounters)
    recent_tests = {
        c.metadata.get("test_name", "").lower()
        for c in recent if not _is_patient_level(c)
    }

    recent_ids = {c.source_id for c in recent}
    unique_old = [
        c for c in chunks
        if c.source_id not in recent_ids
        and not _is_patient_level(c)
        and c.metadata.get("test_name", "").lower() not in recent_tests
        and (c.metadata.get("is_abnormal") or c.metadata.get("is_critical"))
    ]

    return recent + unique_old


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SECTION_QUERY: dict[str, str] = {
    "overview":            "thông tin nhân khẩu học bệnh nhân, tuổi, giới tính, chẩn đoán chính, sinh hiệu",
    "reason_for_visit":    "lý do khám bệnh, triệu chứng chính, bệnh sử hiện tại",
    "medical_history":     "tiền sử bệnh, tiền sử gia đình, bệnh nền, phẫu thuật trước đó",
    "current_medications": "thuốc đang dùng hiện tại, liều lượng, tần suất uống thuốc",
    "allergies":           "dị ứng thuốc, dị ứng thức ăn, phản ứng dị ứng, mức độ nghiêm trọng",
    "abnormal_labs":       "xét nghiệm bất thường, HbA1c, glucose, creatinine, cholesterol",
    "diagnoses":           "chẩn đoán bệnh, mã ICD-10, bệnh chính, bệnh kèm, biến chứng",
    "treatment_timeline":  "diễn biến điều trị, thay đổi thuốc, kết quả xét nghiệm theo thời gian",
    "clinical_alerts":     "cảnh báo lâm sàng, dị ứng nghiêm trọng, xét nghiệm nguy hiểm, tương tác thuốc",
}


def retrieve_for_section(
    chunks: list[SourceChunk],
    section_id: str,
    max_chunks: int = 15,
    vector_store: Optional["VectorStore"] = None,
) -> list[SourceChunk]:
    """
    Return up to max_chunks SourceChunks relevant for section_id.

    Filters applied in order:
      1. source_type whitelist per section
      2. Domain-specific filters (is_abnormal, is_current, dedup)
      3. Encounter filter (latest / n-latest / cumulative by section)
      4. Sort: vector re-rank if vector_store provided, else recency/chronological
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
        # Latest 2 encounters for trend + unique diagnostic tests from older encounters
        filtered = _dedup_labs_with_unique(filtered, n_encounters=2)

    elif section_id == "current_medications":
        current = [c for c in filtered if c.metadata.get("is_current")]
        if current:
            filtered = current

    elif section_id == "diagnoses":
        # All encounters, deduplicated by ICD code (latest version wins)
        filtered = _dedup_diagnoses(filtered)

    # ── Encounter filter ─────────────────────────────────────────────────
    if section_id in _LATEST_ENCOUNTER_SECTIONS:
        filtered = _filter_latest_encounter(filtered)

    elif section_id == "overview":
        # Vitals: latest encounter only (current state)
        # Diagnoses: all encounters, deduplicated by ICD code
        # Patient_info: always included
        vitals = [c for c in filtered if c.source_type == "vitals"]
        diagnoses = [c for c in filtered if c.source_type == "diagnoses"]
        other = [c for c in filtered if c.source_type not in ("vitals", "diagnoses")]
        vitals = _filter_latest_encounter(vitals)
        diagnoses = _dedup_diagnoses(diagnoses)
        filtered = vitals + diagnoses + other

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

    # ── Sort / Re-rank ────────────────────────────────────────────────────
    if vector_store is not None and section_id in SECTION_QUERY and filtered:
        filtered = _hybrid_rerank(filtered, section_id, vector_store, max_chunks)
    elif section_id in _CHRONOLOGICAL:
        filtered = sorted(filtered, key=lambda c: c.date or "")
    elif section_id == "allergies":
        allergy_chunks = [c for c in filtered if c.source_type == "allergies"]
        other_chunks = sorted(
            [c for c in filtered if c.source_type != "allergies"],
            key=lambda c: c.date or "", reverse=True,
        )
        filtered = allergy_chunks + other_chunks
    else:
        patient_level = sorted(
            [c for c in filtered if _is_patient_level(c)],
            key=lambda c: c.date or "",
            reverse=True,
        )
        encounter_level = sorted(
            [c for c in filtered if not _is_patient_level(c)],
            key=lambda c: c.date or "",
            reverse=True,
        )
        filtered = patient_level + encounter_level

    return filtered[:max_chunks]


def _hybrid_rerank(
    rule_filtered: list[SourceChunk],
    section_id: str,
    vector_store: "VectorStore",
    max_chunks: int,
) -> list[SourceChunk]:
    """Re-rank rule-filtered chunks using vector similarity scores."""
    query = SECTION_QUERY[section_id]
    allowed_types = [c.source_type for c in rule_filtered]
    vs_results = vector_store.search(query, top_k=max_chunks * 3, allowed_source_types=allowed_types)

    rule_ids = {c.source_id for c in rule_filtered}
    scored: dict[str, float] = {}
    for chunk, score in vs_results:
        if chunk.source_id in rule_ids:
            scored[chunk.source_id] = score

    # Chunks that passed rule filter but weren't in vector results get score 0
    for c in rule_filtered:
        scored.setdefault(c.source_id, 0.0)

    chunk_map = {c.source_id: c for c in rule_filtered}

    if section_id in _CHRONOLOGICAL:
        return sorted(
            rule_filtered,
            key=lambda c: (c.date or "", scored.get(c.source_id, 0.0)),
        )
    else:
        # patient_info always first, then patient-level, then rest — within tiers, rank by score
        def _rank_key(c: SourceChunk) -> tuple:
            tier = 2 if c.source_type == "patient_info" else (1 if _is_patient_level(c) else 0)
            return (tier, scored.get(c.source_id, 0.0))

        return sorted(rule_filtered, key=_rank_key, reverse=True)
