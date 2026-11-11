import type {
  ActionKind,
  ActionResult,
  ApiErrorBody,
  ChatRequest,
  ChatResponse,
  DemoSnapshot,
  GateConfig,
  GateEvalResponse,
  GateProvider,
  EvalCase,
  EvalResult,
  EvalRunResponse,
  EvalSummary,
  Health,
  Me,
  Mode,
  ModelTarget,
  Persona,
  PrototypeRecord,
  StaffConversation,
  StaffConversationDetail,
  SafeContext,
  Verdict,
} from "./types";

// Public backend URL only. LLM provider keys live exclusively on the Python server.
// A production build without NEXT_PUBLIC_API_BASE_URL (the here.now replay) never calls localhost: it goes straight to
// the recorded snapshot. Local development and tests default to the local backend.
export const LIVE_BACKEND_CONFIGURED = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000")
).replace(/\/$/, "");
// Render's free plan can take about a minute to wake up; give up after this instead of waiting forever.
const REQUEST_TIMEOUT_MS = 90_000;

/** The sign-in token (a Supabase access token) is added to every backend call when someone is signed in. The backend
 * checks it and the invite list; the website never decides who a person is. Set once by lib/useAuth. */
let tokenProvider: (() => Promise<string | null>) | null = null;
export function setTokenProvider(fn: (() => Promise<string | null>) | null): void {
  tokenProvider = fn;
}

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
    // FastAPI HTTPException with a structured detail: {"detail": {code, message, retryable}}
    if (b.detail && typeof b.detail === "object" && typeof (b.detail as ApiErrorBody).code === "string") {
      const d = b.detail as ApiErrorBody;
      return new ApiError(d.code, d.message ?? `Request failed (${res.status})`, !!d.retryable, res.status);
    }
    if (b.detail) {
      const detail = typeof b.detail === "string" ? b.detail : "Request validation failed";
      return new ApiError(res.status === 422 ? "VALIDATION_ERROR" : `HTTP_${res.status}`, detail, false, res.status);
    }
  }
  return new ApiError(`HTTP_${res.status}`, `Request failed (${res.status})`, res.status >= 500, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) throw new ApiError("BACKEND_UNREACHABLE", "No backend is configured for this site.", false);
  let res: Response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const token = tokenProvider ? await tokenProvider().catch(() => null) : null;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("BACKEND_UNREACHABLE", `Cannot reach the backend at ${API_BASE}.`, true);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  me: () => request<Me>("/api/me"),
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
  /** Routing-only comparison. "llm" makes one model call per scenario. */
  evaluateGates: (providers: GateProvider[]) =>
    request<GateEvalResponse>("/api/gates/evaluate", { method: "POST", body: JSON.stringify({ providers }) }),
  /** The body names the session and kind only; the backend saves its own server-side draft. */
  confirmAction: (session_id: string, persona_id: string | null, kind: ActionKind) =>
    request<ActionResult>("/api/actions/confirm", { method: "POST", body: JSON.stringify({ session_id, persona_id, kind }) }),
  cancelAction: (session_id: string, persona_id: string | null, kind: ActionKind) =>
    request<ActionResult>("/api/actions/cancel", { method: "POST", body: JSON.stringify({ session_id, persona_id, kind }) }),
  prototypeRecords: (limit = 50) => request<PrototypeRecord[]>(`/api/prototype/records?limit=${limit}`),
  staffConversations: (limit = 30) => request<StaffConversation[]>(`/api/staff/conversations?limit=${limit}`),
  staffConversation: (hash: string) => request<StaffConversationDetail>(`/api/staff/conversations/${encodeURIComponent(hash)}`),
};

/** Whether the customer page may offer the demo sign-in picker. The backend decides (app/auth.py): a hosted backend
 * says demo_personas_enabled=false and returns no personas, so the page is guest-only. Picking a demo persona is
 * NOT authentication; the backend re-derives and checks the principal on every request. */
export function demoSignInAvailable(personas: Persona[], health: Health | null): boolean {
  if (health?.demo_personas_enabled === false) return false;
  return personas.length > 0;
}

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
