import type {
  ActionKind,
  ActionResult,
  ApiErrorBody,
  ChatRequest,
  ChatResponse,
  DemoSnapshot,
  GateConfig,
  GateEvalResponse,
  GateLogEntry,
  GateProvider,
  GateScenario,
  EvalCase,
  EvalResult,
  EvalRunResponse,
  EvalSummary,
  Health,
  Mode,
  ModelTarget,
  Persona,
  PrototypeRecord,
  SafeContext,
  Verdict,
} from "./types";

// Public backend URL only. LLM provider keys live exclusively on the Python server.
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public retryable = false,
    public status = 0,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error */
  }
  if (body && typeof body === "object") {
    const b = body as { error?: ApiErrorBody; detail?: unknown };
    if (b.error?.code) return new ApiError(b.error.code, b.error.message, b.error.retryable, res.status);
    if (b.detail) {
      const detail = typeof b.detail === "string" ? b.detail : "Request validation failed";
      return new ApiError(res.status === 422 ? "VALIDATION_ERROR" : `HTTP_${res.status}`, detail, false, res.status);
    }
  }
  return new ApiError(`HTTP_${res.status}`, `Request failed (${res.status})`, res.status >= 500, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("BACKEND_UNREACHABLE", `Cannot reach the backend at ${API_BASE}. Is uvicorn running?`, true);
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  models: () => request<ModelTarget[]>("/api/models"),
  personas: () => request<Persona[]>("/api/personas"),
  contextPreview: (persona_id: string | null, message: string) =>
    request<SafeContext>("/api/context/preview", { method: "POST", body: JSON.stringify({ persona_id, message }) }),
  chat: (body: ChatRequest) => request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify(body) }),
  evalCases: () => request<EvalCase[]>("/api/evals/cases"),
  runEvals: (targets: string[], case_ids?: string[], modes?: Mode[]) =>
    request<EvalRunResponse>("/api/evals/run", { method: "POST", body: JSON.stringify({ targets, case_ids, modes }) }),
  evalResults: (run_id?: number) => request<EvalRunResponse>(`/api/evals/results${run_id ? `?run_id=${run_id}` : ""}`),
  evalSummary: (run_id?: number) => request<EvalSummary>(`/api/evals/summary${run_id ? `?run_id=${run_id}` : ""}`),
  review: (id: number, human_verdict: Verdict | null, human_notes: string | null) =>
    request<EvalResult>(`/api/evals/results/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ human_verdict, human_notes }),
    }),
  gatesConfig: () => request<GateConfig>("/api/gates/config"),
  gateScenarios: () => request<GateScenario[]>("/api/gates/scenarios"),
  /** Routing-only comparison. "llm" makes one model call per scenario. */
  evaluateGates: (providers: GateProvider[]) =>
    request<GateEvalResponse>("/api/gates/evaluate", { method: "POST", body: JSON.stringify({ providers }) }),
  gateLog: (limit = 50) => request<GateLogEntry[]>(`/api/gates/log?limit=${limit}`),
  /** The body names the session and kind only; the backend saves its own server-side draft. */
  confirmAction: (session_id: string, persona_id: string | null, kind: ActionKind) =>
    request<ActionResult>("/api/actions/confirm", { method: "POST", body: JSON.stringify({ session_id, persona_id, kind }) }),
  cancelAction: (session_id: string, persona_id: string | null, kind: ActionKind) =>
    request<ActionResult>("/api/actions/cancel", { method: "POST", body: JSON.stringify({ session_id, persona_id, kind }) }),
  prototypeRecords: (limit = 50) => request<PrototypeRecord[]>(`/api/prototype/records?limit=${limit}`),
};

/** Root-relative static snapshot served with the site (used when the backend is unreachable). */
export const SNAPSHOT_PATH = "/demo/snapshot.json";

export async function loadDemoSnapshot(): Promise<DemoSnapshot> {
  let res: Response;
  try {
    res = await fetch(SNAPSHOT_PATH, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("SNAPSHOT_UNAVAILABLE", "The static demo snapshot could not be loaded.");
  }
  if (!res.ok) throw new ApiError("SNAPSHOT_UNAVAILABLE", `The static demo snapshot could not be loaded (${res.status}).`);
  const data = (await res.json()) as DemoSnapshot;
  if (data?.kind !== "static_demo_snapshot" || !data.responses || !Array.isArray(data.cases)) {
    throw new ApiError("SNAPSHOT_INVALID", "The static demo snapshot is not in the expected format.");
  }
  return data;
}
