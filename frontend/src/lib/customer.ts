import type { ActionKind, ActionResult, ChatResponse, Journey, Persona, ProposedAction } from "./types";

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
    return `Hola, ${identity.firstName ?? ""}. Soy el asistente automático de McKinley, no una persona. Si prefiere hablar con alguien del equipo, dígamelo y preparo una nota. Puedo ayudarle a reportar una reparación, revisar sus solicitudes, hablar de su renovación o comunicarle con la oficina.`;
  }
  // I-01 AI disclosure (team draft, McKinley approves). "Automated, not a person" is true for the fixed-rule demo
  // responder and for a live AI model, and it is short enough for a 320px screen.
  const intro = "I'm McKinley's automated assistant, not a person. Want a person instead? Just say so and I'll prepare a note for our team.";
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
    lang: "en",
    stage: { collecting: "Draft: a few details to go", ready: "Check, then send", submitted: "Sent", blocked: "Not available here" },
    source: { you_said: "You told us", on_file: "On your account", assistant: "Added by the assistant", missing: "Still needed" },
    stillNeeded: "Still needed:",
    dontSend: "Don't send",
    sending: "Sending…",
    whatWasSent: "What was sent",
    notSent: "Not sent",
    reference: "Reference",
    assistantSaid: "Assistant said:",
    youSaid: "You said:",
    youChose: "You pressed:",
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
    replyMock: "Replies here come from fixed rules, not an AI model.",
    replyAi: "Replies are written by an AI model and checked by fixed safety rules; it can make mistakes.",
    staffLink: "Staff and demo console",
    message: "Message the assistant",
    send: "Send message",
    conversation: "Conversation",
    suggestions: "Suggested replies",
    unreachable: "I can't reach the assistant right now, so your message wasn't sent.",
    serverError: "Something went wrong on our side, so your message wasn't handled.",
    tryAgain: "Please try again. In an emergency, call 911.",
    notSaved: "That didn't save, so nothing was sent. Please try again, or contact the office directly.",
    declinedMsg: "Okay, I haven't sent anything. Is there something else I can help with?",
    whatItSaid: "What it said",
    fromProfile: "From your profile",
    cancelFailed: "I couldn't update that just now. Nothing has been sent.",
    opened: "opened",
    showAll: (n: number) => `Show all (${n})`,
    showFewer: "Show fewer",
    assistantName: "McKinley assistant",
    assistantMessage: "Assistant message",
    signInHint: "Changing this starts a new conversation.",
    signInConfirm: "Switch sign-in? This conversation will be cleared from this screen.",
    howCanIHelp: "What do you need help with?",
    afterSend: ["Check its status", "Report a repair"],
    afterDecline: ["Send it after all", "Report a repair"],
    talkToPerson: "Talk to a person",
    gasCall: "Get outside, then call 911",
    newChat: "Start over",
    newChatConfirm: "Start a new conversation? This one will be cleared from this screen.",
    prototype: "Prototype with made-up data.",
    emergencyLead: "Emergency?",
    emergencyCall: "Emergency: call 911",
    demoButton: "Demo",
    demoTitle: "About this demo",
    demoSignIn: "Demo sign-in",
    demoClose: "Close",
    safetyInfo: "If that happens",
  },
  es: {
    lang: "es",
    stage: { collecting: "Borrador: faltan algunos datos", ready: "Revise y envíe", submitted: "Enviada", blocked: "No disponible aquí" },
    source: { you_said: "Lo que dijo", on_file: "En su cuenta", assistant: "Agregado por el asistente", missing: "Falta" },
    stillNeeded: "Falta:",
    dontSend: "No enviar",
    sending: "Enviando…",
    whatWasSent: "Lo que se envió",
    notSent: "No enviada",
    reference: "Referencia",
    assistantSaid: "El asistente dijo:",
    youSaid: "Usted dijo:",
    youChose: "Usted pulsó:",
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
    replyMock: "Las respuestas aquí vienen de reglas fijas, no de un modelo de IA.",
    replyAi: "Las respuestas las escribe un modelo de IA y las revisan reglas de seguridad fijas; puede equivocarse.",
    staffLink: "Consola del personal",
    message: "Escriba al asistente",
    send: "Enviar mensaje",
    conversation: "Conversación",
    suggestions: "Respuestas sugeridas",
    unreachable: "No puedo comunicarme con el asistente ahora, así que su mensaje no se envió.",
    serverError: "Algo salió mal de nuestro lado, así que su mensaje no se procesó.",
    tryAgain: "Inténtelo de nuevo. En una emergencia, llame al 911.",
    notSaved: "No se guardó, así que no se envió nada. Inténtelo de nuevo o comuníquese con la oficina.",
    declinedMsg: "De acuerdo, no envié nada. ¿Le ayudo con algo más?",
    afterSend: ["Ver mis solicitudes", "Reportar una reparación"],
    afterDecline: ["Envíelo", "Reportar una reparación"],
    talkToPerson: "Hablar con una persona",
    newChat: "Empezar de nuevo",
    newChatConfirm: "¿Empezar una conversación nueva? Esta se borrará de la pantalla.",
    prototype: "Prototipo con datos ficticios.",
    emergencyLead: "¿Emergencia?",
    emergencyCall: "Emergencia: llame al 911",
    demoButton: "Demo",
    demoTitle: "Sobre esta demo",
    demoSignIn: "Inicio de sesión de demo",
    demoClose: "Cerrar",
    gasCall: "Salga y luego llame al 911",
    safetyInfo: "Si eso pasa",
    whatItSaid: "Lo que decía",
    fromProfile: "De su perfil",
    cancelFailed: "No pude actualizar eso ahora. No se ha enviado nada.",
    opened: "abierta el",
    showAll: (n: number) => `Ver todas (${n})`,
    showFewer: "Ver menos",
    assistantName: "Asistente de McKinley",
    assistantMessage: "Mensaje del asistente",
    signInHint: "Si cambia esto, empieza una conversación nueva.",
    signInConfirm: "¿Cambiar de cuenta? Esta conversación se borrará de la pantalla.",
    howCanIHelp: "¿En qué le puedo ayudar?",
  },
} as const;

export type UIStrings = (typeof UI)["en"] | (typeof UI)["es"];

export function formatDate(iso: string, lang: Lang): string {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(lang === "es" ? "es-MX" : "en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ---- customer session restore (live mode only; same tab, sessionStorage) ----

export const SESSION_KEY = "mckinley.customerSession";

export function saveSession<T>(data: T): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
  } catch {
    /* storage unavailable: a reload starts a new conversation */
  }
}

export function loadSession<T>(): T | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

// ---- conversation hand-off to the staff console (same browser, sessionStorage only) ----

export const CONVERSATION_KEY = "mckinley.lastConversation";

export type StoredTurn = { message: string; response: ChatResponse } | { confirm: ActionKind; result: ActionResult };

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
