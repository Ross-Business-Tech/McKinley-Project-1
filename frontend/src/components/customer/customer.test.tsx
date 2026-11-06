import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, Persona, ProposedAction } from "@/lib/types";

import { CustomerApp } from "./CustomerApp";

const personas: Persona[] = [
  { id: "R001", label: "R001 · Marisol (synthetic resident)", kind: "resident", description: "Synthetic workbook resident at Heron Lake Apartments.", synthetic: true },
  { id: "R012", label: "R012 · Valeria (synthetic resident)", kind: "resident", description: "Synthetic workbook resident at Heron Lake Apartments.", synthetic: true, language: "es" },
];

const readyCard: ProposedAction = {
  kind: "maintenance_request",
  stage: "ready",
  title: "Repair request",
  fields: [{ key: "issue", label: "What's wrong", value: "Kitchen faucet drips", source: "you_said" }],
  missing: [],
  confirm_label: "Send repair request",
  note: "Nothing is sent until you press send.",
  record: null,
};

function resp(over: Partial<ChatResponse>): ChatResponse {
  return {
    reply: "ok", safety_notice: null, mode: "aware", audience: "resident", recommended_handoff: false, handoff_reason: null,
    handoff_category: "none", handoff_is_recommendation_only: true, model_handoff: false, policy_signals: [], output_checks: [],
    source_context_fields: [], provider: "mock", requested_model: "m", model: "m", is_mock: true, parse_mode: "json",
    temperature: 0, prompt_version: "v", usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 }, latency_ms: 1,
    stop_reason: null, session_id: "s", created_at: "2026-11-06T00:00:00Z", gate: null, workflow: null, maintenance: null,
    lead: null, renewal: null, handoff: null, pipeline: [], language: "en", suggested_replies: [], ...over,
  };
}

function live(chat: (body: { message: string }) => ChatResponse | Error) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/api/personas")) return new Response(JSON.stringify(personas));
    if (url.endsWith("/api/chat")) {
      const out = chat(JSON.parse(String(init?.body)));
      if (out instanceof Error) throw out;
      return new Response(JSON.stringify(out));
    }
    if (url.endsWith("/api/actions/cancel")) return new Response(JSON.stringify({ ok: true, message: "ok", action: null, record: null, error_code: null }));
    throw new TypeError("fetch failed");
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CustomerApp", () => {
  it("marks a declined card as not sent and removes its send button", async () => {
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    const card = await screen.findByRole("group", { name: "Repair request" });
    await user.click(within(card).getByRole("button", { name: "Don't send" }));
    await waitFor(() => expect(within(card).getByText("Not sent")).toBeInTheDocument());
    expect(within(card).queryByRole("button", { name: "Send repair request" })).not.toBeInTheDocument();
    // focus never falls to <body> after the focused button disappears
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  });

  it("gives emergencies a tap-to-call 911 link", async () => {
    live(() => resp({
      reply: "Leave now. Call 911.", safety_notice: "Leave now.", emergency_kind: "gas",
      safety_heading: "If anyone is in danger, call 911 now", reply_source: "template",
    }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "I smell gas{Enter}");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("link", { name: /Call 911/ })).toHaveAttribute("href", "tel:911");
  });

  it("marks a failed message and keeps focus in the composer", async () => {
    live(() => new TypeError("fetch failed"));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    const box = screen.getByLabelText("Message the assistant");
    await user.type(box, "Is parking included?{Enter}");
    expect(await screen.findByText("Not sent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send again/ })).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(box));
  });

  it("greets a Spanish-preferring resident in Spanish and tags replies with lang", async () => {
    live(() => resp({ reply: "¿En qué parte del apartamento es?", language: "es", action: { ...readyCard, stage: "collecting", confirm_label: null, missing: ["Dónde"] } }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R012");
    expect(screen.getByText(/Soy el asistente virtual de McKinley/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Escriba al asistente"), "el horno no calienta{Enter}");
    const reply = await screen.findByText("¿En qué parte del apartamento es?");
    expect(reply.closest("[lang]")).toHaveAttribute("lang", "es");
    expect(screen.getByText("Borrador: faltan algunos datos")).toBeInTheDocument();
    expect(screen.getByText("el horno no calienta").closest("[lang]")).toHaveAttribute("lang", "es");
  });

  it("preview mode never shows a disabled primary button", async () => {
    const snapshot = {
      kind: "static_demo_snapshot", generated_at: "2026-11-06", notice: "n", workbook_loaded: true,
      personas, cases: [], responses: {}, contexts: {}, gate_eval: { note: "", summary: {}, rows: [] },
      journeys: [{ id: "j", persona_id: "R001", title: "My faucet drips", steps: [
        { kind: "chat", message: "My kitchen faucet drips", response: resp({ reply: "Here's your request.", action: readyCard }) },
        { kind: "chat", message: "Actually it's the bathroom", response: resp({ reply: "Updated.", action: readyCard }) },
      ] }],
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/demo/snapshot.json") return new Response(JSON.stringify(snapshot));
      throw new TypeError("fetch failed");
    }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.click(screen.getByRole("button", { name: "My faucet drips" }));
    await screen.findByText("Here's your request.");
    expect(screen.queryByRole("button", { name: "Send repair request" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actually it's the bathroom" })).toBeEnabled();
  });
});
