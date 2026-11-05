"""Deterministic rule-based decision gate. Auditable, offline, zero cost; the safety floor for every provider."""

import re

from app.context import MAINTENANCE_TOPICS, detect_topics
from app.gates.base import ALWAYS_HUMAN_FLAGS, LOW_CONFIDENCE_THRESHOLD, GateContext
from app.models import GateDecision, Intent, Urgency
from app.safety import looks_like_injection, normalize_for_matching, pre_model_gates

_LEASING = re.compile(
    r"\btour\b|\bapply\b|application|availab|floor ?plans?|\b\d\s?-?\s?(bed|br|bedroom)s?\b|\bbeds?\b|bedroom|"
    r"studio|move[- ]?in|moving (to|here)|relocat|looking (for|to rent)|cheapest|how much|price|pricing|"
    r"\bspecials?\b|pet[- ]friendly|apartments? (in|near)",
    re.IGNORECASE,
)
_RENEWAL = re.compile(r"renew|renewal|lease (end|term|offer|option)|extend my lease|month lease|move[- ]out notice",
                      re.IGNORECASE)
_HIGH_MAINT = re.compile(
    r"no (heat|hot water|water|power|electricity|a/?c|air)|locked out|toilet (overflow|won'?t stop)|"
    r"(water|leak)\w* (from|through) (the )?ceiling|sewage|backing up|freezing|pipe burst|burst pipe",
    re.IGNORECASE,
)
_PRIVATE = re.compile(
    r"\bmy (balance|account|rent|payment|lease|work orders?|requests?|tickets?|unit|renewal|deposit|bill)\b|"
    r"status of my|what do i owe|how much do i owe",
    re.IGNORECASE,
)
_EXPLICIT_HUMAN = re.compile(
    r"real (person|human)|not a (bot|robot|machine)|(talk|speak) (to|with) (a |an )?(human|person|manager|agent|"
    r"representative)|\bhuman please\b|stop (the )?bot",
    re.IGNORECASE,
)
_FRUSTRATION = re.compile(r"really upset|frustrat|unacceptable|ridiculous|angry|fed up|furious|complain",
                          re.IGNORECASE)

FLAG_REASONS = {
    "emergency_hazard": "Possible acute hazard: emergency channels must be prioritized.",
    "human_requested": "Person asked for a human.",
    "sensitive_data_request": "Message involves highly sensitive identifiers; never collect them in chat.",
    "fair_housing_or_legal": "Fair-housing, accommodation or legal topic needs authorized staff.",
    "financial_or_lease": "Financial or lease-term decision cannot be made by the assistant.",
    "voucher_eligibility": "Voucher eligibility must be confirmed by staff.",
    "unverified_private_request": "Account-specific request but identity is not verified.",
    "context_repeat_issue": "Record shows repeated related maintenance contacts.",
    "context_open_commitment": "Record shows an open item where follow-up is owed.",
    "repeat_with_history": "Message describes a recurring problem and history confirms it.",
    "repeated_low_confidence": "Assistant could not classify the request twice in a row.",
}


def _intent(message: str, ctx: GateContext, topics: list[str]) -> tuple[Intent, list[str], float]:
    """Return (intent, matched categories, heuristic confidence)."""
    maint = bool(set(topics) & (MAINTENANCE_TOPICS | {"maintenance_general"}))
    renewal = bool(_RENEWAL.search(message)) or "renewal" in topics
    leasing = bool(_LEASING.search(message))
    matched = [n for n, hit in (("maintenance", maint), ("renewal", renewal), ("leasing", leasing)) if hit]

    if ctx.audience == "prospect":
        # A prospect asking about appliances or lease terms is still a leasing conversation.
        return "leasing", matched or ["prospect_default"], 0.85 if matched else 0.6
    if not matched:
        if ctx.audience == "resident" and set(topics) - {"contact_preference"}:
            return "general", ["resident_topic"], 0.6
        return "general", [], 0.35
    if len(matched) == 1:
        intent = matched[0]
        if intent == "leasing" and ctx.audience == "resident":
            return "general", matched, 0.55  # resident asking about other floor plans: transfer -> staff
        return intent, matched, 0.85  # type: ignore[return-value]
    # Competing categories: prefer the operationally safer one (maintenance > renewal > leasing).
    for pick in ("maintenance", "renewal", "leasing"):
        if pick in matched:
            return pick, matched, 0.6  # type: ignore[return-value]
    return "general", matched, 0.4


def classify_rules(message: str, ctx: GateContext) -> GateDecision:
    message = normalize_for_matching(message)
    topics = ctx.topics or detect_topics(message)
    signals = pre_model_gates(message)
    flags = [s.code for s in signals]
    rationale = [f"pattern:{s.code}" for s in signals]

    if _PRIVATE.search(message) and not ctx.identity_verified and ctx.audience != "prospect":
        flags.append("unverified_private_request")
        rationale.append("account-specific wording without a verified record")
    if _EXPLICIT_HUMAN.search(message):
        flags.append("explicit_human_request")  # switches to the handoff workflow (soft asks do not)
        if "human_requested" not in flags:
            flags.append("human_requested")
    if looks_like_injection(message):
        flags.append("message_injection_attempt")  # informational: message is data, never instructions
    if _FRUSTRATION.search(message):
        flags.append("complaint_or_frustration")
    if "repeat_issue_flag" in ctx.context_flags:
        flags.append("context_repeat_issue")
    if "open_commitment_flag" in ctx.context_flags:
        flags.append("context_open_commitment")
    if "repeat_language" in flags and "repeat_issue_flag" in ctx.context_flags:
        flags.append("repeat_with_history")
    if ctx.audience == "resident" and not ctx.record_found:
        flags.append("no_matched_record")

    intent, matched, confidence = _intent(message, ctx, topics)
    rationale.append(f"intent:{intent} via {matched or 'no keyword match'}")
    if "emergency_hazard" in flags:
        intent, confidence = "maintenance", 0.95

    urgency: Urgency = "low"
    if "emergency_hazard" in flags:
        urgency = "emergency"
    elif intent == "maintenance" and (_HIGH_MAINT.search(message) or "context_repeat_issue" in flags
                                       or "repeat_language" in flags):
        urgency = "high"
    elif {"human_requested", "fair_housing_or_legal", "financial_or_lease", "complaint_or_frustration",
          "context_open_commitment", "unverified_private_request"} & set(flags) or intent == "maintenance":
        urgency = "medium"

    if confidence < LOW_CONFIDENCE_THRESHOLD:
        flags.append("low_confidence")
        if ctx.prior_low_confidence:
            flags.append("repeated_low_confidence")

    flags = list(dict.fromkeys(flags))
    human_flags = [f for f in flags if f in ALWAYS_HUMAN_FLAGS]
    reason = " ".join(FLAG_REASONS[f] for f in human_flags) or None
    return GateDecision(
        audience=ctx.audience,
        intent=intent,
        urgency=urgency,
        requires_human=bool(human_flags),
        handoff_reason=reason,
        confidence=confidence,
        confidence_calibrated=False,
        risk_flags=flags,
        decision_source="rules",
        requested_provider="rules",
        rationale=rationale,
    )
