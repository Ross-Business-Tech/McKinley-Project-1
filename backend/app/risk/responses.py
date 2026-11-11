"""Approved response selection: maps a RiskDecision to fixed TEAM-DRAFT safety text (I-17/I-18, not McKinley-approved).

No model writes safety text. 911 is used for physical/medical danger, 988 for self-harm, Poison Help for poisoning,
the community's emergency maintenance line for property hazards; ordinary maintenance gets none of these.
"""

from dataclasses import dataclass

from app.emergency import ALSO_988, CARE_NOTE, INFO_LEAD, notice
from app.risk.models import RiskDecision
from app.templates import t
from app.workflows import EMERGENCY_NOTICE


@dataclass
class SafetyText:
    safety_notice: str | None = None  # the full alert (urgent banner)
    care_kind: str | None = None
    care_note: str | None = None  # calm line above the reply


def generic_steps(lang: str) -> str:
    """Safety steps when the hazard kind is unknown (no note claim; EN keeps the long-standing EMERGENCY_NOTICE)."""
    return EMERGENCY_NOTICE if lang != "es" else t("emergency_steps", "es")


def select(decision: RiskDecision, lang: str) -> SafetyText:
    lang = lang if lang in ("en", "es") else "en"
    if decision.response == "full_alert":
        known = decision.kind not in (None, "other")
        text = notice(decision.kind, lang) if known else generic_steps(lang)  # type: ignore[arg-type]
        if decision.also_988:
            text += ALSO_988[lang]
        return SafetyText(safety_notice=text)
    if decision.response == "safety_info" and decision.kind:
        # final round: R5p = a small event that already happened ("i got a little shock"): the steps directly,
        # without "If that happens:"
        lead = "" if decision.rule == "R5p" else INFO_LEAD[lang]
        return SafetyText(care_kind="info", care_note=lead + notice(decision.kind, lang))
    if decision.response == "care_line" and decision.care in CARE_NOTE:
        return SafetyText(care_kind=decision.care, care_note=CARE_NOTE[decision.care][lang])
    return SafetyText()
