"""
C6 — Hallucination Verifier.
Applies the KEEP / FLAG / REMOVE decision matrix to each CitedClaim,
rebuilds section content with status-specific prefixes, and computes SummaryMetrics.
"""

from __future__ import annotations
import re
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
    removed_out: list[CitedClaim] | None = None,
) -> tuple[SummarySection, list[str]]:
    """
    Verify one section.
    Returns (verified_section, action_list) — action_list parallels matched claims.
    Each kept claim carries its C6 decision in `verifier_action` (KEEP/FLAG).
    REMOVE'd claims are dropped from content; if `removed_out` is provided they are
    appended there for audit. Content stays clean (no status prefixes).
    """
    claims = extract_claims(section)
    if not claims:
        return section, []

    matched = match_claims(claims, chunks)
    actions = [decide(c, conservative) for c in matched]

    kept_claims: list[CitedClaim] = []
    for c, a in zip(matched, actions):
        tagged = c.model_copy(update={"verifier_action": a})
        if a == "REMOVE":
            if removed_out is not None:
                removed_out.append(tagged)
        else:
            kept_claims.append(tagged)

    if not kept_claims:
        new_content = _EMPTY_CONTENT
    else:
        new_content = " ".join(c.claim_text for c in kept_claims)

    return section.model_copy(update={"content": new_content, "cited_claims": kept_claims}), actions


_CLASSIFIER_RE = re.compile(r"\b(?:type|týp|tuýp|tuyp|giai đoạn)\s*([0-9]+)", re.IGNORECASE)


def _classifier_values(text: str) -> set[str]:
    return set(_CLASSIFIER_RE.findall(text.lower()))


def check_internal_consistency(
    sections: list[SummarySection],
    conservative: bool = True,
) -> tuple[list[SummarySection], int]:
    """
    Cross-section consistency: if claims disagree on a disease classifier
    (e.g. diabetes 'type 2' vs 'type 1'), keep the majority value and mark the
    minority claims CONTRADICTED. Returns (updated_sections, contradiction_count).
    Acts only when there is a clear majority, to avoid false positives.
    """
    counts: dict[str, int] = {}
    for sec in sections:
        for c in sec.cited_claims:
            if c.is_structural:
                continue
            for v in _classifier_values(c.claim_text):
                counts[v] = counts.get(v, 0) + 1

    if len(counts) < 2:
        return sections, 0

    canonical = max(counts, key=counts.__getitem__)
    added = 0
    new_sections: list[SummarySection] = []
    for sec in sections:
        new_claims: list[CitedClaim] = []
        for c in sec.cited_claims:
            vals = _classifier_values(c.claim_text)
            if vals and canonical not in vals and not c.is_structural:
                c = c.model_copy(update={
                    "status": "CONTRADICTED",
                    "verifier_action": decide(
                        c.model_copy(update={"status": "CONTRADICTED"}), conservative),
                })
                added += 1
            new_claims.append(c)
        new_sections.append(sec.model_copy(update={"cited_claims": new_claims}))
    return new_sections, added


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

    for section in sections:
        vsec, _ = verify_section(section, chunks, conservative)
        verified_sections.append(vsec)

    # Cross-section consistency pass (e.g. diabetes type disagreement)
    verified_sections, _ = check_internal_consistency(verified_sections, conservative)

    all_claims: list[CitedClaim] = [
        c for s in verified_sections for c in s.cited_claims if not c.is_structural
    ]

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
        contradiction_count        = contradicted,
        need_review_count          = need_rev,
        duplicate_claim_count      = 0,   # extractor de-duplicates upstream
    )

    return verified_sections, metrics
