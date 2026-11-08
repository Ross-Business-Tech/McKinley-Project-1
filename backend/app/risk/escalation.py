"""Human escalation recommendation for safety decisions. A recommendation only: nothing is paged, called or sent."""

from app.handoff import NOT_SENT
from app.models import HandoffRecommendation
from app.risk.models import RiskDecision
from app.risk.policy import is_people_hazard


def recommend(decision: RiskDecision, included_fields: list[str]) -> HandoffRecommendation | None:
    """Full alerts are handled by the planner (urgent prototype note). This covers care-line cases that a person
    should look at (possible distress, semantic 'urgent'), which previously produced no staff signal at all."""
    if decision.response == "full_alert":
        team = "management" if is_people_hazard(decision.kind) else "emergency_maintenance"
        return HandoffRecommendation(team=team, priority="urgent", category="safety_emergency",  # type: ignore[arg-type]
                                     reasons=[f"Safety policy {decision.rule}: possible emergency ({decision.kind})"],
                                     summary="Possible emergency: check on the person (prototype).",
                                     included_fields=included_fields, contact_guidance=None, delivery_note=NOT_SENT)
    if decision.needs_human:
        return HandoffRecommendation(team="management", priority=decision.escalation_priority or "high",
                                     category="safety_emergency",
                                     reasons=[f"Safety policy {decision.rule}: possible {decision.care or 'risk'}; "
                                              "a person should check in"],
                                     summary="Possible wellbeing concern: a staff member should check in (prototype).",
                                     included_fields=included_fields, contact_guidance=None, delivery_note=NOT_SENT)
    return None
