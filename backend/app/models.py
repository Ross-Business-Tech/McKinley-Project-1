"""Pydantic API contracts shared by the chat, persona and eval endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["baseline", "aware"]
Audience = Literal["prospect", "resident", "unknown"]
PersonaKind = Literal["prospect", "resident", "unmatched_resident"]
Verdict = Literal["GOOD", "BAD"]

HandoffCategory = Literal[
    "none",
    "safety_emergency",
    "repeat_issue",
    "unresolved_commitment",
    "human_requested",
    "policy_or_eligibility",
    "financial_or_lease",
    "fair_housing_or_legal",
    "leasing_follow_up",
    "sensitive_data_request",
    "other",
]


class Persona(BaseModel):
    """Safe, task-scoped persona label. Never carries raw resident fields."""

    id: str
    label: str
    kind: PersonaKind
    description: str
    synthetic: bool = True


class ContextField(BaseModel):
    name: str
    value: str
    source: str  # provenance, e.g. "Residents.preferred_contact" or "Interactions[I003].subject"


class SafeContext(BaseModel):
    persona_id: str | None
    persona_kind: PersonaKind | None
    audience: Audience
    record_found: bool
    topics: list[str]
    fields: list[ContextField]
    withheld_fields: list[str] = Field(default_factory=list)
    dropped_items: list[str] = Field(default_factory=list)  # e.g. note dropped by injection screen
    notes: list[str] = Field(default_factory=list)


class ContextPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona_id: str | None = Field(default=None, max_length=40)
    message: str = Field(default="", max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    persona_id: str | None = Field(default=None, max_length=40)
    mode: Mode
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    target: str | None = Field(default=None, max_length=120, description="provider:model from /api/models")


class Usage(BaseModel):
    input_tokens: int | None = None  # None when the provider does not report usage
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None


class PolicySignal(BaseModel):
    """Deterministic backend gate result (pre- or post-model)."""

    code: str
    category: HandoffCategory
    detail: str


class OutputCheck(BaseModel):
    code: str
    passed: bool
    detail: str


class ChatResponse(BaseModel):
    reply: str
    mode: Mode
    audience: Audience
    recommended_handoff: bool
    handoff_reason: str | None
    handoff_category: HandoffCategory
    handoff_is_recommendation_only: bool = True
    model_handoff: bool
    policy_signals: list[PolicySignal]
    output_checks: list[OutputCheck]
    source_context_fields: list[str]
    provider: str
    requested_model: str
    model: str
    is_mock: bool
    parse_mode: str
    temperature: float | None
    prompt_version: str
    usage: Usage
    latency_ms: int
    stop_reason: str | None
    session_id: str
    created_at: datetime


class ErrorBody(BaseModel):
    code: str  # NEEDS_API_KEY | MODEL_AUTH_ERROR | MODEL_RATE_LIMITED | MODEL_TIMEOUT | ...
    message: str
    retryable: bool = False


class ModelTarget(BaseModel):
    key: str  # "provider:model"
    provider: str
    model: str
    is_default: bool
    ready: bool
    status: str
    is_mock: bool


class HealthResponse(BaseModel):
    status: Literal["ok"]
    provider: str
    model: str
    provider_ready: bool
    provider_status: str
    prompt_version: str
    data_loaded: bool
    data_error: str | None
    resident_count: int
    interaction_count: int


# ---- evals -----------------------------------------------------------------


class EvalCase(BaseModel):
    id: str
    title: str
    persona_id: str
    message: str
    expected_audience: Audience
    expect_handoff: bool | None  # None = either acceptable
    reference_note: str


class CriterionResult(BaseModel):
    criterion: str
    passed: bool | None  # None = requires human judgment
    detail: str


class EvalResult(BaseModel):
    id: int
    run_id: int
    case_id: str
    mode: Mode
    created_at: datetime
    status: Literal["ok", "error"]
    error_code: str | None = None
    error_message: str | None = None
    reply: str | None = None
    audience: str | None = None
    recommended_handoff: bool | None = None
    handoff_category: str | None = None
    handoff_reason: str | None = None
    provider: str
    requested_model: str
    model: str
    is_mock: bool = False
    parse_mode: str | None = None
    temperature: float | None = None
    prompt_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_ms: int | None = None
    criteria: list[CriterionResult] = Field(default_factory=list)
    provisional_verdict: Verdict | None = None
    provisional_rationale: str | None = None
    human_verdict: Verdict | None = None
    human_notes: str | None = None


class EvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_ids: list[str] | None = None
    modes: list[Mode] = Field(default_factory=lambda: ["baseline", "aware"])
    # provider:model keys; the default target is used when omitted
    targets: list[str] | None = Field(default=None, max_length=6)


class EvalRunResponse(BaseModel):
    run_id: int
    results: list[EvalResult]


class EvalReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    human_verdict: Verdict | None = None
    human_notes: str | None = Field(default=None, max_length=2000)


class EvalRun(BaseModel):
    id: int
    created_at: datetime
    targets: list[str]
    aware_prompt_version: str
    baseline_prompt_version: str
    temperature: float | None


class TargetModeSummary(BaseModel):
    target: str
    mode: str
    is_mock: int
    runs: int
    errors: int
    good: int
    bad: int
    human_reviewed: int
    handoffs_recommended: int
    json_contract_failures: int
    avg_latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None


class EvalSummary(BaseModel):
    run_id: int | None
    total: int
    by_target_mode: dict[str, TargetModeSummary]
    failure_categories: dict[str, int]
