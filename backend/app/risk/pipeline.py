"""Layered safety pipeline: detect (rules) -> classify (semantic LLM) -> decide (policy) -> select (approved text)
-> recommend (human escalation). Sprint 6: concept slots in layer 1 (risk/concepts.py), incident-specific notice
selection (risk/category.py) and persistent incident state (risk/incident.py, applied by chat_engine step 2b).
Runs before workflow routing and before any response generation.
See docs/safety/safety-evaluation.md and docs/diagrams/safety-architecture.md."""

from app.risk.category import refine
from app.risk.classifier import SemanticRiskClassifier
from app.risk.detect import detect
from app.risk.models import RiskAssessment
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
    return RiskAssessment(deterministic=det, semantic=sem, decision=decision)


__all__ = ["RiskAssessment", "SemanticRiskClassifier", "assess"]
