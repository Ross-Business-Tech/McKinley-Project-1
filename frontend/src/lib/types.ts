// Mirrors backend Pydantic contracts in backend/app/models.py.

export type Mode = "baseline" | "aware";
export type Audience = "prospect" | "resident" | "unknown";
export type Verdict = "GOOD" | "BAD";

export interface Persona {
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

export interface ChatResponse {
  reply: string;
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
