"""Shared gate types: trusted input context and the provider protocol."""

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Audience, GateDecision

INTENTS = ["leasing", "maintenance", "renewal", "general"]
URGENCIES = ["low", "medium", "high", "emergency"]
URGENCY_RANK = {u: i for i, u in enumerate(URGENCIES)}

# Risk flags that always require a human, whatever any model says.
ALWAYS_HUMAN_FLAGS = {
    "emergency_hazard", "human_requested", "sensitive_data_request", "fair_housing_or_legal",
    "financial_or_lease", "voucher_eligibility", "unverified_private_request", "context_repeat_issue",
    "context_open_commitment", "repeat_with_history", "repeated_low_confidence",
}
# Flags an external gate may *add* (it can never remove any flag).
EXTERNAL_FLAG_VOCAB = [
    "emergency_hazard", "human_requested", "sensitive_data_request", "fair_housing_or_legal",
    "financial_or_lease", "voucher_eligibility", "complaint_or_frustration", "unverified_private_request",
]
LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class GateContext:
    """Facts established by the application, never by the model or the message text."""

    audience: Audience  # from the demo persona / trusted app context
    identity_verified: bool  # True only for a matched resident record
    record_found: bool
    topics: list[str] = field(default_factory=list)
    context_flags: frozenset[str] = frozenset()  # e.g. {"repeat_issue_flag", "open_commitment_flag"}
    prior_low_confidence: bool = False  # previous turn in this session was low confidence


class GateUnavailable(Exception):
    """External gate could not produce a decision (not configured, timeout, bad response)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class GateProvider(Protocol):
    name: str

    def classify(self, message: str, ctx: GateContext, rules: GateDecision) -> GateDecision: ...
