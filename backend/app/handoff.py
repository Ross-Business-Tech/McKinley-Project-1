"""Structured human-handoff recommendation. Built deterministically; NOTHING is sent anywhere.

The summary uses only minimized context field names/values already approved for the model, never model free
text (except a clearly labelled, redacted, length-capped model reason).
"""

from app.models import (
    GateDecision,
    HandoffCategory,
    HandoffRecommendation,
    HandoffTeam,
    LeadProfile,
    MaintenanceTriage,
    SafeContext,
    WorkflowSelection,
)
from app.safety import redact

# Most specific / most severe first.
FLAG_CATEGORY: list[tuple[str, HandoffCategory]] = [
    ("emergency_hazard", "safety_emergency"),
    ("sensitive_data_request", "sensitive_data_request"),
    ("unverified_private_request", "sensitive_data_request"),
    ("fair_housing_or_legal", "fair_housing_or_legal"),
    ("context_repeat_issue", "repeat_issue"),
    ("repeat_with_history", "repeat_issue"),
    ("context_open_commitment", "unresolved_commitment"),
    ("financial_or_lease", "financial_or_lease"),
    ("human_requested", "human_requested"),
    ("voucher_eligibility", "policy_or_eligibility"),
    ("repeated_low_confidence", "other"),
]

NOT_SENT = ("Not sent. This prototype has no staff queue, call transfer or on-call integration; a staff member "
            "must act on this recommendation.")
NOT_SENT_EMERGENCY = ("Not sent. The person was told to call 911 / the emergency maintenance line directly; this "
                      "prototype cannot page on-call staff.")


def _team(d: GateDecision, wf: WorkflowSelection) -> HandoffTeam:
    flags = set(d.risk_flags)
    if d.urgency == "emergency":
        return "emergency_maintenance"
    if flags & {"fair_housing_or_legal", "unverified_private_request", "sensitive_data_request",
                "repeated_low_confidence"}:
        return "management"
    if d.intent == "maintenance":
        # Repeated failures with an owed follow-up are a service-recovery issue for the manager.
        return "management" if {"context_repeat_issue", "context_open_commitment"} <= flags else "maintenance"
    if d.intent in ("leasing", "renewal") or wf.id in ("leasing", "renewal"):
        return "leasing"
    if "financial_or_lease" in flags:
        return "accounting"
    return "leasing" if d.audience in ("prospect", "unknown") else "management"


def build_handoff(
    d: GateDecision, wf: WorkflowSelection, ctx: SafeContext, model_handoff: bool, model_reason: str,
    triage: MaintenanceTriage | None = None, lead: LeadProfile | None = None,
) -> HandoffRecommendation | None:
    high_lead = lead is not None and lead.intent_level == "high"
    if not (d.requires_human or model_handoff or high_lead):
        return None
    flags = set(d.risk_flags)
    category: HandoffCategory = next((c for f, c in FLAG_CATEGORY if f in flags), "other")
    if category == "other" and (high_lead or (model_handoff and d.intent == "leasing")):
        category = "leasing_follow_up"

    reasons = [d.handoff_reason] if d.handoff_reason else []
    if high_lead:
        reasons.append("High-intent prospect: leasing team should follow up to confirm availability and a tour.")
    if model_handoff and model_reason:
        reasons.append(f"Model suggested: {redact(model_reason)[:200]}")

    priority = ("urgent" if d.urgency == "emergency" else
                "high" if d.urgency == "high" or flags & {"context_repeat_issue", "context_open_commitment"}
                else "normal")

    names = {f.name for f in ctx.fields}
    count = next((f.value for f in ctx.fields if f.name == "related_history_count"), None)
    parts = [f"{d.audience.capitalize()} · {d.intent} · urgency {d.urgency}."]
    if ctx.topics:
        parts.append(f"Topics: {', '.join(ctx.topics)}.")
    if triage:
        parts.append(f"Maintenance triage: {triage.level} ({triage.category}); no work order exists.")
    if count and count != "0":
        parts.append(f"{count} related prior contact(s) on record.")
    if "open_commitment_flag" in names:
        parts.append("An earlier follow-up is still owed.")
    if lead:
        parts.append(f"Lead intent {lead.intent_level}; known: {', '.join(f'{k}={v}' for k, v in lead.known.items())
                                                              or 'none'}.")
    if d.audience == "resident" and not ctx.record_found:
        parts.append("Identity NOT verified: no account details were shared.")

    guidance = []
    for n in ("preferred_contact_channel", "staff_noted_contact_preference", "preferred_language"):
        for f in ctx.fields:
            if f.name == n and not (n == "preferred_language" and f.value.lower() == "english"):
                guidance.append(f.value)
    return HandoffRecommendation(
        team=_team(d, wf),
        priority=priority,
        category=category,
        reasons=list(dict.fromkeys(reasons)) or ["Assistant recommends staff review."],
        summary=" ".join(parts),
        included_fields=sorted(names),
        contact_guidance="; ".join(guidance) or None,
        delivery_note=NOT_SENT_EMERGENCY if d.urgency == "emergency" else NOT_SENT,
    )
