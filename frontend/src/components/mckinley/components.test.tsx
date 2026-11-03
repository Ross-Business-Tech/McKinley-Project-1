import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, EvalCase, ModelTarget, Persona } from "@/lib/types";

import { ChatWorkbench } from "./ChatWorkbench";
import { HandoffPanel } from "./ResponseDetails";

afterEach(() => vi.unstubAllGlobals());

const personas: Persona[] = [
  { id: "R001", label: "R001 · Marisol (synthetic resident)", kind: "resident", description: "", synthetic: true },
];
const targets: ModelTarget[] = [
  { key: "mock:mock-deterministic-v1", provider: "mock", model: "mock-deterministic-v1", is_default: true, ready: true,
    status: "deterministic mock", is_mock: true },
];
const cases: EvalCase[] = [
  { id: "case3", title: "Repeated AC", persona_id: "R001", message: "My AC stopped cooling again.",
    expected_audience: "resident", expect_handoff: true, reference_note: "" },
];

function chatResponse(mode: "baseline" | "aware"): ChatResponse {
  return {
    reply: `${mode} reply text`, mode, audience: "resident", recommended_handoff: mode === "aware",
    handoff_reason: "Repeated related maintenance requests", handoff_category: "repeat_issue",
    handoff_is_recommendation_only: true, model_handoff: true, policy_signals: [],
    output_checks: [{ code: "terminology", passed: true, detail: "ok" }], source_context_fields: [],
    provider: "mock", requested_model: "mock-deterministic-v1", model: "mock-deterministic-v1", is_mock: true,
    parse_mode: "json", temperature: 0.2, prompt_version: "v", usage: { input_tokens: 1, output_tokens: 1,
    estimated_cost_usd: 0 }, latency_ms: 5, stop_reason: "mock", session_id: "s", created_at: "",
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

describe("ChatWorkbench", () => {
  it("loads a scenario and sends the same message to both modes", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/context/preview")) {
        return new Response(JSON.stringify({ persona_id: "R001", persona_kind: "resident", audience: "resident",
          record_found: true, topics: ["hvac"], fields: [{ name: "first_name", value: "Marisol", source: "Residents.first_name" }],
          withheld_fields: ["email"], dropped_items: [], notes: [] }));
      }
      const body = JSON.parse(String(init?.body));
      return new Response(JSON.stringify(chatResponse(body.mode)));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWorkbench personas={personas} targets={targets} cases={cases} />);

    await user.click(screen.getByRole("button", { name: /Repeated AC/ }));
    expect(screen.getByLabelText(/Message/)).toHaveValue("My AC stopped cooling again.");
    await user.click(screen.getByRole("button", { name: "Compare responses" }));

    await waitFor(() => expect(screen.getByText("aware reply text")).toBeInTheDocument());
    expect(screen.getByText("baseline reply text")).toBeInTheDocument();
    const chatBodies = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/api/chat")).map(([, i]) => JSON.parse(String(i?.body)));
    expect(chatBodies.map((b) => b.mode).sort()).toEqual(["aware", "baseline"]);
    expect(new Set(chatBodies.map((b) => b.message)).size).toBe(1);
    expect(screen.getAllByText("MOCK").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Marisol")).toBeInTheDocument());
  });
});
