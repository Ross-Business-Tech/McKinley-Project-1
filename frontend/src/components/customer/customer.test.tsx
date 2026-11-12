import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, Persona, ProposedAction, SafetyContact } from "@/lib/types";

import { UI, safetyContactsOf, safetyStateOf } from "@/lib/customer";

import { CustomerApp, sortStatusItems } from "./CustomerApp";

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
    if (url.endsWith("/api/actions/confirm")) {
      const record = { id: "DEMO-WO-1001", kind: "maintenance_request", status: "submitted_for_review", status_label: "Saved in demo", persona_id: "R001", session_hash: "abc", created_at: "2026-11-07T00:00:00Z", summary: "s", fields: [], system: "prototype" };
      const action = { ...readyCard, stage: "submitted", confirm_label: null, record, note: "Not sent to maintenance. No visit is scheduled." };
      return new Response(JSON.stringify({ ok: true, message: "Your repair request is saved in this demo. It hasn't been sent to maintenance.", action, record, error_code: null }));
    }
    throw new TypeError("fetch failed");
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  sessionStorage.clear();
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

  it("gives the 'Details' disclosure a 44px target (inner span; WebKit ignores flex on <summary>)", async () => {
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    await user.click(await screen.findByRole("button", { name: "Send repair request" }));
    const label = await screen.findByText("Details");
    expect(label.tagName).toBe("SPAN");
    expect(label).toHaveClass("min-h-11");
    expect(label.closest("summary")).toHaveClass("min-h-11");
  });

  it("retires the read-back card's buttons once the request is sent", async () => {
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    await user.click(await screen.findByRole("button", { name: "Send repair request" }));
    await screen.findByText(/Saved in demo/);
    expect(screen.queryByRole("button", { name: "Send repair request" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Don't send" })).not.toBeInTheDocument();
    // the press is shown as the person's own turn, so the saved message reads as the reply to it
    expect(screen.getByTestId("choice")).toHaveTextContent("Send repair request");
    // a resident who sent a repair is offered its status and another repair
    expect(screen.getByRole("button", { name: "Check its status" })).toBeInTheDocument();
  });

  it("announces the outcome of Send once, with its reference", async () => {
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    await user.click(await screen.findByRole("button", { name: "Send repair request" }));
    await screen.findByText(/Saved in demo/);
    const region = document.querySelector('[aria-live="polite"]');
    await waitFor(() => expect(region).toHaveTextContent(/Assistant said:.*DEMO-WO-/));
  });

  it("puts focus in the message box after Start over", async () => {
    live(() => resp({ reply: "Got it." }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "hello{Enter}");
    await screen.findByText("Got it.");
    await user.click(screen.getByRole("button", { name: "Start over" }));
    await waitFor(() => expect(screen.getByLabelText("Message the assistant")).toHaveFocus());
    expect(screen.queryByText("Got it.")).not.toBeInTheDocument();
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
    // gas: the button says to get outside first (the notice says not to use phones inside)
    expect(within(alert).getByRole("link", { name: /Get outside, then call 911/ })).toHaveAttribute("href", "tel:911");
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
    expect(screen.getByText(/Soy el asistente automático de McKinley, no una persona/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Escriba al asistente"), "el horno no calienta{Enter}");
    const reply = await screen.findByText("¿En qué parte del apartamento es?");
    expect(reply.closest("[lang]")).toHaveAttribute("lang", "es");
    // still collecting: a one-line progress note, not a full card
    expect(screen.getByTestId("progress-hint")).toHaveTextContent("Falta agregar: dónde");
    expect(screen.queryByRole("group", { name: "Repair request" })).not.toBeInTheDocument();
    expect(screen.getByText("el horno no calienta").closest("[lang]")).toHaveAttribute("lang", "es");
  });

  it("shows a calm care note with 988 links, not the emergency alert", async () => {
    live(() => resp({ reply: "I can help with the sink.", care_kind: "distress", care_note: "You can call or text 988 any time." }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "what's the point{Enter}");
    const note = await screen.findByTestId("care-note");
    expect(within(note).getByRole("link", { name: /Call 988/ })).toHaveAttribute("href", "tel:988");
    expect(within(note).getByRole("link", { name: /Text 988/ })).toHaveAttribute("href", "sms:988");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows hypothetical safety info calmly, with no call buttons and no alert", async () => {
    live(() => resp({ reply: "Is anything like that happening right now?", care_kind: "info", care_note: "If that happens: Leave now." }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "what if I smell gas?{Enter}");
    const note = await screen.findByTestId("care-note");
    expect(within(note).getByText("If that happens")).toBeInTheDocument();
    expect(within(note).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says plainly whether replies come from fixed rules or an AI model", async () => {
    live(() => resp({ reply: "Got it.", is_mock: true }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "my sink leaks{Enter}");
    await screen.findByText("Got it.");
    await user.click(screen.getByRole("button", { name: "About this demo" }));
    expect(within(screen.getByTestId("about-demo")).getByText(/come from fixed rules, not an AI model/)).toBeInTheDocument();
  });

  it("names OpenRouter and the served model, and says when a live provider's reply was approved wording", async () => {
    let n = 0;
    live(() => (++n === 1
      ? resp({ reply: "Sure.", is_mock: false, provider: "openrouter", model: "vendor/model-x:free", reply_source: "model" })
      : resp({ reply: "Okay.", is_mock: false, provider: "openrouter", model: "vendor/model-x:free", reply_source: "template" })));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "hi{Enter}");
    await screen.findByText("Sure.");
    await user.click(screen.getByRole("button", { name: "About this demo" }));
    expect(within(screen.getByTestId("about-demo")).getByText(/AI model \(OpenRouter: vendor\/model-x:free\)/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Message the assistant"), "thanks{Enter}");
    await screen.findByText("Okay.");
    expect(within(screen.getByTestId("about-demo")).getByText(/approved wording, not the AI model \(OpenRouter/)).toBeInTheDocument();
  });

  it("labels live model replies as AI-written", async () => {
    live(() => resp({ reply: "Got it.", is_mock: false, provider: "gemini", reply_source: "model" }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "my sink leaks{Enter}");
    await screen.findByText("Got it.");
    await user.click(screen.getByRole("button", { name: "About this demo" }));
    expect(within(screen.getByTestId("about-demo")).getByText(/written by an AI model \(Gemini/)).toBeInTheDocument();
  });

  // Sprint 8 (product owner decision): the always-visible "Emergency: call 911" tap-to-call link was removed. This test
  // used to assert that link; it now asserts there is no tap-to-call control on open, only a plain-text 911 line.
  it("has no persistent tap-to-call 911 control, a plain-text 911 line, and an honest 'not a person' greeting", async () => {
    live(() => resp({ reply: "Got it." }));
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    expect(document.querySelector('a[href^="tel:"], a[href^="sms:"]')).toBeNull();
    const footer = screen.getByTestId("emergency-footer");
    expect(footer).toHaveTextContent("In an emergency, call 911.");
    expect(footer.closest("a, button")).toBeNull();
    expect(screen.getByText(/automated assistant, not a person/)).toBeInTheDocument();
    expect(screen.queryByText(/I'm an AI/)).not.toBeInTheDocument();
  });

  it("opens and closes 'About this demo' from the keyboard and returns focus", async () => {
    live(() => resp({ reply: "Got it." }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    const toggle = screen.getByRole("button", { name: "About this demo" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByTestId("about-demo");
    expect(within(panel).getByRole("link", { name: "Staff and demo console" })).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: /Close/ }));
    await user.click(toggle);
    await user.keyboard("{Tab}{Escape}");
    expect(screen.queryByTestId("about-demo")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  it("always offers a way to talk to a person", async () => {
    live(() => resp({ reply: "A team member should handle this." }));
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    expect(screen.getByRole("button", { name: /Talk to a person/ })).toBeInTheDocument();
  });

  it("lists urgent and overdue requests first and hides the rest behind Show all", async () => {
    const item = (n: number, status: string, opened: string) => ({ reference: `DEMO-WO-${n}`, title: `Request ${n}`, status, opened, source: "prototype_store" as const, note: null });
    live(() => resp({ reply: "Here are your requests.", status_items: [
      item(1, "Submitted, waiting for staff review", "2026-11-01"), item(2, "Submitted, waiting for staff review", "2026-11-02"),
      item(3, "Submitted, waiting for staff review", "2026-11-03"), item(4, "Submitted, waiting for staff review", "2026-11-04"),
      item(5, "Urgent; in the office queue", "2026-10-01"), item(6, "Follow-up owed", "2026-09-01"),
    ] }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await screen.findByLabelText("Demo sign-in");
    await user.type(screen.getByLabelText("Message the assistant"), "check my requests{Enter}");
    const list = await screen.findByRole("list", { name: "Your open requests" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(5); // 2 pinned + 3 most recent
    expect(rows[0]).toHaveTextContent("DEMO-WO-5");
    expect(rows[1]).toHaveTextContent("DEMO-WO-6");
    expect(rows[2]).toHaveTextContent("DEMO-WO-4");
    await user.click(screen.getByRole("button", { name: "Show all (6)" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(6);
  });

  it("asks before a sign-in change clears the conversation", async () => {
    live(() => resp({ reply: "ok" }));
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<CustomerApp />);
    const who = await screen.findByLabelText("Demo sign-in");
    expect(screen.getByText("Changing this starts a new conversation.")).toBeVisible();
    await user.type(screen.getByLabelText("Message the assistant"), "hello there{Enter}");
    await screen.findByText("hello there");
    await user.selectOptions(who, "R001");
    expect(ask).toHaveBeenCalled();
    expect(who).toHaveValue(""); // stayed on the guest identity
    expect(screen.getByText("hello there")).toBeInTheDocument();
  });

  it("restores the conversation after a reload in the same tab", async () => {
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const user = userEvent.setup();
    const first = render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    await screen.findByRole("group", { name: "Repair request" });
    first.unmount();
    render(<CustomerApp />);
    expect(await screen.findByText("My kitchen faucet drips")).toBeInTheDocument();
    expect(screen.getByLabelText("Demo sign-in")).toHaveValue("R001");
    expect(screen.getByRole("group", { name: "Repair request" })).toBeInTheDocument();
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


describe("Sprint 5.1 UI fixes", () => {
  it("marks a failed Send as not sent, announces it, and retries the same card", async () => {
    let fail = true;
    live(() => resp({ reply: "Here's your request.", action: readyCard }));
    const base = globalThis.fetch as unknown as (u: string, i?: RequestInit) => Promise<Response>;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/actions/confirm") && fail) { fail = false; return new Response("{}", { status: 500 }); }
      return base(url, init);
    }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    await user.click(await screen.findByRole("button", { name: "Send repair request" }));
    expect((await screen.findAllByText(/That didn't save/)).length).toBeGreaterThan(0);
    expect(screen.getByTestId("choice").parentElement).toHaveTextContent("Not sent");
    expect(document.querySelector('[aria-live="polite"]')).toHaveTextContent(/That didn't save/);
    await user.click(screen.getByRole("button", { name: /Send again/ }));
    expect(await screen.findByText(/Saved in demo/)).toBeInTheDocument();
    // Sprint 7 (judge H-10): after the retry goes through, no stale "Send again" button stays on screen
    expect(screen.queryByRole("button", { name: /Send again/ })).not.toBeInTheDocument();
  });

  it("shows 'Ready to send', hides demo-system rows, and gives a sent card one honest line", async () => {
    const card = { ...readyCard, fields: [...readyCard.fields,
      { key: "who", label: "Account", value: "Signed-in resident (demo account)", source: "on_file" as const },
      { key: "contact_route", label: "Contact route", value: "Not collected in this prototype", source: "assistant" as const }] };
    live(() => resp({ reply: "Here's your request.", action: card }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "My kitchen faucet drips{Enter}");
    const group = await screen.findByRole("group", { name: "Repair request" });
    expect(within(group).getByText("Ready to send")).toBeInTheDocument();
    expect(within(group).queryByText(/demo account/)).not.toBeInTheDocument();
    expect(within(group).queryByText(/Not collected in this prototype/)).not.toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Send repair request" }));
    // Sprint 9: one backend-written demo line on the saved card, the status pill says "Saved in demo", reference below
    expect(await screen.findByText("Not sent to maintenance. No visit is scheduled.")).toBeInTheDocument();
    const saved = screen.getAllByTestId("action-card").at(-1)!;
    expect(within(saved).getByText("Saved in demo")).toBeInTheDocument();
    expect(within(saved).getByTestId("card-reference")).toHaveTextContent("DEMO-WO-1001");
    expect(within(saved).queryByText(/No McKinley staff will see it/)).not.toBeInTheDocument();
  });

  it("never pins more than three urgent rows and always shows the newest request", async () => {
    const status_items = [
      ...Array.from({ length: 6 }, (_, i) => ({ reference: `DEMO-TASK-10${i}`, title: `Alert ${i}`, status: "Urgent; in the office queue", opened: "2026-11-10", source: "prototype_store" as const, note: null })),
      { reference: "DEMO-WO-1080", title: "Bathroom sink", status: "Submitted, waiting for staff review", opened: "2026-11-10", source: "prototype_store" as const, note: null },
    ];
    live(() => resp({ reply: "Here are your open requests.", status_items }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
    await user.type(screen.getByLabelText("Message the assistant"), "check my requests{Enter}");
    const list = await screen.findByRole("list", { name: "Your open requests" });
    expect(within(list).getByText("Bathroom sink")).toBeInTheDocument();
    expect(within(list).getAllByText(/Urgent/).length).toBe(3);
    expect(sortStatusItems(status_items)[0].status).toMatch(/^Urgent/);
  });
});

describe("Sprint 6 authorization: demo sign-in follows the backend", () => {
  it("hides the demo sign-in and sends no persona when the backend has no demo personas (hosted)", async () => {
    const bodies: { persona_id: string | null; session_id: string }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/personas")) return new Response(JSON.stringify([]));
      if (url.endsWith("/api/health")) {
        return new Response(JSON.stringify({ status: "ok", provider: "mock", model: "m", provider_ready: true, provider_status: "ok",
          prompt_version: "v", data_loaded: true, data_error: null, resident_count: 0, interaction_count: 0, app_env: "hosted",
          is_mock: true, demo_personas_enabled: false }));
      }
      if (url.endsWith("/api/chat")) {
        bodies.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify(resp({ reply: "General help only.", audience: "unknown", session_id: "server-new" })));
      }
      throw new TypeError("fetch failed");
    }));
    const user = userEvent.setup();
    render(<CustomerApp />);
    expect(await screen.findByTestId("guest-only")).toBeInTheDocument();
    expect(screen.queryByLabelText("Demo sign-in")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Message the assistant"), "show my requests{Enter}");
    await screen.findByText("General help only.");
    await user.type(screen.getByLabelText("Message the assistant"), "and my renewal?{Enter}");
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies.every((b) => b.persona_id === null)).toBe(true);
    expect(bodies[1].session_id).toBe("server-new"); // follows a new conversation the backend started
  });

  it("keeps the demo sign-in on a local backend", async () => {
    live(() => resp({}));
    render(<CustomerApp />);
    expect(await screen.findByLabelText("Demo sign-in")).toBeInTheDocument();
    expect(screen.queryByTestId("guest-only")).not.toBeInTheDocument();
  });
});

// ---- Sprint 8: safety_state (normal / concern / active) ----

const C911: SafetyContact = { label: "Call 911", href: "tel:911", kind: "call" };
const C988: SafetyContact = { label: "Call or text 988", href: "tel:988", kind: "call" };
const T988: SafetyContact = { label: "Text 988", href: "sms:988", kind: "text" };
const POISON: SafetyContact = { label: "Call Poison Help 1-800-222-1222", href: "tel:18002221222", kind: "call" };

async function chatOnce(chat: (body: { message: string }) => ChatResponse, ...messages: string[]) {
  live(chat);
  const user = userEvent.setup();
  render(<CustomerApp />);
  await user.selectOptions(await screen.findByLabelText("Demo sign-in"), "R001");
  for (const m of messages) {
    const before = screen.queryAllByRole("article").length;
    await user.type(screen.getByLabelText("Message the assistant"), `${m}{Enter}`);
    await waitFor(() => expect(screen.getAllByRole("article").length).toBeGreaterThan(before));
  }
  return user;
}
const callLinks = () => [...document.querySelectorAll('a[href^="tel:"], a[href^="sms:"]')];

describe("CustomerApp safety states (Sprint 8)", () => {
  it("normal: no tel:/sms: link anywhere — greeting, chips, cards, status list, composer", async () => {
    await chatOnce(() => resp({
      reply: "Here's your request.", safety_state: "normal", safety_contacts: [], action: readyCard,
      suggested_replies: ["Check my requests"],
      status_items: [{ reference: "DEMO-WO-1", title: "Leaking sink", status: "Open", opened: "2026-11-01" } as never],
    }), "My kitchen faucet drips");
    expect(screen.getByRole("group", { name: "Repair request" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Your open requests" })).toBeInTheDocument();
    expect(callLinks()).toHaveLength(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("care-note")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to a person" })).toBeInTheDocument();
  });

  it("concern: a calm inline note, no call button when no contacts are given, announced politely once", async () => {
    await chatOnce(() => resp({
      reply: "I can help with the heater.", safety_state: "concern", safety_contacts: [],
      care_kind: "danger", care_note: "If anyone feels dizzy or sick, get fresh air.",
    }), "the heater smells odd sometimes");
    const note = screen.getByTestId("care-note");
    expect(note).toHaveTextContent("If anyone feels dizzy or sick, get fresh air.");
    expect(within(note).queryByRole("link")).not.toBeInTheDocument();
    expect(callLinks()).toHaveLength(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const polite = document.querySelectorAll('[aria-live="polite"]');
    expect(polite).toHaveLength(1);
    await waitFor(() => expect(polite[0]).toHaveTextContent(/Assistant said: If anyone feels dizzy.*I can help with the heater/));
    expect(document.querySelectorAll('[aria-live="assertive"]')).toHaveLength(0);
  });

  it("concern: shows the backend's contacts when it sends them (e.g. 988 for distress)", async () => {
    await chatOnce(() => resp({
      reply: "I can help with the sink.", safety_state: "concern", care_kind: "distress",
      care_note: "If you're having a hard time, you can call or text 988.", safety_contacts: [C988, T988],
    }), "everything is too much");
    const note = screen.getByTestId("care-note");
    expect(within(note).getByRole("link", { name: /Call or text 988/ })).toHaveAttribute("href", "tel:988");
    expect(within(note).getByRole("link", { name: /Text 988/ })).toHaveAttribute("href", "sms:988");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    ["medical", [C911], [["Call 911", "tel:911"]]],
    ["gas", [{ ...C911, label: "Get outside, then call 911" }, { label: "Or call your gas company from outside", href: null, kind: "info" } as SafetyContact],
      [["Get outside, then call 911", "tel:911"]]],
    ["poison", [POISON, { ...C911, label: "Call 911 if they are hard to wake or not breathing" }],
      [["Call Poison Help 1-800-222-1222", "tel:18002221222"], ["Call 911 if they are hard to wake or not breathing", "tel:911"]]],
    ["self_harm", [C988, T988, { ...C911, label: "Call 911 if you are in immediate danger" }],
      [["Call or text 988", "tel:988"], ["Text 988", "sms:988"], ["Call 911 if you are in immediate danger", "tel:911"]]],
  ] as const)("active (%s): an in-conversation alert with labelled contact links, alert first", async (kind, contacts, want) => {
    await chatOnce(() => resp({
      reply: "Please follow the steps above.", safety_state: "active", safety_contacts: [...contacts], emergency_kind: kind,
      safety_heading: "Your safety comes first", safety_notice: "Follow these steps now.", action: readyCard,
    }), "help");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Your safety comes first");
    expect(alert).toHaveTextContent("Follow these steps now.");
    const links = within(alert).getAllByRole("link");
    expect(links.map((a) => [a.textContent?.trim(), a.getAttribute("href")])).toEqual(want);
    // nothing outside the alert is a call link, and the alert comes before the card and the reply in the turn
    expect(callLinks().every((a) => alert.contains(a))).toBe(true);
    const card = screen.getByRole("group", { name: "Repair request" });
    expect(alert.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(alert.compareDocumentPosition(screen.getByText("Please follow the steps above.")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // info-only contacts are plain text, not links
    if (kind === "gas") expect(within(alert).getByText("Or call your gas company from outside").closest("a")).toBeNull();
    // no flashing / animation on the alert
    expect(alert.className).not.toMatch(/animate/);
    expect(alert.querySelector('[class*="animate"]')).toBeNull();
  });

  it("active: the contact links come right after the heading, before the guidance text (judge fix round)", async () => {
    await chatOnce(() => resp({
      reply: "Please follow the steps above.", safety_state: "active", safety_contacts: [POISON, C911], emergency_kind: "poison",
      safety_heading: "Get help now", safety_notice: "Don't make them vomit. Keep the container with you.",
    }), "my son swallowed a pod");
    const alert = screen.getByRole("alert");
    const first = within(alert).getAllByRole("link")[0];
    const notice = within(alert).getByText(/Don't make them vomit/);
    expect(first.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(alert).getByText("Get help now").compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // the Poison Help number never breaks mid-number
    const num = within(first).getByTestId("phone-number");
    expect(num).toHaveTextContent("1-800-222-1222");
    expect(num).toHaveClass("whitespace-nowrap");
    expect(first).toHaveTextContent("Call Poison Help 1-800-222-1222");
    // focus stays in the message box, never on a call link (a stray Enter must not dial)
    await waitFor(() => expect(screen.getByLabelText("Message the assistant")).toHaveFocus());
  });

  it("active: never dials on render, links only open when tapped", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    await chatOnce(() => resp({ reply: "Leave now.", safety_state: "active", safety_contacts: [C911], safety_notice: "Leave now." }), "fire");
    expect(open).not.toHaveBeenCalled();
    expect(window.location.href).not.toMatch(/^tel:/);
  });

  it("active: announced once by the alert (assertive), not again by the polite region", async () => {
    await chatOnce(() => resp({ reply: "Leave now.", safety_state: "active", safety_contacts: [C911], safety_notice: "Get out now." }), "fire");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(document.querySelector('[aria-live="polite"]')).not.toHaveTextContent(/Get out now/);
  });

  it("recovers to normal: a resolved incident's next turn has no alert or links; the earlier alert stays in history", async () => {
    let n = 0;
    await chatOnce(() => (++n === 1
      ? resp({ reply: "Get out and call 911.", safety_state: "active", safety_contacts: [C911], safety_notice: "Get out now.", emergency_kind: "fire_smoke" })
      : resp({ reply: "Glad everyone is safe. Want to report the damage?", safety_state: "normal", safety_contacts: [] })),
    "there's smoke", "it was just toast, all fine");
    const articles = screen.getAllByRole("article");
    const last = articles[articles.length - 1];
    expect(within(last).queryByRole("link")).not.toBeInTheDocument();
    expect(within(last).queryByTestId("safety-alert")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("safety-alert")).toHaveLength(1); // the first turn keeps its history
    expect(screen.getAllByTestId("safety-alert")[0].closest('[role="article"]')).not.toBe(last);
  });

  it("drops contact targets that are not on the allow-list (shown as text, never a link)", async () => {
    await chatOnce(() => resp({
      reply: "ok", safety_state: "active", safety_notice: "Get out now.",
      safety_contacts: [{ label: "Call this number", href: "javascript:alert(1)" as never, kind: "call" }, C911],
    }), "fire");
    const alert = screen.getByRole("alert");
    expect(within(alert).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["tel:911"]);
    expect(within(alert).getByText("Call this number").closest("a")).toBeNull();
  });

  it("keeps the composer and Talk to a person usable during an active alert", async () => {
    await chatOnce(() => resp({ reply: "Leave now.", safety_state: "active", safety_contacts: [C911], safety_notice: "Get out now." }), "fire");
    expect(screen.getByLabelText("Message the assistant")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Talk to a person" })).toBeEnabled();
  });
});

describe("safetyStateOf / safetyContactsOf (backward compatibility)", () => {
  const t = UI.en;
  it("derives the state when an older backend or the replay snapshot has no safety_state", () => {
    expect(safetyStateOf(resp({}))).toBe("normal");
    expect(safetyStateOf(resp({ safety_notice: "Leave now." }))).toBe("active");
    expect(safetyStateOf(resp({ emergency_kind: "gas" }))).toBe("active");
    expect(safetyStateOf(resp({ care_note: "You can call or text 988.", care_kind: "distress" }))).toBe("concern");
    expect(safetyStateOf(null)).toBe("normal");
  });
  it("trusts an explicit safety_state, but never hides a safety_notice behind 'normal'", () => {
    expect(safetyStateOf(resp({ safety_state: "normal", care_note: "x" }))).toBe("normal");
    expect(safetyStateOf(resp({ safety_state: "concern", safety_notice: "x" }))).toBe("concern");
    expect(safetyStateOf(resp({ safety_state: "normal", safety_notice: "Leave now." }))).toBe("active");
  });
  it("derives the pre-Sprint-8 links for older responses", () => {
    const hrefs = (r: ChatResponse) => safetyContactsOf(r, t).map((c) => c.href);
    expect(hrefs(resp({ safety_notice: "Leave.", emergency_kind: "gas" }))).toEqual(["tel:911"]);
    expect(safetyContactsOf(resp({ safety_notice: "Leave.", emergency_kind: "gas" }), t)[0].label).toBe("Get outside, then call 911");
    expect(hrefs(resp({ safety_notice: "Call 988.", emergency_kind: "self_harm" }))).toEqual(["tel:988", "sms:988"]);
    expect(hrefs(resp({ safety_notice: "Call Poison Help.", emergency_kind: "poison" }))).toEqual(["tel:18002221222", "tel:911"]);
    expect(hrefs(resp({ care_note: "988 any time", care_kind: "distress" }))).toEqual(["tel:988", "sms:988"]);
    expect(hrefs(resp({ care_note: "If that happens: leave", care_kind: "info" }))).toEqual([]);
    expect(hrefs(resp({}))).toEqual([]);
    // a normal turn never has contacts, even if the backend sent some
    expect(hrefs(resp({ safety_state: "normal", safety_contacts: [C911] }))).toEqual([]);
  });
  it("uses the backend's empty contact list as-is for a concern (no derived buttons)", () => {
    expect(safetyContactsOf(resp({ safety_state: "concern", care_kind: "distress", care_note: "x", safety_contacts: [] }), t)).toEqual([]);
  });
});
