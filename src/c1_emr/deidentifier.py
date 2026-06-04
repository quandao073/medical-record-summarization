"""
C1 — EMR Integration: PII De-identifier.
Masks sensitive patient fields before any LLM API call.

Field categories:
  FULL_REDACT  — replaced with "[REDACTED]"
  YEAR_ONLY    — date kept as "YYYY" only
  PARTIAL_ADDR — street/house stripped, district/province kept
  STRIP        — key removed entirely (synthetic metadata)
"""

from __future__ import annotations
import copy
import re


# ---------------------------------------------------------------------------
# PII field sets — key names are lower-cased for comparison
# ---------------------------------------------------------------------------

# Direct identifiers → "[REDACTED]"
PII_FIELDS_FULL = {
    "citizen_id",       # CCCD / CMND (12-digit national ID)
    "insurance_id",     # Số BHYT
    "phone",            # Số điện thoại
}

# Quasi-identifiers: date reduced to year
PII_FIELDS_YEAR_ONLY = {
    "date_of_birth",    # "1969-01-15" → "1969"
}

# Address: keep district/province only
PII_FIELDS_PARTIAL = {
    "address",          # "Số 5, Nguyễn Trãi, Quận 1, TP.HCM" → "Quận 1, TP.HCM"
}

# Synthetic test metadata — strip key entirely (not patient data, not clinical data)
PII_FIELDS_STRIP = {
    "data_note",        # annotation injected during synthetic data creation
}


# ---------------------------------------------------------------------------
# Field-level masking functions
# ---------------------------------------------------------------------------

def _redact_full(_value) -> str:
    return "[REDACTED]"


def _mask_year_only(value) -> str:
    """Extract YYYY from an ISO date string. Falls back to "[REDACTED]"."""
    if not value:
        return "[REDACTED]"
    s = str(value).strip()
    m = re.match(r"(\d{4})", s)
    return m.group(1) if m else "[REDACTED]"


def _redact_partial_address(address: str) -> str:
    """Strip house number/street, keep last 2 comma-separated tokens (district, province)."""
    if not address or str(address) in ("[REDACTED]", ""):
        return address
    parts = [p.strip() for p in str(address).split(",")]
    if len(parts) >= 2:
        return ", ".join(parts[-2:])
    return parts[-1] if parts else "[REDACTED]"


# ---------------------------------------------------------------------------
# Recursive walk
# ---------------------------------------------------------------------------

def _deidentify_dict(obj: dict, depth: int = 0) -> dict:
    if depth > 10:
        return obj

    result = {}
    for key, value in obj.items():
        kl = key.lower()

        if kl in PII_FIELDS_STRIP:
            continue                                        # drop key entirely
        elif kl in PII_FIELDS_FULL:
            result[key] = _redact_full(value)
        elif kl in PII_FIELDS_YEAR_ONLY:
            result[key] = _mask_year_only(value)
        elif kl in PII_FIELDS_PARTIAL:
            result[key] = _redact_partial_address(str(value)) if value else value
        elif isinstance(value, dict):
            result[key] = _deidentify_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = [
                _deidentify_dict(item, depth + 1) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deidentify(ehr: dict) -> dict:
    """
    Return a deep copy of ehr with all PII fields masked.
    Does NOT mutate the input.
    """
    return _deidentify_dict(copy.deepcopy(ehr))


_PHONE_RE  = re.compile(r"\b0[35789]\d{8}\b")   # Vietnamese mobile: 0[35789]XXXXXXXX
_CCCD_RE   = re.compile(r"\b\d{12}\b")           # CCCD: exactly 12 digits
_BHYT_RE   = re.compile(r"\b[A-Z]{2}\d{13}\b")  # BHYT card: 2 letters + 13 digits


def is_deidentified(ehr: dict) -> bool:
    """
    Heuristic check: returns False if any known PII pattern is still present.
    Checks the serialised text of the entire EHR dict.
    """
    text = str(ehr)
    if _CCCD_RE.search(text):
        return False
    if _PHONE_RE.search(text):
        return False
    if _BHYT_RE.search(text):
        return False
    return True
