"""
C1 — EMR Integration: Vietnamese Medical Abbreviation Normalizer.
Expands common abbreviations in clinical text fields.
"""

from __future__ import annotations
import re
import json
from pathlib import Path
from functools import lru_cache


ROOT = Path(__file__).parent.parent.parent
DEFAULT_DICT_PATH = ROOT / "data" / "dictionaries" / "medical_abbreviations_vi.json"

# Text fields to normalize (dot-notation paths relative to encounter or patient)
NORMALIZE_FIELDS_ENCOUNTER = [
    "chief_complaint",
    "visit_reason",
]

NORMALIZE_FIELDS_NOTE = ["text"]

NORMALIZE_FIELDS_DIAGNOSIS = ["diagnosis_text"]

# Fields NOT to normalize (preserve exact values)
NO_NORMALIZE = {
    "icd10_code", "test_code", "drug_name", "strength",
    "source_system", "patient_id", "encounter_id",
}


@lru_cache(maxsize=1)
def _load_abbrev_dict(dict_path: str) -> dict[str, str]:
    with open(dict_path, encoding="utf-8") as f:
        return json.load(f)


def normalize_text(
    text: str,
    abbrev_dict: dict[str, str] | None = None,
    dict_path: str | None = None,
) -> str:
    """
    Expand Vietnamese medical abbreviations in text.
    Uses word-boundary matching to avoid partial replacements.
    e.g. 'THA' -> 'tăng huyết áp', but 'THAY' is not touched.
    """
    if not text or not isinstance(text, str):
        return text

    if abbrev_dict is None:
        path = dict_path or str(DEFAULT_DICT_PATH)
        abbrev_dict = _load_abbrev_dict(path)

    result = text
    # Sort by length desc so longer abbreviations match first
    for abbr, expansion in sorted(abbrev_dict.items(), key=lambda x: -len(x[0])):
        # Word boundary: match abbr as a whole word (handles Vietnamese upper case tokens)
        pattern = r'(?<![a-zA-ZÀ-ɏ])' + re.escape(abbr) + r'(?![a-zA-ZÀ-ɏ])'
        result = re.sub(pattern, expansion, result)

    return result


def normalize_encounter(enc: dict, abbrev_dict: dict[str, str]) -> dict:
    """Normalize text fields within a single encounter dict."""
    enc = dict(enc)

    for field in NORMALIZE_FIELDS_ENCOUNTER:
        if enc.get(field):
            enc[field] = normalize_text(enc[field], abbrev_dict)

    # Clinical notes
    enc["clinical_notes"] = [
        {**note, "text": normalize_text(note.get("text", ""), abbrev_dict)}
        for note in enc.get("clinical_notes", [])
    ]

    # Diagnoses
    enc["diagnoses"] = [
        {**dx, "diagnosis_text": normalize_text(dx.get("diagnosis_text", ""), abbrev_dict)}
        if "diagnosis_text" in dx else dx
        for dx in enc.get("diagnoses", [])
    ]

    return enc


def normalize_ehr(ehr: dict, dict_path: str | None = None) -> dict:
    """
    Normalize all relevant text fields in an assembled EHR dict.
    Returns a new dict (shallow copy of top-level, deep copy of modified fields).
    """
    abbrev_dict = _load_abbrev_dict(dict_path or str(DEFAULT_DICT_PATH))

    result = dict(ehr)
    result["encounters"] = [normalize_encounter(enc, abbrev_dict) for enc in ehr.get("encounters", [])]
    return result
