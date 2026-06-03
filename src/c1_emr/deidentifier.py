"""
C1 — EMR Integration: PII De-identifier.
Masks sensitive fields before any LLM API call.
"""

from __future__ import annotations
import copy
import re


# Fields that must be fully redacted
PII_FIELDS_FULL = {
    "cccd", "citizen_id",
    "so_bhyt", "insurance_id",
    "so_dien_thoai", "phone",
}

# Fields to partial-mask: keep district/province, remove house number
PII_FIELDS_PARTIAL = {"dia_chi", "address"}

# Patient name: keep for display but track for later masking if needed
# In MVP we keep the name as-is since seed data uses fictional names


def _redact_full(value) -> str:
    return "[REDACTED]"


def _redact_partial_address(address: str) -> str:
    """Remove house number/street, keep district/province."""
    if not address or address == "[REDACTED]":
        return address
    # Keep only the last 1-2 comma-separated tokens (district/province)
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        return ", ".join(parts[-2:])
    return parts[-1] if parts else "[REDACTED]"


def _deidentify_dict(obj: dict, depth: int = 0) -> dict:
    """Recursively de-identify a dict."""
    if depth > 10:
        return obj

    result = {}
    for key, value in obj.items():
        key_lower = key.lower()

        if key_lower in PII_FIELDS_FULL:
            result[key] = _redact_full(value)
        elif key_lower in PII_FIELDS_PARTIAL:
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


def deidentify(ehr: dict) -> dict:
    """
    Return a deep copy of ehr with PII fields masked.
    Does NOT mutate the input.
    """
    return _deidentify_dict(copy.deepcopy(ehr))


def is_deidentified(ehr: dict) -> bool:
    """Quick check: no raw CCCD/BHYT values remaining."""
    text = str(ehr)
    # Simple heuristic: no 12-digit number sequences (CCCD pattern)
    if re.search(r'\b\d{12}\b', text):
        return False
    # No 15-digit BHYT patterns
    if re.search(r'\b[A-Z]{2}\d{13}\b', text):
        return False
    return True
