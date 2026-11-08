"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatLatency, formatTokens } from "@/lib/format";
import type { EvalCase, GateConfig, GateEvalResponse, GateProvider } from "@/lib/types";

const PROVIDERS: { id: GateProvider; label: string }[] = [
  { id: "rules", label: "Rules (deterministic, free)" },
  { id: "llm", label: "LLM classifier" },
  { id: "jev", label: "Jev (experimental)" },
];

function Mark({ ok }: { ok: boolean | null }) {
  if (ok === null) return <span className="text-muted-foreground" title="Not labelled for this scenario">–</span>;
  return ok ? <span aria-label="correct">✓</span> : <span className="font-semibold text-destructive" aria-label="incorrect">✗</span>;
}

function SourceBadge({ source }: { source: string }) {
  return source === "mock" ? (
    <Badge variant="secondary" title="Deterministic keyword stand-in, not a real model">mock (stand-in)</Badge>
  ) : (
    <Badge variant="outline">{source}</Badge>
  );
}

export function GateEvalResults({ data, cases }: { data: Pick<GateEvalResponse, "note" | "summary" | "rows">; cases: EvalCase[] }) {
  const title = (id: string) => cases.find((c) => c.id === id)?.title ?? id;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="border-amber-400 text-amber-800 dark:text-amber-200">
          Automated, not human-reviewed
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">{data.note}</p>
      <Table aria-label="Decision gate summary">
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead>Intent</TableHead>
            <TableHead>Workflow</TableHead>
            <TableHead>Urgency</TableHead>
            <TableHead>Handoff</TableHead>
            <TableHead>Critical misses</TableHead>
            <TableHead>Fallbacks</TableHead>
            <TableHead>Sources</TableHead>
            <TableHead>Avg latency</TableHead>
            <TableHead>Tokens</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Object.entries(data.summary).map(([prov, s]) => (
            <TableRow key={prov}>
              <TableCell className="font-medium">{prov}</TableCell>
              <TableCell>{s.intent_correct}</TableCell>
              <TableCell>{s.workflow_correct}</TableCell>
              <TableCell>{s.urgency_correct}</TableCell>
              <TableCell>{s.handoff_correct}</TableCell>
              <TableCell className={s.critical_misses > 0 ? "font-semibold text-destructive" : ""}>{s.critical_misses}</TableCell>
              <TableCell>{s.fallbacks}</TableCell>
              <TableCell>
                <span className="flex flex-wrap gap-1">
                  {s.sources.map((src) => <SourceBadge key={src} source={src} />)}
                </span>
              </TableCell>
              <TableCell>{formatLatency(s.avg_latency_ms)}</TableCell>
              <TableCell>{s.input_tokens || s.output_tokens ? formatTokens(s.input_tokens, s.output_tokens) : "none"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <details className="rounded-md border text-sm">
        <summary className="cursor-pointer px-3 py-2 font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Per-scenario results ({data.rows.length})
        </summary>
        <div className="border-t p-2">
          <Table aria-label="Decision gate per-scenario results">
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Urgency</TableHead>
                <TableHead>Needs human</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((r) => (
                <TableRow key={`${r.scenario}|${r.provider}`} className={r.critical_miss ? "bg-destructive/5" : ""}>
                  <TableCell className="min-w-40 whitespace-normal">{title(r.scenario)}</TableCell>
                  <TableCell>{r.provider}</TableCell>
                  <TableCell><SourceBadge source={r.decision_source} /></TableCell>
                  <TableCell>{r.intent} <Mark ok={r.intent_ok} /></TableCell>
                  <TableCell>{r.workflow} <Mark ok={r.workflow_ok} /></TableCell>
                  <TableCell>{r.urgency} <Mark ok={r.urgency_ok} /></TableCell>
                  <TableCell>{r.requires_human ? "yes" : "no"} <Mark ok={r.handoff_ok} /></TableCell>
                  <TableCell>{r.confidence.toFixed(2)}</TableCell>
                  <TableCell className="min-w-40 whitespace-normal text-xs">
                    {r.critical_miss && <span className="block font-semibold text-destructive">Critical miss</span>}
                    {r.fallback_used && <span className="block">Fallback: {r.fallback_reason ?? "yes"}</span>}
                    {r.overrides.length > 0 && <span className="block">Overrides: {r.overrides.join("; ")}</span>}
                    {r.risk_flags.length > 0 && <span className="block text-muted-foreground">Flags: {r.risk_flags.join(", ")}</span>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </details>
    </div>
  );
}

/** Decision-gate comparison (routing only, no reply generation). */
export function GateEvalPanel({
  cases,
  gateConfig,
  snapshot,
}: {
  cases: EvalCase[];
  gateConfig: GateConfig | null;
  snapshot?: Pick<GateEvalResponse, "note" | "summary" | "rows"> | null;
}) {
  const [providers, setProviders] = useState<GateProvider[]>(["rules"]);
  const [data, setData] = useState<GateEvalResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setData(await api.evaluateGates(providers));
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : "Gate evaluation failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Decision gates</CardTitle>
        <CardDescription>
          Checks only the routing decision (intent, workflow, urgency, handoff) for every labelled scenario — no reply
          is generated.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {snapshot ? (
          <>
            <p className="text-xs text-muted-foreground">
              Pre-computed results from the static snapshot. Running new comparisons needs the live backend.
            </p>
            <GateEvalResults data={snapshot} cases={cases} />
          </>
        ) : (
          <>
            <fieldset>
              <legend className="mb-1 text-sm font-medium">Gate providers to compare</legend>
              <div className="grid gap-1 sm:grid-cols-3">
                {PROVIDERS.map((p) => {
                  const status = gateConfig?.availability[p.id];
                  return (
                    <label key={p.id} className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-0.5 size-4 shrink-0"
                        checked={providers.includes(p.id)}
                        disabled={running || (providers.length === 1 && providers.includes(p.id))}
                        onChange={(e) =>
                          setProviders((prev) => (e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id)))
                        }
                      />
                      <span className="min-w-0">
                        {p.label}
                        {status && <span className="block break-words text-xs text-muted-foreground">{status}</span>}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            {providers.includes("llm") && (
              <p role="note" className="text-xs text-amber-700 dark:text-amber-300">
                The LLM gate makes one model call per scenario. Free-tier rate limits may cause fallbacks to rules.
              </p>
            )}
            <Button onClick={() => void run()} disabled={running || providers.length === 0}>
              {running ? "Evaluating gates…" : "Run gate comparison"}
            </Button>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div aria-live="polite">{data && <GateEvalResults data={data} cases={cases} />}</div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
