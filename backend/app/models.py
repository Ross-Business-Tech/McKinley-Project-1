"""Pydantic API contracts shared by the chat, persona and eval endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.risk.models import RiskAssessment

# baseline = generic prompt, no McKinley layers; prompt_only = McKinley prompt + gate/workflow, NO resident
# context fields; aware = McKinley prompt + gate/workflow + authorized minimized resident context.
Mode = Literal["baseline", "prompt_only", "aware"]
Audience = Literal["prospect", "resident", "unknown"]
PersonaKind = Literal["prospect", "resident", "unmatched_resident"]
Verdict = Literal["GOOD", "BAD"]
# Inbound channel. Phone/voice (F1) has no telephony integration and is not accepted.
Channel = Literal["web_chat", "sms", "email"]
# The nine function modules of "McKinley AI Agent Flow.md" (docs/workflows/traceability.md).
FunctionId = Literal["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]

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
    language: Literal["en", "es"] = "en"  # preferred language on file (greeting language)


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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    persona_id: str | None = Field(default=None, max_length=40)
    mode: Mode
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    target: str | None = Field(default=None, max_length=120, description="provider:model from /api/models")
    gate_provider: Literal["rules", "llm", "jev"] | None = Field(
        default=None, description="Override DECISION_GATE_PROVIDER for this turn (demo/experiments)")
    channel: Channel = "web_chat"


# ---- decision gate / workflow / handoff (pipeline v2) ----------------------------------

Intent = Literal["leasing", "maintenance", "renewal", "general"]
Urgency = Literal["low", "medium", "high", "emergency"]
GateSource = Literal["rules", "jev", "llm", "mock"]
WorkflowId = Literal["leasing", "tour_request", "faq", "resident_support", "maintenance", "status_lookup", "renewal",
                     "human_handoff", "general_inquiry", "sms_opt_out"]
HandoffTeam = Literal["emergency_maintenance", "maintenance", "leasing", "accounting", "management"]


class GateDecision(BaseModel):
    """Typed routing decision. `audience` is ALWAYS the trusted (application-established) audience."""

    audience: Audience
    intent: Intent
    urgency: Urgency
    requires_human: bool
    handoff_reason: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_calibrated: bool = False  # rules confidence is a heuristic, never a calibrated probability
    risk_flags: list[str] = Field(default_factory=list)
    decision_source: GateSource
    requested_provider: str  # what DECISION_GATE_PROVIDER asked for
    fallback_used: bool = False
    fallback_reason: str | None = None
    overrides: list[str] = Field(default_factory=list)  # deterministic safety-floor changes to the provider output
    rationale: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    gate_usage: "Usage | None" = None  # tokens/cost when an LLM gate made an extra call


class WorkflowSelection(BaseModel):
    id: WorkflowId
    label: str
    reason: str
    instructions_version: str


class MaintenanceTriage(BaseModel):
    level: Literal["emergency", "repeat", "routine", "unclear"]
    category: str
    approved_troubleshooting: list[str]
    entry_window_on_file: bool
    work_order_created: Literal[False] = False  # no work-order integration exists


class LeadProfile(BaseModel):
    intent_level: Literal["high", "low", "unclear"]
    signals: list[str]
    known: dict[str, str]
    missing: list[str]
    next_question: str | None


class RenewalAssessment(BaseModel):
    concerns: list[str]
    renewal_status_known: bool
    open_commitments: int
    tone: str


class HandoffRecommendation(BaseModel):
    status: Literal["recommended_not_sent"] = "recommended_not_sent"
    completed: Literal[False] = False
    team: HandoffTeam
    priority: Literal["urgent", "high", "normal"]
    category: HandoffCategory
    reasons: list[str]
    summary: str  # built deterministically from minimal context; never from model free text
    included_fields: list[str]
    contact_guidance: str | None
    delivery_note: str


class PipelineStep(BaseModel):
    step: str
    status: Literal["ok", "skipped", "warn", "fallback"]
    detail: str
    ms: int = 0


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


# ---- customer actions (prototype system of record; see app/actions.py) --------------------------------

ActionKind = Literal["maintenance_request", "tour_request", "staff_handoff"]
# collecting = still asking questions; ready = read-back shown, waiting for the person to confirm;
# submitted = a prototype record was actually written; blocked = not allowed for this identity.
ActionStage = Literal["collecting", "ready", "submitted", "blocked"]


class ActionField(BaseModel):
    key: str
    label: str
    value: str | None
    source: Literal["you_said", "on_file", "assistant", "missing"]


class ProposedAction(BaseModel):
    """What the person can do next. Never claims completion unless `stage == 'submitted'` and `record` is set."""

    kind: ActionKind
    stage: ActionStage
    title: str
    fields: list[ActionField] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    confirm_label: str | None = None
    note: str  # plain-language statement of what will (or did) happen, including that this is a prototype
    record: "PrototypeRecord | None" = None


class PrototypeRecord(BaseModel):
    """A row in the clearly-labelled prototype store. Not Yardi, not a real queue; nobody is notified."""

    id: str  # DEMO-WO-1001 / DEMO-TOUR-1001 / DEMO-TASK-1001
    kind: ActionKind
    status: Literal["submitted_for_review", "requested", "queued", "urgent_queued"]
    status_label: str
    persona_id: str | None
    session_hash: str
    created_at: datetime
    summary: str
    fields: list[ActionField] = Field(default_factory=list)
    team: str | None = None
    priority: str | None = None
    system: Literal["prototype"] = "prototype"
    # Sprint 8 (agent C, staff view): repeat-request history and the manager review flag saved with a repair. Stored
    # by app/actions.py; returned by the staff /api/prototype/records route. app/api/views.customer_record removes
    # them from anything a non-staff caller gets.
    repeat_history: dict[str, Any] | None = None
    manager_review: bool | None = None
    review_queue: str | None = None


class StatusItem(BaseModel):
    """One item of a verified resident's request history (F8). No entry windows, no staff notes."""

    reference: str
    title: str
    status: str
    opened: str | None
    source: Literal["prototype_store", "resident_history"]
    note: str | None = None


class ActionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    persona_id: str | None = Field(default=None, max_length=40)
    kind: ActionKind


class ActionResult(BaseModel):
    ok: bool
    message: str
    action: ProposedAction | None = None
    record: PrototypeRecord | None = None
    error_code: str | None = None


SafetyState = Literal["normal", "concern", "active"]


class SafetyContact(BaseModel):
    """Sprint 8: one explicit, labelled contact the website may show (never auto-dialled). Chosen by
    app/risk/ui_state.py from the final safety decision; the label is fixed text from app/emergency.CONTACT_LABEL."""

    label: str
    href: Literal["tel:911", "tel:988", "sms:988", "tel:18002221222"] | None = None
    kind: Literal["call", "text", "info"] = "call"


class ChatResponse(BaseModel):
    reply: str
    safety_notice: str | None = None  # deterministic notice shown above the reply (e.g. emergencies)
    emergency_kind: str | None = None  # gas | co | fire_smoke | electrical | flood | structural | ...
    safety_heading: str | None = None
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
    gate: GateDecision | None = None  # None in baseline (generic) mode
    workflow: WorkflowSelection | None = None  # the active flow (may refine the routed one, e.g. leasing -> tour)
    routed_workflow: WorkflowSelection | None = None  # what the decision gate selected; evals grade this
    maintenance: MaintenanceTriage | None = None
    lead: LeadProfile | None = None
    renewal: RenewalAssessment | None = None
    handoff: HandoffRecommendation | None = None
    pipeline: list[PipelineStep] = Field(default_factory=list)
    # ---- customer experience layer (pipeline v3) ----
    channel: Channel = "web_chat"
    language: Literal["en", "es"] = "en"
    functions: list[FunctionId] = Field(default_factory=list)
    reply_source: Literal["model", "template", "template_after_validation", "template_after_model_error"] = "model"
    action: ProposedAction | None = None
    records_created: list[PrototypeRecord] = Field(default_factory=list)
    status_items: list[StatusItem] = Field(default_factory=list)
    suggested_replies: list[str] = Field(default_factory=list)
    identity_note: str | None = None  # plain-language identity status for the customer UI
    action_cleared: ActionKind | None = None  # the open card of this kind was cancelled this turn (UI: "Not sent")
    # Not an emergency, but a possible risk signal (distress / feeling unwell): a calm line shown above the reply.
    care_kind: Literal["distress", "unwell", "danger", "info"] | None = None
    care_note: str | None = None
    risk: RiskAssessment | None = None  # layered safety result (rules, semantic classifier, policy): staff view
    # Sprint 8 UI safety state (app/risk/ui_state.py): active = an alert is shown this turn; concern = a calm line or
    # safety info is shown; normal = no safety text. Contacts are category-specific and empty for normal.
    safety_state: SafetyState = "normal"
    safety_contacts: list[SafetyContact] = Field(default_factory=list)


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
    # deployment facts (no secrets): where it runs, which database kind, where residents came from
    app_env: str = "local"
    database: str = "sqlite"
    resident_source: str | None = None
    is_mock: bool = False  # the default responder is the deterministic mock, not a language model


# ---- evals -----------------------------------------------------------------


class EvalCase(BaseModel):
    id: str
    title: str
    persona_id: str
    message: str
    expected_audience: Audience
    expect_handoff: bool | None  # None = either acceptable
    reference_note: str
    suite: Literal["core", "extended"] = "core"
    expected_intent: Intent | None = None
    expected_workflow: WorkflowId | None = None
    expected_urgency: Urgency | None = None


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
    gate_intent: str | None = None
    gate_urgency: str | None = None
    gate_source: str | None = None
    workflow_id: str | None = None
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
    modes: list[Mode] = Field(default_factory=lambda: ["baseline", "prompt_only", "aware"])
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


GateDecision.model_rebuild()
ProposedAction.model_rebuild()
