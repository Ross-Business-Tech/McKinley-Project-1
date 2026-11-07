"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { CHECK_LABELS, formatCost, formatLatency, formatTokens, humanize } from "@/lib/format";
import type { ChatResponse, GateDecision, HandoffRecommendation, PipelineStep } from "@/lib/types";

/** Legacy handoff notice, used when the response carries no structured `handoff` (e.g. baseline mode). */
export function HandoffPanel({ r }: { r: Pick<ChatResponse, "recommended_handoff" | "handoff_category" | "handoff_reason" | "model_handoff" | "mode"> }) {
  if (!r.recommended_handoff) {
    return <p className="text-sm text-muted-foreground">No human handoff recommended.</p>;
  }
  return (
    <div role="status" className="rounded-md border border-orange-300 bg-orange-50 p-3 text-sm text-orange-950 dark:border-orange-700 dark:bg-orange-950/40 dark:text-orange-100">
      <p className="font-semibold">Human handoff recommended — {humanize(r.handoff_category)}</p>
      {r.handoff_reason && <p className="mt-1">{r.handoff_reason}</p>}
      <p className="mt-1 text-xs">
        Recommendation only: no staff member has been notified and no ticket was created.
        {r.mode !== "baseline" && !r.model_handoff && " (Raised by backend policy gate; the model did not request it.)"}
      </p>
    </div>
  );
}

export function SafetyNotice({ text }: { text: string }) {
  return (
    <div role="alert" className="rounded-md border-2 border-red-400 bg-red-50 p-3 text-sm font-medium text-red-950 dark:border-red-700 dark:bg-red-950/50 dark:text-red-100">
      <p className="mb-1 text-sm font-semibold">Safety notice</p>
      <p>{text}</p>
    </div>
  );
}

/** Compact staff-handoff card. Always explicit that nothing was sent. */
export function HandoffCard({ h, noWorkOrder }: { h: HandoffRecommendation; noWorkOrder?: boolean }) {
  return (
    <div role="status" aria-label="Staff handoff recommendation"
      className="rounded-md border border-orange-300 bg-orange-50 p-3 text-sm text-orange-950 dark:border-orange-700 dark:bg-orange-950/40 dark:text-orange-100">
      <div className="flex flex-wrap items-center gap-1.5">
        <p className="font-semibold">Staff handoff: Recommended — not sent</p>
        <Badge variant="outline" className="border-orange-400">{h.priority}</Badge>
      </div>
      <p className="mt-1">
        <span className="font-medium">Team:</span> {humanize(h.team)} · <span className="font-medium">Category:</span>{" "}
        {humanize(h.category)}
      </p>
      <p className="mt-1">{h.summary}</p>
      <p className="mt-1 text-xs">{h.delivery_note}</p>
      {noWorkOrder && <p className="mt-1 text-xs font-medium">No work order created (no integration).</p>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1">
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      {children}
    </section>
  );
}

function KV({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] gap-x-3 gap-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

const STEP_STYLE: Record<PipelineStep["status"], string> = {
  ok: "border-emerald-300 text-emerald-800 dark:border-emerald-700 dark:text-emerald-200",
  skipped: "border-border text-muted-foreground",
  warn: "border-amber-400 text-amber-800 dark:border-amber-600 dark:text-amber-200",
  fallback: "border-orange-400 text-orange-800 dark:border-orange-600 dark:text-orange-200",
};

export function sourceLabel(source: string): string {
  return source === "mock" ? "mock (deterministic stand-in, not a real model)" : source;
}

function identityDetail(pipeline: PipelineStep[]): string | null {
  return pipeline.find((p) => p.step.endsWith("identity"))?.detail ?? null;
}

function GateSection({ g, pipeline }: { g: GateDecision; pipeline: PipelineStep[] }) {
  const identity = identityDetail(pipeline);
  return (
    <Section title="Decision gate">
      <KV
        rows={[
          ["Audience (trusted)", g.audience],
          ...(identity ? ([["Identity", identity]] as [string, ReactNode][]) : []),
          ["Intent", g.intent],
          ["Urgency", g.urgency],
          ["Needs a human", g.requires_human ? `yes${g.handoff_reason ? ` — ${g.handoff_reason}` : ""}` : "no"],
          [
            "Confidence",
            <>
              {g.confidence.toFixed(2)}
              {!g.confidence_calibrated && <span className="text-muted-foreground"> (heuristic, not calibrated)</span>}
            </>,
          ],
          ["Decision source", <>{sourceLabel(g.decision_source)} <span className="text-muted-foreground">(requested: {g.requested_provider})</span></>],
          ["Fallback", g.fallback_used ? `yes — ${g.fallback_reason ?? "no reason given"}` : "no"],
          ["Safety-floor overrides", g.overrides.length ? g.overrides.join("; ") : "none"],
          ["Risk flags", g.risk_flags.length ? g.risk_flags.join(", ") : "none"],
          ...(g.rationale.length ? ([["Rationale", g.rationale.join("; ")]] as [string, ReactNode][]) : []),
          ...(g.gate_usage
            ? ([["Gate model usage", `${formatTokens(g.gate_usage.input_tokens, g.gate_usage.output_tokens)} · ${formatCost(g.gate_usage.estimated_cost_usd)}`]] as [string, ReactNode][])
            : []),
        ]}
      />
    </Section>
  );
}

/** Developer diagnostics: closed by default so the customer-facing reply stays clean. */
export function Diagnostics({ r }: { r: ChatResponse }) {
  return (
    <details className="group rounded-md border bg-muted/30 text-xs">
      <summary className="cursor-pointer select-none rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        Why this answer <span className="font-normal text-muted-foreground">(diagnostics)</span>
      </summary>
      <div className="space-y-4 border-t px-3 py-3">
        {r.gate ? (
          <GateSection g={r.gate} pipeline={r.pipeline} />
        ) : (
          <Section title="Decision gate">
            <p className="text-muted-foreground">
              None — generic baseline mode has no decision gate, workflow or resident context. Audience reported by
              the model: {r.audience}.
            </p>
          </Section>
        )}

        {r.workflow && (
          <Section title="Workflow">
            <KV rows={[["Selected", `${r.workflow.label} (${r.workflow.id})`], ["Reason", r.workflow.reason],
              ["Instructions", r.workflow.instructions_version]]} />
          </Section>
        )}

        {r.maintenance && (
          <Section title="Maintenance triage">
            <KV rows={[
              ["Level", r.maintenance.level],
              ["Category", r.maintenance.category],
              ["Approved steps", r.maintenance.approved_troubleshooting.length ? r.maintenance.approved_troubleshooting.join("; ") : "none"],
              ["Entry window on file", r.maintenance.entry_window_on_file ? "yes" : "no"],
              ["Work order", <span key="wo" className="font-medium">No work order created (no integration)</span>],
            ]} />
          </Section>
        )}

        {r.lead && (
          <Section title="Lead profile">
            <KV rows={[
              ["Intent level", r.lead.intent_level],
              ["Signals", r.lead.signals.length ? r.lead.signals.map(humanize).join(", ") : "none"],
              ["Known", Object.keys(r.lead.known).length ? Object.entries(r.lead.known).map(([k, v]) => `${humanize(k)}: ${v}`).join("; ") : "nothing yet"],
              ["Missing", r.lead.missing.length ? r.lead.missing.map(humanize).join(", ") : "none"],
              ...(r.lead.next_question ? ([["Next question", r.lead.next_question]] as [string, ReactNode][]) : []),
            ]} />
          </Section>
        )}

        {r.renewal && (
          <Section title="Renewal assessment">
            <KV rows={[
              ["Concerns", r.renewal.concerns.length ? r.renewal.concerns.map(humanize).join(", ") : "none"],
              ["Renewal status known", r.renewal.renewal_status_known ? "yes" : "no"],
              ["Open commitments", String(r.renewal.open_commitments)],
              ["Tone", r.renewal.tone],
            ]} />
          </Section>
        )}

        {r.handoff && (
          <Section title="Handoff details (not sent)">
            <KV rows={[
              ["Reasons", r.handoff.reasons.join("; ")],
              ["Fields included", r.handoff.included_fields.length ? r.handoff.included_fields.join(", ") : "none"],
              ["Contact guidance", r.handoff.contact_guidance ?? "none"],
            ]} />
          </Section>
        )}

        <Section title="Context fields used">
          {r.source_context_fields.length ? (
            <ul className="list-disc space-y-0.5 pl-4 break-words">
              {r.source_context_fields.map((f) => <li key={f}>{f}</li>)}
            </ul>
          ) : (
            <p className="text-muted-foreground">No resident context fields were sent to the model.</p>
          )}
        </Section>

        {r.policy_signals.length > 0 && (
          <Section title="Policy signals">
            <ul className="list-disc space-y-0.5 pl-4">
              {r.policy_signals.map((s) => (
                <li key={s.code}><span className="font-mono">{s.code}</span>: {s.detail}</li>
              ))}
            </ul>
          </Section>
        )}

        {r.pipeline.length > 0 && (
          <Section title="Pipeline trace">
            <ol className="space-y-1">
              {r.pipeline.map((p) => (
                <li key={p.step} className="flex flex-wrap items-start gap-x-2 gap-y-0.5">
                  <span className={`rounded border px-1 font-mono text-[0.7rem] ${STEP_STYLE[p.status]}`}>{p.status}</span>
                  <span className="font-medium">{humanize(p.step.replace(/^\d+_/, (m) => m.replace("_", ". ")))}</span>
                  <span className="min-w-0 basis-full break-words text-muted-foreground sm:basis-auto sm:flex-1">{p.detail}</span>
                </li>
              ))}
            </ol>
          </Section>
        )}

        <Section title="Model">
          <KV rows={[
            ["Provider / model", <span key="pm" className="break-all">{r.provider}:{r.model}{r.is_mock ? " (MOCK)" : ""}</span>],
            ["Prompt version", <span key="pv" className="break-all">{r.prompt_version}</span>],
            ["Latency", formatLatency(r.latency_ms)],
            ["Tokens", formatTokens(r.usage.input_tokens, r.usage.output_tokens)],
            ["Est. cost", formatCost(r.usage.estimated_cost_usd)],
            ["Temperature", String(r.temperature ?? "n/a")],
            ["Output parse", r.parse_mode],
          ]} />
        </Section>

        <Section title="Output checks">
          <ul className="flex flex-wrap gap-1.5" aria-label="Automated output checks">
            {r.output_checks.map((c) => (
              <li key={c.code}>
                <Badge variant={c.passed ? "outline" : "destructive"} title={c.detail}>
                  {c.passed ? "✓" : "✗"} {CHECK_LABELS[c.code] ?? c.code}
                </Badge>
              </li>
            ))}
          </ul>
          {r.output_checks.some((c) => !c.passed) && (
            <ul className="list-disc pl-4 text-destructive">
              {r.output_checks.filter((c) => !c.passed).map((c) => <li key={c.code}>{c.detail}</li>)}
            </ul>
          )}
        </Section>
      </div>
    </details>
  );
}

/** The reply as the customer would see it, with safety notice above and a compact handoff card below. */
export function ResponseView({ r }: { r: ChatResponse }) {
  return (
    <div className="space-y-2">
      {r.is_mock && (
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary" title="Deterministic template, not a language model">Mock</Badge>
        </div>
      )}
      {r.safety_notice && <SafetyNotice text={r.safety_notice} />}
      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        <span className="sr-only">Assistant: </span>
        {r.reply}
      </p>
      {r.handoff ? <HandoffCard h={r.handoff} noWorkOrder={!!r.maintenance && !r.maintenance.work_order_created} /> : <HandoffPanel r={r} />}
      <Diagnostics r={r} />
    </div>
  );
}

/** Back-compat export. */
export const ResponseDetails = ResponseView;
