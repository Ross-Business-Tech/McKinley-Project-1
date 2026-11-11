"""Who sees which part of a chat response. Customers get what the customer website needs; staff get diagnostics.

`ChatResponse` (app/models.py) carries both the customer answer and the staff diagnostics (risk layers, decision
gate, pipeline trace, context-field provenance, policy rule ids, output checks, workflow internals). `/api/chat`
returns the full object only to a staff caller (app/api/staff_guard.staff_allowed: loopback without a token on a
local deployment, or the X-Staff-Token). Everyone else gets `customer_view`.

Deny by default: `customer_view` COPIES only the allowlisted fields below; every other field takes its neutral
value (required fields) or its model default (optional fields). A field added to ChatResponse later is therefore
hidden from customers until someone adds it to CUSTOMER_FIELDS on purpose. The shape stays the same as the full
response, so the website's TypeScript type (frontend/src/lib/types.ts ChatResponse) keeps working unchanged.
"""

from __future__ import annotations

from typing import Any

from app.models import ChatResponse

# Exactly what frontend/src/components/customer (CustomerApp, ActionCard, StatusPill) and lib/customer.ts read,
# plus the caller's own data (records it created, its own status items) and plain response metadata.
CUSTOMER_FIELDS: frozenset[str] = frozenset({
    "reply", "safety_notice", "emergency_kind", "safety_heading", "care_kind", "care_note",
    "mode", "session_id", "created_at", "channel", "language", "reply_source",
    "action", "action_cleared", "records_created", "status_items", "suggested_replies", "identity_note",
    # "replied by <provider/model>" footer and the MOCK label (the same facts /api/models publishes)
    "provider", "requested_model", "model", "is_mock",
    # coarse outcome only (not the reason text, not which rule fired)
    "recommended_handoff", "handoff_category", "handoff_is_recommendation_only", "audience",
})

# Required ChatResponse fields that customers do not get: neutral values of the right type.
_NEUTRAL: dict[str, Any] = {
    "handoff_reason": None,
    "model_handoff": False,
    "policy_signals": [],
    "output_checks": [],
    "source_context_fields": [],
    "parse_mode": "",
    "temperature": None,
    "usage": {},
    "latency_ms": 0,
    "stop_reason": None,
    "prompt_version": "",
}

# Staff-only diagnostics, listed so tests can prove none of them reaches a customer (risk, gate, pipeline, ...).
STAFF_ONLY_FIELDS: frozenset[str] = frozenset(set(ChatResponse.model_fields) - CUSTOMER_FIELDS)


def customer_view(resp: ChatResponse) -> ChatResponse:
    """The response with every staff diagnostic removed (deny by default, see the module docstring)."""
    data = {k: getattr(resp, k) for k in CUSTOMER_FIELDS}
    return ChatResponse.model_validate({**_NEUTRAL, **data})
