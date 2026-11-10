"use client";

import { useId, useState } from "react";

import data from "@/lib/usability.json";
import { cn } from "@/lib/utils";

type Outcomes = Record<"success" | "simulated_success" | "blocked" | "partial" | "failure", number>;
interface Agg {
  scenarios: number;
  outcomes: Outcomes;
  avg_user_turns: number;
  unnecessary_questions: number;
  repeated_questions: number;
  repeated_replies?: number;
  unwanted_records?: number;
  routing_ok: number;
  handoff_ok: number;
  false_claims: number;
  safety_violations: number;
  avg_friction: number;
}
interface Row {
  scenario: string;
  persona: string;
  group: string;
  goal: string;
  risk: string;
  outcome: keyof Outcomes;
  user_turns: number;
  questions_asked: number;
  unnecessary: number;
  repeated_replies: number;
  unwanted_records: number;
  false_claims: number;
  safety_violations: number;
  execution: string;
  notes: string;
}
interface Run {
  label: string;
  meta: { run_at: string; target: string; note?: string };
  summary: Record<string, Agg> & { execution: Record<string, number> };
  rows: Row[];
}

const RUNS = (data as unknown as { runs: Run[] }).runs;

const OUTCOME_TEXT: Record<keyof Outcomes, string> = {
  success: "Success",
  simulated_success: "Simulated success",
  blocked: "Blocked (missing data or approval)",
  partial: "Partial",
  failure: "Failure",
};
const OUTCOME_TONE: Record<keyof Outcomes, string> = {
  success: "bg-mk-done-soft text-mk-done",
  simulated_success: "bg-mk-brand-soft text-mk-brand-strong",
  blocked: "bg-mk-draft-soft text-mk-draft",
  partial: "bg-mk-attention-soft text-mk-attention",
  failure: "bg-mk-danger-soft text-mk-danger",
};

/** Staff view of the persona usability suite (evals/usability). Mock-model runs measure the product pipeline only. */
export function UsabilityView() {
  const headingId = useId();
  const [runIdx, setRunIdx] = useState(RUNS.length - 1);
  const [onlyProblems, setOnlyProblems] = useState(true);
  if (!RUNS.length) return <p>No usability runs exported yet.</p>;
  const run = RUNS[runIdx];
  const base = RUNS[0];
  const rows = run.rows.filter((r) => !onlyProblems || ["partial", "failure"].includes(r.outcome) || r.safety_violations);
  const metrics: [string, (a: Agg) => number, boolean][] = [
    ["Failures", (a) => a.outcomes.failure, true],
    ["Partial", (a) => a.outcomes.partial, true],
    ["Safety violations", (a) => a.safety_violations, true],
    ["False claims", (a) => a.false_claims, true],
    ["Unneeded questions", (a) => a.unnecessary_questions, true],
    ["Identical replies repeated", (a) => a.repeated_replies ?? 0, true],
    ["Extra records beyond the goal", (a) => a.unwanted_records ?? 0, true],
    ["Average turns", (a) => a.avg_user_turns, true],
  ];
  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 id={headingId} className="text-lg font-semibold">
        Usability suite: 25 synthetic personas, {run.summary.all.scenarios} multi-turn scenarios
      </h2>
      <p className="max-w-prose text-mk-muted">
        An adaptive simulated person talks to the real API; a separate evaluator grades the end state. Every run here
        used the mock model, so this measures routing, questions, actions and honesty, not AI writing. Simulated
        success means a record was saved in the prototype store, not in Yardi.
      </p>
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2">
          <span>Run</span>
          <select
            className="mk-focus min-h-11 rounded-md border border-mk-line-strong bg-mk-surface px-2"
            value={runIdx}
            onChange={(e) => setRunIdx(Number(e.target.value))}
          >
            {RUNS.map((r, i) => (
              <option key={r.label} value={i}>
                {r.label} ({r.meta.note || r.meta.target})
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-2">
          <input type="checkbox" className="size-5 accent-mk-brand" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
          Only partial, failed or unsafe scenarios
        </label>
      </div>

      <div role="region" aria-label="Usability metrics" tabIndex={0} className="mk-focus overflow-x-auto rounded-lg border border-mk-line bg-mk-surface">
        <table className="w-full text-left">
          <caption className="sr-only">Lower is better for every metric. Baseline is the first run.</caption>
          <thead className="border-b border-mk-line text-sm text-mk-muted">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Metric (lower is better)</th>
              <th scope="col" className="px-3 py-2 font-medium">{base.label}</th>
              {runIdx !== 0 && <th scope="col" className="px-3 py-2 font-medium">{run.label}</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-mk-line">
            {metrics.map(([name, get]) => (
              <tr key={name}>
                <th scope="row" className="px-3 py-2 font-normal">{name}</th>
                <td className="px-3 py-2 tabular-nums">{get(base.summary.all)}</td>
                {runIdx !== 0 && <td className="px-3 py-2 font-semibold tabular-nums">{get(run.summary.all)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-2" aria-label="Scenarios">
        {rows.map((r) => (
          <li key={r.scenario} className="rounded-lg border border-mk-line bg-mk-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">{r.goal}</h3>
              <span className={cn("rounded-full px-2.5 py-1 text-sm font-medium", OUTCOME_TONE[r.outcome])}>{OUTCOME_TEXT[r.outcome]}</span>
            </div>
            <p className="mt-1 text-sm text-mk-muted">
              {r.scenario} · {r.group} · {r.risk} risk · {r.user_turns} turns · {r.questions_asked} questions · {r.execution}
            </p>
            {r.notes && <p className="mt-1 text-sm">{r.notes}</p>}
          </li>
        ))}
        {!rows.length && <li className="text-mk-muted">No partial, failed or unsafe scenarios in this run.</li>}
      </ul>
    </section>
  );
}
