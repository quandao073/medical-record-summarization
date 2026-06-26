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
    "bệnh_nhân",
    "a", "an", "the", "and", "or", "of", "in", "is", "are", "for",
}

_COMPOUND_TERMS = [
    "đái tháo đường",
    "tăng huyết áp",
    "rối loạn chuyển hóa lipid",
    "nhồi máu cơ tim",
    "suy thận mạn",
    "bệnh thần kinh ngoại biên",
    "viêm gan siêu vi",
    "xơ vữa động mạch",
    "suy tim sung huyết",
    "bệnh phổi tắc nghẽn mạn tính",
    "huyết áp",
    "nhịp tim",
    "nhiệt độ",
    "mề đay",
    "phì đại thất trái",
    "gan nhiễm mỡ",
    "dị ứng thuốc",
    "acid uric",
    "protein niệu",
    "thiếu máu",
    "viêm loét dạ dày",
    "cường giáp",
    "bệnh nhân",
]

_COMPOUND_SORTED = sorted(_COMPOUND_TERMS, key=len, reverse=True)


def _extract_compound_tokens(text: str) -> set[str]:
    """Find compound medical terms and return their underscore-joined forms."""
    lowered = text.lower()
    found: set[str] = set()
    for term in _COMPOUND_SORTED:
        if term in lowered:
            found.add(term.replace(" ", "_"))
    return found


_NUMERIC_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(%|mmol|mg|µmol|umol|U/L|IU/L|g/dL|ng/mL|mL|mcg|mmHg)"
)
_COMMA_DOT_RE = re.compile(r"(\d+),(\d+)")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text.lower().strip())


def _norm_numeric(text: str) -> str:
    """Extended normalization: comma→dot and number+unit joining for token matching."""
    result = _norm(text)
    result = _COMMA_DOT_RE.sub(r"\1.\2", result)
    result = _NUMERIC_UNIT_RE.sub(r"\1\2", result)
    return result


_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$")


def _tokens(text: str) -> set[str]:
    normalized = _norm_numeric(text)
    words = set()
    for w in normalized.split():
        clean = _PUNCT_RE.sub("", w)
        if clean:
            words.add(clean)
    words |= _extract_compound_tokens(text)
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

    elif stype == "patient_info":
        name = _norm(meta.get("full_name", ""))
        age = str(meta.get("age", ""))
        gender = _norm(meta.get("gender", ""))
        if name and len(name) > 3 and name in ct:
            return True
        if age and age in ct and ("tuổi" in ct or "age" in ct):
            return True
        if gender and gender in ct:
            return True

    return False


# ---------------------------------------------------------------------------
# Source priority — prefer the most clinically appropriate source type
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY: dict[str, int] = {
    "patient_info": 10,
    "labs": 9,
    "medications": 8,
    "diagnoses": 7,
    "vitals": 6,
    "allergies": 5,
    "clinical_notes": 3,
}


def _sort_by_source_priority(source_ids: list[str], chunks: list[SourceChunk]) -> list[str]:
    chunk_map = {c.source_id: c for c in chunks}
    return sorted(
        source_ids,
        key=lambda sid: _SOURCE_PRIORITY.get(
            chunk_map[sid].source_type if sid in chunk_map else "", 0
        ),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Semantic matching — unit normalization, drug synonyms, abbreviations
# ---------------------------------------------------------------------------

_UNIT_TO_MG: dict[str, float] = {
    "g": 1000.0, "mg": 1.0, "mcg": 0.001, "µg": 0.001,
}

_UNIT_TO_ML: dict[str, float] = {
    "l": 1000.0, "dl": 100.0, "ml": 1.0,
}


def _normalize_strength_mg(strength: str) -> float | None:
    s = _norm(strength)
    for unit, factor in sorted(_UNIT_TO_MG.items(), key=lambda x: -len(x[0])):
        if s.endswith(unit):
            try:
                return float(s[: -len(unit)].strip().replace(",", ".")) * factor
            except ValueError:
                return None
    return None


_DRUG_SYNONYMS: dict[str, set[str]] = {
    "aspirin": {"acetylsalicylic acid", "axit acetylsalicylic", "asa"},
    "paracetamol": {"acetaminophen", "tylenol"},
    "insulin nph": {"insulin isophane"},
    "metformin": {"glucophage"},
    "amlodipine": {"norvasc"},
    "losartan": {"cozaar"},
    "atorvastatin": {"lipitor"},
    "omeprazole": {"prilosec"},
    "pantoprazole": {"protonix"},
    "esomeprazole": {"nexium"},
    "amoxicillin": {"amoxil"},
    "clarithromycin": {"biaxin"},
}

_SYNONYM_REVERSE: dict[str, str] = {}
for _canonical, _alts in _DRUG_SYNONYMS.items():
    for _alt in _alts:
        _SYNONYM_REVERSE[_alt] = _canonical
    _SYNONYM_REVERSE[_canonical] = _canonical


def _canonical_drug(name: str) -> str:
    n = _norm(name)
    return _SYNONYM_REVERSE.get(n, n)


_ABBREVIATIONS: dict[str, str] = {
    "ha": "huyết áp",
    "đtđ": "đái tháo đường",
    "tha": "tăng huyết áp",
    "rlmm": "rối loạn mỡ máu",
    "tsh": "thyroid stimulating hormone",
    "ft4": "free thyroxine",
    "ft3": "free triiodothyronine",
    "hba1c": "hemoglobin glycated",
    "ldl": "low-density lipoprotein",
    "hdl": "high-density lipoprotein",
    "alt": "alanine aminotransferase",
    "ast": "aspartate aminotransferase",
    "gfr": "glomerular filtration rate",
    "bmi": "body mass index",
    "spo2": "oxygen saturation",
}


def _expand_abbreviations(text: str) -> str:
    words = _norm(text).split()
    expanded = []
    for w in words:
        clean = _PUNCT_RE.sub("", w)
        if clean in _ABBREVIATIONS:
            expanded.append(_ABBREVIATIONS[clean])
        expanded.append(w)
    return " ".join(expanded)


def _semantic_match(claim_text: str, chunk: SourceChunk) -> bool:
    ct = _norm(claim_text)
    meta = chunk.metadata
    stype = chunk.source_type

    if stype == "medications":
        drug = meta.get("drug_name", "")
        claim_canonical = _canonical_drug(ct)
        drug_canonical = _canonical_drug(drug)
        if drug_canonical and drug_canonical in claim_canonical:
            strength = meta.get("strength", "")
            if strength:
                chunk_mg = _normalize_strength_mg(strength)
                for token in ct.split():
                    claim_mg = _normalize_strength_mg(token)
                    if claim_mg is not None and chunk_mg is not None:
                        if abs(claim_mg - chunk_mg) < 0.01:
                            return True

    elif stype == "labs":
        test_name = _norm(meta.get("test_name", ""))
        test_short = test_name.split("(")[0].strip()
        expanded_claim = _expand_abbreviations(claim_text)
        expanded_test = _expand_abbreviations(test_name)

        name_match = (
            (test_short and len(test_short) > 2 and test_short in expanded_claim)
            or (expanded_test and expanded_test in expanded_claim)
        )
        if name_match:
            val = meta.get("value")
            if val is not None and any(v in ct for v in _value_strings(val)):
                return True

    elif stype == "diagnoses":
        dname = _norm(meta.get("diagnosis_name", ""))
        expanded_claim = _expand_abbreviations(claim_text)
        expanded_dname = _expand_abbreviations(dname)
        if expanded_dname and len(expanded_dname) > 5 and expanded_dname in expanded_claim:
            return True

    return False


# ---------------------------------------------------------------------------
# Conflict detection — block false SUPPORTED on discriminative differences
# ---------------------------------------------------------------------------

# Disease classifier numbers, e.g. "type 2", "týp 1", "tuýp 2", "giai đoạn 3"
_CLASSIFIER_RE = re.compile(
    r"\b(?:type|týp|tuýp|tuyp|giai đoạn)\s*([0-9]+)", re.IGNORECASE
)


def _classifier_values(text: str) -> set[str]:
    return set(_CLASSIFIER_RE.findall(text.lower()))


def _has_conflicting_token(claim_text: str, chunk_content: str) -> bool:
    """
    True when claim and chunk both specify a discriminative classifier
    (e.g. diabetes type) but the values differ — preventing a false SUPPORTED
    such as "ĐTĐ type 1" matched against a "type 2" source.
    """
    cl = _classifier_values(claim_text)
    ch = _classifier_values(chunk_content)
    if cl and ch and cl.isdisjoint(ch):
        return True
    return False


# ---------------------------------------------------------------------------
# Numeric value match — supports multi-fact and trend claims
# ---------------------------------------------------------------------------

def _value_match(claim_text: str, chunk: SourceChunk) -> bool:
    """
    True when a lab's numeric value appears in the claim alongside its unit
    or short name. Catches trend claims ("7.8% xuống 7.5%") and multi-fact
    timeline lines where the full test name is absent.
    """
    if chunk.source_type != "labs":
        return False
    ct = _norm(claim_text)
    val = chunk.metadata.get("value")
    if val is None or not any(v in ct for v in _value_strings(val)):
        return False
    unit = _norm(str(chunk.metadata.get("unit", "")))
    test_short = _norm(chunk.metadata.get("test_name", "")).split("(")[0].strip()
    if unit and unit in ct:
        return True
    if test_short and len(test_short) > 2 and test_short in ct:
        return True
    return False


def _substance_core(substance: str) -> str:
    """Core substance word, dropping any parenthetical, e.g.
    'Thuốc (không rõ loại)' → 'thuốc', 'Sulfonamide (Co-trimoxazole)' → 'sulfonamide'."""
    return _norm(substance.split("(")[0])


def _dedup(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


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
    Returns a new CitedClaim with status, citations and confidence_score populated.

    Match tiers (highest to lowest):
      1. SUPPORTED           — exact metadata / numeric value match  (conf 1.0 / 0.85)
      2. SUPPORTED           — ≥70% content overlap                  (conf 0.8)
      3. NEED_REVIEW         — allergy needing patient confirmation   (conf 0.6)
      4. PARTIALLY_SUPPORTED — low keyword overlap                    (conf 0.5)
      5. CONTRADICTED        — only conflicting evidence found        (conf 0.0)
      6. NO_CITATION / UNSUPPORTED — no evidence                      (conf 0.0)
    """
    if claim.is_structural or is_structural_content(claim.claim_text):
        return claim.model_copy(update={
            "status": "SUPPORTED", "citations": [], "is_structural": True,
            "confidence_score": None,
        })

    norm_claim = _norm(claim.claim_text)

    exact_ids: list[str] = []
    value_ids: list[str] = []
    semantic_ids: list[str] = []
    high_overlap_ids: list[str] = []
    allergy_review_ids: list[str] = []
    allergy_exact_ids: list[str] = []
    keyword_ids: list[str] = []
    conflict_ids: list[str] = []

    for chunk in chunks:
        if chunk.source_type == "allergies":
            core = _substance_core(chunk.metadata.get("substance", ""))
            if core and len(core) >= 3 and core in norm_claim:
                if chunk.metadata.get("needs_patient_confirmation"):
                    allergy_review_ids.append(chunk.source_id)
                else:
                    allergy_exact_ids.append(chunk.source_id)
            continue

        # Discriminative conflict (e.g. diabetes type mismatch) → not positive evidence
        if _has_conflicting_token(claim.claim_text, chunk.content):
            conflict_ids.append(chunk.source_id)
            continue

        if _exact_match(claim.claim_text, chunk):
            exact_ids.append(chunk.source_id)
        elif _value_match(claim.claim_text, chunk):
            value_ids.append(chunk.source_id)
        elif _semantic_match(claim.claim_text, chunk):
            semantic_ids.append(chunk.source_id)
        elif _high_content_overlap(claim.claim_text, chunk.content):
            high_overlap_ids.append(chunk.source_id)
        elif _keyword_overlap(claim.claim_text, chunk.content, min_overlap=min_keyword_overlap):
            keyword_ids.append(chunk.source_id)

    strong = _dedup(_sort_by_source_priority(exact_ids + allergy_exact_ids + value_ids, chunks))
    if strong:
        conf = 1.0 if (exact_ids or allergy_exact_ids) else 0.85
        return claim.model_copy(update={
            "status": "SUPPORTED", "citations": strong[:5], "confidence_score": conf})
    if semantic_ids:
        return claim.model_copy(update={
            "status": "SUPPORTED",
            "citations": _dedup(_sort_by_source_priority(semantic_ids, chunks))[:5],
            "confidence_score": 0.9})
    if high_overlap_ids:
        return claim.model_copy(update={
            "status": "SUPPORTED",
            "citations": _dedup(_sort_by_source_priority(high_overlap_ids, chunks))[:5],
            "confidence_score": 0.8})
    if allergy_review_ids:
        return claim.model_copy(update={
            "status": "NEED_REVIEW", "citations": _dedup(allergy_review_ids)[:5],
            "confidence_score": 0.6})
    if keyword_ids:
        return claim.model_copy(update={
            "status": "PARTIALLY_SUPPORTED", "citations": _dedup(keyword_ids)[:3],
            "confidence_score": 0.5})
    if conflict_ids:
        return claim.model_copy(update={
            "status": "CONTRADICTED", "citations": _dedup(conflict_ids)[:3],
            "confidence_score": 0.0})

    status: ClaimStatus = "NO_CITATION" if claim.is_critical else "UNSUPPORTED"
    return claim.model_copy(update={"status": status, "citations": [], "confidence_score": 0.0})


def match_claims(
    claims: list[CitedClaim],
    chunks: list[SourceChunk],
    min_keyword_overlap: int = 2,
) -> list[CitedClaim]:
    """Batch version of match_claim."""
    return [match_claim(c, chunks, min_keyword_overlap) for c in claims]
