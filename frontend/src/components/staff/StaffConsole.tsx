"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  DemoSnapshot,
  Health,
  PrototypeRecord,
  StaffConversation,
  StaffConversationDetail,
} from "@/lib/types";
import { StatusPill, statusTone } from "@/components/customer/StatusPill";

interface Boot {
  live: boolean;
  health: Health | null;
  snapshot: DemoSnapshot | null;
}

async function boot(): Promise<Boot> {
  const snapshot = await loadDemoSnapshot().catch(() => null);
  try {
    const health = await api.health();
    return { live: true, health, snapshot };
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "BACKEND_UNREACHABLE" || !snapshot) throw e;
    return { live: false, health: null, snapshot };
  }
}

/** "Needs action" markers on live conversations (from the safety/gate log; never from message text). */
const NEEDS_TEXT: Record<string, string> = {
  urgent: "Urgent: safety alert shown",
  wellbeing: "Check in: wellbeing line shown",
  asked_for_person: "Asked for a person",
  safety_check_failed: "Safety classifier failed",
};
const NEEDS_TONE: Record<string, string> = {
  urgent: "bg-mk-danger-soft text-mk-danger",
  wellbeing: "bg-mk-sent-soft text-mk-sent",
  asked_for_person: "bg-mk-attention-soft text-mk-attention",
  safety_check_failed: "bg-mk-draft-soft text-mk-draft",
};

const TEAM: Record<string, string> = {
  emergency_maintenance: "Emergency maintenance",
  maintenance: "Maintenance",
  leasing: "Leasing",
  accounting: "Accounting",
  management: "Property management",
};

function teamLabel(t: string): string {
  return TEAM[t] ?? t.replaceAll("_", " ");
}

export function StaffConsole() {
  const [state, setState] = useState<Boot | null>(null);
  // On a hosted backend the staff routes refuse browsers (no staff sign-in yet): use the recorded demo there.
  const staffTools = Boolean(state?.live && state.health?.app_env !== "hosted");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    boot()
      .then(setState)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "The console could not load."));
  }, []);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mk-band bg-mk-brand-strong text-white">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-[max(1rem,env(safe-area-inset-left))] pt-[max(0.625rem,env(safe-area-inset-top))] pb-2.5 md:px-6">
          <h1 className="flex min-w-0 flex-wrap items-center gap-x-3 leading-tight">
            <span className="font-heading text-[1.4rem] font-semibold tracking-[-0.01em]">McKinley</span>
            <span className="rounded-md bg-white px-2 py-0.5 font-heading text-sm font-semibold text-mk-brand-strong">Staff</span>
            <span className="font-heading text-base font-medium">Staff queue</span>
          </h1>
          <Link href="/" prefetch={false} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-white/80 px-4 font-medium text-white hover:bg-white/10">
            Open the customer view
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-4 px-[max(1rem,env(safe-area-inset-left))] py-4 md:px-6">
        <p className="text-mk-muted">Requests customers sent from the assistant, and recent conversations. Made-up data only.</p>
        {error && (
          <p role="alert" className="rounded-md border border-mk-danger bg-mk-danger-soft p-3 text-mk-danger">
            Backend unavailable: {error}
          </p>
        )}
        {state && !state.live && state.snapshot && (
          <p role="note" className="flex gap-2 rounded-md border border-mk-line bg-mk-surface px-4 py-3 text-mk-muted">
            <Info aria-hidden className="mt-1 size-4 shrink-0" />
            <span>
              Recorded demo: no backend runs behind this link. Everything here was recorded on{" "}
              {state.snapshot.generated_at.slice(0, 10)} with a mock model (fixed templates, not an AI). Saved requests
              stay in the prototype.
            </span>
          </p>
        )}
        {state?.live && !staffTools && (
          <p role="note" data-testid="staff-locked" className="flex gap-2 rounded-md border border-mk-line bg-mk-surface px-4 py-3 text-mk-muted">
            <Info aria-hidden className="mt-1 size-4 shrink-0" />
            <span>
              Staff tools are locked on the shared site until real staff sign-in exists. Saved requests and live
              conversations below show the recorded demo, not this backend&apos;s data.
            </span>
          </p>
        )}
        {!state && !error && <p role="status">Loading…</p>}
        {state && (
          <Tabs defaultValue="records">
            {/* One row on every width; on phones it scrolls sideways. Selected = 3px blue bar. */}
            <div className="-mx-4 overflow-x-auto overscroll-x-contain border-b border-mk-line px-4 [scrollbar-width:thin] md:mx-0 md:px-1">
              <TabsList variant="line" className="h-auto! w-max flex-nowrap justify-start gap-0 p-0">
                {[["records", "Saved requests"], ["live", "Live conversations"]].map(([v, label]) => (
                  <TabsTrigger
                    key={v}
                    value={v}
                    className="mk-focus min-h-12 flex-none px-3 font-heading text-base font-medium text-mk-muted after:h-[3px]! after:bg-mk-brand hover:text-mk-ink focus-visible:border-transparent focus-visible:ring-0 data-active:font-semibold data-active:text-mk-ink"
                  >
                    {label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            <TabsContent value="records">
              <Records live={staffTools} snapshot={state.snapshot} />
            </TabsContent>
            <TabsContent value="live">
              <LiveConversations live={staffTools} />
            </TabsContent>
          </Tabs>
        )}
      </main>
    </div>
  );
}

// ---- prototype records: staff work queue ----------------------------------------------------------------

const KIND_LABEL: Record<string, string> = { maintenance_request: "Repair request", tour_request: "Tour request", staff_handoff: "Note for the office" };
const PRIORITY_RANK: Record<string, number> = { urgent: 0, high: 1, normal: 2 };
const MAIN_KEYS = ["issue", "topic", "what_you_said", "request", "requests"];
const DETAIL_KEYS = ["location", "entry", "area", "days", "time", "move_in", "beds", "contact", "priority_note"];

function field(r: PrototypeRecord, key: string): string | null {
  return r.fields.find((f) => f.key === key)?.value ?? null;
}

function recordPriority(r: PrototypeRecord): string {
  return r.status === "urgent_queued" ? "urgent" : (r.priority ?? "normal");
}

function recordHeadline(r: PrototypeRecord): string {
  for (const k of MAIN_KEYS) {
    const v = field(r, k);
    if (v) return v.split(" Also: ")[0];
  }
  if (r.kind === "tour_request") return [field(r, "area"), field(r, "days"), field(r, "time")].filter(Boolean).join(", ") || r.summary;
  return r.fields.find((f) => f.value)?.value ?? r.summary;
}

function recordDetails(r: PrototypeRecord): { label: string; value: string }[] {
  return DETAIL_KEYS.flatMap((k) => {
    const f = r.fields.find((x) => x.key === k && x.value);
    return f ? [{ label: f.label, value: f.value as string }] : [];
  });
}

export function ageLabel(iso: string, now = Date.now()): string {
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (Number.isNaN(mins)) return "";
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function sortQueue(rows: PrototypeRecord[]): PrototypeRecord[] {
  return [...rows].sort(
    (a, b) => (PRIORITY_RANK[recordPriority(a)] ?? 3) - (PRIORITY_RANK[recordPriority(b)] ?? 3) || b.created_at.localeCompare(a.created_at),
  );
}

function RecordStatus({ r }: { r: PrototypeRecord }) {
  return <StatusPill tone={statusTone(r.status_label, recordPriority(r))}>{r.status_label}</StatusPill>;
}

const PAGE = 20;

function Records({ live, snapshot }: { live: boolean; snapshot: DemoSnapshot | null }) {
  const [rows, setRows] = useState<PrototypeRecord[] | null>(live ? null : (snapshot?.prototype_records ?? []));
  const [err, setErr] = useState<string | null>(null);
  const [kind, setKind] = useState("all");
  const [prio, setPrio] = useState("all");
  useEffect(() => {
    if (!live) return;
    api
      .prototypeRecords(100)
      .then(setRows)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : "Could not load records"));
  }, [live]);
  const [pageSize, setPageSize] = useState(PAGE);
  const matching = useMemo(
    () => sortQueue((rows ?? []).filter((r) => (kind === "all" || r.kind === kind) && (prio === "all" || recordPriority(r) === prio))),
    [rows, kind, prio],
  );
  // Sprint 10 (review P1): 20 at a time (the full list was 8,685 px tall on a phone)
  const shown = matching.slice(0, pageSize);
  const select = "mk-focus h-11 rounded-md border border-mk-line-strong bg-mk-surface px-3";

  return (
    <section aria-labelledby="records-h" className="space-y-3">
      <h2 id="records-h" className="text-lg font-semibold">
        Saved requests (prototype store)
      </h2>
      <p className="text-mk-muted">
        Stand-in for Yardi work orders, the CRM and the staff queue. Nothing here reaches a real system and no one is notified.
        {!live && " These were saved while recording the demo conversations."} Urgent first, then high priority, then newest.
      </p>
      {err && <p role="alert">{err}</p>}
      {rows === null && !err && <p role="status">Loading…</p>}
      {rows && rows.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="q-kind" className="text-sm text-mk-muted">Type</label>
            <select id="q-kind" value={kind} onChange={(e) => setKind(e.target.value)} className={select}>
              <option value="all">All types</option>
              {Object.entries(KIND_LABEL).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="q-prio" className="text-sm text-mk-muted">Priority</label>
            <select id="q-prio" value={prio} onChange={(e) => setPrio(e.target.value)} className={select}>
              <option value="all">All priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="normal">Normal</option>
            </select>
          </div>
          <p className="pb-2.5 text-sm text-mk-muted" role="status">
            Showing {shown.length} of {matching.length === rows.length ? rows.length : `${matching.length} matching (${rows.length} in all)`}
          </p>
        </div>
      )}
      {rows && shown.length === 0 && (
        <p className="rounded-md border border-dashed border-mk-line-strong p-4 text-mk-muted">
          {rows.length === 0 ? "No requests saved yet. Requests appear here after someone presses send in the customer view." : "Nothing matches these filters."}
        </p>
      )}
      {shown.length > 0 && (
        <>
          {/* Phones and tablets (below 1024px): stacked cards. */}
          <ul className="space-y-3 lg:hidden" aria-label="Saved requests">
            {shown.map((r) => (
              <li key={r.id} className="rounded-lg border border-mk-line bg-mk-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold tabular-nums">{r.id}</p>
                  <RecordStatus r={r} />
                </div>
                <p className="mt-1 text-sm text-mk-muted">
                  {KIND_LABEL[r.kind] ?? r.kind}
                  {r.team ? `, ${teamLabel(r.team)}` : ""}, {recordPriority(r)} priority, {ageLabel(r.created_at)}
                </p>
                <p className="mt-2 break-words">{recordHeadline(r)}</p>
                <RecordDetails r={r} />
              </li>
            ))}
          </ul>
          {/* Desktop: a table. */}
          <div tabIndex={0} role="region" aria-label="Saved requests table" className="mk-focus hidden overflow-x-auto rounded-lg border border-mk-line bg-mk-surface lg:block">
            <table className="w-full table-fixed text-left">
              <caption className="sr-only">Prototype records, urgent first</caption>
              <colgroup>
                <col className="w-36" />
                <col className="w-60" />
                <col />
                <col className="w-44" />
                <col className="w-24" />
              </colgroup>
              <thead className="border-b border-mk-line text-sm text-mk-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Reference</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 font-medium">Request</th>
                  <th scope="col" className="px-3 py-2 font-medium">Team and priority</th>
                  <th scope="col" className="px-3 py-2 font-medium">Age</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-mk-line align-top">
                {shown.map((r) => (
                  <tr key={r.id}>
                    <th scope="row" className="px-3 py-2.5 font-semibold tabular-nums">
                      {r.id}
                      <span className="block text-sm font-normal text-mk-muted">{KIND_LABEL[r.kind] ?? r.kind}</span>
                    </th>
                    <td className="px-3 py-2.5"><RecordStatus r={r} /></td>
                    <td className="px-3 py-2.5">
                      <p className="break-words">{recordHeadline(r)}</p>
                      <RecordDetails r={r} />
                    </td>
                    <td className="px-3 py-2.5">
                      {r.team ? teamLabel(r.team) : "Not set"}
                      <span className="block text-sm text-mk-muted">{recordPriority(r)} priority, {r.persona_id || "not signed in"}</span>
                    </td>
                    <td className="px-3 py-2.5 text-sm text-mk-muted">{ageLabel(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {matching.length > shown.length && (
            <button
              type="button"
              onClick={() => setPageSize((n) => n + PAGE)}
              className="mk-focus inline-flex min-h-11 items-center rounded-md border border-mk-line-strong bg-mk-surface px-4 font-medium"
            >
              Show {Math.min(PAGE, matching.length - shown.length)} more
            </button>
          )}
        </>
      )}
    </section>
  );
}

function RecordDetails({ r }: { r: PrototypeRecord }) {
  const d = recordDetails(r);
  if (!d.length) return null;
  return (
    <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-sm">
      {d.map((x) => (
        <div key={x.label} className="flex gap-1">
          <dt className="text-mk-muted">{x.label}:</dt>
          <dd className="break-words">{x.value}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---- live conversations (local backend only) -------------------------------------------------------------

function LiveConversations({ live }: { live: boolean }) {
  const [list, setList] = useState<StaffConversation[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const [detail, setDetail] = useState<StaffConversationDetail | null>(null);
  const [detailErr, setDetailErr] = useState<string | null>(null);
  const detailHeadingRef = useRef<HTMLHeadingElement>(null);
  const loadedHash = detail?.session_hash;
  useEffect(() => {
    // phones: move focus to the opened conversation once per selection (not on every re-render)
    if (loadedHash && window.innerWidth < 768) detailHeadingRef.current?.focus();
  }, [loadedHash]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!live) return;
    api
      .staffConversations(30)
      .then((l) => {
        setList(l);
        setErr(null);
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : "Could not load conversations"));
  }, [live, tick]);
  useEffect(() => {
    if (!pick) return;
    let stale = false;
    api
      .staffConversation(pick)
      .then((d) => {
        if (stale) return;
        setDetail(d);
        setDetailErr(null);
      })
      .catch((e: unknown) => {
        if (stale) return;
        setDetail(null);
        setDetailErr(e instanceof ApiError ? e.message : "Could not load this conversation");
      });
    return () => {
      stale = true;
    };
  }, [pick, tick]);

  return (
    <section aria-labelledby="live-h" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="live-h" className="text-lg font-semibold">Live conversations</h2>
        {live && (
          <button type="button" onClick={() => setTick((n) => n + 1)} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-mk-line-strong bg-mk-surface px-4">
            Refresh
          </button>
        )}
      </div>
      <p className="text-mk-muted">Recent conversations on this local backend, with what each one saved. Contact details are redacted; people are made up.</p>
      {!live && (
        <p className="rounded-md border border-dashed border-mk-line-strong p-4 text-mk-muted">
          Live conversations need the local backend. This recorded demo has none; use the Conversation inspector tab instead.
        </p>
      )}
      {err && <p role="alert">{err}</p>}
      {live && list === null && !err && <p role="status">Loading…</p>}
      {list && list.length === 0 && (
        <p className="rounded-md border border-dashed border-mk-line-strong p-4 text-mk-muted">No conversations yet. Talk to the assistant in the customer view, then press Refresh.</p>
      )}
      {list && list.length > 0 && (
        <div className="grid gap-4 md:grid-cols-[20rem_minmax(0,1fr)]">
          <ul aria-label="Recent conversations" className="space-y-2 md:max-h-[70vh] md:overflow-y-auto md:pr-1">
            {list.map((c) => (
              <li key={c.session_hash}>
                <button
                  type="button"
                  aria-pressed={pick === c.session_hash}
                  onClick={() => {
                    if (c.session_hash === pick) return;
                    setDetail(null); // never show the previous conversation under the new selection
                    setDetailErr(null);
                    setPick(c.session_hash);
                  }}
                  className={cn(
                    "mk-focus w-full rounded-lg border bg-mk-surface p-3 text-left hover:bg-mk-paper",
                    pick === c.session_hash ? "border-mk-brand ring-1 ring-mk-brand" : "border-mk-line",
                  )}
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold">{c.persona_id ?? "Not signed in"}</span>
                    <span className="text-sm text-mk-muted">{ageLabel(c.last)}</span>
                  </span>
                  {!!c.needs_action?.length && (
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {c.needs_action.map((f) => (
                        <span key={f} className={cn("rounded-full px-2 py-0.5 text-sm font-medium", NEEDS_TONE[f])}>
                          {NEEDS_TEXT[f]}
                        </span>
                      ))}
                    </span>
                  )}
                  <span className="block text-sm text-mk-muted">
                    {c.messages} message{c.messages === 1 ? "" : "s"}
                    {c.records.length ? `, saved ${c.records.map((r) => r.id).join(", ")}` : ", nothing saved"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0 rounded-lg border border-mk-line bg-mk-surface p-4">
            {!pick && <p className="text-mk-muted">Choose a conversation to read it.</p>}
            {pick && detailErr && <p role="alert">{detailErr}</p>}
            {pick && !detail && !detailErr && <p role="status">Loading…</p>}
            {detail && (
              <article aria-labelledby="live-detail-h">
                <p role="status" className="sr-only">
                  Conversation loaded, {detail.turns.length} messages.
                </p>
                <h3 id="live-detail-h" tabIndex={-1} className="mk-focus font-semibold" ref={detailHeadingRef}>
                  Conversation {detail.session_hash} ({detail.turns[0]?.persona_id === "none" ? "not signed in" : detail.turns[0]?.persona_id})
                </h3>
                {detail.records.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2" aria-label="Saved from this conversation">
                    {detail.records.map((r) => (
                      <li key={r.id}>
                        <StatusPill tone={statusTone(r.status_label, recordPriority(r))}>
                          {r.id}: {r.status_label}
                        </StatusPill>
                      </li>
                    ))}
                  </ul>
                )}
                <ol className="mt-3 space-y-2">
                  {detail.turns.map((tr, i) => (
                    <li key={i} lang={/[áéíóúñ¿¡]/i.test(tr.content) ? "es" : "en"} className={cn("rounded-md px-3 py-2", tr.role === "user" ? "bg-mk-brand-soft" : "bg-mk-paper")}>
                      <p className="text-sm font-semibold text-mk-muted">{tr.role === "user" ? "Person" : "Assistant"}</p>
                      <p className="break-words whitespace-pre-wrap">{tr.content}</p>
                    </li>
                  ))}
                </ol>
              </article>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
