"""
C5 — Citation Pipeline: Evidence Matcher.
For each CitedClaim, searches the SourceChunk list for supporting evidence
and assigns a ClaimStatus based on match quality.
"""

from __future__ import annotations
import re
from src.schemas import CitedClaim, SourceChunk, ClaimStatus


# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_STOPWORDS = {
    "và", "hoặc", "của", "trong", "là", "có", "được", "cho", "với",
    "a", "an", "the", "and", "or", "of", "in", "is", "are", "for",
}


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text.lower().strip())


def _tokens(text: str) -> set[str]:
    words = set(_norm(text).split())
    return words - _STOPWORDS


def _keyword_overlap(claim_text: str, chunk_content: str, min_overlap: int = 2) -> bool:
    return len(_tokens(claim_text) & _tokens(chunk_content)) >= min_overlap


# ---------------------------------------------------------------------------
# Exact metadata match per source type
# ---------------------------------------------------------------------------

def _exact_match(claim_text: str, chunk: SourceChunk) -> bool:
    """
    True when structured metadata from the chunk is explicitly mentioned in the claim.
    Higher precision than keyword overlap.
    """
    ct = _norm(claim_text)
    meta = chunk.metadata
    stype = chunk.source_type

    if stype == "medications":
        drug = _norm(meta.get("drug_name", ""))
        if drug and drug in ct:
            # Require dose/strength also present for full exact match
            strength = _norm(str(meta.get("strength", "")))
            if strength and strength in ct:
                return True

    elif stype == "labs":
        test = _norm(meta.get("test_name", ""))
        if test and test in ct:
            val = str(meta.get("value", ""))
            if val and val in ct:
                return True

    elif stype == "diagnoses":
        icd = meta.get("icd10_code", "")
        dname = _norm(meta.get("diagnosis_name", ""))
        if (icd and icd in claim_text) or (dname and len(dname) > 3 and dname in ct):
            return True

    elif stype == "allergies":
        substance = _norm(meta.get("substance", ""))
        if substance and len(substance) > 3 and substance in ct:
            return True

    elif stype == "vitals":
        # Check BP values
        bp_sys = meta.get("blood_pressure_systolic")
        bp_dia = meta.get("blood_pressure_diastolic")
        if bp_sys and bp_dia:
            bp_str = f"{bp_sys}/{bp_dia}"
            if bp_str in claim_text:
                return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_claim(
    claim: CitedClaim,
    chunks: list[SourceChunk],
    min_keyword_overlap: int = 2,
) -> CitedClaim:
    """
    Search chunks for evidence supporting claim.
    Returns a new CitedClaim with status and citations populated.

    Status assignment:
      SUPPORTED           — at least one exact metadata match
      PARTIALLY_SUPPORTED — keyword overlap ≥ min_keyword_overlap, no exact match
      LOW_CONFIDENCE      — keyword overlap = 1 (below threshold)
      NO_CITATION         — no match at all (for critical claims)
      UNSUPPORTED         — no match at all (for non-critical claims)
    """
    exact_ids: list[str] = []
    keyword_ids: list[str] = []

    for chunk in chunks:
        if _exact_match(claim.claim_text, chunk):
            exact_ids.append(chunk.source_id)
        elif _keyword_overlap(claim.claim_text, chunk.content, min_overlap=min_keyword_overlap):
            keyword_ids.append(chunk.source_id)

    if exact_ids:
        status: ClaimStatus = "SUPPORTED"
        citations = exact_ids[:5]
    elif keyword_ids:
        status = "PARTIALLY_SUPPORTED"
        citations = keyword_ids[:3]
    else:
        # No match
        status = "NO_CITATION" if claim.is_critical else "UNSUPPORTED"
        citations = []

    return claim.model_copy(update={"status": status, "citations": citations})


def match_claims(
    claims: list[CitedClaim],
    chunks: list[SourceChunk],
    min_keyword_overlap: int = 2,
) -> list[CitedClaim]:
    """Batch version of match_claim."""
    return [match_claim(c, chunks, min_keyword_overlap) for c in claims]
