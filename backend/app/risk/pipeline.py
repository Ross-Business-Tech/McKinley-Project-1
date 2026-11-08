"""Layered safety pipeline: detect (rules) -> classify (semantic LLM) -> decide (policy) -> select (approved text)
-> recommend (human escalation). Runs before workflow routing and before any response generation.
See docs/SAFETY_EVALUATION.md and docs/diagrams/safety-architecture.md."""

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
    return RiskAssessment(deterministic=det, semantic=sem, decision=decide(det, sem, prior_hazards))


__all__ = ["RiskAssessment", "SemanticRiskClassifier", "assess"]
