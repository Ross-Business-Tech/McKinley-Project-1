// Mirrors backend Pydantic contracts in backend/app/models.py.

// baseline = generic prompt; prompt_only = McKinley prompt + gate/workflow, no resident context;
// aware = McKinley prompt + gate/workflow + authorized minimized resident context.
export type Mode = "baseline" | "prompt_only" | "aware";
export type Audience = "prospect" | "resident" | "unknown";

export interface Persona {
  language?: "en" | "es";
  id: string;
  label: string;
  kind: "prospect" | "resident" | "unmatched_resident";
  description: string;
  synthetic: boolean;
}

/** Mirrors backend/app/models.py HandoffCategory. */
export type HandoffCategory =
  | "none"
  | "safety_emergency"
  | "repeat_issue"
  | "unresolved_commitment"
  | "human_requested"
  | "policy_or_eligibility"
  | "financial_or_lease"
  | "fair_housing_or_legal"
  | "leasing_follow_up"
  | "sensitive_data_request"
  | "other";

export interface PolicySignal {
  code: string;
  category: HandoffCategory;
  detail: string;
}

export interface OutputCheck {
  code: string;
  passed: boolean;
  detail: string;
}

export interface Usage {
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
}

// ---- decision gate / workflow / handoff (pipeline v2) ----

export type Intent = "leasing" | "maintenance" | "renewal" | "general";
export type Urgency = "low" | "medium" | "high" | "emergency";
export type GateSource = "rules" | "jev" | "llm" | "mock";
export type GateProvider = "rules" | "llm" | "jev";
export type WorkflowId =
  | "leasing"
  | "tour_request"
  | "faq"
  | "resident_support"
  | "maintenance"
  | "status_lookup"
  | "renewal"
  | "human_handoff"
  | "general_inquiry"
  | "sms_opt_out";
export type HandoffTeam = "emergency_maintenance" | "maintenance" | "leasing" | "accounting" | "management";

export interface GateDecision {
  /** Always the trusted (application-established) audience. */
  audience: Audience;
  intent: Intent;
  urgency: Urgency;
  requires_human: boolean;
  handoff_reason: string | null;
  confidence: number;
  confidence_calibrated: boolean;
  risk_flags: string[];
  decision_source: GateSource;
  requested_provider: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  overrides: string[];
  rationale: string[];
  latency_ms: number;
  gate_usage: Usage | null;
}

export interface WorkflowSelection {
  id: WorkflowId;
  label: string;
  reason: string;
  instructions_version: string;
}

export interface MaintenanceTriage {
  level: "emergency" | "repeat" | "routine" | "unclear";
  category: string;
  approved_troubleshooting: string[];
  entry_window_on_file: boolean;
  work_order_created: false;
}

export interface LeadProfile {
  intent_level: "high" | "low" | "unclear";
  signals: string[];
  known: Record<string, string>;
  missing: string[];
  next_question: string | null;
}

export interface RenewalAssessment {
  concerns: string[];
  renewal_status_known: boolean;
  open_commitments: number;
  tone: string;
}

export interface HandoffRecommendation {
  status: "recommended_not_sent";
  completed: false;
  team: HandoffTeam;
  priority: "urgent" | "high" | "normal";
  category: HandoffCategory;
  reasons: string[];
  summary: string;
  included_fields: string[];
  contact_guidance: string | null;
  delivery_note: string;
}

export interface PipelineStep {
  step: string;
  status: "ok" | "skipped" | "warn" | "fallback";
  detail: string;
  ms: number;
}

export interface ChatResponse {
  reply: string;
  safety_notice: string | null;
  mode: Mode;
  audience: Audience;
  recommended_handoff: boolean;
  handoff_reason: string | null;
  handoff_category: HandoffCategory;
  handoff_is_recommendation_only: boolean;
  model_handoff: boolean;
  policy_signals: PolicySignal[];
  output_checks: OutputCheck[];
  source_context_fields: string[];
  provider: string;
  requested_model: string;
  model: string;
  is_mock: boolean;
  parse_mode: string;
  temperature: number | null;
  prompt_version: string;
  usage: Usage;
  latency_ms: number;
  stop_reason: string | null;
  session_id: string;
  created_at: string;
  gate: GateDecision | null; // null in baseline (generic) mode
  workflow: WorkflowSelection | null;
  maintenance: MaintenanceTriage | null;
  lead: LeadProfile | null;
  renewal: RenewalAssessment | null;
  handoff: HandoffRecommendation | null;
  pipeline: PipelineStep[];
  // ---- customer experience layer (pipeline v3); optional so older snapshots still load ----
  routed_workflow?: WorkflowSelection | null;
  channel?: Channel;
  language?: "en" | "es";
  functions?: FunctionId[];
  reply_source?: ReplySource;
  action?: ProposedAction | null;
  records_created?: PrototypeRecord[];
  status_items?: StatusItem[];
  suggested_replies?: string[];
  identity_note?: string | null;
  action_cleared?: ActionKind | null;
  emergency_kind?: string | null;
  safety_heading?: string | null;
  /** Not an emergency but a possible risk signal: a calm line shown above the reply (never the red alert). */
  care_kind?: "distress" | "unwell" | "danger" | "info" | null;
  risk?: RiskAssessment | null;
  care_note?: string | null;
  /** Sprint 8: how the customer screen shows safety this turn. Missing on older backends / the replay snapshot. */
  safety_state?: SafetyState | null;
  /** Sprint 8: category-specific contacts for this turn (empty for "normal"). Never auto-dialled. */
  safety_contacts?: SafetyContact[] | null;
}

/** normal = nothing shown; concern = calm inline note; active = in-conversation alert with labelled contact links. */
export type SafetyState = "normal" | "concern" | "active";

/** The only numbers the customer screen will ever turn into a link (anything else is shown as plain text). */
export type SafetyHref = "tel:911" | "tel:988" | "sms:988" | "tel:18002221222";

export interface SafetyContact {
  label: string;
  href: SafetyHref | null;
  kind: "call" | "text" | "info";
}

export type Channel = "web_chat" | "sms" | "email";
export type FunctionId = "F1" | "F2" | "F3" | "F4" | "F5" | "F6" | "F7" | "F8" | "F9";
export type ReplySource = "model" | "template" | "template_after_validation" | "template_after_model_error";
export type ActionKind = "maintenance_request" | "tour_request" | "staff_handoff";
export type ActionStage = "collecting" | "ready" | "submitted" | "blocked";

export interface ActionField {
  key: string;
  label: string;
  value: string | null;
  source: "you_said" | "on_file" | "assistant" | "missing";
}

export interface PrototypeRecord {
  id: string;
  kind: ActionKind;
  status: "submitted_for_review" | "requested" | "queued" | "urgent_queued";
  status_label: string;
  persona_id: string | null;
  session_hash: string;
  created_at: string;
  summary: string;
  fields: ActionField[];
  team: string | null;
  priority: string | null;
  system: "prototype";
}

export interface ProposedAction {
  kind: ActionKind;
  stage: ActionStage;
  title: string;
  fields: ActionField[];
  missing: string[];
  confirm_label: string | null;
  note: string;
  record: PrototypeRecord | null;
}

export interface StatusItem {
  reference: string;
  title: string;
  status: string;
  opened: string | null;
  source: "prototype_store" | "resident_history";
  note: string | null;
}

export interface ActionResult {
  ok: boolean;
  message: string;
  action: ProposedAction | null;
  record: PrototypeRecord | null;
  error_code: string | null;
}

export type JourneyStep =
  | { kind: "chat"; message: string; response: ChatResponse }
  | { kind: "confirm"; action_kind: ActionKind; result: ActionResult };

export interface Journey {
  id: string;
  persona_id: string;
  title: string;
  steps: JourneyStep[];
}

export interface ChatRequest {
  message: string;
  persona_id: string | null;
  mode: Mode;
  session_id: string;
  target?: string;
  gate_provider?: GateProvider;
  channel?: Channel;
}

export interface Health {
  status: "ok";
  provider: string;
  model: string;
  provider_ready: boolean;
  provider_status: string;
  prompt_version: string;
  data_loaded: boolean;
  data_error: string | null;
  resident_count: number;
  interaction_count: number;
  // deployment facts (optional: older backends and the static snapshot don't send them)
  app_env?: "local" | "hosted";
  database?: "sqlite" | "postgres" | ""; // "" = public health subset (not staff)
  resident_source?: string | null;
  is_mock?: boolean;
  /** Sprint 10: API version and the short git commit of the deployment (when the host provides it). */
  version?: string;
  commit?: string | null;
  // false = this backend has no demo personas (APP_ENV=hosted): hide the demo sign-in, guest only
  demo_personas_enabled?: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
}

// ---- /api/gates ----

// ---- static demo snapshot (frontend/public/demo/snapshot.json, built by backend/app/export_demo.py) ----

export interface DemoSnapshot {
  kind: "static_demo_snapshot";
  generated_at: string;
  notice: string;
  workbook_loaded: boolean;
  personas: Persona[];
  journeys?: Journey[];
  prototype_records?: PrototypeRecord[];
}

/** Staff console: a recent live conversation (keyed by a one-way session hash, never the session id). */
export interface StaffConversation {
  session_hash: string;
  persona_id: string | null;
  messages: number;
  started: string;
  last: string;
  records: { id: string; kind: ActionKind; status_label: string | null; priority: string | null }[];
  needs_action?: ("urgent" | "wellbeing" | "asked_for_person" | "safety_check_failed")[];
}

export interface StaffConversationDetail {
  session_hash: string;
  turns: { role: "user" | "assistant"; content: string; persona_id: string; created_at: string }[];
  records: PrototypeRecord[];
}

/** Layered safety result (mirrors backend/app/risk/models.py). Shown in the staff/demo console only; note the
 * customer API response also carries it, so it must never contain anything the customer may not see. */
export type RiskCategory =
  | "fire_smoke" | "gas" | "co" | "electrical" | "flood" | "structural" | "trapped" | "medical" | "poison"
  | "personal_safety" | "self_harm";
export type Framing = "report" | "hypothetical" | "past" | "joking" | "quoted" | "figurative" | "none";
export type ClassifierStatus =
  | "ok" | "disabled" | "unavailable" | "timeout" | "rate_limited" | "error" | "bad_output" | "mock";

export interface DeterministicRisk {
  kind: string | null;
  framing: Framing;
  mentioned_kind: string | null;
  care: "distress" | "unwell" | "danger" | null;
  via_window: boolean;
  self_harm_intent: boolean;
}

export interface SemanticRisk {
  risk_level: "none" | "uncertain" | "urgent" | "emergency";
  risk_categories: RiskCategory[];
  immediate_danger: boolean;
  needs_human: boolean;
  confidence: number | null;
  framing: Framing;
  reason: string;
}

export interface SemanticResult {
  status: ClassifierStatus;
  risk?: SemanticRisk | null;
  target?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  detail?: string | null;
}

export interface RiskDecision {
  response: "full_alert" | "care_line" | "safety_info" | "none";
  kind: string | null;
  care: "distress" | "unwell" | "danger" | "info" | null;
  also_988: boolean;
  needs_human: boolean;
  escalation_priority: "urgent" | "high" | "normal" | null;
  sources: string[];
  rule: string;
  conflict: string | null;
  degraded: boolean;
}

export interface RiskAssessment {
  deterministic: DeterministicRisk;
  semantic: SemanticResult;
  decision: RiskDecision;
}
