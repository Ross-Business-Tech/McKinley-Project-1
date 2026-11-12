import { ApiError } from "./api";
import type {
  ActionKind, ActionResult, ChatResponse, Journey, Persona, ProposedAction, SafetyContact, SafetyHref, SafetyState,
} from "./types";

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

/** Backend record / status-list labels (English) in Spanish. Unknown labels are shown as they are. */
const ES_STATUS: Record<string, string> = {
  "submitted, waiting for staff review": "Enviada, en espera de revisión del personal",
  "saved in demo": "Guardada en la demo",
  "urgent · saved in demo": "Urgente · guardada en la demo",
  // labels stored before Sprint 9 (the backend now relabels them on read)
  "requested; leasing team to confirm a time": "Solicitada; el equipo de arrendamiento confirmará una hora",
  "in the office queue": "En la cola de la oficina",
  "urgent; in the office queue": "Urgente; en la cola de la oficina",
  "urgent": "Urgente",
  "submitted": "Enviada",
  "open": "Abierta",
  "in progress": "En curso",
  "scheduled": "Programada",
  "completed": "Completada",
  "closed": "Cerrada",
};

/** Customer-facing UI strings. Spanish = draft translation (needs review by a fluent McKinley staff member). */
export const UI = {
  en: {
    lang: "en",
    stage: { collecting: "Draft", ready: "Ready to send", submitted: "Saved in demo", blocked: "Not available here" },
    source: { you_said: "You told us", on_file: "On your account", assistant: "Added by the assistant", missing: "Still needed" },
    stillNeeded: "Still to add:",
    dontSend: "Don't send",
    sending: "Sending…",
    whatWasSent: "Details",
    notSent: "Not sent",
    reference: "Reference",
    assistantSaid: "Assistant said:",
    youSaid: "You said:",
    youChose: "You pressed:",
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
    replyMock: "Replies here come from fixed rules, not an AI model.",
    replyAi: "Replies are written by an AI model and checked by fixed safety rules; it can make mistakes.",
    replyModel: (who: string) => `Replies are written by an AI model (${who}) and checked by fixed safety rules; it can make mistakes.`,
    replyTemplate: (who: string) => `The last reply used approved wording, not the AI model (${who}).`,
    staffLink: "Staff and demo console",
    message: "Message the assistant",
    send: "Send message",
    conversation: "Conversation",
    suggestions: "Suggested replies",
    unreachable: "I can't reach the assistant right now, so your message wasn't sent.",
    serverError: "Something went wrong on our side, so your message wasn't handled.",
    // the AI model is busy or slow (rate limit, timeout): worth retrying soon
    busy: "The assistant is busy right now, so your message wasn't answered.",
    // the assistant is switched off or misconfigured: retrying will not help, the office can
    unavailable: "The assistant isn't available right now, so your message wasn't answered. You can contact the office directly.",
    tryAgain: "Please try again. In an emergency, call 911.",
    tryLater: "In an emergency, call 911.",
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
    afterSendGuest: ["What happens next?"],
    subtitle: "Resident and leasing help",
    statusText: (label: string) => label,
    talkToPerson: "Talk to a person",
    gasCall: "Get outside, then call 911",
    newChat: "Start over",
    newChatConfirm: "Start a new conversation? This one will be cleared from this screen.",
    // NEEDS McKINLEY REVIEW (Sprint 9): the persistent demo identity; the details are in "About this demo"
    prototype: "Demo · Sample data · No requests sent to staff",
    demoAbout: "This is a prototype with made-up sample data. Requests you save stay in this demo: McKinley staff don't see them and no one is notified, so nothing is booked, scheduled or charged.",
    // NEEDS McKINLEY REVIEW (Sprint 8): the only always-on mention of 911. Plain muted text, deliberately not a link.
    emergencyFooter: "In an emergency, call 911.",
    // NEEDS McKINLEY REVIEW (Sprint 8): contact link label and the alert heading when the backend sends none
    callPoison: "Call Poison Help 1-800-222-1222",
    safetyHeading: "Your safety comes first",
    demoButton: "Demo",
    demoTitle: "About this demo",
    demoSignIn: "Demo sign-in",
    // NEEDS McKINLEY REVIEW: public demo (no sign-in) - say plainly what a visitor cannot do here
    guestOnlyAbout: "On this public demo everyone is a guest: you can ask general questions, request a tour or leave a note for the office. Resident features such as repairs on your account and request status need a sign-in, which this demo does not have.",
    demoClose: "Close",
    safetyInfo: "If that happens",
  },
  es: {
    lang: "es",
    stage: { collecting: "Borrador", ready: "Lista para enviar", submitted: "Guardada en la demo", blocked: "No disponible aquí" },
    source: { you_said: "Lo que dijo", on_file: "En su cuenta", assistant: "Agregado por el asistente", missing: "Falta" },
    stillNeeded: "Falta agregar:",
    dontSend: "No enviar",
    sending: "Enviando…",
    whatWasSent: "Detalles",
    notSent: "No enviada",
    reference: "Referencia",
    assistantSaid: "El asistente dijo:",
    youSaid: "Usted dijo:",
    youChose: "Usted pulsó:",
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
    replyMock: "Las respuestas aquí vienen de reglas fijas, no de un modelo de IA.",
    replyAi: "Las respuestas las escribe un modelo de IA y las revisan reglas de seguridad fijas; puede equivocarse.",
    replyModel: (who: string) => `Las respuestas las escribe un modelo de IA (${who}) y las revisan reglas de seguridad fijas; puede equivocarse.`,
    replyTemplate: (who: string) => `La última respuesta usó un texto aprobado, no el modelo de IA (${who}).`,
    staffLink: "Consola del personal",
    message: "Escriba al asistente",
    send: "Enviar mensaje",
    conversation: "Conversación",
    suggestions: "Respuestas sugeridas",
    unreachable: "No puedo comunicarme con el asistente ahora, así que su mensaje no se envió.",
    serverError: "Algo salió mal de nuestro lado, así que su mensaje no se procesó.",
    busy: "El asistente está ocupado ahora, así que su mensaje no se respondió.",
    unavailable: "El asistente no está disponible ahora, así que su mensaje no se respondió. Puede comunicarse directamente con la oficina.",
    tryAgain: "Inténtelo de nuevo. En una emergencia, llame al 911.",
    tryLater: "En una emergencia, llame al 911.",
    notSaved: "No se guardó, así que no se envió nada. Inténtelo de nuevo o comuníquese con la oficina.",
    declinedMsg: "De acuerdo, no envié nada. ¿Le ayudo con algo más?",
    afterSend: ["Ver mis solicitudes", "Reportar una reparación"],
    afterDecline: ["Envíelo", "Reportar una reparación"],
    afterSendGuest: ["¿Qué pasa ahora?"],
    subtitle: "Ayuda para residentes y arrendamiento",
    statusText: (label: string) => ES_STATUS[label.trim().toLowerCase()] ?? label,
    talkToPerson: "Hablar con una persona",
    newChat: "Empezar de nuevo",
    newChatConfirm: "¿Empezar una conversación nueva? Esta se borrará de la pantalla.",
    prototype: "Demo · Datos de ejemplo · No se envía nada al personal",
    demoAbout: "Este es un prototipo con datos ficticios de ejemplo. Lo que guarde se queda en esta demostración: el personal de McKinley no lo ve y no se avisa a nadie, así que no se reserva, programa ni cobra nada.",
    // NEEDS McKINLEY REVIEW (Sprint 8)
    emergencyFooter: "En una emergencia, llame al 911.",
    callPoison: "Llamar a Poison Help 1-800-222-1222",
    safetyHeading: "Su seguridad es lo primero",
    demoButton: "Demo",
    demoTitle: "Sobre esta demo",
    demoSignIn: "Inicio de sesión de demo",
    // NEEDS McKINLEY REVIEW
    guestOnlyAbout: "En esta demostración pública todos son invitados: puede hacer preguntas generales, pedir una visita o dejar una nota para la oficina. Las funciones para residentes, como reparaciones en su cuenta y el estado de sus solicitudes, requieren iniciar sesión, algo que esta demostración no tiene.",
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

const PROVIDER_LABEL: Record<string, string> = {
  openrouter: "OpenRouter", gemini: "Gemini", ollama: "Ollama (local)", anthropic: "Anthropic", mock: "Mock",
};

/** "OpenRouter: model-id" for the About panel and diagnostics; never shows prompts or keys. */
export function providerLabel(provider?: string | null, model?: string | null): string {
  const name = PROVIDER_LABEL[provider ?? ""] ?? provider ?? "unknown provider";
  return model ? `${name}: ${model}` : name;
}

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

// ---- Sprint 8: safety state (normal / concern / active) ----

const SAFETY_STATES = new Set<SafetyState>(["normal", "concern", "active"]);
const SAFE_HREFS = new Set<SafetyHref>(["tel:911", "tel:988", "sms:988", "tel:18002221222"]);

/**
 * How this turn shows safety. The backend's `safety_state` wins; older backends and the recorded replay snapshot have
 * none, so it is derived from the fields they do have (safety_notice / emergency_kind -> active, care_note -> concern).
 * Fail-safe: a "normal" turn that still carries a safety_notice is shown as active rather than hiding the notice.
 */
export function safetyStateOf(r: ChatResponse | null | undefined): SafetyState {
  if (!r) return "normal";
  const s = r.safety_state;
  if (s && SAFETY_STATES.has(s)) return s === "normal" && r.safety_notice ? "active" : s;
  if (r.safety_notice || r.emergency_kind) return "active";
  if (r.care_note) return "concern";
  return "normal";
}

/** Fallback label for a contact the backend sent without one (and for contacts derived from older responses). */
function hrefLabel(href: SafetyHref, t: UIStrings): string {
  return { "tel:911": t.call911, "tel:988": t.call988, "sms:988": t.text988, "tel:18002221222": t.callPoison }[href];
}

/**
 * The contact links for one turn. Backend `safety_contacts` when present (only allow-listed tel:/sms: targets become
 * links; anything else is plain text). Otherwise, for older responses, the same links the screen showed before Sprint 8.
 * "normal" turns never get contacts.
 */
export function safetyContactsOf(r: ChatResponse | null | undefined, t: UIStrings): SafetyContact[] {
  const state = safetyStateOf(r);
  if (!r || state === "normal") return [];
  if (Array.isArray(r.safety_contacts)) {
    return r.safety_contacts.flatMap((c) => {
      if (!c || typeof c !== "object") return [];
      const href = c.href && SAFE_HREFS.has(c.href) ? c.href : null;
      const label = (typeof c.label === "string" && c.label.trim()) || (href ? hrefLabel(href, t) : "");
      if (!label) return [];
      return [{ label, href, kind: href ? (c.kind === "text" || href.startsWith("sms:") ? "text" : "call") : "info" } as SafetyContact];
    });
  }
  const link = (href: SafetyHref, label = hrefLabel(href, t)): SafetyContact => ({ label, href, kind: href.startsWith("sms:") ? "text" : "call" });
  if (state === "active") {
    const kind = r.emergency_kind ?? null;
    if (kind === "self_harm") return [link("tel:988"), link("sms:988")];
    if (kind === "poison") return [link("tel:18002221222"), link("tel:911")];
    const out = [link("tel:911", kind === "gas" || kind === "co" ? t.gasCall : t.call911)];
    if (/\b988\b/.test(r.safety_notice ?? "")) out.push(link("tel:988"));
    return out;
  }
  // concern from an older response: the care line's previous links (distress -> 988; unwell/danger -> 911; info -> none)
  if (!r.care_note || r.care_kind === "info") return [];
  return r.care_kind === "distress" ? [link("tel:988"), link("sms:988")] : [link("tel:911")];
}

// ---- why a message was not answered ----

/** Busy model (wait and retry), switched-off assistant (contact the office), no connection, or a server error. */
const BUSY_CODES = new Set(["ASSISTANT_BUSY", "MODEL_RATE_LIMITED", "MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR"]);
const UNAVAILABLE_CODES = new Set(["ASSISTANT_UNAVAILABLE", "NEEDS_API_KEY", "MODEL_AUTH_ERROR", "MODEL_PAYMENT_REQUIRED"]);

export function sendErrorText(e: unknown, t: UIStrings): string {
  const code = e instanceof ApiError ? e.code : "";
  if (code === "BACKEND_UNREACHABLE") return `${t.unreachable} ${t.tryAgain}`;
  if (BUSY_CODES.has(code)) return `${t.busy} ${t.tryAgain}`;
  if (UNAVAILABLE_CODES.has(code)) return `${t.unavailable} ${t.tryLater}`;
  return `${t.serverError} ${t.tryAgain}`;
}
