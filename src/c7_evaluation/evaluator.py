"""
C7 Evaluator — citation precision/recall against gold labels.

Usage:
    from src.c7_evaluation.evaluator import evaluate_summary
    report = evaluate_summary(summary, gold_path)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.schemas import FinalSummary, CitedClaim


# ---------------------------------------------------------------------------
# Gold label schema
# ---------------------------------------------------------------------------

class GoldClaim(BaseModel):
    claim_pattern: str
    expected_source_ids: list[str] = Field(default_factory=list)
    # Strict mode: citation is correct only if emitted citations contain ALL ids in at least one group
    acceptable_source_groups: list[list[str]] = Field(default_factory=list)
    is_critical: bool = False
    note: str = ""


class GoldSection(BaseModel):
    section_id: str
    expected_claims: list[GoldClaim] = Field(default_factory=list)


class GoldLabels(BaseModel):
    patient_id: str
    evaluation_mode: str = "loose"  # "loose" or "store_aware_strict"
    sections: list[GoldSection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Eval report
# ---------------------------------------------------------------------------

class ClaimEval(BaseModel):
    claim_text: str
    status: str
    citations: list[str] = Field(default_factory=list)
    matched_gold_pattern: str | None = None
    expected_source_ids: list[str] = Field(default_factory=list)
    has_correct_citation: bool = False
    is_critical: bool = False


class SectionEval(BaseModel):
    section_id: str
    total_claims: int = 0
    supported_claims: int = 0
    precision_correct: int = 0
    gold_matched: int = 0
    gold_total: int = 0
    claim_evals: list[ClaimEval] = Field(default_factory=list)


class EvalReport(BaseModel):
    patient_id: str
    evaluation_mode: str = "loose"
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    critical_precision: float = 0.0
    total_supported: int = 0
    precision_correct: int = 0
    total_gold: int = 0
    gold_matched: int = 0
    sections: list[SectionEval] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _match_claim_to_gold(claim: CitedClaim, golds: list[GoldClaim]) -> GoldClaim | None:
    for g in golds:
        try:
            if re.search(g.claim_pattern, claim.claim_text, re.IGNORECASE):
                return g
        except re.error:
            if g.claim_pattern.lower() in claim.claim_text.lower():
                return g
    return None


def _citation_correct(emitted: list[str], gold: GoldClaim, strict: bool) -> bool:
    """
    Loose mode: at least one expected_source_id appears in emitted citations.
    Strict mode: if acceptable_source_groups defined, at least one complete group
                 must be a subset of emitted citations; else fall back to loose.
    """
    emitted_set = set(emitted)
    if strict and gold.acceptable_source_groups:
        return any(
            set(group).issubset(emitted_set)
            for group in gold.acceptable_source_groups
        )
    # loose: any expected id present
    return any(sid in emitted_set for sid in gold.expected_source_ids)


def evaluate_summary(summary: FinalSummary, gold_path: Path) -> EvalReport:
    gold_data = json.loads(gold_path.read_text(encoding="utf-8"))
    gold = GoldLabels(**gold_data)
    strict = gold.evaluation_mode == "store_aware_strict"

    gold_by_section: dict[str, list[GoldClaim]] = {}
    for gs in gold.sections:
        gold_by_section[gs.section_id] = gs.expected_claims

    report = EvalReport(patient_id=summary.patient_id, evaluation_mode=gold.evaluation_mode)
    total_supported = 0
    precision_correct = 0
    critical_supported = 0
    critical_correct = 0
    total_gold = 0
    gold_matched = 0

    for section in summary.sections:
        sec_golds = gold_by_section.get(section.section_id, [])
        total_gold += len(sec_golds)
        matched_gold_indices: set[int] = set()

        sec_eval = SectionEval(
            section_id=section.section_id,
            total_claims=len(section.cited_claims),
            gold_total=len(sec_golds),
        )

        for claim in section.cited_claims:
            if claim.is_structural:
                continue

            ce = ClaimEval(
                claim_text=claim.claim_text,
                status=claim.status,
                citations=claim.citations,
                is_critical=claim.is_critical,
            )

            if claim.status == "SUPPORTED":
                total_supported += 1
                sec_eval.supported_claims += 1
                if claim.is_critical:
                    critical_supported += 1

                matched = _match_claim_to_gold(claim, sec_golds)
                if matched:
                    ce.matched_gold_pattern = matched.claim_pattern
                    ce.expected_source_ids = matched.expected_source_ids

                    idx = next(
                        (i for i, g in enumerate(sec_golds) if g is matched), -1
                    )
                    if idx >= 0:
                        matched_gold_indices.add(idx)

                    correct = _citation_correct(claim.citations, matched, strict)
                    ce.has_correct_citation = correct
                    if correct:
                        precision_correct += 1
                        sec_eval.precision_correct += 1
                        if claim.is_critical:
                            critical_correct += 1

            sec_eval.claim_evals.append(ce)

        sec_eval.gold_matched = len(matched_gold_indices)
        gold_matched += len(matched_gold_indices)
        report.sections.append(sec_eval)

    report.total_supported = total_supported
    report.precision_correct = precision_correct
    report.total_gold = total_gold
    report.gold_matched = gold_matched
    report.citation_precision = (
        precision_correct / total_supported if total_supported > 0 else 0.0
    )
    report.citation_recall = (
        gold_matched / total_gold if total_gold > 0 else 0.0
    )
    report.critical_precision = (
        critical_correct / critical_supported if critical_supported > 0 else 0.0
    )
    return report
