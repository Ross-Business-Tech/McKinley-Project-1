import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, DemoSnapshot, EvalCase, GateConfig, Mode, ModelTarget, Persona } from "@/lib/types";

import { AppShell } from "./AppShell";
import { ChatWorkbench } from "./ChatWorkbench";
import { Diagnostics, HandoffCard, HandoffPanel, ResponseView } from "./ResponseDetails";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const personas: Persona[] = [
  { id: "R001", label: "R001 · Marisol (synthetic resident)", kind: "resident", description: "", synthetic: true },
];
const targets: ModelTarget[] = [
  { key: "mock:mock-deterministic-v1", provider: "mock", model: "mock-deterministic-v1", is_default: true, ready: true,
    status: "deterministic mock", is_mock: true },
];
const cases: EvalCase[] = [
  { id: "case3", title: "Repeated AC", persona_id: "R001", message: "My AC stopped cooling again.",
    expected_audience: "resident", expect_handoff: true, reference_note: "", suite: "core",
    expected_intent: "maintenance", expected_workflow: "maintenance", expected_urgency: "high" },
  { id: "x01", title: "Emergency: gas smell", persona_id: "R001", message: "I smell gas in my kitchen.",
    expected_audience: "resident", expect_handoff: true, reference_note: "", suite: "extended",
    expected_intent: "maintenance", expected_workflow: "maintenance", expected_urgency: "emergency" },
];
const gateConfig: GateConfig = {
  configured_provider: "rules",
  availability: { rules: "ready (deterministic)", llm: "ready: mock:mock-deterministic-v1 (mock)", jev: "unavailable: TYPESAFE_API_KEY not set" },
  low_confidence_threshold: 0.5,
};

function chatResponse(mode: Mode, extra: Partial<ChatResponse> = {}): ChatResponse {
  const routed = mode !== "baseline";
  return {
    reply: `${mode} reply text`, safety_notice: null, mode, audience: "resident", recommended_handoff: routed,
    handoff_reason: "Repeated related maintenance requests", handoff_category: "repeat_issue",
    handoff_is_recommendation_only: true, model_handoff: true, policy_signals: [],
    output_checks: [{ code: "terminology", passed: true, detail: "ok" }],
    source_context_fields: mode === "aware" ? ["first_name ← Residents.first_name"] : [],
    provider: "mock", requested_model: "mock-deterministic-v1", model: "mock-deterministic-v1", is_mock: true,
    parse_mode: "json", temperature: 0.2, prompt_version: "v", usage: { input_tokens: 1, output_tokens: 1,
    estimated_cost_usd: 0 }, latency_ms: 5, stop_reason: "mock", session_id: "s", created_at: "",
    gate: routed ? {
      audience: "resident", intent: "maintenance", urgency: "high", requires_human: true,
      handoff_reason: "Repeat issue", confidence: 0.85, confidence_calibrated: false, risk_flags: ["repeat_issue"],
      decision_source: "mock", requested_provider: "llm", fallback_used: true, fallback_reason: "provider timeout",
      overrides: ["urgency raised to high by safety floor"], rationale: ["pattern:repeat"], latency_ms: 0, gate_usage: null,
    } : null,
    workflow: routed ? { id: "maintenance", label: "Maintenance", reason: "Repair request", instructions_version: "wf-v1" } : null,
    maintenance: routed ? { level: "repeat", category: "hvac", approved_troubleshooting: ["Check thermostat mode"],
      entry_window_on_file: true, work_order_created: false } : null,
    lead: null,
    renewal: null,
    handoff: routed ? {
      status: "recommended_not_sent", completed: false, team: "maintenance", priority: "high", category: "repeat_issue",
      reasons: ["Repeat issue"], summary: "Resident · maintenance · urgency high.", included_fields: ["first_name"],
      contact_guidance: "portal", delivery_note: "Not sent. This prototype has no staff notification integration.",
    } : null,
    pipeline: routed ? [
      { step: "2_identity", status: "ok", detail: "audience=resident, identity_verified=True", ms: 0 },
      { step: "5_gate", status: "fallback", detail: "llm failed; rules used", ms: 0 },
      { step: "10_persist", status: "skipped", detail: "not stored", ms: 0 },
    ] : [],
    ...extra,
  };
}

describe("HandoffPanel", () => {
  it("states that handoff is a recommendation only", () => {
    render(<HandoffPanel r={{ recommended_handoff: true, handoff_category: "repeat_issue", handoff_reason: "why",
      model_handoff: false, mode: "aware" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Recommendation only");
    expect(screen.getByRole("status")).toHaveTextContent("backend policy gate");
  });
});

describe("HandoffCard", () => {
  it("says the handoff was recommended but not sent and shows the delivery note", () => {
    const h = chatResponse("aware").handoff!;
    render(<HandoffCard h={h} noWorkOrder />);
    const card = screen.getByRole("status", { name: "Staff handoff recommendation" });
    expect(card).toHaveTextContent("Recommended — not sent");
    expect(card).toHaveTextContent(h.delivery_note);
    expect(card).toHaveTextContent("No work order created (no integration)");
  });
});

describe("ResponseView", () => {
  it("renders the safety notice as an alert above the reply", () => {
    const r = chatResponse("aware", { safety_notice: "Leave the area now and call 911.", reply: "Your safety comes first." });
    render(<ResponseView r={r} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Leave the area now and call 911.");
    const reply = screen.getByText("Your safety comes first.");
    expect(alert.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("MOCK")).toBeInTheDocument();
  });

  it("shows no safety alert when there is no notice", () => {
    render(<ResponseView r={chatResponse("aware")} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Diagnostics", () => {
  it("is closed by default and exposes gate, workflow, triage and pipeline details", async () => {
    const user = userEvent.setup();
    const { container } = render(<Diagnostics r={chatResponse("aware")} />);
    const details = container.querySelector("details")!;
    expect(details.open).toBe(false);
    await user.click(screen.getByText(/Why this answer/));
    expect(details.open).toBe(true);
    const panel = within(details);
    expect(panel.getByText("(heuristic, not calibrated)")).toBeInTheDocument();
    expect(panel.getByText(/mock \(deterministic stand-in/)).toBeInTheDocument();
    expect(panel.getByText(/yes — provider timeout/)).toBeInTheDocument();
    expect(panel.getByText(/urgency raised to high by safety floor/)).toBeInTheDocument();
    expect(panel.getByText("Maintenance (maintenance)")).toBeInTheDocument();
    expect(panel.getByText("No work order created (no integration)")).toBeInTheDocument();
    expect(panel.getByText("first_name ← Residents.first_name")).toBeInTheDocument();
    expect(panel.getByText("fallback")).toBeInTheDocument();
    expect(panel.getAllByText(/identity_verified=True/).length).toBeGreaterThan(0);
  });

  it("explains that baseline mode has no gate", () => {
    render(<Diagnostics r={chatResponse("baseline")} />);
    expect(screen.getByText(/generic baseline mode has no decision gate/)).toBeInTheDocument();
  });
});

function liveFetch() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/context/preview")) {
      return new Response(JSON.stringify({ persona_id: "R001", persona_kind: "resident", audience: "resident",
        record_found: true, topics: ["hvac"], fields: [{ name: "first_name", value: "Marisol", source: "Residents.first_name" }],
        withheld_fields: ["email"], dropped_items: [], notes: [] }));
    }
    const body = JSON.parse(String(init?.body));
    return new Response(JSON.stringify(chatResponse(body.mode)));
  });
}

const chatBodies = (fetchMock: ReturnType<typeof liveFetch>) =>
  fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/api/chat")).map(([, i]) => JSON.parse(String(i?.body)));

describe("ChatWorkbench", () => {
  it("defaults to modes A and C and sends the same message to both", async () => {
    const fetchMock = liveFetch();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWorkbench personas={personas} targets={targets} cases={cases} gateConfig={gateConfig} />);

    expect(screen.getByRole("checkbox", { name: /Generic baseline/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /McKinley prompt only/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /McKinley \+ resident context/ })).toBeChecked();
    expect(screen.getByRole("group", { name: "Core five" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Extended scenarios" })).toBeInTheDocument();
    expect(screen.getByLabelText("Decision gate")).toHaveValue("rules");

    await user.click(screen.getByRole("button", { name: /Repeated AC/ }));
    expect(screen.getByLabelText(/Message/)).toHaveValue("My AC stopped cooling again.");
    await user.click(screen.getByRole("button", { name: "Compare responses" }));

    await waitFor(() => expect(screen.getByText("aware reply text")).toBeInTheDocument());
    expect(screen.getByText("baseline reply text")).toBeInTheDocument();
    const bodies = chatBodies(fetchMock);
    expect(bodies.map((b) => b.mode).sort()).toEqual(["aware", "baseline"]);
    expect(new Set(bodies.map((b) => b.message)).size).toBe(1);
    expect(bodies.every((b) => b.gate_provider === "rules")).toBe(true);
    expect(screen.getAllByText("MOCK").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Marisol")).toBeInTheDocument());
  });

  it("mode toggles control which modes are called", async () => {
    const fetchMock = liveFetch();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWorkbench personas={personas} targets={targets} cases={cases} gateConfig={gateConfig} />);

    await user.click(screen.getByRole("checkbox", { name: /Generic baseline/ }));
    await user.click(screen.getByRole("checkbox", { name: /McKinley prompt only/ }));
    await user.selectOptions(screen.getByLabelText("Decision gate"), "llm");
    await user.type(screen.getByLabelText(/Message/), "Hello");
    await user.click(screen.getByRole("button", { name: "Compare responses" }));

    await waitFor(() => expect(screen.getByText("prompt_only reply text")).toBeInTheDocument());
    const bodies = chatBodies(fetchMock);
    expect(bodies.map((b) => b.mode).sort()).toEqual(["aware", "prompt_only"]);
    expect(bodies.every((b) => b.gate_provider === "llm")).toBe(true);
    expect(screen.queryByRole("region", { name: /Generic baseline responses/ })).not.toBeInTheDocument();
  });

  it("does not allow deselecting the last mode", async () => {
    vi.stubGlobal("fetch", liveFetch());
    const user = userEvent.setup();
    render(<ChatWorkbench personas={personas} targets={targets} cases={cases} />);
    await user.click(screen.getByRole("checkbox", { name: /Generic baseline/ }));
    expect(screen.getByRole("checkbox", { name: /McKinley \+ resident context/ })).toBeDisabled();
  });
});

const snapshot: DemoSnapshot = {
  kind: "static_demo_snapshot",
  generated_at: "2026-11-05T07:57:22Z",
  notice: "Static demonstration: pre-computed with the deterministic MOCK provider.",
  workbook_loaded: true,
  personas,
  cases,
  responses: {
    x01: {
      baseline: chatResponse("baseline", { reply: "snapshot baseline reply" }),
      prompt_only: chatResponse("prompt_only", { reply: "snapshot prompt-only reply" }),
      aware: chatResponse("aware", { reply: "snapshot aware reply", safety_notice: "Call 911 from outside." }),
    },
  },
  contexts: {
    x01: { persona_id: "R001", persona_kind: "resident", audience: "resident", record_found: true, topics: ["gas"],
      fields: [{ name: "first_name", value: "Snapshot Marisol", source: "Residents.first_name" }],
      withheld_fields: [], dropped_items: [], notes: [] },
  },
  gate_eval: {
    note: "Automated comparison against developer labels.",
    summary: { rules: { scenarios: 1, intent_correct: "1/1", workflow_correct: "1/1", urgency_correct: "1/1",
      handoff_correct: "1/1", critical_misses: 0, fallbacks: 0, sources: ["rules"], avg_latency_ms: 0,
      input_tokens: 0, output_tokens: 0 } },
    rows: [],
  },
};

describe("AppShell static demo fallback", () => {
  it("loads the snapshot when the backend is unreachable", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response(JSON.stringify(snapshot));
      throw new TypeError("fetch failed");
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AppShell />);

    await waitFor(() => expect(screen.getByText(/Static demo — responses were pre-computed/)).toBeInTheDocument());
    expect(screen.getByText(/Static demonstration: pre-computed/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Message/)).toBeDisabled();
    expect(screen.getByText(/needs the live backend/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compare responses" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Emergency: gas smell/ }));
    expect(screen.getByText("snapshot aware reply")).toBeInTheDocument();
    expect(screen.getByText("snapshot baseline reply")).toBeInTheDocument();
    expect(screen.queryByText("snapshot prompt-only reply")).not.toBeInTheDocument();
    expect(screen.getByText("Call 911 from outside.")).toBeInTheDocument();
    expect(screen.getByText("Snapshot Marisol")).toBeInTheDocument();

    // Toggling mode B shows the stored response without any network call.
    const callsBefore = fetchMock.mock.calls.length;
    await user.click(screen.getByRole("checkbox", { name: /McKinley prompt only/ }));
    expect(screen.getByText("snapshot prompt-only reply")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
    expect(fetchMock.mock.calls.every(([u]) => !String(u).includes("/api/chat"))).toBe(true);

    await user.click(screen.getByRole("tab", { name: "Evaluation" }));
    expect(await screen.findByText("Automated, not human-reviewed")).toBeInTheDocument();
    expect(screen.getByText("Automated comparison against developer labels.")).toBeInTheDocument();
  });

  it("shows the backend error when the snapshot also fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response("not found", { status: 404 });
      throw new TypeError("fetch failed");
    }));
    render(<AppShell />);
    await waitFor(() => expect(screen.getByText(/Backend unavailable: Cannot reach the backend/)).toBeInTheDocument());
    expect(screen.queryByText(/Static demo — responses/)).not.toBeInTheDocument();
  });
});
