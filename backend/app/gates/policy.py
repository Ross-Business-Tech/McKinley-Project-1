"""Deterministic safety floor applied to every non-rules gate decision.

An external gate (LLM, Jev) can add risk flags, raise urgency or ask for a human. It can never:
- change the trusted audience (identity comes from the application, not a model);
- remove a rules risk flag or lower urgency below the rules decision;
- clear `requires_human` when any always-human flag is present;
- turn a low-confidence answer into a "safe" one (low confidence is flagged and handled downstream).
"""

from app.gates.base import ALWAYS_HUMAN_FLAGS, LOW_CONFIDENCE_THRESHOLD, URGENCY_RANK, GateContext
from app.gates.rules import FLAG_REASONS
from app.models import GateDecision


def apply_safety_floor(external: GateDecision, rules: GateDecision, ctx: GateContext) -> GateDecision:
    overrides: list[str] = []
    flags = list(dict.fromkeys([*rules.risk_flags, *external.risk_flags]))

    audience = ctx.audience
    if external.audience != audience:
        overrides.append(f"audience '{external.audience}' ignored; trusted audience is '{audience}'")

    intent = external.intent
    if "emergency_hazard" in flags and intent != "maintenance":
        overrides.append(f"intent '{intent}' -> 'maintenance' (emergency hazard)")
        intent = "maintenance"

    urgency = external.urgency
    if URGENCY_RANK[rules.urgency] > URGENCY_RANK[urgency]:
        overrides.append(f"urgency '{urgency}' raised to rules floor '{rules.urgency}'")
        urgency = rules.urgency
    if "emergency_hazard" in flags and urgency != "emergency":
        overrides.append("urgency forced to 'emergency' (hazard flag)")
        urgency = "emergency"

    if external.confidence < LOW_CONFIDENCE_THRESHOLD and "low_confidence" not in flags:
        flags.append("low_confidence")
        overrides.append(f"confidence {external.confidence:.2f} below {LOW_CONFIDENCE_THRESHOLD}: flagged")
        if ctx.prior_low_confidence and "repeated_low_confidence" not in flags:
            flags.append("repeated_low_confidence")

    human_flags = [f for f in flags if f in ALWAYS_HUMAN_FLAGS]
    requires_human = external.requires_human or bool(human_flags) or rules.requires_human
    if requires_human and not external.requires_human:
        overrides.append(f"requires_human forced by deterministic flags {human_flags}")

    reasons = [external.handoff_reason] if external.handoff_reason else []
    reasons += [FLAG_REASONS[f] for f in human_flags if FLAG_REASONS[f] not in reasons]
    return external.model_copy(update={
        "audience": audience,
        "intent": intent,
        "urgency": urgency,
        "requires_human": requires_human,
        "handoff_reason": " ".join(reasons) or None,
        "risk_flags": flags,
        "overrides": [*external.overrides, *overrides],
    })
