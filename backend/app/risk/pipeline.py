"""Layered safety pipeline: detect (rules) -> classify (semantic LLM) -> decide (policy) -> select (approved text)
-> recommend (human escalation). Sprint 6: concept slots in layer 1 (risk/concepts.py), incident-specific notice
selection (risk/category.py) and persistent incident state (risk/incident.py, applied by chat_engine step 2b).
Runs before workflow routing and before any response generation.
See docs/safety/safety-evaluation.md and docs/diagrams/safety-architecture.md."""

from app.risk.category import refine
from app.risk.classifier import SemanticRiskClassifier
from app.risk.detect import detect
from app.risk.models import DeterministicRisk, RiskAssessment, RiskDecision
from app.risk.policy import decide


def assess(message: str, recent: list[str] | None, classifier: SemanticRiskClassifier | None,
           prior_hazards: list[str] | None = None) -> RiskAssessment:
    det = detect(message, recent)
    if classifier is None:
        from app.risk.models import SemanticResult
        sem = SemanticResult(status="disabled", detail="no classifier in this context")
    else:
        sem = classifier.classify(message, recent)
    decision = decide(det, sem, prior_hazards)
    if decision.response == "full_alert" and decision.kind:
        # Layer 4a: the approved notice that fits THIS incident (a child in a hot car is not an elevator case)
        text = " . ".join([*(recent or [])[-3:], message]) if det.via_window else message
        kind, reason = refine(decision.kind, text)
        decision = decision.model_copy(update={"detected_kind": decision.kind, "kind": kind,
                                               "notice_reason": reason})
    decision = decision.model_copy(update={"person_danger": person_danger(decision, det)})
    return RiskAssessment(deterministic=det, semantic=sem, decision=decision)


def person_danger(decision: RiskDecision, det: DeterministicRisk | None = None) -> bool:
    """Full alert, or a care line from a person sign (concern / frame person state / distress / R9 / R10q memory)."""
    if decision.response == "full_alert" or decision.conditional_danger:
        return True
    if decision.response != "care_line":
        return False
    if decision.care == "distress" or decision.rule in ("R9", "R9e", "R10", "R10q"):
        return True
    if det is None:
        return False
    fr = det.frame or {}
    exposure_only = fr.get("care_hint") == "unwell" and not fr.get("states")
    people = [w for w in fr.get("who") or [] if w != "self"]
    return not exposure_only and (det.concern or bool(people and (fr.get("states") or fr.get("hazards"))))


__all__ = ["RiskAssessment", "SemanticRiskClassifier", "assess"]
