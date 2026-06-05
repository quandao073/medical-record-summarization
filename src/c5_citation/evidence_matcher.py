"""
C5 — Citation Pipeline: Evidence Matcher.
For each CitedClaim, searches the SourceChunk list for supporting evidence
and assigns a ClaimStatus based on match quality.
"""

from __future__ import annotations
import re
from src.schemas import CitedClaim, SourceChunk, ClaimStatus, is_structural_content


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


_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$")


def _tokens(text: str) -> set[str]:
    words = set()
    for w in _norm(text).split():
        clean = _PUNCT_RE.sub("", w)
        if clean:
            words.add(clean)
    return words - _STOPWORDS


def _keyword_overlap(claim_text: str, chunk_content: str, min_overlap: int = 2) -> bool:
    return len(_tokens(claim_text) & _tokens(chunk_content)) >= min_overlap


def _high_content_overlap(claim_text: str, chunk_content: str, min_ratio: float = 0.7) -> bool:
    """True when ≥70% of meaningful claim words appear in chunk content."""
    ct = _tokens(claim_text)
    if len(ct) < 3:
        return False
    cc = _tokens(chunk_content)
    overlap = ct & cc
    return len(overlap) / len(ct) >= min_ratio


# ---------------------------------------------------------------------------
# Exact metadata match per source type
# ---------------------------------------------------------------------------

def _value_strings(val: object) -> set[str]:
    """Return plausible string representations of a numeric value for matching."""
    if val is None:
        return set()
    s = str(val)
    result = {s}
    if isinstance(val, float) and val == int(val):
        result.add(str(int(val)))          # 32.0 → "32"
    elif isinstance(val, int):
        result.add(f"{val}.0")             # 32 → "32.0"
    return result


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
            strength = _norm(str(meta.get("strength", "")))
            if strength and strength in ct:
                return True

    elif stype == "labs":
        test_full = _norm(meta.get("test_name", ""))
        test_short = test_full.split("(")[0].strip()
        test_code = _norm(meta.get("test_code", ""))

        name_match = (
            (test_full and test_full in ct)
            or (test_short and len(test_short) > 2 and test_short in ct)
            or (test_code and len(test_code) > 2 and test_code in ct)
        )
        if name_match:
            val = meta.get("value")
            if val is not None and any(v in ct for v in _value_strings(val)):
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
        bp = meta.get("blood_pressure")
        if bp and bp in claim_text:
            return True
        bmi = meta.get("bmi")
        if bmi is not None and any(v in ct for v in _value_strings(bmi)):
            if "bmi" in ct:
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

    Match tiers (highest to lowest):
      1. SUPPORTED           — exact structured metadata match
      2. SUPPORTED           — ≥70% keyword overlap with chunk content
      3. NEED_REVIEW         — allergy match with needs_patient_confirmation
      4. PARTIALLY_SUPPORTED — keyword overlap ≥ min_keyword_overlap (low overlap)
      5. NO_CITATION         — no match (critical claim)
      6. UNSUPPORTED         — no match (non-critical claim)
    """
    if claim.is_structural or is_structural_content(claim.claim_text):
        return claim.model_copy(update={"status": "SUPPORTED", "citations": [], "is_structural": True})

    exact_ids: list[str] = []
    high_overlap_ids: list[str] = []
    need_review_ids: list[str] = []
    keyword_ids: list[str] = []

    for chunk in chunks:
        if chunk.source_type == "allergies":
            substance = _norm(chunk.metadata.get("substance", ""))
            if substance and len(substance) > 3 and substance in _norm(claim.claim_text):
                if chunk.metadata.get("needs_patient_confirmation"):
                    need_review_ids.append(chunk.source_id)
                else:
                    exact_ids.append(chunk.source_id)
        elif _exact_match(claim.claim_text, chunk):
            exact_ids.append(chunk.source_id)
        elif _high_content_overlap(claim.claim_text, chunk.content):
            high_overlap_ids.append(chunk.source_id)
        elif _keyword_overlap(claim.claim_text, chunk.content, min_overlap=min_keyword_overlap):
            keyword_ids.append(chunk.source_id)

    if exact_ids:
        return claim.model_copy(update={"status": "SUPPORTED", "citations": exact_ids[:5]})
    elif high_overlap_ids:
        return claim.model_copy(update={"status": "SUPPORTED", "citations": high_overlap_ids[:5]})
    elif need_review_ids:
        return claim.model_copy(update={"status": "NEED_REVIEW", "citations": need_review_ids})
    elif keyword_ids:
        return claim.model_copy(update={"status": "PARTIALLY_SUPPORTED", "citations": keyword_ids[:3]})
    else:
        status: ClaimStatus = "NO_CITATION" if claim.is_critical else "UNSUPPORTED"
        return claim.model_copy(update={"status": status, "citations": []})


def match_claims(
    claims: list[CitedClaim],
    chunks: list[SourceChunk],
    min_keyword_overlap: int = 2,
) -> list[CitedClaim]:
    """Batch version of match_claim."""
    return [match_claim(c, chunks, min_keyword_overlap) for c in claims]
