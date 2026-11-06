"use client";

import { AlertTriangle, ArrowUp, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import {
  GUEST,
  type Identity,
  type StoredTurn,
  greeting,
  identityStatus,
  journeyPersonaIds,
  saveConversation,
  starters,
  toIdentities,
} from "@/lib/customer";
import { newSessionId } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActionKind, ActionResult, ChatResponse, Journey } from "@/lib/types";

import { ActionCard } from "./ActionCard";

type Boot =
  | { mode: "loading" }
  | { mode: "live"; identities: Identity[] }
  | { mode: "preview"; identities: Identity[]; journeys: Journey[] }
  | { mode: "error"; message: string };

interface Msg {
  id: string;
  role: "assistant" | "user";
  text: string;
  lang?: "en" | "es";
  response?: ChatResponse;
  result?: ActionResult;
  error?: { retry: string };
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
  const endRef = useRef<HTMLDivElement>(null);
  const lastAssistantRef = useRef<HTMLDivElement>(null);
  const inputId = useId();
  const statusId = useId();

  useEffect(() => {
    let cancelled = false;
    boot().then((b) => {
      if (cancelled) return;
      setState(b);
      setMessages([{ id: mid(), role: "assistant", text: greeting(GUEST) }]); // first greeting, AI disclosure (I-01 draft)
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reset = useCallback((next: Identity) => {
    setIdentity(next);
    setSessionId(newSessionId());
    setMessages([{ id: mid(), role: "assistant", text: greeting(next) }]);
    setTurns([]);
    setJourney(null);
    setStep(0);
    setDraft("");
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  useEffect(() => {
    if (turns.length) saveConversation({ persona_id: identity.id, session_id: sessionId, saved_at: new Date().toISOString(), turns });
  }, [turns, identity.id, sessionId]);

  const preview = state.mode === "preview" ? state : null;
  const lastResponse = [...messages].reverse().find((m) => m.response)?.response;
  const actionIndex = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].response?.action || messages[i].result?.action) return i;
    }
    return -1;
  }, [messages]);

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
        { id: mid(), role: "user", text: message },
        { id: mid(), role: "assistant", text: s.response.reply, lang: s.response.language, response: s.response },
      ]);
      setTurns((t) => [...t, { message, response: s.response }]);
      setStep(i + 1);
      setDraft("");
      return;
    }
    setDraft("");
    setMessages((m) => [...m.filter((x) => !x.error), { id: mid(), role: "user", text: message }]);
    setBusy(true);
    try {
      const response = await api.chat({ message, persona_id: identity.id || null, mode: "aware", session_id: sessionId });
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: response.reply, lang: response.language, response }]);
      setTurns((t) => [...t, { message, response }]);
    } catch (e) {
      const why =
        e instanceof ApiError && e.code === "BACKEND_UNREACHABLE"
          ? "I can't reach the assistant right now, so your message wasn't sent."
          : "Something went wrong on our side, so your message wasn't handled.";
      setMessages((m) => [
        ...m,
        { id: mid(), role: "assistant", text: `${why} Please try again. In an emergency, call 911.`, error: { retry: message } },
      ]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => lastAssistantRef.current?.focus());
    }
  }

  async function confirmAction(kind: ActionKind) {
    if (busy) return;
    if (preview) {
      if (!journey || nextStep?.kind !== "confirm" || nextStep.action_kind !== kind) return;
      const result = nextStep.result;
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result }]);
      setTurns((t) => [...t, { confirm: kind, result }]);
      setStep(step + 1);
      requestAnimationFrame(() => lastAssistantRef.current?.focus());
      return;
    }
    setBusy(true);
    try {
      const result = await api.confirmAction(sessionId, identity.id || null, kind);
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result }]);
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
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.ok ? "Okay, I haven't sent anything. Is there something else I can help with?" : result.message }]);
    } catch {
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: "I couldn't update that just now. Nothing has been sent." }]);
    } finally {
      setBusy(false);
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
        </div>
      }
    >
      {preview && (
        <p className="mx-4 mt-3 max-w-2xl rounded-md bg-mk-sent-soft px-4 py-2.5 text-sm text-mk-sent sm:mx-auto sm:w-full">
          Preview link: this page replays real conversations recorded from the prototype, with made-up data and no live AI.
          Typing is turned off here. Tap a suggestion to continue.
        </p>
      )}
      {identity.kind !== "guest" && (
        <p className="mx-auto mt-3 w-full max-w-2xl px-4 text-sm text-mk-muted sm:px-0">{identityStatus(identity)}</p>
      )}

      <div role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation" className="mx-auto w-full max-w-2xl flex-1 space-y-4 px-4 py-4 sm:px-0">
        {messages.map((m, i) => (
          <Message
            key={m.id}
            msg={m}
            focusRef={m === lastAssistant ? lastAssistantRef : undefined}
            interactive={i === actionIndex}
            busy={busy}
            preview={!!preview}
            nextConfirmKind={nextStep?.kind === "confirm" ? nextStep.action_kind : null}
            onConfirm={confirmAction}
            onCancel={cancelAction}
            onRetry={send}
          />
        ))}
        {busy && (
          <p role="status" className="text-mk-muted">
            The assistant is replying…
          </p>
        )}
        <div ref={endRef} />
      </div>

      <div className="sticky bottom-0 border-t border-mk-line bg-mk-paper/95 backdrop-blur supports-[backdrop-filter]:bg-mk-paper/85">
        <div className="mx-auto w-full max-w-2xl px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-0">
          {chips.length > 0 && (
            <div role="group" aria-label="Suggested replies" className="-mx-1 mb-3 flex flex-wrap gap-2 px-1">
              {chips.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  disabled={busy}
                  onClick={() => send(c.send)}
                  className="mk-focus min-h-11 max-w-full rounded-full border border-mk-brand bg-mk-surface px-4 py-2 text-left text-base text-mk-brand hover:bg-mk-brand-soft disabled:opacity-60"
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
              Message the assistant
            </label>
            <textarea
              id={inputId}
              rows={1}
              value={draft}
              disabled={!!preview}
              aria-describedby={statusId}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
              placeholder={preview ? "Typing is off in this preview" : "Type your message"}
              maxLength={4000}
              className="mk-focus max-h-40 min-h-11 flex-1 resize-none rounded-md border border-mk-line-strong bg-mk-surface px-3 py-2.5 text-base placeholder:text-mk-muted disabled:bg-mk-draft-soft"
            />
            <button
              type="submit"
              disabled={!!preview || busy || !draft.trim()}
              className="mk-focus inline-flex size-11 shrink-0 items-center justify-center rounded-md bg-mk-brand text-white hover:bg-mk-brand-hover disabled:opacity-50"
            >
              <ArrowUp aria-hidden className="size-5" />
              <span className="sr-only">Send message</span>
            </button>
          </form>
          <p id={statusId} className="mt-2 text-sm text-mk-muted">
            Prototype with made-up data. In an emergency, call 911.{" "}
            <Link href="/staff" prefetch={false} className="mk-focus underline underline-offset-2">
              Staff and demo console
            </Link>
          </p>
        </div>
      </div>
    </Frame>
  );
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

function Message({
  msg,
  focusRef,
  interactive,
  busy,
  preview,
  nextConfirmKind,
  onConfirm,
  onCancel,
  onRetry,
}: {
  msg: Msg;
  focusRef?: React.Ref<HTMLDivElement>;
  interactive: boolean;
  busy: boolean;
  preview: boolean;
  nextConfirmKind: ActionKind | null;
  onConfirm: (k: ActionKind) => void;
  onCancel: (k: ActionKind) => void;
  onRetry: (text: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-lg rounded-br-sm bg-mk-brand-soft px-4 py-2.5 break-words whitespace-pre-wrap">
          <span className="sr-only">You said: </span>
          {msg.text}
        </p>
      </div>
    );
  }
  const r = msg.response;
  const action = msg.result?.action ?? r?.action ?? null;
  const emergency = !!r?.safety_notice;
  // When the reply itself already gives the 911 guidance, show it once, inside the alert.
  const templateCoversNotice = emergency && /\b911\b/.test(msg.text);
  const confirmReason =
    preview && action?.stage === "ready" && nextConfirmKind !== action.kind
      ? "In this preview you can only continue the recorded conversation."
      : null;

  return (
    <div ref={focusRef} tabIndex={-1} lang={msg.lang} className="mk-focus max-w-[95%] rounded-md outline-none">
      <span className="sr-only">Assistant said: </span>
      {emergency && (
        <div role="alert" className="mb-2 rounded-lg border-2 border-mk-danger bg-mk-danger-soft p-4 text-mk-danger">
          <p className="flex items-center gap-2 text-lg font-bold">
            <AlertTriangle aria-hidden className="size-5 shrink-0" />
            {msg.lang === "es" ? "Si hay peligro, llame al 911 ahora" : "If anyone is in danger, call 911 now"}
          </p>
          <p className="mt-1 text-base text-mk-ink">{templateCoversNotice ? msg.text : r?.safety_notice}</p>
        </div>
      )}
      {!templateCoversNotice && (
        <p className={cn("text-base leading-relaxed break-words whitespace-pre-wrap", msg.error && "text-mk-ink")}>{msg.text}</p>
      )}
      {msg.error && (
        <button
          type="button"
          onClick={() => onRetry(msg.error!.retry)}
          className="mk-focus mt-2 inline-flex min-h-11 items-center gap-2 rounded-md border border-mk-line-strong bg-mk-surface px-4"
        >
          <RotateCcw aria-hidden className="size-4" /> Send again
        </button>
      )}
      {r?.status_items && r.status_items.length > 0 && (
        <ul aria-label="Your open requests" className="mt-3 divide-y divide-mk-line rounded-lg border border-mk-line bg-mk-surface">
          {r.status_items.map((s) => (
            <li key={s.reference} className="px-4 py-3">
              <p className="font-semibold">{s.title}</p>
              <p className="text-base">{s.status}</p>
              <p className="text-sm text-mk-muted">
                Reference {s.reference}
                {s.opened ? `, opened ${formatDate(s.opened)}` : ""}
                {s.source === "prototype_store" ? ". Sent through this assistant (prototype)" : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
      {action && (
        <ActionCard
          action={action}
          interactive={interactive}
          busy={busy}
          cancelAvailable={!preview}
          confirmDisabledReason={confirmReason}
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
