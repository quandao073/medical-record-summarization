"""
C6 — Hallucination Verifier.
Applies the KEEP / FLAG / REMOVE decision matrix to each CitedClaim,
rebuilds section content with status-specific prefixes, and computes SummaryMetrics.
"""

from __future__ import annotations
from src.schemas import CitedClaim, SummarySection, SummaryMetrics, SourceChunk
from src.c5_citation.claim_extractor import extract_claims
from src.c5_citation.evidence_matcher import match_claims


# ---------------------------------------------------------------------------
# Decision matrix: (ClaimStatus, is_critical) → action
# ---------------------------------------------------------------------------

_ACTION: dict[tuple[str, bool], str] = {
    ("SUPPORTED",           True):  "KEEP",
    ("SUPPORTED",           False): "KEEP",
    ("PARTIALLY_SUPPORTED", True):  "FLAG",
    ("PARTIALLY_SUPPORTED", False): "FLAG",
    ("LOW_CONFIDENCE",      True):  "FLAG",
    ("LOW_CONFIDENCE",      False): "FLAG",
    ("UNSUPPORTED",         True):  "REMOVE",
    ("UNSUPPORTED",         False): "FLAG",
    ("NO_CITATION",         True):  "REMOVE",
    ("NO_CITATION",         False): "FLAG",
    ("CONTRADICTED",        True):  "REMOVE",
    ("CONTRADICTED",        False): "REMOVE",
    ("NEED_REVIEW",         True):  "FLAG",
    ("NEED_REVIEW",         False): "FLAG",
}

# Status-specific prefixes — match the UI labels in ClaimContent.tsx
_STATUS_PREFIX: dict[str, str] = {
    "PARTIALLY_SUPPORTED": "[Hỗ trợ một phần] ",
    "LOW_CONFIDENCE":      "[Độ tin cậy thấp] ",
    "UNSUPPORTED":         "[Cần xác minh] ",
    "NO_CITATION":         "[Chưa có nguồn] ",
    "NEED_REVIEW":         "[Cần xem xét] ",
    "CONTRADICTED":        "[Mâu thuẫn] ",
}

_EMPTY_CONTENT = "Chưa thấy ghi nhận được xác minh trong dữ liệu được cung cấp."


def decide(claim: CitedClaim, conservative: bool = True) -> str:
    """
    Return 'KEEP', 'FLAG', or 'REMOVE' for a single claim.
    conservative=True: REMOVE → FLAG (avoids silencing valid claims in demo).
    """
    action = _ACTION.get((claim.status, claim.is_critical), "FLAG")
    if conservative and action == "REMOVE":
        return "FLAG"
    return action


def verify_section(
    section: SummarySection,
    chunks: list[SourceChunk],
    conservative: bool = True,
) -> tuple[SummarySection, list[str]]:
    """
    Verify one section.
    Returns (verified_section, action_list) — action_list parallels matched claims.
    FLAG claims get a status-specific prefix (e.g. "[Cần xác minh]"), not a blanket label.
    """
    claims = extract_claims(section)
    if not claims:
        return section, []

    matched = match_claims(claims, chunks)
    actions = [decide(c, conservative) for c in matched]

    kept_pairs = [(c, a) for c, a in zip(matched, actions) if a != "REMOVE"]

    if not kept_pairs:
        new_content = _EMPTY_CONTENT
        kept_claims: list[CitedClaim] = []
    else:
        parts = [c.claim_text for c, _ in kept_pairs]
        new_content = " ".join(parts)
        kept_claims = [c for c, _ in kept_pairs]

    return section.model_copy(update={"content": new_content, "cited_claims": kept_claims}), actions


def verify_summary(
    sections: list[SummarySection],
    chunks: list[SourceChunk],
    conservative: bool = True,
) -> tuple[list[SummarySection], SummaryMetrics]:
    """
    Verify all sections and compute aggregate SummaryMetrics.
    All rates are consistent with the UI label taxonomy.
    """
    verified_sections: list[SummarySection] = []
    all_claims: list[CitedClaim] = []

    for section in sections:
        vsec, _ = verify_section(section, chunks, conservative)
        verified_sections.append(vsec)
        all_claims.extend([c for c in vsec.cited_claims if not c.is_structural])

    total = len(all_claims)

    critical_claims = [c for c in all_claims if c.is_critical]
    total_critical = len(critical_claims)

    supported       = sum(1 for c in all_claims if c.status == "SUPPORTED")
    crit_supported  = sum(1 for c in critical_claims if c.status == "SUPPORTED")
    unsupported     = sum(1 for c in all_claims if c.status in ("UNSUPPORTED", "NO_CITATION"))
    low_conf        = sum(1 for c in all_claims if c.status in ("PARTIALLY_SUPPORTED", "LOW_CONFIDENCE"))
    need_rev        = sum(1 for c in all_claims if c.status == "NEED_REVIEW")
    contradicted    = sum(1 for c in all_claims if c.status == "CONTRADICTED")
    empty           = sum(1 for s in verified_sections if _EMPTY_CONTENT in s.content)

    metrics = SummaryMetrics(
        citation_coverage          = round(supported / total, 3)        if total          else 0.0,
        critical_citation_coverage = round(crit_supported / total_critical, 3) if total_critical else 0.0,
        total_critical_claims      = total_critical,
        unsupported_claim_rate     = round(unsupported / total, 3)       if total          else 0.0,
        low_confidence_rate        = round(low_conf / total, 3)          if total          else 0.0,
        need_review_rate           = round(need_rev / total, 3)          if total          else 0.0,
        hallucination_rate         = round(contradicted / total, 3)      if total          else 0.0,
        missing_section_rate       = round(empty / len(sections), 3)     if sections       else 0.0,
        total_claims               = total,
    )

    return verified_sections, metrics
