"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatWorkbench } from "@/components/mckinley/ChatWorkbench";
import { EvalDashboard } from "@/components/mckinley/EvalDashboard";
import { Diagnostics } from "@/components/mckinley/ResponseDetails";
import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import { COVERAGE, type CoverageStatus } from "@/lib/coverage";
import { type StoredTurn, loadConversation } from "@/lib/customer";
import { formatCost, formatLatency } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  ChatResponse,
  DemoSnapshot,
  EvalCase,
  GateConfig,
  Health,
  ModelTarget,
  Persona,
  PrototypeRecord,
  StaffConversation,
  StaffConversationDetail,
} from "@/lib/types";
import { AuthButton, AuthForm, NotInvitedNote } from "@/components/auth/AuthPanel";
import { StatusPill, statusTone } from "@/components/customer/StatusPill";
import { UsabilityView } from "@/components/staff/UsabilityView";
import { useAuth } from "@/lib/useAuth";

interface Boot {
  live: boolean;
  health: Health | null;
  personas: Persona[];
  targets: ModelTarget[];
  cases: EvalCase[];
  gateConfig: GateConfig | null;
  snapshot: DemoSnapshot | null;
}

async function boot(): Promise<Boot> {
  const snapshot = await loadDemoSnapshot().catch(() => null);
  try {
    const [health, personas, targets] = await Promise.all([api.health(), api.personas(), api.models()]);
    // staff-only route: refused (403) when this browser isn't local and has no staff token; fall back, don't fail
    const cases = await api.evalCases().catch(() => snapshot?.cases ?? []);
    const gateConfig = await api.gatesConfig().catch(() => null);
    return { live: true, health, personas, targets, cases, gateConfig, snapshot };
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "BACKEND_UNREACHABLE" || !snapshot) throw e;
    return { live: false, health: null, personas: snapshot.personas, targets: [], cases: snapshot.cases, gateConfig: null, snapshot };
  }
}

/** Visual vocabulary for states. Text always states the meaning; colour only reinforces it. */
export type StateTone = "normal" | "pending" | "completed" | "unavailable" | "escalation" | "emergency";
const TONE_CLASS: Record<StateTone, string> = {
  normal: "border-mk-line bg-mk-surface text-mk-ink",
  pending: "border-mk-line-strong bg-mk-draft-soft text-mk-draft",
  completed: "border-mk-done/40 bg-mk-done-soft text-mk-done",
  unavailable: "border-dashed border-mk-line-strong bg-mk-surface text-mk-muted",
  escalation: "border-mk-attention/40 bg-mk-attention-soft text-mk-attention",
  emergency: "border-mk-danger bg-mk-danger-soft text-mk-danger",
};

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

export function StateTag({ tone, children }: { tone: StateTone; children: React.ReactNode }) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-medium", TONE_CLASS[tone])}>{children}</span>;
}

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

function groupCounts(names: string[]): [string, number][] {
  const m = new Map<string, number>();
  for (const n of names) m.set(n, (m.get(n) ?? 0) + 1);
  return [...m.entries()];
}

const COVERAGE_TONE: Record<CoverageStatus, { tone: StateTone; text: string }> = {
  working: { tone: "completed", text: "Working (synthetic data)" },
  partial: { tone: "pending", text: "Partly working" },
  simulated: { tone: "pending", text: "Simulated" },
  unavailable: { tone: "unavailable", text: "Not available" },
};

export function StaffConsole() {
  const [state, setState] = useState<Boot | null>(null);
  const auth = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const authAnchorRef = useRef<HTMLDivElement>(null);
  // On a hosted backend the staff routes refuse anonymous browsers: a signed-in, invited staff member (checked by the
  // backend, not by this page) gets the live tools; everyone else sees the recorded demo there.
  const staffTools = Boolean(state?.live && (state.health?.app_env !== "hosted" || auth.role === "staff"));
  const [error, setError] = useState<string | null>(null);

  // Load once sign-in has settled, and again whenever who is signed in changes (the tools depend on it).
  useEffect(() => {
    if (!auth.ready) return;
    let cancelled = false;
    boot()
      .then((b) => {
        if (cancelled) return;
        setError(null);
        setState(b);
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e.message : "The console could not load."));
    return () => {
      cancelled = true;
    };
  }, [auth.ready, auth.key]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mk-band bg-mk-brand-strong text-white">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-[max(1rem,env(safe-area-inset-left))] pt-[max(0.625rem,env(safe-area-inset-top))] pb-2.5 md:px-6">
          <h1 className="flex min-w-0 flex-wrap items-center gap-x-3 leading-tight">
            <span className="font-heading text-[1.4rem] font-semibold tracking-[-0.01em]">McKinley</span>
            <span className="rounded-md bg-white px-2 py-0.5 font-heading text-sm font-semibold text-mk-brand-strong">Staff</span>
            <span className="font-heading text-base font-medium">Demo console</span>
          </h1>
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <div ref={authAnchorRef} className="min-w-0">
              <AuthButton auth={auth} open={authOpen} onToggle={() => setAuthOpen((v) => !v)} tone="band" />
            </div>
            <Link href="/" prefetch={false} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-white/80 px-4 font-medium text-white hover:bg-white/10">
              Open the customer view
            </Link>
          </div>
        </div>
        {authOpen && auth.status === "signedOut" ? (
          <AuthForm
            auth={auth}
            onClose={() => setAuthOpen(false)}
            onReturnFocus={() => authAnchorRef.current?.querySelector("button")?.focus()}
          />
        ) : null}
        <NotInvitedNote auth={auth} />
      </header>
      <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-4 px-[max(1rem,env(safe-area-inset-left))] py-4 md:px-6">
        <p className="text-mk-muted">What the assistant decided behind each reply, what it saved, and what is still simulated. Made-up data only.</p>
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
              {state.snapshot.generated_at.slice(0, 10)} with a mock model (fixed templates, not an AI) and the rules
              decision gate. Handoffs and saved requests stay in the prototype.
            </span>
          </p>
        )}
        {state?.live && state.health && (
          <div role="note" data-testid="backend-status" className="rounded-lg border border-mk-line bg-mk-surface px-4 py-3">
            <p className="sr-only">Backend status</p>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm lg:grid-cols-4">
              {[
                ["Replies", state.health.is_mock || state.health.provider === "mock"
                  ? "mock responder (fixed templates, not an AI model)"
                  : `${state.health.provider} · ${state.health.model} (live AI model${state.health.provider_ready ? "" : ", NOT configured: missing key"})`],
                ["Database", state.health.database ?? "sqlite"],
                ["Residents from", state.health.resident_source ?? "nowhere (none loaded)"],
                ["Environment", state.health.app_env === "hosted" ? "hosted deployment" : "local"],
              ].map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="font-medium text-mk-muted">{k}</dt>
                  <dd className="break-words text-mk-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {state?.live && !staffTools && (
          <p role="note" data-testid="staff-locked" className="flex gap-2 rounded-md border border-mk-line bg-mk-surface px-4 py-3 text-mk-muted">
            <Info aria-hidden className="mt-1 size-4 shrink-0" />
            <span>
              Staff tools are locked on the shared site until real staff sign-in exists. Saved requests, live
              conversations and evaluations below show the recorded demo, not this backend&apos;s data.
            </span>
          </p>
        )}
        {!state && !error && <p role="status">Loading…</p>}
        {state && (
          <Tabs defaultValue={staffTools ? "records" : "inspector"}>
            {/* One row on every width; on phones it scrolls sideways (the next tab peeks in). Selected = 3px blue bar. */}
            <div className="-mx-4 overflow-x-auto overscroll-x-contain border-b border-mk-line px-4 [scrollbar-width:thin] max-md:[mask-image:linear-gradient(to_right,#000_88%,transparent)] md:mx-0 md:px-1">
              <TabsList variant="line" className="h-auto! w-max flex-nowrap justify-start gap-0 p-0">
                {[
                  ["records", "Saved requests"],
                  ["live", "Live conversations"],
                  ["inspector", "Conversation inspector"],
                  ["coverage", "Workflow coverage"],
                  ["usability", "Usability"],
                  ["compare", "Model comparison"],
                  ["evals", "Evaluation"],
                ].map(([v, label]) => (
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
            <TabsContent value="inspector">
              <Inspector snapshot={state.snapshot} />
            </TabsContent>
            <TabsContent value="records">
              <Records live={staffTools} snapshot={state.snapshot} />
            </TabsContent>
            <TabsContent value="live">
              <LiveConversations live={staffTools} />
            </TabsContent>
            <TabsContent value="coverage">
              <CoverageTable />
            </TabsContent>
            <TabsContent value="usability">
              <UsabilityView />
            </TabsContent>
            <TabsContent value="compare">
              <ChatWorkbench
                personas={state.personas}
                targets={state.targets}
                cases={state.cases}
                gateConfig={state.gateConfig}
                demo={staffTools ? null : state.snapshot}
              />
            </TabsContent>
            <TabsContent value="evals">
              <EvalDashboard targets={state.targets} cases={state.cases} gateConfig={state.gateConfig} demo={staffTools ? null : state.snapshot} />
            </TabsContent>
          </Tabs>
        )}
      </main>
    </div>
  );
}

// ---- conversation inspector ------------------------------------------------------------------------------

function Inspector({ snapshot }: { snapshot: DemoSnapshot | null }) {
  const stored = useMemo(() => (typeof window === "undefined" ? null : loadConversation()), []);
  const journeys = snapshot?.journeys ?? [];
  const [pick, setPick] = useState<string>(stored ? "stored" : (journeys[0]?.id ?? ""));
  const turns: StoredTurn[] =
    pick === "stored" && stored
      ? stored.turns
      : (journeys.find((j) => j.id === pick)?.steps.map((s) =>
          s.kind === "chat" ? { message: s.message, response: s.response } : { confirm: s.action_kind, result: s.result },
        ) ?? []);

  return (
    <section aria-labelledby="inspector-h" className="space-y-4">
      <div className="flex flex-col gap-1 sm:max-w-md">
        <h2 id="inspector-h" className="text-lg font-semibold">
          Conversation inspector
        </h2>
        <label htmlFor="inspect-pick" className="text-sm text-mk-muted">
          Conversation to inspect
        </label>
        <select
          id="inspect-pick"
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          className="mk-focus h-11 rounded-md border border-mk-line-strong bg-mk-surface px-3"
        >
          {stored && <option value="stored">Latest conversation in this browser ({stored.turns.length} steps)</option>}
          {journeys.map((j) => (
            <option key={j.id} value={j.id}>
              Recorded: {j.title}
            </option>
          ))}
        </select>
      </div>
      {turns.length === 0 && (
        <p className="rounded-md border border-dashed border-mk-line-strong p-4 text-mk-muted">
          Nothing to inspect yet. Have a conversation in the customer view, then come back to this tab.
        </p>
      )}
      <ol className="space-y-4">
        {turns.map((t, i) => (
          <li key={i} className="rounded-lg border border-mk-line bg-mk-surface p-4" aria-label={`Step ${i + 1}`}>
            {"message" in t ? (
              <TurnView n={i + 1} message={t.message} r={t.response} />
            ) : (
              <div>
                <h3 className="text-sm font-semibold text-mk-muted">Step {i + 1}: person pressed the send button</h3>
                <p className="mt-1">{t.result.message}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {t.result.record ? (
                    <StateTag tone={t.result.record.status === "urgent_queued" ? "emergency" : "completed"}>
                      Saved {t.result.record.id} (prototype store)
                    </StateTag>
                  ) : (
                    <StateTag tone="escalation">Not saved: {t.result.error_code}</StateTag>
                  )}
                </div>
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-mk-muted">{label}</dt>
      <dd className="mt-0.5 break-words">{children}</dd>
    </div>
  );
}

export function TurnView({ n, message, r }: { n: number; message: string; r: ChatResponse }) {
  const g = r.gate;
  const failed = r.output_checks.filter((c) => !c.passed);
  const emergency = g?.urgency === "emergency";
  const actionTone: StateTone = !r.action
    ? "normal"
    : r.action.stage === "submitted"
      ? r.action.record?.status === "urgent_queued"
        ? "emergency"
        : "completed"
      : "pending";

  return (
    <article aria-labelledby={`step-${n}-h`}>
      <h3 id={`step-${n}-h`} className="text-sm font-semibold text-mk-muted">Step {n}: the person wrote</h3>
      <p className="font-medium">&ldquo;{message}&rdquo;</p>
      <p className="mt-2 text-sm text-mk-muted">Assistant replied</p>
      <p lang={r.language}>{r.reply}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {emergency && <StateTag tone="emergency">Emergency: safety first</StateTag>}
        {r.recommended_handoff ? <StateTag tone="escalation">Person should help: {teamLabel(r.handoff?.team ?? r.handoff_category)}</StateTag> : <StateTag tone="normal">Assistant can handle</StateTag>}
        {r.action && (
          <StateTag tone={actionTone}>
            {r.action.title}: {r.action.stage === "submitted" ? `saved ${r.action.record?.id}` : r.action.stage}
          </StateTag>
        )}
        {(r.records_created ?? []).map((rec) => (
          <StateTag key={rec.id} tone={rec.status === "urgent_queued" ? "emergency" : "completed"}>
            Saved {rec.id}
          </StateTag>
        ))}
        {r.reply_source && r.reply_source !== "model" && (
          <StateTag tone={r.reply_source === "template" ? "normal" : "escalation"}>
            {r.reply_source === "template"
              ? "Fixed backend reply (no model call)"
              : r.reply_source === "template_after_validation"
                ? "Model reply blocked by checks; backend reply shown"
                : "Model failed; backend reply shown"}
          </StateTag>
        )}
        {r.is_mock && <StateTag tone="unavailable">Mock model, not AI</StateTag>}
      </div>

      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Fact label="Who (trusted app context)">
          {r.audience}
          {r.identity_note ? `, ${r.identity_note}` : ""}
        </Fact>
        <Fact label="Workflow">
          {r.routed_workflow && r.routed_workflow.id !== r.workflow?.id ? `${r.routed_workflow.label}, then ${r.workflow?.label}` : (r.workflow?.label ?? "None (baseline)")}
          {r.functions?.length ? <span className="block text-sm text-mk-muted">Modules {r.functions.join(", ")}</span> : null}
        </Fact>
        <Fact label="Decision gate">
          {g ? (
            <>
              {g.intent}, urgency {g.urgency}, {g.decision_source}
              {g.fallback_used ? " (fell back to rules)" : ""}
              <span className="block text-sm text-mk-muted">
                Confidence {g.confidence.toFixed(2)} (heuristic){g.risk_flags.length ? `; flags: ${g.risk_flags.join(", ")}` : ""}
              </span>
            </>
          ) : (
            "Skipped"
          )}
        </Fact>
        <Fact label="Model">
          {r.provider}:{r.model}
          <span className="block text-sm text-mk-muted">
            {formatLatency(r.latency_ms)}, {formatCost(r.usage.estimated_cost_usd)}
          </span>
        </Fact>
        <Fact label="Account facts used (names only)">
          {r.source_context_fields.length ? (
            <ul className="text-sm">
              {groupCounts(r.source_context_fields.map((f) => f.split(" ← ")[0])).map(([name, n]) => (
                <li key={name}>
                  {name.replaceAll("_", " ")}
                  {n > 1 ? ` (${n})` : ""}
                </li>
              ))}
            </ul>
          ) : (
            "None"
          )}
        </Fact>
        <Fact label="Handoff">
          {r.handoff ? (
            <>
              {teamLabel(r.handoff.team)}, {r.handoff.priority} priority
              <span className="block text-sm text-mk-muted">{r.handoff.delivery_note}</span>
            </>
          ) : (
            "Not needed"
          )}
        </Fact>
        <Fact label="Reply checks">
          {failed.length ? (
            <span className="text-mk-attention">Failed: {failed.map((c) => c.code).join(", ")}</span>
          ) : (
            `All ${r.output_checks.length} passed`
          )}
        </Fact>
        <Fact label="Channel and language">
          {r.channel ?? "web_chat"}, {r.language === "es" ? "Spanish" : "English"}
        </Fact>
      </dl>
      <details className="mt-3">
        <summary className="mk-focus inline-flex min-h-11 cursor-pointer items-center rounded text-mk-brand-hover underline underline-offset-2">Full pipeline trace</summary>
        <div className="mt-2">
          <Diagnostics r={r} />
        </div>
      </details>
    </article>
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
  const shown = useMemo(
    () => sortQueue((rows ?? []).filter((r) => (kind === "all" || r.kind === kind) && (prio === "all" || recordPriority(r) === prio))),
    [rows, kind, prio],
  );
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
            Showing {shown.length} of {rows.length}
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

// ---- coverage -------------------------------------------------------------------------------------------------

function CoverageTable() {
  return (
    <section aria-labelledby="coverage-h" className="space-y-3">
      <h2 id="coverage-h" className="text-lg font-semibold">
        Workflow coverage (McKinley AI Agent Flow, F1 to F9)
      </h2>
      <p className="text-mk-muted">Simulated means it works end to end against the prototype store, not a real McKinley system.</p>
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {COVERAGE.map((c) => (
          <li key={c.id} className="rounded-lg border border-mk-line bg-mk-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">
                {c.id} {c.name}
              </h3>
              <StateTag tone={COVERAGE_TONE[c.status].tone}>{COVERAGE_TONE[c.status].text}</StateTag>
            </div>
            <p className="mt-2">{c.works}</p>
            <p className="mt-2 text-sm text-mk-muted">
              <span className="font-semibold text-mk-ink">Waiting on:</span> {c.blockedOn}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
