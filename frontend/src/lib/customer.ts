import type { ActionResult, ChatResponse, Journey, Persona, ProposedAction } from "./types";

/** Security-test fixture personas never appear in the customer view (staff console only). */
const STAFF_ONLY = new Set(["F-INJECT"]);

export type Lang = "en" | "es";

export interface Identity {
  id: string; // "" = not signed in
  lang: Lang;
  label: string;
  group: "Not signed in" | "Looking for a home" | "Residents";
  kind: "guest" | "prospect" | "resident" | "unmatched_resident";
  firstName: string | null;
  community: string | null;
}

export const GUEST: Identity = {
  id: "",
  lang: "en",
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
      out.push({ id: p.id, lang: "en", label: `Prospect, ${label}`, group: "Looking for a home", kind: "prospect", firstName: null, community: null });
    } else if (p.kind === "unmatched_resident") {
      out.push({
        id: p.id,
        lang: "en",
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
        lang: p.language === "es" ? "es" : "en",
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
  if (identity.lang === "es") {
    return `Hola, ${identity.firstName ?? ""}. Soy el asistente virtual de McKinley. Soy una IA; si prefiere hablar con una persona, dígamelo y preparo una nota para nuestro equipo. Puedo ayudarle a reportar una reparación, revisar sus solicitudes, hablar de su renovación o comunicarle con la oficina.`;
  }
  const intro = "I'm McKinley's virtual assistant. I'm an AI. If you'd rather talk to a person, just say so and I'll prepare a note for our team.";
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
  if (identity.lang === "es") return ["Reportar una reparación", "Ver mis solicitudes", "Hablar con la oficina"];
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

/** Customer-facing UI strings. Spanish = draft translation (needs review by a fluent McKinley staff member). */
export const UI = {
  en: {
    stage: { collecting: "Draft: a few details to go", ready: "Check, then send", submitted: "Sent", blocked: "Not available here" },
    source: { you_said: "You told us", on_file: "On your account", assistant: "Added by the assistant", missing: "Still needed" },
    stillNeeded: "Still needed:",
    dontSend: "Don't send",
    sending: "Sending…",
    whatWasSent: "What was sent",
    notSent: "Not sent",
    replaced: "Earlier version",
    reference: "Reference",
    assistantSaid: "Assistant said:",
    youSaid: "You said:",
    placeholder: "Type your message",
    previewPlaceholder: "Typing is off in this preview",
    replying: "The assistant is replying…",
    failed: "Not sent",
    sendAgain: "Send again",
    call911: "Call 911",
    call988: "Call 988",
    text988: "Text 988",
    noEmergencyLine: "Your community's emergency maintenance number isn't connected in this prototype.",
    openRequests: "Your open requests",
    followUpOwed: "Follow-up owed",
    footer: "Prototype with made-up data. In an emergency, call 911.",
    staffLink: "Staff and demo console",
    message: "Message the assistant",
    send: "Send message",
    conversation: "Conversation",
    suggestions: "Suggested replies",
  },
  es: {
    stage: { collecting: "Borrador: faltan algunos datos", ready: "Revise y envíe", submitted: "Enviada", blocked: "No disponible aquí" },
    source: { you_said: "Lo que dijo", on_file: "En su cuenta", assistant: "Agregado por el asistente", missing: "Falta" },
    stillNeeded: "Falta:",
    dontSend: "No enviar",
    sending: "Enviando…",
    whatWasSent: "Lo que se envió",
    notSent: "No enviada",
    replaced: "Versión anterior",
    reference: "Referencia",
    assistantSaid: "El asistente dijo:",
    youSaid: "Usted dijo:",
    placeholder: "Escriba su mensaje",
    previewPlaceholder: "En esta vista previa no se puede escribir",
    replying: "El asistente está respondiendo…",
    failed: "No enviado",
    sendAgain: "Enviar de nuevo",
    call911: "Llamar al 911",
    call988: "Llamar al 988",
    text988: "Mensaje al 988",
    noEmergencyLine: "El número de emergencias de mantenimiento de su comunidad no está conectado en este prototipo.",
    openRequests: "Sus solicitudes abiertas",
    followUpOwed: "Seguimiento pendiente",
    footer: "Prototipo con datos ficticios. En una emergencia, llame al 911.",
    staffLink: "Consola del personal",
    message: "Escriba al asistente",
    send: "Enviar mensaje",
    conversation: "Conversación",
    suggestions: "Respuestas sugeridas",
  },
} as const;

export type UIStrings = (typeof UI)["en"] | (typeof UI)["es"];

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
