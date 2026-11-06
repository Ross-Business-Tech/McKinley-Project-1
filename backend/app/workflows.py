"""Business workflow selection and per-workflow deterministic analysis (no side effects, no extra LLM calls).

One response-generation LLM is used for every workflow; workflows differ only in the trusted instructions and
backend-computed facts appended to the system prompt. See docs/WORKFLOW_REVIEW.md and docs/DECISIONS.md.
"""

import re

from app.models import (
    GateDecision,
    LeadProfile,
    MaintenanceTriage,
    RenewalAssessment,
    SafeContext,
    WorkflowId,
    WorkflowSelection,
)

WORKFLOW_VERSION = "wf-v1"

LABELS: dict[WorkflowId, str] = {
    "leasing": "Prospect / leasing",
    "resident_support": "Existing resident support",
    "maintenance": "Maintenance",
    "renewal": "Renewal / retention",
    "human_handoff": "Human handoff",
    "general_inquiry": "General inquiry",
    "tour_request": "Tour request (F5)",
    "faq": "Property & leasing FAQ (F4)",
    "status_lookup": "Request status lookup (F8)",
    "sms_opt_out": "SMS opt-out (F2)",
}

# Flags that send the whole conversation to the handoff workflow (the assistant explains, staff decide).
HANDOFF_WORKFLOW_FLAGS = ["explicit_human_request", "fair_housing_or_legal", "sensitive_data_request",
                          "unverified_private_request", "repeated_low_confidence"]

INSTRUCTIONS: dict[WorkflowId, str] = {
    "leasing": (
        "Prospect / leasing workflow. Be welcoming and proactively helpful. Use 'beds' and 'floor plans'. "
        "You have NO live prices, availability, specials or tour calendar: never state or estimate them and never "
        "confirm a tour. Offer to prepare a request for the leasing team instead. Ask at most ONE question: use "
        "the suggested next question below if one is given. Match energy to lead intent: concrete next step for "
        "high intent; light, no-pressure guidance for low intent."
    ),
    "resident_support": (
        "Existing resident support workflow. Be patient and empathetic. Use the resident's first name once if "
        "known. Do not ask for information already in SAFE_CONTEXT (language, contact preference). Reply in the "
        "resident's preferred language. Mention history only when it is relevant to this message."
    ),
    "maintenance": (
        "Maintenance workflow. Acknowledge the problem. Offer ONLY the approved troubleshooting steps listed "
        "below, word for word in meaning, and nothing else; if none are listed, offer none. Never claim a work "
        "order, ticket, technician or appointment exists or was created. Explain that the request should be "
        "submitted to (or reviewed by) the community maintenance team. If a repeat issue is flagged, acknowledge "
        "the history and say why it deserves review rather than another routine request."
    ),
    "renewal": (
        "Renewal / retention workflow. Be compassionate and never pushy. Do not state, estimate or negotiate "
        "renewal prices, discounts, concessions or terms, and do not promise outcomes. Acknowledge open "
        "commitments from history if relevant. Respect the stated contact preference. Recommend that the "
        "leasing office explain the options."
    ),
    "human_handoff": (
        "Human handoff workflow. Briefly acknowledge the request, explain in one sentence why a staff member "
        "needs to handle it, and say that a handoff is recommended. Do NOT say anyone was notified, a call is "
        "scheduled, or a ticket was created. Never request or repeat sensitive identifiers. If identity is not "
        "verified, do not discuss account-specific details."
    ),
    "tour_request": (
        "Tour request workflow. Collect only what the backend draft asks for. A tour REQUEST goes to the leasing "
        "team, who pick the time; it is never a booking. Never offer clock times or say a time is available."
    ),
    "faq": (
        "FAQ workflow. Answer ONLY with the approved facts in the backend draft. If it says details are not "
        "approved or not available, say so plainly and offer the leasing team. Never guess."
    ),
    "status_lookup": (
        "Status lookup workflow. The interface lists the items; summarize at most briefly. Never estimate when a "
        "repair will happen."
    ),
    "sms_opt_out": "SMS opt-out. Confirm the opt-out only.",
    "general_inquiry": (
        "General inquiry workflow. The request is unclear or the person is unidentified. Give a safe, general "
        "answer or ask ONE short clarifying question (e.g. whether they live in a McKinley community or are "
        "looking for a home). Do not assume account details."
    ),
}

EMERGENCY_NOTICE = (
    "If anyone is in danger, leave the area now and call 911. If you smell gas, leave without using switches or "
    "flames and call 911 or your gas utility from outside. Then call your community's emergency maintenance line. "
    "This assistant cannot dispatch anyone."
)

# Approved low-risk resident troubleshooting (draft; requires McKinley approval, see WORKFLOW_REVIEW I-20).
APPROVED_TROUBLESHOOTING: list[tuple[str, re.Pattern[str], list[str]]] = [
    ("plumbing_drip", re.compile(r"drip|faucet|tap", re.I), [
        "Make sure the faucet handle is fully turned off.",
        "Place a towel or container under the drip to limit water damage.",
    ]),
    ("plumbing_drain", re.compile(r"drain|clog|slow sink|slow tub", re.I), [
        "Stop using that drain until it is looked at.",
        "Do not use chemical drain cleaners.",
    ]),
    ("hvac", re.compile(r"\bac\b|a/c|air condition|cooling|heat|thermostat|furnace", re.I), [
        "Check the thermostat is set to the right mode (cool or heat) and to a temperature past the room's.",
        "Make sure the air vents are open and not blocked by furniture.",
    ]),
    ("appliance", re.compile(r"dishwasher|fridge|refrigerator|oven|stove|washer|dryer|microwave|disposal", re.I), [
        "Check that the appliance is plugged in and its door is fully closed.",
    ]),
    ("pest", re.compile(r"roach|bug|pest|mice|mouse|ants", re.I), [
        "Keep food in sealed containers and wipe up crumbs.",
        "Do not use bug foggers before staff advise.",
    ]),
]

_HIGH_INTENT = [
    ("tour_request", re.compile(r"\btour\b|visit|see (it|the|a)", re.I)),
    ("move_in_timeframe", re.compile(r"next (week|month)|this (week|month)|asap|move[- ]in|moving|relocat|"
                                     r"\bby (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)),
    ("application", re.compile(r"\bapply\b|application|sign a lease", re.I)),
]
_LOW_INTENT = [
    ("price_only", re.compile(r"cheapest|lowest price|how much|price|pricing", re.I)),
    ("browsing", re.compile(r"just (looking|browsing)|curious|maybe someday", re.I)),
]
_FLOOR_PLAN = re.compile(r"\b(\d)\s?-?\s?(?:bed|br|bedroom)s?\b|studio", re.I)
_BUDGET = re.compile(r"\$\s?\d[\d,]*|budget|under \d|less than \d", re.I)
_LOCATION = re.compile(r"\b(?:in|near|around) ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)")


def select_workflow(d: GateDecision) -> WorkflowSelection:
    def sel(wid: WorkflowId, reason: str) -> WorkflowSelection:
        return WorkflowSelection(id=wid, label=LABELS[wid], reason=reason, instructions_version=WORKFLOW_VERSION)

    if d.urgency == "emergency":
        return sel("maintenance", "Emergency indicators: maintenance workflow with emergency triage.")
    flags = [f for f in HANDOFF_WORKFLOW_FLAGS if f in d.risk_flags]
    if flags:
        return sel("human_handoff", f"Deterministic flag(s) require staff: {', '.join(flags)}.")
    if d.intent == "leasing" and d.audience != "resident":
        return sel("leasing", "Leasing intent from a prospect or unidentified visitor.")
    if d.intent == "maintenance":
        return sel("maintenance", "Maintenance intent.")
    if d.intent == "renewal" and d.audience == "resident":
        return sel("renewal", "Renewal intent from an identified resident.")
    if d.audience == "resident":
        return sel("resident_support", f"Resident with '{d.intent}' intent.")
    return sel("general_inquiry", "Audience or intent unclear.")


def _ctx(ctx: SafeContext, name: str) -> list[str]:
    return [f.value for f in ctx.fields if f.name == name]


def maintenance_triage(message: str, ctx: SafeContext, d: GateDecision) -> MaintenanceTriage:
    category = next((name for name, pat, _ in APPROVED_TROUBLESHOOTING if pat.search(message)), "other")
    steps = next((s for name, _, s in APPROVED_TROUBLESHOOTING if name == category), [])
    if d.urgency == "emergency":
        level, steps = "emergency", []
    elif "context_repeat_issue" in d.risk_flags or "repeat_with_history" in d.risk_flags:
        level, steps = "repeat", []  # don't send a repeat complainant through the same checks again
    elif category == "other":
        level = "unclear"
    else:
        level = "routine"
    return MaintenanceTriage(level=level, category=category, approved_troubleshooting=steps,
                             entry_window_on_file=bool(_ctx(ctx, "preferred_entry_window")))


def lead_profile(message: str, ctx: SafeContext) -> LeadProfile:
    known: dict[str, str] = {}
    for field_name, key in (("interest_area", "location"), ("desired_floor_plan", "floor_plan"),
                            ("move_in_timeframe", "move_in")):
        if v := _ctx(ctx, field_name):
            known[key] = v[0]
    if m := _FLOOR_PLAN.search(message):
        known["floor_plan"] = f"{m.group(1)}-bed" if m.group(1) else "studio"
    if m := _LOCATION.search(message):
        known.setdefault("location", m.group(1))
    if _BUDGET.search(message):
        known["budget"] = "mentioned"
    high = [n for n, p in _HIGH_INTENT if p.search(message)]
    low = [n for n, p in _LOW_INTENT if p.search(message)]
    if "move_in_timeframe" in high and "move_in" not in known:
        known["move_in"] = "mentioned"
    if "tour_request" in high or "application" in high or len(high) >= 2:
        level = "high"
    elif low and not high:
        level = "low"
    else:
        level = "unclear"
    missing = [k for k in ("location", "move_in", "floor_plan", "budget") if k not in known]
    questions = {"location": "Which city or community are you most interested in?",
                 "move_in": "When are you hoping to move in?",
                 "floor_plan": "How many beds are you looking for?"}
    next_q = next((questions[k] for k in missing if k in questions), None)
    return LeadProfile(intent_level=level, signals=high + low, known=known, missing=missing, next_question=next_q)


_CONCERNS = [
    ("affordability", re.compile(r"cost|afford|increase|expensive|price|rent (go|went) up|too much|worried", re.I)),
    ("lease_term", re.compile(r"\d+[- ]month|term|longer|shorter", re.I)),
    ("contact_preference", re.compile(r"call|text|email|sleep|in writing", re.I)),
    ("considering_leaving", re.compile(r"move out|moving out|leav|buy(ing)? a (home|house)|not renew", re.I)),
]


def renewal_assessment(message: str, ctx: SafeContext) -> RenewalAssessment:
    open_items = 0
    for v in _ctx(ctx, "open_commitment_flag"):
        m = re.match(r"(\d+)", v)
        open_items += int(m.group(1)) if m else 1
    concerns = [n for n, p in _CONCERNS if p.search(message)]
    tone = "compassionate, no pressure" + ("; acknowledge affordability worry" if "affordability" in concerns else "")
    return RenewalAssessment(concerns=concerns, renewal_status_known=bool(_ctx(ctx, "renewal_status")),
                             open_commitments=open_items, tone=tone)


def workflow_prompt_section(sel: WorkflowSelection, d: GateDecision, triage: MaintenanceTriage | None,
                            lead: LeadProfile | None, renewal: RenewalAssessment | None) -> str:
    """Trusted, backend-generated instructions appended to the system prompt."""
    lines = [f"## Active workflow: {sel.label} ({WORKFLOW_VERSION})", INSTRUCTIONS[sel.id],
             f"Backend routing decision: intent={d.intent}, urgency={d.urgency}, "
             f"human_handoff_required={'yes' if d.requires_human else 'no'}."]
    if d.requires_human:
        lines.append("A human handoff WILL be recommended to staff by the backend. Tell the person a staff "
                     "member should follow up; do not claim it has already happened.")
    if "low_confidence" in d.risk_flags:
        lines.append("Routing confidence is low: ask one short clarifying question rather than guessing.")
    if triage:
        if triage.level == "emergency":
            lines.append("EMERGENCY: lead with safety (leave the area, call 911 / emergency maintenance). "
                         "Give no troubleshooting.")
        lines.append(f"Maintenance triage: level={triage.level}, category={triage.category}.")
        lines.append("Approved troubleshooting: " + (" ".join(triage.approved_troubleshooting) or "NONE."))
    if lead:
        lines.append(f"Lead intent: {lead.intent_level}. Known: {lead.known or 'nothing yet'}.")
        if lead.next_question:
            lines.append(f"Suggested next question: {lead.next_question}")
    if renewal:
        lines.append(f"Renewal concerns detected: {', '.join(renewal.concerns) or 'none'}; tone: {renewal.tone}; "
                     f"open commitments on record: {renewal.open_commitments}.")
    return "\n".join(lines)
