import type { ActionResult, ActionStage, ChatResponse, Journey, Persona, ProposedAction } from "./types";

/** Security-test fixture personas never appear in the customer view (staff console only). */
const STAFF_ONLY = new Set(["F-INJECT"]);

export interface Identity {
  id: string; // "" = not signed in
  label: string;
  group: "Not signed in" | "Looking for a home" | "Residents";
  kind: "guest" | "prospect" | "resident" | "unmatched_resident";
  firstName: string | null;
  community: string | null;
}

export const GUEST: Identity = {
  id: "",
  label: "Not signed in",
  group: "Not signed in",
  kind: "guest",
  firstName: null,
  community: null,
};

export function toIdentities(personas: Persona[]): Identity[] {
  const out: Identity[] = [GUEST];
  for (const p of personas) {
    if (STAFF_ONLY.has(p.id)) continue;
    if (p.kind === "prospect") {
      const label = p.label.replace(/^Fictional prospect · /, "");
      out.push({ id: p.id, label: `Prospect, ${label}`, group: "Looking for a home", kind: "prospect", firstName: null, community: null });
    } else if (p.kind === "unmatched_resident") {
      out.push({
        id: p.id,
        label: "Says they're a resident (no account match)",
        group: "Not signed in",
        kind: "unmatched_resident",
        firstName: null,
        community: null,
      });
    } else {
      const first = p.label.match(/· ([^(]+?) \(/)?.[1]?.trim() ?? p.id;
      const community = p.description.match(/resident at (.+?)\.?$/)?.[1] ?? null;
      out.push({
        id: p.id,
        label: community ? `${first}, ${community}` : first,
        group: "Residents",
        kind: "resident",
        firstName: first,
        community,
      });
    }
  }
  return out;
}

/** I-01 draft: AI disclosure on the first message. Wording still needs McKinley approval. */
export function greeting(identity: Identity): string {
  const intro = "I'm McKinley's virtual assistant. I'm an AI, and a person on our team can step in anytime.";
  switch (identity.kind) {
    case "resident":
      return `Hi ${identity.firstName ?? "there"}. ${intro} I can help you report a repair, check your open requests, ask about your renewal, or reach the office.`;
    case "prospect":
      return `Welcome! ${intro} I can answer general questions and send a tour request to our leasing team.`;
    case "unmatched_resident":
      return `Hi. ${intro} I couldn't match you to a resident account, so I can share general information and pass a note to the office.`;
    default:
      return `Hi! ${intro} Are you looking for a home, or do you already live at a McKinley community?`;
  }
}

/** Starter actions per identity. Only actions the backend actually supports are offered. */
export function starters(identity: Identity): string[] {
  switch (identity.kind) {
    case "resident":
      return ["Report a repair", "Check my requests", "Ask about my renewal", "Talk to the office"];
    case "unmatched_resident":
      return ["Report a repair", "Talk to the office"];
    case "prospect":
      return ["Request a tour", "Do you accept housing vouchers?", "Talk to the leasing team"];
    default:
      return ["Request a tour", "Do you accept housing vouchers?", "I live at McKinley"];
  }
}

export function identityStatus(identity: Identity): string {
  switch (identity.kind) {
    case "resident":
      return `Signed in as ${identity.firstName} (demo account)`;
    case "prospect":
      return "Browsing with a demo prospect profile";
    case "unmatched_resident":
      return "Not matched to a resident account";
    default:
      return "Not signed in";
  }
}

export type Tone = "draft" | "ready" | "sent" | "urgent" | "blocked";

export function actionTone(a: ProposedAction): Tone {
  if (a.stage === "submitted") return a.record?.status === "urgent_queued" ? "urgent" : "sent";
  if (a.stage === "ready") return "ready";
  if (a.stage === "blocked") return "blocked";
  return "draft";
}

export const STAGE_TEXT: Record<ActionStage, string> = {
  collecting: "Draft, a few details to go",
  ready: "Ready to send: please check it",
  submitted: "Sent",
  blocked: "Not available here",
};

export const SOURCE_TEXT: Record<string, string> = {
  you_said: "You told us",
  on_file: "On your account",
  assistant: "Added by the assistant",
  missing: "Still needed",
};

// ---- conversation hand-off to the staff console (same browser, sessionStorage only) ----

export const CONVERSATION_KEY = "mckinley.lastConversation";

export type StoredTurn = { message: string; response: ChatResponse } | { confirm: string; result: ActionResult };

export interface StoredConversation {
  persona_id: string;
  session_id: string;
  saved_at: string;
  turns: StoredTurn[];
}

export function saveConversation(c: StoredConversation): void {
  try {
    sessionStorage.setItem(CONVERSATION_KEY, JSON.stringify(c));
  } catch {
    /* storage unavailable (private mode): the staff console just shows recorded journeys */
  }
}

export function loadConversation(): StoredConversation | null {
  try {
    const raw = sessionStorage.getItem(CONVERSATION_KEY);
    return raw ? (JSON.parse(raw) as StoredConversation) : null;
  } catch {
    return null;
  }
}

/** Personas that appear in recorded journeys (static preview identity list). */
export function journeyPersonaIds(journeys: Journey[]): Set<string> {
  return new Set(journeys.map((j) => j.persona_id));
}
