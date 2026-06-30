"""Output guardrail — role-drift detection in summary content."""
from __future__ import annotations

import re

from src.logging_config import get_logger
from src.schemas import SummarySection, SafetyViolation

_logger = get_logger("guardrails.output")

ROLE_DRIFT_PATTERNS: list[str] = [
    r"nên dùng",
    r"nên tăng",
    r"nên giảm",
    r"nên bổ sung",
    r"cần tăng (liều|thuốc)",
    r"cần bổ sung",
    r"khuyến (cáo|nghị|khích)",
    r"đề xuất (dùng|thêm|đổi)",
    r"should (prescribe|use|increase|add)",
    r"recommend(ed)?",
    r"consider (adding|switching|increasing)",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in ROLE_DRIFT_PATTERNS]


def check_role_drift(sections: list[SummarySection]) -> list[SafetyViolation]:
    """Return a SafetyViolation for each role-drift phrase found in any section."""
    violations: list[SafetyViolation] = []
    for section in sections:
        for pattern in _COMPILED:
            m = pattern.search(section.content)
            if m:
                violations.append(SafetyViolation(
                    section_id=section.section_id,
                    matched_text=m.group(0),
                    severity="HIGH",
                ))
                _logger.info(
                    "Role-drift detected",
                    extra={
                        "section_id": section.section_id,
                        "matched_text": m.group(0),
                    },
                )
    return violations
