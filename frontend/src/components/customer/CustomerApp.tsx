"use client";

import { AlertTriangle, ArrowUp, Info, MessageSquareText, Phone, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import {
  GUEST,
  type Identity,
  type Lang,
  type StoredTurn,
  UI,
  type UIStrings,
  greeting,
  journeyPersonaIds,
  saveConversation,
  starters,
  toIdentities,
} from "@/lib/customer";
import { newSessionId } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActionKind, ActionResult, ChatResponse, Journey } from "@/lib/types";

import { ActionCard, type CardState } from "./ActionCard";

type Boot =
  | { mode: "loading" }
  | { mode: "live"; identities: Identity[] }
  | { mode: "preview"; identities: Identity[]; journeys: Journey[] }
  | { mode: "error"; message: string };

interface Msg {
  id: string;
  role: "assistant" | "user";
  text: string;
  lang?: Lang;
  response?: ChatResponse;
  result?: ActionResult;
  error?: { retry: string };
  failed?: boolean; // user message that never reached the assistant
  cleared?: string; // assistant message confirming a card of this kind was not sent
}

let counter = 0;
const mid = () => `m${++counter}`;

async function boot(): Promise<Boot> {
  try {
    const personas = await api.personas();
    return { mode: "live", identities: toIdentities(personas) };
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "BACKEND_UNREACHABLE") {
      return { mode: "error", message: e instanceof ApiError ? e.message : "The assistant could not start." };
    }
    try {
      const snap = await loadDemoSnapshot();
      const journeys = snap.journeys ?? [];
      const used = journeyPersonaIds(journeys);
      const identities = toIdentities(snap.personas).filter((i) => used.has(i.id));
      return { mode: "preview", identities, journeys };
    } catch {
      return { mode: "error", message: "The assistant is not reachable right now. Please try again in a minute." };
    }
  }
}

export function CustomerApp() {
  const [state, setState] = useState<Boot>({ mode: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [identity, setIdentity] = useState<Identity>(GUEST);
  const [sessionId, setSessionId] = useState(() => newSessionId());
  const [messages, setMessages] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<StoredTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [step, setStep] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const lastAssistantRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputId = useId();
  const statusId = useId();
  const bannerId = useId();
  const whoHintId = useId();

  useEffect(() => {
    let cancelled = false;
    boot().then((b) => {
      if (cancelled) return;
      setState(b);
      setMessages([{ id: mid(), role: "assistant", text: greeting(GUEST), lang: "en" }]); // AI disclosure (I-01 draft)
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reset = useCallback((next: Identity) => {
    setIdentity(next);
    setSessionId(newSessionId());
    setMessages([{ id: mid(), role: "assistant", text: greeting(next), lang: next.lang }]);
    setTurns([]);
    setJourney(null);
    setStep(0);
    setDraft("");
  }, []);

  // Keep the newest message (and its buttons) fully above the sticky composer: scroll the page to its end.
  useEffect(() => {
    const el = document.scrollingElement ?? document.documentElement;
    requestAnimationFrame(() => el.scrollTo?.({ top: el.scrollHeight }));
  }, [messages, busy]);

  useEffect(() => {
    if (turns.length) saveConversation({ persona_id: identity.id, session_id: sessionId, saved_at: new Date().toISOString(), turns });
  }, [turns, identity.id, sessionId]);

  const preview = state.mode === "preview" ? state : null;
  const lastResponse = [...messages].reverse().find((m) => m.response)?.response;
  const lang: Lang = lastResponse?.language ?? identity.lang;
  const t = UI[lang];
  const cardStates = useMemo(() => cardStatesFor(messages), [messages]);

  // ---- suggestions -------------------------------------------------------------------------------------------
  const nextStep = journey ? journey.steps[step] : undefined;
  let chips: { label: string; send: string }[] = [];
  if (preview) {
    if (!journey) {
      chips = preview.journeys
        .filter((j) => j.persona_id === identity.id)
        .map((j) => ({ label: j.title, send: (j.steps[0] as { message: string }).message }));
    } else if (nextStep?.kind === "chat") {
      chips = [{ label: nextStep.message, send: nextStep.message }];
    }
  } else if (messages.length <= 1) {
    chips = starters(identity).map((s) => ({ label: s, send: s }));
  } else if (lastResponse?.suggested_replies?.length && !busy) {
    const last = messages[messages.length - 1];
    if (last.response) chips = lastResponse.suggested_replies.map((s) => ({ label: s, send: s }));
  }
  const journeyDone = !!journey && step >= journey.steps.length;

  // ---- actions -----------------------------------------------------------------------------------------------
  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    if (preview) {
      let j = journey;
      let i = step;
      if (!j) {
        j = preview.journeys.find((x) => x.persona_id === identity.id && x.steps[0].kind === "chat" && x.steps[0].message === message) ?? null;
        i = 0;
        if (!j) return;
        setJourney(j);
      }
      const s = j.steps[i];
      if (s?.kind !== "chat" || s.message !== message) return;
      setMessages((m) => [
        ...m,
        { id: mid(), role: "user", text: message, lang: s.response.language },
        { id: mid(), role: "assistant", text: s.response.reply, lang: s.response.language, response: s.response },
      ]);
      setTurns((t) => [...t, { message, response: s.response }]);
      announce(s.response);
      setStep(i + 1);
      setDraft("");
      requestAnimationFrame(() => lastAssistantRef.current?.focus()); // the tapped chip is gone; land on the reply
      return;
    }
    setDraft("");
    const userId = mid();
    setMessages((m) => [...m.filter((x) => !x.error), { id: userId, role: "user", text: message, lang }]);
    setBusy(true);
    try {
      const response = await api.chat({ message, persona_id: identity.id || null, mode: "aware", session_id: sessionId });
      setMessages((m) => [
        ...m.map((x) => (x.id === userId ? { ...x, lang: response.language ?? x.lang } : x)),
        { id: mid(), role: "assistant", text: response.reply, lang: response.language, response },
      ]);
      setTurns((t) => [...t, { message, response }]);
      announce(response);
    } catch (e) {
      const why =
        e instanceof ApiError && e.code === "BACKEND_UNREACHABLE"
          ? "I can't reach the assistant right now, so your message wasn't sent."
          : "Something went wrong on our side, so your message wasn't handled.";
      const text = `${why} Please try again. In an emergency, call 911.`;
      setMessages((m) => [
        ...m.map((x) => (x.id === userId ? { ...x, failed: true } : x)),
        { id: mid(), role: "assistant", text, error: { retry: message } },
      ]);
      setAnnouncement(text);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus()); // keep typing where you were (keyboard stays open)
    }
  }

  function announce(r: ChatResponse) {
    if (r.safety_notice) return setAnnouncement(""); // the role=alert block announces itself, once
    const a = r.action;
    const card = a ? ` ${a.title}: ${a.stage === "submitted" ? (a.record?.status_label ?? "") : UI[r.language ?? "en"].stage[a.stage]}.` : "";
    setAnnouncement(`${UI[r.language ?? "en"].assistantSaid} ${r.reply}${card}`);
  }

  async function confirmAction(kind: ActionKind) {
    if (busy) return;
    if (preview) {
      if (!journey || nextStep?.kind !== "confirm" || nextStep.action_kind !== kind) return;
      const result = nextStep.result;
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result, lang }]);
      setAnnouncement(result.message);
      setTurns((t) => [...t, { confirm: kind, result }]);
      setStep(step + 1);
      requestAnimationFrame(() => lastAssistantRef.current?.focus());
      return;
    }
    setBusy(true);
    try {
      const result = await api.confirmAction(sessionId, identity.id || null, kind);
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result, lang }]);
      setAnnouncement(result.message);
      setTurns((t) => [...t, { confirm: kind, result }]);
    } catch {
      setMessages((m) => [
        ...m,
        { id: mid(), role: "assistant", text: "That didn't save, so nothing was sent. Please try again, or contact the office directly." },
      ]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => lastAssistantRef.current?.focus());
    }
  }

  async function cancelAction(kind: ActionKind) {
    if (busy || preview) return;
    setBusy(true);
    try {
      const result = await api.cancelAction(sessionId, identity.id || null, kind);
      const text = result.ok
        ? lang === "es"
          ? "De acuerdo, no envié nada. ¿Le ayudo con algo más?"
          : "Okay, I haven't sent anything. Is there something else I can help with?"
        : result.message;
      setMessages((m) => [...m, { id: mid(), role: "assistant", text, lang, cleared: result.ok ? kind : undefined }]);
      setAnnouncement(text);
    } catch {
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: "I couldn't update that just now. Nothing has been sent." }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => lastAssistantRef.current?.focus()); // the button that had focus is gone
    }
  }

  // ---- render ------------------------------------------------------------------------------------------------
  if (state.mode === "loading") {
    return (
      <Frame>
        <p role="status" className="px-4 py-10 text-center text-mk-muted">
          Starting the assistant…
        </p>
      </Frame>
    );
  }
  if (state.mode === "error") {
    return (
      <Frame>
        <div role="alert" className="mx-4 my-10 rounded-lg border border-mk-line bg-mk-surface p-5">
          <p className="font-semibold">{state.message}</p>
          <p className="mt-1 text-mk-muted">In an emergency, call 911 or your community&apos;s emergency maintenance line.</p>
          <button
            type="button"
            onClick={() => setAttempt((a) => a + 1)}
            className="mk-focus mt-4 inline-flex min-h-11 items-center gap-2 rounded-md bg-mk-brand px-4 font-semibold text-white"
          >
            <RotateCcw aria-hidden className="size-4" /> Try again
          </button>
        </div>
      </Frame>
    );
  }

  const groups = ["Not signed in", "Looking for a home", "Residents"] as const;
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <Frame
      identityControl={
        <div className="flex min-w-0 flex-col gap-1 sm:items-end">
          <label htmlFor={`${inputId}-who`} className="text-sm text-mk-muted">
            Demo sign-in
          </label>
          <select
            id={`${inputId}-who`}
            value={identity.id}
            aria-describedby={whoHintId}
            onChange={(e) => reset(state.identities.find((i) => i.id === e.target.value) ?? GUEST)}
            className="mk-focus h-11 w-full min-w-0 rounded-md border border-mk-line-strong bg-mk-surface px-3 text-base sm:w-72"
          >
            {groups.map((g) => {
              const opts = state.identities.filter((i) => i.group === g);
              return opts.length ? (
                <optgroup key={g} label={g}>
                  {opts.map((i) => (
                    <option key={i.id || "guest"} value={i.id}>
                      {i.label}
                    </option>
                  ))}
                </optgroup>
              ) : null;
            })}
          </select>
          <span id={whoHintId} className="sr-only">
            Changing this starts a new conversation.
          </span>
        </div>
      }
    >
      {preview && (
        <p id={bannerId} className="mx-4 mt-3 flex max-w-2xl gap-2 rounded-md border border-mk-line bg-mk-surface px-4 py-2.5 text-sm text-mk-muted sm:mx-auto sm:w-full">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            Preview link: this page replays real conversations recorded from the prototype, with made-up data and no live AI.
            Typing is turned off here. Tap a suggestion to continue.
          </span>
        </p>
      )}

      <section aria-labelledby={`${inputId}-conv`} className="mx-auto w-full max-w-2xl flex-1 px-4 py-4 sm:px-0">
        <h2 id={`${inputId}-conv`} className="sr-only">
          {t.conversation}
        </h2>
        <div className="space-y-4">
          {messages.map((m, i) => (
            <Message
              key={m.id}
              msg={m}
              t={UI[m.lang ?? lang]}
              focusRef={m === lastAssistant ? lastAssistantRef : undefined}
              cardState={cardStates[i] ?? "current"}
              busy={busy}
              preview={!!preview}
              nextConfirmKind={nextStep?.kind === "confirm" ? nextStep.action_kind : null}
              onConfirm={confirmAction}
              onCancel={cancelAction}
              onRetry={send}
            />
          ))}
          {busy && (
            <p className="text-mk-muted" aria-hidden>
              <span className="inline-flex gap-1 align-middle">
                <span className="size-1.5 animate-pulse rounded-full bg-mk-muted" />
                <span className="size-1.5 animate-pulse rounded-full bg-mk-muted [animation-delay:150ms]" />
                <span className="size-1.5 animate-pulse rounded-full bg-mk-muted [animation-delay:300ms]" />
              </span>{" "}
              {t.replying}
            </p>
          )}
        </div>
        {/* One short, polite announcement per reply (the visible transcript is not a live region). */}
        <p className="sr-only" aria-live="polite">
          {busy ? t.replying : announcement}
        </p>
      </section>

      <div className="sticky bottom-0 border-t border-mk-line bg-mk-paper/95 backdrop-blur supports-[backdrop-filter]:bg-mk-paper/85">
        <div className="mx-auto w-full max-w-2xl px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-0">
          {chips.length > 0 && (
            <div
              role="group"
              aria-label={t.suggestions}
              lang={lang}
              className="-mx-4 mb-3 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:thin] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0"
            >
              {chips.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  disabled={busy}
                  onClick={() => send(c.send)}
                  className="mk-focus min-h-11 shrink-0 rounded-full border border-mk-brand bg-mk-surface px-4 py-2 text-left text-base whitespace-nowrap text-mk-brand hover:bg-mk-brand-soft disabled:opacity-60 sm:shrink sm:whitespace-normal"
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
          {journeyDone && (
            <button
              type="button"
              onClick={() => reset(identity)}
              className="mk-focus mb-3 inline-flex min-h-11 items-center gap-2 rounded-md border border-mk-line-strong bg-mk-surface px-4"
            >
              <RotateCcw aria-hidden className="size-4" /> Start another conversation
            </button>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(draft);
            }}
            className="flex items-end gap-2"
          >
            <label htmlFor={inputId} className="sr-only">
              {t.message}
            </label>
            <textarea
              id={inputId}
              ref={inputRef}
              rows={1}
              value={draft}
              disabled={!!preview}
              lang={lang}
              aria-describedby={preview ? `${bannerId} ${statusId}` : statusId}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
              placeholder={preview ? t.previewPlaceholder : t.placeholder}
              maxLength={4000}
              className="mk-focus max-h-40 min-h-11 flex-1 resize-none rounded-md border border-mk-line-strong bg-mk-surface px-3 py-2.5 text-base placeholder:text-mk-muted disabled:bg-mk-draft-soft"
            />
            <button
              type="submit"
              disabled={!!preview || busy || !draft.trim()}
              className="mk-focus inline-flex size-11 shrink-0 items-center justify-center rounded-md bg-mk-brand text-white hover:bg-mk-brand-hover disabled:bg-mk-line-strong disabled:text-mk-surface"
            >
              <ArrowUp aria-hidden className="size-5" />
              <span className="sr-only">{t.send}</span>
            </button>
          </form>
          <p id={statusId} className="mt-2 text-sm text-mk-muted" lang={lang}>
            {t.footer}{" "}
            <Link href="/staff" prefetch={false} className="mk-focus underline underline-offset-2">
              {t.staffLink}
            </Link>
          </p>
        </div>
      </div>
    </Frame>
  );
}

/** Final visual state of each card in the transcript: only the newest open card is active. */
function cardStatesFor(messages: Msg[]): CardState[] {
  const out: CardState[] = [];
  for (let i = 0; i < messages.length; i++) {
    const a = messages[i].result?.action ?? messages[i].response?.action;
    if (!a) continue;
    if (a.stage === "submitted") {
      out[i] = "current";
      continue;
    }
    let state: CardState = "current";
    for (let j = i + 1; j < messages.length; j++) {
      const later = messages[j];
      if (later.cleared === a.kind || later.response?.action_cleared === a.kind) {
        state = "declined";
        break;
      }
      const la = later.result?.action ?? later.response?.action;
      if (la) {
        state = "superseded";
        break;
      }
    }
    out[i] = state;
  }
  return out;
}

function Frame({ children, identityControl }: { children: React.ReactNode; identityControl?: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-mk-line bg-mk-surface">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-end sm:justify-between sm:px-0">
          <div>
            <p className="text-xl font-bold tracking-tight text-mk-brand">McKinley</p>
            <h1 className="text-base font-semibold">Resident and leasing help</h1>
          </div>
          {identityControl}
        </div>
      </header>
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}

const CALL_KINDS_WITHOUT_MAINTENANCE = new Set(["self_harm", "medical", "personal_safety"]);

function Message({
  msg,
  t,
  focusRef,
  cardState,
  busy,
  preview,
  nextConfirmKind,
  onConfirm,
  onCancel,
  onRetry,
}: {
  msg: Msg;
  t: UIStrings;
  focusRef?: React.Ref<HTMLDivElement>;
  cardState: CardState;
  busy: boolean;
  preview: boolean;
  nextConfirmKind: ActionKind | null;
  onConfirm: (k: ActionKind) => void;
  onCancel: (k: ActionKind) => void;
  onRetry: (text: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex flex-col items-end" lang={msg.lang}>
        <p className={cn("max-w-[85%] rounded-lg rounded-br-sm px-4 py-2.5 break-words whitespace-pre-wrap",
          msg.failed ? "border border-dashed border-mk-attention bg-mk-surface" : "bg-mk-brand-soft")}>
          <span className="sr-only">{t.youSaid} </span>
          {msg.text}
        </p>
        {msg.failed && (
          <p className="mt-1 inline-flex items-center gap-1 text-sm text-mk-attention">
            <AlertTriangle aria-hidden className="size-4" /> {t.failed}
          </p>
        )}
      </div>
    );
  }
  const r = msg.response;
  const action = msg.result?.action ?? r?.action ?? null;
  const emergency = !!r?.safety_notice;
  const kind = r?.emergency_kind ?? null;
  const templateCoversNotice = emergency && /\b(911|988)\b/.test(msg.text);

  if (msg.error) {
    return (
      <div ref={focusRef} tabIndex={-1} className="mk-focus max-w-[95%] rounded-lg border border-mk-attention/40 bg-mk-attention-soft p-4 outline-none" role="status">
        <p className="flex items-start gap-2 text-mk-attention">
          <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0" />
          <span className="text-base text-mk-ink">{msg.text}</span>
        </p>
        <button
          type="button"
          onClick={() => onRetry(msg.error!.retry)}
          className="mk-focus mt-3 inline-flex min-h-11 items-center gap-2 rounded-md border border-mk-line-strong bg-mk-surface px-4"
        >
          <RotateCcw aria-hidden className="size-4" /> {t.sendAgain}
        </button>
      </div>
    );
  }

  return (
    <div ref={focusRef} tabIndex={-1} lang={msg.lang} className="mk-focus max-w-[95%] rounded-md outline-none">
      <span className="sr-only">{t.assistantSaid} </span>
      {emergency && (
        <div role="alert" className="mb-2 rounded-lg border-2 border-mk-danger bg-mk-danger-soft p-4">
          <p className="flex items-start gap-2 text-lg leading-snug font-bold text-mk-danger">
            <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0" />
            <span>{r?.safety_heading ?? t.call911}</span>
          </p>
          <p className="mt-2 text-base text-mk-ink">{templateCoversNotice ? msg.text : r?.safety_notice}</p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            {kind === "self_harm" ? (
              <>
                <a href="tel:988" className="mk-focus inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-mk-danger px-5 text-lg font-bold text-white">
                  <Phone aria-hidden className="size-5" /> {t.call988}
                </a>
                <a href="sms:988" className="mk-focus inline-flex min-h-12 items-center justify-center gap-2 rounded-md border-2 border-mk-danger bg-mk-surface px-5 text-lg font-bold text-mk-danger">
                  <MessageSquareText aria-hidden className="size-5" /> {t.text988}
                </a>
              </>
            ) : (
              <a href="tel:911" className="mk-focus inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-mk-danger px-5 text-lg font-bold text-white">
                <Phone aria-hidden className="size-5" /> {t.call911}
              </a>
            )}
          </div>
          {kind && !CALL_KINDS_WITHOUT_MAINTENANCE.has(kind) && <p className="mt-2 text-sm text-mk-muted">{t.noEmergencyLine}</p>}
        </div>
      )}
      {!templateCoversNotice && <p className="text-base leading-relaxed break-words whitespace-pre-wrap">{msg.text}</p>}
      {r?.status_items && r.status_items.length > 0 && (
        <ul aria-label={t.openRequests} className="mt-3 divide-y divide-mk-line rounded-lg border border-mk-line bg-mk-surface">
          {r.status_items.map((s) => {
            const owed = /owed/i.test(s.status);
            return (
              <li key={s.reference} className="px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{s.title}</p>
                  <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-medium whitespace-nowrap",
                    owed ? "bg-mk-attention-soft text-mk-attention" : "bg-mk-sent-soft text-mk-sent")}>
                    {owed && <AlertTriangle aria-hidden className="size-3.5" />}
                    {owed ? t.followUpOwed : s.status.split(";")[0]}
                  </span>
                </div>
                <p className="text-sm text-mk-muted">
                  {t.reference} <span className="tabular-nums">{s.reference}</span>
                  {s.opened ? `, opened ${formatDate(s.opened)}` : ""}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {action && (
        <ActionCard
          action={action}
          state={cardState}
          t={t}
          busy={busy}
          confirmAvailable={!preview || nextConfirmKind === action.kind}
          cancelAvailable={!preview}
          onConfirm={() => onConfirm(action.kind)}
          onCancel={() => onCancel(action.kind)}
        />
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
