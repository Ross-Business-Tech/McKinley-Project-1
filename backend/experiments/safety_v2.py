"""EXPERIMENT (offline only; app/ never imports it): a safety policy that lets the semantic classifier correct the
LOW-PRECISION deterministic lines that cause the known false alarms, and separates maintenance urgency from immediate
personal danger. The production policy (app/risk/policy.decide) is not changed.

How it works. The production decision is computed first and kept, except in two narrow cases:

  V2-L  a calm care line (R6 / R7) whose ONLY deterministic evidence is low-precision, AND the classifier answered
        (status ok) "none" with confidence >= NONE_CONFIDENCE, no category, no immediate danger, AND no earlier
        person-danger alert or active incident in this conversation  ->  no safety text.
  V2-M  a classifier care line (R4) for a PROPERTY hazard (flood / structural / electrical / gas / fire_smoke) that
        the classifier itself calls "urgent" or "uncertain" with no immediate danger and no person at risk, AND the
        rules saw low-precision wording (never when the classifier is the ONLY source of the line: then a
        mislabelled real emergency the rules missed would lose its guidance)  ->  no safety text,
        `maintenance_urgency = "urgent"` (the repair is prioritised; no 911 line about a contained leak).

Low-precision evidence is classified from what the existing detector already reports (no new keyword lists):
  * the frame's lone "final" self-harm group ("possible self-harm sign: final": one wording group only; two or more
    groups are already an alert), with no phrase-rule care evidence;
  * the generic danger vocabulary (`possible_risk_evidence` == "danger_vocabulary") with no person concern, no body
    state, no hazard and no category in the frame.
Everything else is high-confidence and passes through unchanged: every full alert (R1 / R2 / R9e / R10...), any
self-harm category or self-harm intent, explicit distress / farewell / stockpile / person-concern evidence, hypothetical
or past hazards (R5), earlier alerts and active incidents (R9), and EVERY classifier failure (timeout, blocked,
bad_output, unavailable, error, disabled, mock): fail-safe means "as production".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.emergency import possible_risk_evidence
from app.risk.models import DeterministicRisk, RiskDecision, SemanticResult
from app.risk.policy import decide as production_decide
from app.risk.policy import is_people_hazard

NONE_CONFIDENCE = 0.85
PROPERTY = {"flood", "structural", "electrical", "gas", "fire_smoke"}
LOW_SELF_HARM_REASON = "possible self-harm sign: final"


@dataclass(frozen=True)
class V2Decision:
    decision: RiskDecision  # what would be shown (a production decision, or a "none" from V2-L / V2-M)
    production_rule: str  # what production decides for the same inputs
    changed_by: str | None  # None, "V2-L" or "V2-M"
    maintenance_urgency: str | None = None  # "urgent" when V2-M moved a property hazard to the repair priority
    evidence: str = "none"  # "none" | "low" | "high": the deterministic evidence tier


def evidence_tier(det: DeterministicRisk, message: str) -> str:
    """'none', 'low' or 'high' from the existing detector output (no new patterns)."""
    fr = det.frame or {}
    if det.kind or det.self_harm_intent or det.mentioned_kind or det.conditional_danger or det.happened:
        return "high"
    care_rule = possible_risk_evidence(message)[1]
    if det.care is None:
        return "none"
    lone_final = (fr.get("reason") == LOW_SELF_HARM_REASON and care_rule is None)
    vocabulary_only = (care_rule == "danger_vocabulary" and not det.concern and not fr.get("states")
                       and not fr.get("hazards") and not fr.get("category"))
    return "low" if (lone_final or vocabulary_only) else "high"


def _confident_none(sem: SemanticResult) -> bool:
    r = sem.risk
    return (sem.status == "ok" and r is not None and r.risk_level == "none" and not r.risk_categories
            and not r.immediate_danger and (r.confidence or 0) >= NONE_CONFIDENCE)


def _property_urgency(sem: SemanticResult) -> bool:
    r = sem.risk
    return (sem.status == "ok" and r is not None and r.risk_level in ("urgent", "uncertain") and not r.immediate_danger
            and bool(r.risk_categories) and set(r.risk_categories) <= PROPERTY
            and r.subject in ("none", "unknown"))


def decide(det: DeterministicRisk, sem: SemanticResult, message: str,
           prior_hazards: list[str] | None = None, incident_active: bool = False) -> V2Decision:
    base = production_decide(det, sem, prior_hazards)
    tier = evidence_tier(det, message)
    people_before = any(is_people_hazard(h) for h in (prior_hazards or []))
    if incident_active or people_before or base.response in ("full_alert", "safety_info"):
        return V2Decision(base, base.rule, None, evidence=tier)
    if base.rule in ("R6", "R7") and tier == "low" and _confident_none(sem):
        quiet = RiskDecision(response="none", rule="V2-L", sources=["deterministic", "semantic"],
                             conflict=f"low-precision {base.rule} line removed: classifier confident none")
        return V2Decision(quiet, base.rule, "V2-L", evidence=tier)
    if base.rule == "R4" and tier == "low" and _property_urgency(sem):
        quiet = RiskDecision(response="none", rule="V2-M", sources=["semantic"],
                             conflict="contained property hazard: repair priority, not a personal-danger line")
        return V2Decision(quiet, base.rule, "V2-M", maintenance_urgency="urgent", evidence=tier)
    return V2Decision(base, base.rule, None, evidence=tier)
