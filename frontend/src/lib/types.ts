// Mirrors backend Pydantic contracts in backend/app/models.py.

// baseline = generic prompt; prompt_only = McKinley prompt + gate/workflow, no resident context;
// aware = McKinley prompt + gate/workflow + authorized minimized resident context.
export type Mode = "baseline" | "prompt_only" | "aware";
export type Audience = "prospect" | "resident" | "unknown";
export type Verdict = "GOOD" | "BAD";

export interface Persona {
  language?: "en" | "es";
  id: string;
  label: string;
  kind: "prospect" | "resident" | "unmatched_resident";
  description: string;
  synthetic: boolean;
}

export interface ContextField {
  name: string;
  value: string;
  source: string;
}

export interface SafeContext {
  persona_id: string | null;
  persona_kind: Persona["kind"] | null;
  audience: Audience;
  record_found: boolean;
  topics: string[];
  fields: ContextField[];
  withheld_fields: string[];
  dropped_items: string[];
  notes: string[];
}

export interface PolicySignal {
  code: string;
  category: string;
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
export type Suite = "core" | "extended";

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
  category: string;
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
  handoff_category: string;
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
  care_kind?: "distress" | "unwell" | null;
  care_note?: string | null;
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

export interface ModelTarget {
  key: string;
  provider: string;
  model: string;
  is_default: boolean;
  ready: boolean;
  status: string;
  is_mock: boolean;
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
}

export interface EvalCase {
  id: string;
  title: string;
  persona_id: string;
  message: string;
  expected_audience: Audience;
  expect_handoff: boolean | null;
  reference_note: string;
  suite: Suite;
  expected_intent: Intent | null;
  expected_workflow: WorkflowId | null;
  expected_urgency: Urgency | null;
}

export interface CriterionResult {
  criterion: string;
  passed: boolean | null;
  detail: string;
}

export interface EvalResult {
  id: number;
  run_id: number;
  case_id: string;
  mode: Mode;
  created_at: string;
  status: "ok" | "error";
  error_code: string | null;
  error_message: string | null;
  reply: string | null;
  audience: string | null;
  gate_intent: string | null;
  gate_urgency: string | null;
  gate_source: string | null;
  workflow_id: string | null;
  recommended_handoff: boolean | null;
  handoff_category: string | null;
  handoff_reason: string | null;
  provider: string;
  requested_model: string;
  model: string;
  is_mock: boolean;
  parse_mode: string | null;
  temperature: number | null;
  prompt_version: string;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
  latency_ms: number | null;
  criteria: CriterionResult[];
  provisional_verdict: Verdict | null;
  provisional_rationale: string | null;
  human_verdict: Verdict | null;
  human_notes: string | null;
}

export interface EvalRunResponse {
  run_id: number;
  results: EvalResult[];
}

export interface TargetModeSummary {
  target: string;
  mode: string;
  is_mock: number;
  runs: number;
  errors: number;
  good: number;
  bad: number;
  human_reviewed: number;
  handoffs_recommended: number;
  json_contract_failures: number;
  avg_latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
}

export interface EvalSummary {
  run_id: number | null;
  total: number;
  by_target_mode: Record<string, TargetModeSummary>;
  failure_categories: Record<string, number>;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
}

// ---- /api/gates ----

export interface GateConfig {
  configured_provider: string;
  availability: Record<string, string>;
  low_confidence_threshold: number;
}

export interface GateScenario {
  id: string;
  title: string;
  suite: Suite;
  persona_id: string;
  message: string;
  expected_intent: Intent | null;
  expected_workflow: WorkflowId | null;
  expected_urgency: Urgency | null;
  expect_handoff: boolean | null;
}

export interface GateEvalRow {
  scenario: string;
  provider: string;
  decision_source: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  intent: string;
  intent_ok: boolean;
  workflow: string;
  workflow_ok: boolean;
  urgency: string;
  urgency_ok: boolean | null;
  requires_human: boolean;
  handoff_ok: boolean | null;
  critical_miss: boolean;
  confidence: number;
  risk_flags: string[];
  overrides: string[];
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
}

export interface GateEvalProviderSummary {
  scenarios: number;
  intent_correct: string;
  workflow_correct: string;
  urgency_correct: string;
  handoff_correct: string;
  critical_misses: number;
  fallbacks: number;
  sources: string[];
  avg_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
}

export interface GateEvalResponse {
  note: string;
  availability?: Record<string, string>;
  summary: Record<string, GateEvalProviderSummary>;
  rows: GateEvalRow[];
}

/** Routing metadata only (never message text): gate_decisions row + the stored decision JSON. */
export type GateLogEntry = {
  id: number;
  session_id: string | null;
  mode: Mode;
  persona_id: string | null;
  created_at: string;
} & Partial<GateDecision> & Record<string, unknown>;

// ---- static demo snapshot (frontend/public/demo/snapshot.json, built by backend/app/export_demo.py) ----

export interface DemoSnapshot {
  kind: "static_demo_snapshot";
  generated_at: string;
  notice: string;
  workbook_loaded: boolean;
  personas: Persona[];
  cases: EvalCase[];
  responses: Record<string, Partial<Record<Mode, ChatResponse>>>;
  contexts: Record<string, SafeContext>;
  gate_eval: Pick<GateEvalResponse, "note" | "summary" | "rows">;
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
}

export interface StaffConversationDetail {
  session_hash: string;
  turns: { role: "user" | "assistant"; content: string; persona_id: string; created_at: string }[];
  records: PrototypeRecord[];
}
