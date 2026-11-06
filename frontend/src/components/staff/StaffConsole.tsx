"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatWorkbench } from "@/components/mckinley/ChatWorkbench";
import { EvalDashboard } from "@/components/mckinley/EvalDashboard";
import { Diagnostics } from "@/components/mckinley/ResponseDetails";
import { StaticDemoBanner } from "@/components/mckinley/StatusBar";
import { ApiError, api, loadDemoSnapshot } from "@/lib/api";
import { COVERAGE, type CoverageStatus } from "@/lib/coverage";
import { type StoredTurn, loadConversation } from "@/lib/customer";
import { formatCost, formatLatency } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChatResponse, DemoSnapshot, EvalCase, GateConfig, Health, ModelTarget, Persona, PrototypeRecord } from "@/lib/types";

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
    const [health, personas, targets, cases] = await Promise.all([api.health(), api.personas(), api.models(), api.evalCases()]);
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
  completed: "border-mk-sent/40 bg-mk-sent-soft text-mk-sent",
  unavailable: "border-dashed border-mk-line-strong bg-mk-surface text-mk-muted",
  escalation: "border-mk-attention/40 bg-mk-attention-soft text-mk-attention",
  emergency: "border-mk-danger bg-mk-danger-soft text-mk-danger",
};

export function StateTag({ tone, children }: { tone: StateTone; children: React.ReactNode }) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-sm font-medium", TONE_CLASS[tone])}>{children}</span>;
}

const COVERAGE_TONE: Record<CoverageStatus, { tone: StateTone; text: string }> = {
  working: { tone: "completed", text: "Working (synthetic data)" },
  partial: { tone: "pending", text: "Partly working" },
  simulated: { tone: "pending", text: "Simulated" },
  unavailable: { tone: "unavailable", text: "Not available" },
};

export function StaffConsole() {
  const [state, setState] = useState<Boot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    boot()
      .then(setState)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "The console could not load."));
  }, []);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-mk-line bg-mk-surface">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-end justify-between gap-3 px-4 py-3 md:px-6">
          <div>
            <p className="text-xl font-bold tracking-tight text-mk-brand">McKinley</p>
            <h1 className="text-base font-semibold">Staff and demo console</h1>
          </div>
          <Link href="/" prefetch={false} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-mk-line-strong px-4">
            Open the customer view
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-4 px-4 py-4 md:px-6">
        <p className="text-mk-muted">
          What the assistant decided behind each reply, what it saved, and what is still simulated. Made-up data only.
          {state && !state.live && " The backend isn't running for this link, so everything here was recorded from it in advance."}
        </p>
        {error && (
          <p role="alert" className="rounded-md border border-mk-danger bg-mk-danger-soft p-3 text-mk-danger">
            Backend unavailable: {error}
          </p>
        )}
        {state && !state.live && state.snapshot && (
          <StaticDemoBanner notice={state.snapshot.notice} generatedAt={state.snapshot.generated_at} />
        )}
        {!state && !error && <p role="status">Loading…</p>}
        {state && (
          <Tabs defaultValue="inspector">
            <TabsList className="flex h-auto flex-wrap">
              <TabsTrigger value="inspector">Conversation inspector</TabsTrigger>
              <TabsTrigger value="records">Saved requests</TabsTrigger>
              <TabsTrigger value="coverage">Workflow coverage</TabsTrigger>
              <TabsTrigger value="compare">Model comparison</TabsTrigger>
              <TabsTrigger value="evals">Evaluation</TabsTrigger>
            </TabsList>
            <TabsContent value="inspector">
              <Inspector snapshot={state.snapshot} />
            </TabsContent>
            <TabsContent value="records">
              <Records live={state.live} snapshot={state.snapshot} />
            </TabsContent>
            <TabsContent value="coverage">
              <CoverageTable />
            </TabsContent>
            <TabsContent value="compare">
              <ChatWorkbench
                personas={state.personas}
                targets={state.targets}
                cases={state.cases}
                gateConfig={state.gateConfig}
                demo={state.live ? null : state.snapshot}
              />
            </TabsContent>
            <TabsContent value="evals">
              <EvalDashboard targets={state.targets} cases={state.cases} gateConfig={state.gateConfig} demo={state.live ? null : state.snapshot} />
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
          <li key={i} className="rounded-lg border border-mk-line bg-mk-surface p-4">
            {"message" in t ? (
              <TurnView n={i + 1} message={t.message} r={t.response} />
            ) : (
              <div>
                <p className="text-sm text-mk-muted">Step {i + 1}: person pressed the confirm button</p>
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
    <article aria-label={`Step ${n}`}>
      <p className="text-sm text-mk-muted">Step {n}: the person wrote</p>
      <p className="font-medium">&ldquo;{message}&rdquo;</p>
      <p className="mt-2 text-sm text-mk-muted">Assistant replied</p>
      <p lang={r.language}>{r.reply}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {emergency && <StateTag tone="emergency">Emergency: safety first</StateTag>}
        {r.recommended_handoff ? <StateTag tone="escalation">Person should help: {r.handoff?.team ?? r.handoff_category}</StateTag> : <StateTag tone="normal">Assistant can handle</StateTag>}
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
              {r.source_context_fields.map((f) => (
                <li key={f}>{f.split(" ← ")[0]}</li>
              ))}
            </ul>
          ) : (
            "None"
          )}
        </Fact>
        <Fact label="Handoff">
          {r.handoff ? (
            <>
              {r.handoff.team}, {r.handoff.priority} priority
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
        <summary className="mk-focus inline-flex min-h-11 cursor-pointer items-center rounded text-mk-brand underline underline-offset-2">Full pipeline trace</summary>
        <div className="mt-2">
          <Diagnostics r={r} />
        </div>
      </details>
    </article>
  );
}

// ---- prototype records -------------------------------------------------------------------------------------

const KIND_LABEL: Record<string, string> = { maintenance_request: "Repair request", tour_request: "Tour request", staff_handoff: "Note for the office" };

function Records({ live, snapshot }: { live: boolean; snapshot: DemoSnapshot | null }) {
  const [rows, setRows] = useState<PrototypeRecord[] | null>(live ? null : (snapshot?.prototype_records ?? []));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!live) return;
    api
      .prototypeRecords(100)
      .then(setRows)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : "Could not load records"));
  }, [live]);

  return (
    <section aria-labelledby="records-h" className="space-y-3">
      <h2 id="records-h" className="text-lg font-semibold">
        Saved requests (prototype store)
      </h2>
      <p className="text-mk-muted">
        Stand-in for Yardi work orders, the CRM and the staff queue. Nothing here reaches a real system and no one is notified.
        {!live && " These were saved while recording the demo conversations."}
      </p>
      {err && <p role="alert">{err}</p>}
      {rows === null && !err && <p role="status">Loading…</p>}
      {rows && rows.length === 0 && <p className="rounded-md border border-dashed border-mk-line-strong p-4 text-mk-muted">No requests saved yet.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-mk-line bg-mk-surface">
          <table className="w-full min-w-[44rem] text-left">
            <caption className="sr-only">Prototype records, newest first</caption>
            <thead className="border-b border-mk-line text-sm text-mk-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Reference</th>
                <th scope="col" className="px-3 py-2 font-medium">Type</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
                <th scope="col" className="px-3 py-2 font-medium">Team</th>
                <th scope="col" className="px-3 py-2 font-medium">Account</th>
                <th scope="col" className="px-3 py-2 font-medium">Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-mk-line">
              {rows.map((r) => (
                <tr key={r.id}>
                  <th scope="row" className="px-3 py-2 font-semibold whitespace-nowrap">{r.id}</th>
                  <td className="px-3 py-2">{KIND_LABEL[r.kind] ?? r.kind}</td>
                  <td className="px-3 py-2">
                    <StateTag tone={r.status === "urgent_queued" ? "emergency" : r.kind === "staff_handoff" ? "escalation" : "completed"}>{r.status_label}</StateTag>
                  </td>
                  <td className="px-3 py-2">{r.team ?? ""}{r.priority ? `, ${r.priority}` : ""}</td>
                  <td className="px-3 py-2">{r.persona_id || "Not signed in"}</td>
                  <td className="px-3 py-2 text-sm">{r.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
