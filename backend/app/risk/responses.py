"""Approved response selection: maps a RiskDecision to fixed TEAM-DRAFT safety text (I-17/I-18, not McKinley-approved).

No model writes safety text. 911 is used for physical/medical danger, 988 for self-harm, Poison Help for poisoning,
the community's emergency maintenance line for property hazards; ordinary maintenance gets none of these.
"""

from dataclasses import dataclass

from app.emergency import ALSO_988, CARE_NOTE, INFO_LEAD, heading, notice
from app.risk.models import RiskDecision
from app.workflows import EMERGENCY_NOTICE


@dataclass
class SafetyText:
    safety_notice: str | None = None  # the full alert (urgent banner)
    safety_heading: str | None = None
    care_kind: str | None = None
    care_note: str | None = None  # calm line above the reply


def select(decision: RiskDecision, lang: str) -> SafetyText:
    lang = lang if lang in ("en", "es") else "en"
    if decision.response == "full_alert":
        known = decision.kind not in (None, "other")
        text = notice(decision.kind, lang) if known else EMERGENCY_NOTICE  # type: ignore[arg-type]
        if decision.also_988:
            text += ALSO_988[lang]
        return SafetyText(safety_notice=text, safety_heading=heading(decision.kind, lang))
    if decision.response == "safety_info" and decision.kind:
        return SafetyText(care_kind="info", care_note=INFO_LEAD[lang] + notice(decision.kind, lang))
    if decision.response == "care_line" and decision.care in CARE_NOTE:
        return SafetyText(care_kind=decision.care, care_note=CARE_NOTE[decision.care][lang])
    return SafetyText()
