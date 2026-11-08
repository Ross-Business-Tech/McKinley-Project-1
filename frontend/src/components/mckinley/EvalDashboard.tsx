"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { ALL_MODES, MODE_META, effectiveVerdict, formatCost, formatLatency, formatTokens, plainStatus } from "@/lib/format";
import type { DemoSnapshot, EvalCase, EvalResult, EvalSummary, GateConfig, Mode, ModelTarget, Verdict } from "@/lib/types";

import { GateEvalPanel } from "./GateEvalPanel";

export function VerdictBadge({ r }: { r: EvalResult }) {
  const { verdict, source } = effectiveVerdict(r);
  if (source === "error") return <Badge variant="destructive">ERROR</Badge>;
  return (
    <Badge variant={verdict === "GOOD" ? "secondary" : "destructive"}>
      {verdict ?? "—"} <span className="ml-1 font-normal">({source === "human" ? "human" : "provisional"})</span>
    </Badge>
  );
}

function ResultCell({ r, onReviewed }: { r: EvalResult | undefined; onReviewed: (r: EvalResult) => void }) {
  const [notes, setNotes] = useState(r?.human_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!r) return <p className="text-xs text-muted-foreground">Not run.</p>;

  async function save(verdict: Verdict | null, newNotes: string) {
    if (!r) return;
    setSaving(true);
    try {
      onReviewed(await api.review(r.id, verdict, newNotes || null));
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (r.status === "error") {
    return (
      <div role="alert" className="text-sm text-destructive">
        <p className="font-semibold">{r.error_code}</p>
        <p className="text-xs">{r.error_message}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerdictBadge r={r} />
        {r.is_mock && <Badge variant="outline">Mock</Badge>}
        {r.recommended_handoff && <Badge variant="outline">handoff: {r.handoff_category}</Badge>}
      </div>
      {(r.gate_intent || r.workflow_id) && (
        <p className="text-xs text-muted-foreground">
          Gate: {r.gate_intent ?? "—"} / {r.gate_urgency ?? "—"}
          {r.gate_source && ` (${r.gate_source === "mock" ? "mock stand-in" : r.gate_source})`} · Workflow: {r.workflow_id ?? "—"}
        </p>
      )}
      <p className="whitespace-pre-wrap break-words leading-relaxed">{r.reply}</p>
      <ul className="space-y-0.5 text-xs">
        {r.criteria.map((c) => (
          <li key={c.criterion} className={c.passed === false ? "text-destructive" : "text-muted-foreground"}>
            {c.passed === null ? "?" : c.passed ? "✓" : "✗"} {c.criterion}: {c.detail}
          </li>
        ))}
      </ul>
      <p className="break-words text-xs text-muted-foreground">
        {r.model} · {formatLatency(r.latency_ms)} · {formatTokens(r.input_tokens, r.output_tokens)} ·{" "}
        {formatCost(r.estimated_cost_usd)} · parse {r.parse_mode}
      </p>
      <div className="flex items-center gap-1.5" role="group" aria-label={`Reviewer verdict for ${r.case_id} ${r.mode}`}>
        <Button size="xs" variant={r.human_verdict === "GOOD" ? "default" : "outline"} disabled={saving}
          aria-pressed={r.human_verdict === "GOOD"} onClick={() => void save("GOOD", notes)}>
          Good
        </Button>
        <Button size="xs" variant={r.human_verdict === "BAD" ? "destructive" : "outline"} disabled={saving}
          aria-pressed={r.human_verdict === "BAD"} onClick={() => void save("BAD", notes)}>
          Bad
        </Button>
        {r.human_verdict && (
          <Button size="xs" variant="ghost" disabled={saving} onClick={() => void save(null, notes)}>
            Clear
          </Button>
        )}
      </div>
      <label className="block text-xs">
        <span className="sr-only">Reviewer notes</span>
        <Textarea rows={2} value={notes} maxLength={2000} placeholder="Reviewer notes / evidence"
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== (r.human_notes ?? "") && void save(r.human_verdict, notes)} />
      </label>
      {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
    </div>
  );
}

export function EvalDashboard({
  targets,
  cases,
  gateConfig = null,
  demo = null,
}: {
  targets: ModelTarget[];
  cases: EvalCase[];
  gateConfig?: GateConfig | null;
  demo?: DemoSnapshot | null;
}) {
  if (demo) {
    return (
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Five-case evaluation</CardTitle>
            <CardDescription>
              Running and reviewing evaluations needs the live backend, which this static demo does not have. The
              decision-gate comparison below was pre-computed.
            </CardDescription>
          </CardHeader>
        </Card>
        <GateEvalPanel cases={cases} gateConfig={null} snapshot={demo.gate_eval} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <FiveCaseEval targets={targets} cases={cases} />
      <GateEvalPanel cases={cases} gateConfig={gateConfig} />
    </div>
  );
}

function FiveCaseEval({ targets, cases: allCases }: { targets: ModelTarget[]; cases: EvalCase[] }) {
  const cases = useMemo(() => allCases.filter((c) => (c.suite ?? "core") === "core"), [allCases]);
  const [modes, setModes] = useState<Mode[]>(ALL_MODES);
  const [selected, setSelected] = useState<string[]>(() => {
    const d = targets.find((t) => t.is_default);
    return d ? [d.key] : [];
  });
  const [results, setResults] = useState<EvalResult[]>([]);
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshSummary = useCallback(async (id?: number) => {
    try {
      setSummary(await api.evalSummary(id));
    } catch {
      /* summary is secondary */
    }
  }, []);

  useEffect(() => {
    api
      .evalResults()
      .then((r) => {
        setResults(r.results);
        setRunId(r.run_id || null);
        if (r.run_id) void refreshSummary(r.run_id);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load results"));
  }, [refreshSummary]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const r = await api.runEvals(selected, cases.map((c) => c.id), ALL_MODES.filter((m) => modes.includes(m)));
      setResults(r.results);
      setRunId(r.run_id);
      await refreshSummary(r.run_id);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "Eval run failed");
    } finally {
      setRunning(false);
    }
  }

  const onReviewed = (updated: EvalResult) => {
    setResults((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    void refreshSummary(updated.run_id);
  };

  const runTargets = useMemo(
    () => Array.from(new Set(results.map((r) => `${r.provider}:${r.requested_model}`))),
    [results],
  );
  const find = (caseId: string, target: string, mode: string) =>
    results.find((r) => r.case_id === caseId && `${r.provider}:${r.requested_model}` === target && r.mode === mode);
  const resultModes = ALL_MODES.filter((m) => results.some((r) => r.mode === m));
  const anyMock = selected.some((k) => targets.find((t) => t.key === k)?.is_mock);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Run five-case evaluation</CardTitle>
          <CardDescription>
            Each selected target runs the five core cases in every selected mode with identical settings.
            Every result is pinned to its target; models are never substituted. Automated verdicts are provisional
            — mark Good/Bad as the reviewer.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <fieldset>
            <legend className="mb-1 text-sm font-medium">Model targets to compare</legend>
            <div className="grid gap-1 sm:grid-cols-2">
              {targets.map((t) => (
                <label key={t.key} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={selected.includes(t.key)}
                    onChange={(e) =>
                      setSelected((prev) => (e.target.checked ? [...prev, t.key] : prev.filter((k) => k !== t.key)))
                    }
                  />
                  <span className="break-all">{t.key}</span>
                  {t.is_mock && <Badge variant="outline">Mock</Badge>}
                  {!t.ready && <Badge variant="destructive">{plainStatus(t.status)}</Badge>}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">Modes</legend>
            <div className="grid gap-1 sm:grid-cols-3">
              {ALL_MODES.map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={modes.includes(m)}
                    disabled={modes.length === 1 && modes.includes(m)}
                    onChange={(e) => setModes((prev) => (e.target.checked ? [...prev, m] : prev.filter((x) => x !== m)))}
                  />
                  {MODE_META[m].letter} · {MODE_META[m].title}
                </label>
              ))}
            </div>
          </fieldset>
          {anyMock && (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Mock results are deterministic templates for testing the harness, not evidence of model quality.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button className="h-auto min-h-8 whitespace-normal" onClick={() => void run()} disabled={running || selected.length === 0}>
              {running ? "Running… (free models can take a few minutes)" : `Run ${selected.length * cases.length * modes.length} evaluations`}
            </Button>
            {runId && <span className="text-xs text-muted-foreground">Showing run #{runId}</span>}
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {summary && summary.total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Score summary — run #{summary.run_id}</CardTitle>
            <CardDescription>Human verdicts override provisional verdicts. Five synthetic cases are a functional demo, not statistical evidence.</CardDescription>
          </CardHeader>
          <CardContent className="min-w-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Target</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Good</TableHead>
                  <TableHead>Bad</TableHead>
                  <TableHead>Errors</TableHead>
                  <TableHead>Human-reviewed</TableHead>
                  <TableHead>Handoffs</TableHead>
                  <TableHead>JSON failures</TableHead>
                  <TableHead>Avg latency</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Est. cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.values(summary.by_target_mode).map((g) => (
                  <TableRow key={`${g.target}|${g.mode}`}>
                    <TableCell className="max-w-56 break-all">
                      {g.target} {g.is_mock ? <Badge variant="outline">Mock</Badge> : null}
                    </TableCell>
                    <TableCell>{MODE_META[g.mode as Mode]?.title ?? g.mode}</TableCell>
                    <TableCell>{g.good}/{g.runs}</TableCell>
                    <TableCell>{g.bad}</TableCell>
                    <TableCell>{g.errors}</TableCell>
                    <TableCell>{g.human_reviewed}</TableCell>
                    <TableCell>{g.handoffs_recommended}</TableCell>
                    <TableCell>{g.json_contract_failures}</TableCell>
                    <TableCell>{formatLatency(g.avg_latency_ms)}</TableCell>
                    <TableCell>{formatTokens(g.input_tokens, g.output_tokens)}</TableCell>
                    <TableCell>{formatCost(g.estimated_cost_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {Object.keys(summary.failure_categories).length > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                Failed criteria (all targets/modes):{" "}
                {Object.entries(summary.failure_categories).map(([k, v]) => `${k} ×${v}`).join(", ")}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {results.length > 0 &&
        cases.map((c, i) => (
          <Card key={c.id}>
            <CardHeader>
              <CardTitle>
                Case {i + 1}: {c.title}
              </CardTitle>
              <CardDescription>
                Persona <span className="font-mono">{c.persona_id}</span> · “{c.message}”
                <span className="block">Rubric focus: {c.reference_note}</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {runTargets.map((t) => (
                <section key={t} aria-label={`${t} results`}>
                  <h4 className="mb-2 break-all text-sm font-semibold">{t}</h4>
                  <div className={`grid gap-4 md:grid-cols-2 ${resultModes.length > 2 ? "xl:grid-cols-3" : ""}`}>
                    {resultModes.map((m) => (
                      <div key={m} className="min-w-0 rounded-md border p-3">
                        <p className="mb-2 text-sm font-medium text-muted-foreground">
                          {MODE_META[m].letter} · {MODE_META[m].title}
                        </p>
                        <ResultCell key={find(c.id, t, m)?.id ?? "none"} r={find(c.id, t, m)}
                          onReviewed={onReviewed} />
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
