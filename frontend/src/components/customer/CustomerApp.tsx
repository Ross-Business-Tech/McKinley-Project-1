"use client";

import { AlertTriangle, ArrowUp, ChevronRight, Info, MessageSquareText, Phone, RotateCcw, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError, LIVE_BACKEND_CONFIGURED, api, loadDemoSnapshot } from "@/lib/api";
import {
  GUEST,
  type Identity,
  type Lang,
  type StoredTurn,
  UI,
  type UIStrings,
  clearSession,
  formatDate,
  greeting,
  journeyPersonaIds,
  loadSession,
  saveConversation,
  saveSession,
  starters,
  toIdentities,
} from "@/lib/customer";
import { newSessionId } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActionKind, ActionResult, ChatResponse, Journey, ProposedAction, StatusItem } from "@/lib/types";

import { ActionCard, type CardState, ProgressHint } from "./ActionCard";
import { StatusPill, statusTone } from "./StatusPill";

type Boot =
  | { mode: "loading" }
  | { mode: "live"; identities: Identity[]; mock: boolean | null }
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
  restored?: boolean; // brought back after a reload: never re-announced as a new alert
}

interface SavedSession {
  v: 1;
  identityId: string;
  sessionId: string;
  messages: Msg[];
  turns: StoredTurn[];
}

let counter = 0;
const mid = () => `m${++counter}`;

async function boot(): Promise<Boot> {
  try {
    const personas = await api.personas();
    const health = await api.health().catch(() => null); // only for the "About this demo" line
    return { mode: "live", identities: toIdentities(personas), mock: health ? health.is_mock ?? health.provider === "mock" : null };
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
  const [slowStart, setSlowStart] = useState(false); // a sleeping hosted backend can take a minute to answer
  useEffect(() => {
    if (state.mode !== "loading") return;
    const id = window.setTimeout(() => setSlowStart(true), 4000);
    return () => window.clearTimeout(id);
  }, [state.mode]);
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
  const [aboutOpen, setAboutOpen] = useState(false);
  const [typing, setTyping] = useState(false); // the message box has focus: on a short screen show only the essentials
  const aboutBtnRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!announcement) return;
    const id = window.setTimeout(() => setAnnouncement(""), 6000); // read once, then gone from the page
    return () => window.clearTimeout(id);
  }, [announcement]);
  const lastAssistantRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const inputId = useId();
  const statusId = useId();
  const bannerId = useId();
  const whoHintId = useId();
  const aboutId = useId();

  useEffect(() => {
    let cancelled = false;
    boot().then((b) => {
      if (cancelled) return;
      setState(b);
      // Live mode: a reload in the same tab restores the conversation (sessionStorage only, never the server).
      const saved = b.mode === "live" ? loadSession<SavedSession>() : null;
      const who = saved && b.mode === "live" ? b.identities.find((i) => i.id === saved.identityId) : undefined;
      if (saved?.v === 1 && who && saved.messages.length) {
        counter = Math.max(counter, ...saved.messages.map((m) => Number(m.id.slice(1)) || 0));
        setIdentity(who);
        setSessionId(saved.sessionId);
        setMessages(saved.messages.filter((m) => !m.error).map((m) => ({ ...m, restored: true })));
        setTurns(saved.turns);
        return;
      }
      setMessages([{ id: mid(), role: "assistant", text: greeting(GUEST), lang: "en" }]); // AI disclosure (I-01 draft)
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reset = useCallback((next: Identity) => {
    clearSession();
    setIdentity(next);
    setSessionId(newSessionId());
    setMessages([{ id: mid(), role: "assistant", text: greeting(next), lang: next.lang }]);
    setTurns([]);
    setJourney(null);
    setStep(0);
    setDraft("");
  }, []);

  // Scrolling after each message. First screen: stay at the top (brand, sign-in, the "not a person" greeting).
  // A new assistant message taller than the space above the composer (a long reply, a card to check before
  // sending) is shown from its first line; anything else scrolls to the end so it sits just above the composer.
  const prevCount = useRef(0);
  useEffect(() => {
    const n = messages.length;
    const grew = n > prevCount.current;
    prevCount.current = n;
    if (n <= 1 && !busy) return;
    const el = document.scrollingElement ?? document.documentElement;
    requestAnimationFrame(() => {
      const nodes = document.querySelectorAll<HTMLElement>("[data-msg]");
      const last = nodes[nodes.length - 1];
      const room = (window.visualViewport?.height ?? window.innerHeight) - (composerRef.current?.offsetHeight ?? 0) - 24;
      if (!busy && grew && last?.dataset.msg === "assistant" && last.offsetHeight > room && last.scrollIntoView) {
        last.scrollIntoView({ block: "start" });
      } else {
        el.scrollTo?.({ top: el.scrollHeight });
      }
    });
  }, [messages, busy]);

  // iOS Safari (and any browser that only shrinks the visual viewport) covers the bottom of the page with the
  // keyboard: lift the sticky composer by the keyboard's height, and mark short screens so it shows only the input.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const root = document.documentElement;
    const el = document.scrollingElement ?? document.documentElement;
    let atEnd = true;
    const onScroll = () => {
      atEnd = el.scrollHeight - (el.scrollTop + (vv.height || window.innerHeight)) < 48;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    let lastH = vv.height;
    const apply = () => {
      const grew = vv.height > lastH + 40; // the keyboard closed (or the phone rotated): stay at the end if you were there
      lastH = vv.height;
      if (grew && atEnd) requestAnimationFrame(() => el.scrollTo?.({ top: el.scrollHeight }));
      const zoomed = Math.abs(vv.scale - 1) > 0.01; // pinch-zoom also shrinks the visual viewport: not a keyboard
      const kb = zoomed ? 0 : Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
      root.style.setProperty("--mk-kb", `${kb}px`);
      root.toggleAttribute("data-mk-short", vv.height < 480);
    };
    vv.addEventListener("resize", apply);
    vv.addEventListener("scroll", apply);
    apply();
    return () => {
      vv.removeEventListener("resize", apply);
      vv.removeEventListener("scroll", apply);
      window.removeEventListener("scroll", onScroll);
      root.style.removeProperty("--mk-kb");
      root.removeAttribute("data-mk-short");
    };
  }, []);

  // Focused controls must never hide under the sticky composer (WCAG 2.4.11): pad scrolling by its real height.
  useEffect(() => {
    const el = composerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const root = document.documentElement;
    const apply = () => {
      const sticky = getComputedStyle(el).position === "sticky";
      root.style.scrollPaddingBottom = sticky ? `${el.offsetHeight + 8}px` : "";
    };
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    window.addEventListener("resize", apply);
    apply();
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", apply);
      root.style.scrollPaddingBottom = "";
    };
  }, [state.mode]);

  useEffect(() => {
    if (turns.length) saveConversation({ persona_id: identity.id, session_id: sessionId, saved_at: new Date().toISOString(), turns });
  }, [turns, identity.id, sessionId]);

  useEffect(() => {
    if (state.mode === "live" && messages.length > 1) {
      saveSession<SavedSession>({ v: 1, identityId: identity.id, sessionId, messages: messages.filter((m) => !m.error), turns });
    }
  }, [state.mode, messages, turns, identity.id, sessionId]);

  const preview = state.mode === "preview" ? state : null;
  const lastResponse = [...messages].reverse().find((m) => m.response)?.response;
  const lang: Lang = lastResponse?.language ?? identity.lang;
  const t = UI[lang];
  const cardStates = useMemo(() => cardStatesFor(messages), [messages]);

  // ---- suggestions -------------------------------------------------------------------------------------------
  const nextStep = journey ? journey.steps[step] : undefined;
  let chips: { label: string; send: string }[] = [];
  let tasks: { label: string; send: string }[] = []; // first screen: larger task rows under the greeting
  if (preview) {
    if (!journey) {
      tasks = preview.journeys
        .filter((j) => j.persona_id === identity.id)
        .flatMap((j) => (j.steps[0]?.kind === "chat" ? [{ label: j.title, send: j.steps[0].message }] : []));
    } else if (nextStep?.kind === "chat") {
      chips = [{ label: nextStep.message, send: nextStep.message }];
    }
  } else if (messages.length <= 1) {
    tasks = starters(identity).map((s) => ({ label: s, send: s }));
  } else if (!busy) {
    const last = messages[messages.length - 1];
    if (last.response && lastResponse?.suggested_replies?.length) {
      chips = lastResponse.suggested_replies.map((s) => ({ label: s, send: s }));
    } else if (last.result?.ok) {
      chips = t.afterSend.map((s) => ({ label: s, send: s })); // next steps after Send
    } else if (last.cleared) {
      chips = t.afterDecline.map((s) => ({ label: s, send: s })); // and after Don't send
    }
  }
  // the "Talk to a person" button is always under the composer, so it is never repeated as a chip
  chips = chips.filter((c) => c.label.toLowerCase() !== t.talkToPerson.toLowerCase()).slice(0, 4);
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
    // A retry replaces its failed copy and the error box (no stale "Not sent" bubble above the one that went through).
    setMessages((m) => [...m.filter((x) => !x.error && !(x.failed && x.text === message)), { id: userId, role: "user", text: message, lang }]);
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
      const why = e instanceof ApiError && e.code === "BACKEND_UNREACHABLE" ? t.unreachable : t.serverError;
      const text = `${why} ${t.tryAgain}`;
      setMessages((m) => [
        ...m.map((x) => (x.id === userId ? { ...x, failed: true } : x)),
        { id: mid(), role: "assistant", text, lang, error: { retry: message } },
      ]);
      setAnnouncement(text);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus()); // keep typing where you were (keyboard stays open)
    }
  }

  function announce(r: ChatResponse) {
    if (r.safety_notice) return setAnnouncement(""); // the role=alert block announces itself, once
    const s = UI[r.language ?? "en"];
    const a = r.action;
    const card = a ? ` ${a.title}: ${a.stage === "submitted" ? (a.record?.status_label ?? "") : s.stage[a.stage]}.` : "";
    setAnnouncement(`${s.assistantSaid} ${r.care_note ? `${r.care_note} ` : ""}${r.reply}${card}`);
  }

  async function confirmAction(kind: ActionKind) {
    if (busy) return;
    if (preview) {
      if (!journey || nextStep?.kind !== "confirm" || nextStep.action_kind !== kind) return;
      const result = nextStep.result;
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result, lang }]);
      setAnnouncement(""); // focus moves to the new message, which is read once
      setTurns((t) => [...t, { confirm: kind, result }]);
      setStep(step + 1);
      requestAnimationFrame(() => lastAssistantRef.current?.focus());
      return;
    }
    setBusy(true);
    try {
      const result = await api.confirmAction(sessionId, identity.id || null, kind);
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: result.message, result, lang }]);
      setAnnouncement("");
      setTurns((t) => [...t, { confirm: kind, result }]);
    } catch {
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: t.notSaved, lang }]);
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
      const text = result.ok ? t.declinedMsg : result.message;
      setMessages((m) => [...m, { id: mid(), role: "assistant", text, lang, cleared: result.ok ? kind : undefined }]);
      setAnnouncement("");
    } catch {
      setMessages((m) => [...m, { id: mid(), role: "assistant", text: t.cancelFailed, lang }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => lastAssistantRef.current?.focus()); // the button that had focus is gone
    }
  }

  function changeIdentity(id: string) {
    if (state.mode !== "live" && state.mode !== "preview") return;
    const next = state.identities.find((i) => i.id === id) ?? GUEST;
    if (next.id === identity.id) return;
    const hasTalked = messages.some((m) => m.role === "user");
    if (hasTalked && !window.confirm(t.signInConfirm)) return; // the select is controlled, so it snaps back
    reset(next);
  }

  // ---- render ------------------------------------------------------------------------------------------------
  if (state.mode === "loading") {
    return (
      <Frame>
        <p role="status" className="px-4 py-10 text-center text-mk-muted">
          {slowStart ? "Waking the assistant up. This can take up to a minute the first time." : "Starting the assistant…"}
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
  const onFileLabel = identity.kind === "resident" ? undefined : t.fromProfile;

  const talked = messages.some((m) => m.role === "user");
  // Plain reply-source line for "About this demo": from the last reply if there is one, else from the backend.
  const replySource = !lastResponse
    ? state.mode === "live" && state.mock !== null ? (state.mock ? t.replyMock : t.replyAi) : preview ? t.replyMock : ""
    : lastResponse.is_mock ? t.replyMock : lastResponse.reply_source === "model" ? t.replyAi : "";

  return (
    <Frame
      demoStrip={
        <div className="border-b border-mk-line bg-mk-surface [@media(max-height:480px)]:static">
          <div className="mx-auto flex w-full max-w-2xl items-center gap-2 px-[max(1rem,env(safe-area-inset-left))] py-1.5 sm:px-0">
            <label htmlFor={`${inputId}-who`} className="shrink-0 text-sm font-medium text-mk-muted">
              {t.demoSignIn}
            </label>
            <select
              id={`${inputId}-who`}
              value={identity.id}
              aria-describedby={whoHintId}
              onChange={(e) => changeIdentity(e.target.value)}
              className="mk-focus h-11 min-w-0 flex-1 rounded-md border border-mk-line-strong bg-mk-surface px-2.5 text-base sm:max-w-80"
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
            <span id={whoHintId} className="sr-only" lang={lang}>
              {t.signInHint}
            </span>
            <button
              ref={aboutBtnRef}
              type="button"
              aria-expanded={aboutOpen}
              aria-controls={aboutId}
              onClick={() => setAboutOpen((v) => !v)}
              className="mk-focus ml-auto inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-md text-mk-brand-hover hover:bg-mk-brand-soft aria-expanded:bg-mk-brand-soft sm:px-3"
            >
              <Info aria-hidden className="size-5" />
              <span className="sr-only sm:not-sr-only sm:font-medium" lang={lang}>{t.demoTitle}</span>
            </button>
          </div>
          {aboutOpen && (
            <section
              id={aboutId}
              aria-label={t.demoTitle}
              lang={lang}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setAboutOpen(false);
                  aboutBtnRef.current?.focus();
                }
              }}
              className="mx-auto w-full max-w-2xl px-[max(1rem,env(safe-area-inset-left))] pb-3 sm:px-0"
              data-testid="about-demo"
            >
              <div className="rounded-lg bg-mk-paper p-4">
                <p className="font-heading text-base font-semibold">{t.demoTitle}</p>
                <p className="mt-1 text-sm text-mk-muted">
                  {t.prototype} {replySource} {t.signInHint}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-4">
                  <Link href="/staff" prefetch={false} className="mk-focus inline-flex min-h-11 items-center font-medium text-mk-brand-hover underline underline-offset-2">
                    {t.staffLink}
                  </Link>
                  <button
                    type="button"
                    onClick={() => {
                      setAboutOpen(false);
                      aboutBtnRef.current?.focus();
                    }}
                    className="mk-focus inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-mk-muted hover:text-mk-ink"
                  >
                    <X aria-hidden className="size-4" /> {t.demoClose}
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      }
    >
      {preview && (
        <p id={bannerId} className="mx-4 mt-3 flex max-w-2xl gap-2 rounded-lg border border-mk-line bg-mk-surface px-4 py-2.5 text-sm text-mk-muted sm:mx-auto sm:w-full">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            {LIVE_BACKEND_CONFIGURED ? (
              <>
                The live assistant can&apos;t be reached right now, so this page is replaying recorded conversations
                (made-up data, no live AI). Typing is turned off.{" "}
                <button type="button" onClick={() => window.location.reload()} className="mk-focus underline underline-offset-2">
                  Try again
                </button>
              </>
            ) : (
              <>
                Preview link: this page replays real conversations recorded from the prototype, with made-up data and no
                live AI. Typing is turned off here. Tap a suggestion to continue.
              </>
            )}
          </span>
        </p>
      )}

      <section aria-labelledby={`${inputId}-conv`} className="mx-auto w-full max-w-2xl flex-1 px-[max(1rem,env(safe-area-inset-left))] py-5 sm:px-0">
        <h2 id={`${inputId}-conv`} className="sr-only" lang={lang}>
          {t.conversation}
        </h2>
        <div className="space-y-5">
          {messages.map((m, i) => (
            <div key={m.id} data-msg={m.role} className="scroll-mt-3 sm:scroll-mt-36">
            <Message
              msg={m}
              t={UI[m.lang ?? lang]}
              speaker={m.role === "assistant" && (i === 0 || messages[i - 1].role === "user")}
              focusRef={m === lastAssistant ? lastAssistantRef : undefined}
              cardState={cardStates[i] ?? null}
              busy={busy}
              preview={!!preview}
              onFileLabel={onFileLabel}
              nextConfirmKind={nextStep?.kind === "confirm" ? nextStep.action_kind : null}
              onConfirm={confirmAction}
              onCancel={cancelAction}
              onRetry={send}
            />
            </div>
          ))}
          {tasks.length > 0 && (
            <nav aria-label={t.howCanIHelp} lang={lang} className="pl-10 sm:max-w-md">
              <ul className="overflow-hidden rounded-xl border border-mk-line bg-mk-surface shadow-[0_1px_2px_rgb(28_37_48/0.06)]">
                {tasks.map((c) => (
                  <li key={c.label} className="border-b border-mk-line last:border-b-0">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => send(c.send)}
                      className="mk-focus flex min-h-12 w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-base text-mk-ink hover:bg-mk-brand-soft active:bg-mk-brand-soft disabled:opacity-60"
                    >
                      <span>{c.label}</span>
                      <ChevronRight aria-hidden className="size-5 shrink-0 text-mk-brand" />
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
          {busy && (
            <p className="pl-10 text-mk-muted" aria-hidden>
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
        <p className="sr-only" aria-live="polite" lang={lang}>
          {busy ? t.replying : announcement}
        </p>
      </section>

      {/* Sticky composer; on short screens (landscape phone, high zoom) it scrolls with the page instead. */}
      <div
        ref={composerRef}
        style={{ bottom: "var(--mk-kb, 0px)" }}
        data-typing={typing || undefined}
        className="group/composer sticky bottom-0 z-10 border-t border-mk-line bg-mk-paper"
      >
        <div className="mx-auto w-full max-w-2xl px-[max(1rem,env(safe-area-inset-left))] pt-2.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-0 [@media(max-height:480px)]:pt-1.5 [html[data-mk-short]_&]:pt-1.5">
          {chips.length > 0 && (
            <div
              role="group"
              aria-label={t.suggestions}
              lang={lang}
              className="mb-2 flex flex-wrap gap-2 py-1 sm:px-1 [@media(max-height:480px)]:group-data-typing/composer:hidden [html[data-mk-short]_&]:group-data-typing/composer:hidden [@media(max-height:480px)]:flex-nowrap [@media(max-height:480px)]:overflow-x-auto [html[data-mk-short]_&]:flex-nowrap [html[data-mk-short]_&]:overflow-x-auto"
            >
              {chips.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  disabled={busy}
                  onClick={() => send(c.send)}
                  className="mk-focus min-h-11 shrink-0 rounded-full border border-mk-brand bg-mk-surface px-4 py-2 text-left text-base font-medium text-mk-brand-hover hover:bg-mk-brand-soft active:bg-mk-brand-soft disabled:opacity-60"
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(draft);
            }}
            className="flex items-end gap-2"
          >
            <label htmlFor={inputId} className="sr-only" lang={lang}>
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
              onFocus={() => setTyping(true)}
              onBlur={() => setTyping(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
              placeholder={preview ? t.previewPlaceholder : t.placeholder}
              maxLength={4000}
              className="max-h-40 min-h-12 flex-1 resize-none rounded-xl border border-mk-line-strong bg-mk-surface px-4 py-3 text-base [field-sizing:content] placeholder:text-mk-muted focus-visible:border-mk-brand focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-mk-focus disabled:bg-mk-draft-soft [@media(max-height:480px)]:max-h-24"
            />
            <button
              type="submit"
              disabled={!!preview || busy || !draft.trim()}
              className="mk-focus inline-flex size-12 shrink-0 items-center justify-center rounded-xl bg-mk-brand text-white hover:bg-mk-brand-hover active:bg-mk-brand-strong disabled:border disabled:border-mk-line disabled:bg-mk-draft-soft disabled:text-mk-line-strong"
            >
              <ArrowUp aria-hidden className="size-5" />
              <span className="sr-only" lang={lang}>
                {t.send}
              </span>
            </button>
          </form>
          {/* One row, always visible: a person, start over, and a tap-to-call emergency number. */}
          <div className="mt-2 flex items-center gap-x-1">
            {!preview && (
              <button
                type="button"
                disabled={busy}
                onClick={() => send(t.talkToPerson)}
                className="mk-focus inline-flex min-h-11 items-center gap-2 rounded-md px-1.5 text-base font-medium text-mk-brand-hover underline underline-offset-2 disabled:opacity-60"
                lang={lang}
              >
                <UserRound aria-hidden className="size-4 shrink-0" /> {t.talkToPerson}
              </button>
            )}
            {(talked || journeyDone) && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  if (journeyDone || window.confirm(t.newChatConfirm)) reset(identity);
                }}
                className="mk-focus inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-md px-1.5 text-base text-mk-muted hover:text-mk-ink disabled:opacity-60"
                lang={lang}
              >
                <RotateCcw aria-hidden className="size-4 shrink-0" />
                <span className="max-[374px]:sr-only">{t.newChat}</span>
              </button>
            )}
            <a
              href="tel:911"
              aria-label={t.emergencyCall}
              className="mk-focus ml-auto inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-md px-2 font-semibold text-mk-danger hover:bg-mk-danger-soft"
              lang={lang}
            >
              <Phone aria-hidden className="size-4" /> 911
            </a>
          </div>
          <p id={statusId} className="pb-0.5 text-sm text-mk-muted [@media(max-height:480px)]:sr-only [html[data-mk-short]_&]:sr-only" lang={lang}>
            {t.prototype} {t.emergencyLead} {t.call911}.
          </p>
        </div>
      </div>
    </Frame>
  );
}

/** Which cards stay visible: "current" (act on it / saved record), "declined" (Not sent), or null (hidden). */
function cardStatesFor(messages: Msg[]): (CardState | null)[] {
  const out: (CardState | null)[] = [];
  const actionOf = (m: Msg) => m.result?.action ?? m.response?.action ?? null;
  for (let i = 0; i < messages.length; i++) {
    const a = actionOf(messages[i]);
    if (!a) continue;
    if (a.stage === "submitted") {
      out[i] = "current";
      continue;
    }
    let state: CardState | null = "current";
    for (let j = i + 1; j < messages.length; j++) {
      const later = messages[j];
      if (later.cleared === a.kind || later.response?.action_cleared === a.kind) {
        // Keep the latest "Not sent" card only; a newer card of the same kind replaces it.
        const newer = messages.slice(j + 1).some((x) => actionOf(x)?.kind === a.kind);
        state = a.stage === "collecting" || newer ? null : "declined";
        break;
      }
      const la = actionOf(later);
      if (la) {
        // Same kind: the newer version replaces this one. Another kind: the backend dropped this draft.
        state = la.kind === a.kind || a.stage === "collecting" ? null : "declined";
        break;
      }
    }
    out[i] = state;
  }
  return out;
}

function Frame({ children, demoStrip }: { children: React.ReactNode; demoStrip?: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <div className="sm:sticky sm:top-0 sm:z-20 [@media(max-height:480px)]:static">
        <header className="mk-band bg-mk-brand text-white">
          <div className="mx-auto flex w-full max-w-2xl items-center px-[max(1rem,env(safe-area-inset-left))] pt-[max(0.625rem,env(safe-area-inset-top))] pb-2.5 sm:px-0">
            <h1 className="flex min-w-0 flex-wrap items-baseline gap-x-3 leading-tight">
              <span className="font-heading text-[1.4rem] font-semibold tracking-[-0.01em]">McKinley</span>
              <span className="font-heading text-base font-medium">Resident and leasing help</span>
            </h1>
          </div>
        </header>
        {demoStrip}
      </div>
      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}

const CALL_KINDS_WITHOUT_MAINTENANCE = new Set(["self_harm", "medical", "personal_safety"]);

function Speaker({ t }: { t: UIStrings }) {
  return (
    <p aria-hidden className="mb-1 flex items-center gap-3 font-heading text-[0.95rem] font-semibold text-mk-ink">
      <span className="inline-flex size-7 items-center justify-center rounded-full bg-mk-brand font-heading text-sm font-semibold text-white">M</span>
      {t.assistantName}
    </p>
  );
}

function Message({
  msg,
  t,
  speaker,
  focusRef,
  cardState,
  busy,
  preview,
  onFileLabel,
  nextConfirmKind,
  onConfirm,
  onCancel,
  onRetry,
}: {
  msg: Msg;
  t: UIStrings;
  speaker: boolean;
  focusRef?: React.Ref<HTMLDivElement>;
  cardState: CardState | null;
  busy: boolean;
  preview: boolean;
  onFileLabel?: string;
  nextConfirmKind: ActionKind | null;
  onConfirm: (k: ActionKind) => void;
  onCancel: (k: ActionKind) => void;
  onRetry: (text: string) => void;
}) {
  if (msg.role === "user") {
    return (
      <div className="flex flex-col items-end" lang={msg.lang}>
        <p className={cn("max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 break-words whitespace-pre-wrap",
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
  const action: ProposedAction | null = msg.result?.action ?? r?.action ?? null;
  const emergency = !!r?.safety_notice;
  const kind = r?.emergency_kind ?? null;
  const templateCoversNotice = emergency && /\b(911|988)\b/.test(msg.text);

  if (msg.error) {
    return (
      <div ref={focusRef} tabIndex={-1} lang={msg.lang} className="mk-focus max-w-[95%] rounded-lg border border-mk-attention/40 bg-mk-attention-soft p-4 outline-none">
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
    <div ref={focusRef} tabIndex={-1} lang={msg.lang} role="article" aria-label={t.assistantMessage} className="mk-focus max-w-[95%] rounded-md outline-none">
      {speaker && <Speaker t={t} />}
      <div className="pl-10">
        <span className="sr-only">{t.assistantSaid} </span>
        {emergency && (
          <div role={msg.restored ? undefined : "alert"} className="mb-2 rounded-lg border-2 border-mk-danger bg-mk-danger-soft p-4">
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
                <>
                  <a href="tel:911" className="mk-focus inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-mk-danger px-5 text-lg font-bold text-white">
                    <Phone aria-hidden className="size-5" /> {kind === "gas" || kind === "co" ? t.gasCall : t.call911}
                  </a>
                  {/988/.test(r?.safety_notice ?? "") && (
                    <a href="tel:988" className="mk-focus inline-flex min-h-12 items-center justify-center gap-2 rounded-md border-2 border-mk-danger bg-mk-surface px-5 text-lg font-bold text-mk-danger">
                      <Phone aria-hidden className="size-5" /> {t.call988}
                    </a>
                  )}
                </>
              )}
            </div>
            {kind && !CALL_KINDS_WITHOUT_MAINTENANCE.has(kind) && <p className="mt-2 text-sm text-mk-muted">{t.noEmergencyLine}</p>}
          </div>
        )}
        {!emergency && r?.care_note && <CareNote kind={r.care_kind ?? "unwell"} note={r.care_note} t={t} />}
        {!templateCoversNotice && <p className="text-base leading-relaxed break-words whitespace-pre-wrap">{msg.text}</p>}
        {r?.status_items && r.status_items.length > 0 && <StatusList items={r.status_items} t={t} />}
        {action && cardState && (action.stage === "collecting" ? (
          cardState === "current" && <ProgressHint action={action} t={t} />
        ) : (
          <ActionCard
            action={action}
            state={cardState}
            t={t}
            busy={busy}
            onFileLabel={onFileLabel}
            confirmAvailable={!preview || nextConfirmKind === action.kind}
            cancelAvailable={!preview}
            onConfirm={() => onConfirm(action.kind)}
            onCancel={() => onCancel(action.kind)}
          />
        ))}
      </div>
    </div>
  );
}

/** Calm, non-alarming line for possible distress or feeling unwell. Never the red emergency alert. */
function CareNote({ kind, note, t }: { kind: "distress" | "unwell" | "danger" | "info"; note: string; t: UIStrings }) {
  if (kind === "info") {
    // A hazard asked about hypothetically or in the past: the approved steps, calmly, no call buttons.
    return (
      <div className="mb-2 rounded-lg border border-mk-line-strong bg-mk-surface p-3" data-testid="care-note">
        <p className="text-sm font-semibold text-mk-muted">{t.safetyInfo}</p>
        <p className="mt-1 flex items-start gap-2 text-base text-mk-ink">
          <Info aria-hidden className="mt-1 size-4 shrink-0 text-mk-muted" />
          <span>{note.replace(/^(If that happens|Si eso pasa): /, "")}</span>
        </p>
      </div>
    );
  }
  const link = "mk-focus inline-flex min-h-11 items-center gap-2 rounded-md border border-mk-sent/40 bg-mk-surface px-3 font-semibold text-mk-sent";
  return (
    <div className="mb-2 rounded-lg border border-mk-sent/30 bg-mk-sent-soft p-3" data-testid="care-note">
      <p className="flex items-start gap-2 text-base text-mk-ink">
        <Info aria-hidden className="mt-1 size-4 shrink-0 text-mk-sent" />
        <span>{note}</span>
      </p>
      <div className="mt-2 flex flex-wrap gap-2 pl-6">
        {kind === "distress" ? (
          <>
            <a href="tel:988" className={link}>
              <Phone aria-hidden className="size-4" /> {t.call988}
            </a>
            <a href="sms:988" className={link}>
              <MessageSquareText aria-hidden className="size-4" /> {t.text988}
            </a>
          </>
        ) : (
          <a href="tel:911" className={link}>
            <Phone aria-hidden className="size-4" /> {t.call911}
          </a>
        )}
      </div>
    </div>
  );
}

const VISIBLE_RECENT = 3;

/** Urgent and follow-up-owed first, then the most recent; the rest behind "Show all". */
export function sortStatusItems(items: StatusItem[]): StatusItem[] {
  const rank = (s: StatusItem) => ({ urgent: 0, owed: 1 } as Record<string, number>)[statusTone(s.status)] ?? 2;
  return [...items].sort((a, b) => rank(a) - rank(b) || (b.opened ?? "").localeCompare(a.opened ?? ""));
}

function StatusList({ items, t }: { items: StatusItem[]; t: UIStrings }) {
  const [all, setAll] = useState(false);
  const listId = useId();
  const sorted = sortStatusItems(items);
  const pinned = Math.min(3, sorted.filter((s) => statusTone(s.status) !== "submitted").length); // never a wall of alerts
  const limit = pinned + VISIBLE_RECENT;
  const shown = all ? sorted : sorted.slice(0, limit);
  return (
    <div className="mt-3">
      <ul id={listId} aria-label={t.openRequests} className="divide-y divide-mk-line rounded-xl border border-mk-line bg-mk-surface">
        {shown.map((s) => {
          const tone = statusTone(s.status);
          return (
            <li key={s.reference} className="flex flex-col gap-1 px-4 py-2.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
              <div className="min-w-0">
                <p className="font-semibold break-words">{s.title.split(" Also: ")[0]}</p>
                <p className="text-sm text-mk-muted">
                  {t.reference} <span className="tabular-nums">{s.reference}</span>
                  {s.opened ? `, ${t.opened} ${formatDate(s.opened, t.lang)}` : ""}
                </p>
              </div>
              <StatusPill tone={tone} className="self-start">
                {tone === "owed" ? t.followUpOwed : s.status.split(";")[0]}
              </StatusPill>
            </li>
          );
        })}
      </ul>
      {sorted.length > limit && (
        <button
          type="button"
          aria-expanded={all}
          aria-controls={listId}
          onClick={() => setAll((v) => !v)}
          className="mk-focus mt-2 inline-flex min-h-11 items-center rounded-md px-2 text-mk-brand-hover underline underline-offset-2"
        >
          {all ? t.showFewer : t.showAll(sorted.length)}
        </button>
      )}
    </div>
  );
}
