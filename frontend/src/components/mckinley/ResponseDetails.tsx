"use client";

import { Badge } from "@/components/ui/badge";
import { CHECK_LABELS, formatCost, formatLatency, formatTokens } from "@/lib/format";
import type { ChatResponse } from "@/lib/types";

export function HandoffPanel({ r }: { r: Pick<ChatResponse, "recommended_handoff" | "handoff_category" | "handoff_reason" | "model_handoff" | "mode"> }) {
  if (!r.recommended_handoff) {
    return <p className="text-sm text-muted-foreground">No human handoff recommended.</p>;
  }
  return (
    <div role="status" className="rounded-md border border-orange-300 bg-orange-50 p-3 text-sm text-orange-950 dark:border-orange-700 dark:bg-orange-950/40 dark:text-orange-100">
      <p className="font-semibold">Human handoff recommended — {r.handoff_category.replaceAll("_", " ")}</p>
      {r.handoff_reason && <p className="mt-1">{r.handoff_reason}</p>}
      <p className="mt-1 text-xs">
        Recommendation only: no staff member has been notified and no ticket was created.
        {r.mode === "aware" && !r.model_handoff && " (Raised by backend policy gate; the model did not request it.)"}
      </p>
    </div>
  );
}

export function ResponseDetails({ r }: { r: ChatResponse }) {
  return (
    <div className="space-y-3">
      <HandoffPanel r={r} />
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
        <ul className="list-disc pl-5 text-xs text-destructive">
          {r.output_checks.filter((c) => !c.passed).map((c) => (
            <li key={c.code}>{c.detail}</li>
          ))}
        </ul>
      )}
      {r.policy_signals.length > 0 && (
        <div className="text-xs">
          <p className="font-medium">Policy signals</p>
          <ul className="list-disc pl-5 text-muted-foreground">
            {r.policy_signals.map((s) => (
              <li key={s.code}>
                <span className="font-mono">{s.code}</span>: {s.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <dt>Provider / model</dt>
        <dd className="break-all">{r.provider}:{r.model}</dd>
        <dt>Prompt</dt>
        <dd className="break-all">{r.prompt_version}</dd>
        <dt>Latency</dt>
        <dd>{formatLatency(r.latency_ms)}</dd>
        <dt>Tokens</dt>
        <dd>{formatTokens(r.usage.input_tokens, r.usage.output_tokens)}</dd>
        <dt>Est. cost</dt>
        <dd>{formatCost(r.usage.estimated_cost_usd)}</dd>
        <dt>Temperature</dt>
        <dd>{r.temperature ?? "n/a"}</dd>
        <dt>Output parse</dt>
        <dd>{r.parse_mode}</dd>
        <dt>Audience (model)</dt>
        <dd>{r.audience}</dd>
      </dl>
    </div>
  );
}
