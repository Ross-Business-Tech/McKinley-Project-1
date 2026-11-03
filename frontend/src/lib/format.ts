import type { EvalResult } from "./types";

export function formatTokens(input: number | null | undefined, output: number | null | undefined): string {
  if (input == null && output == null) return "not reported";
  return `${input ?? "?"} in / ${output ?? "?"} out`;
}

export function formatCost(usd: number | null | undefined): string {
  if (usd == null) return "n/a";
  if (usd === 0) return "$0 (free/local)";
  return usd < 0.01 ? `$${usd.toFixed(5)}` : `$${usd.toFixed(3)}`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return "n/a";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

/** Human verdict wins; otherwise the provisional automated verdict. */
export function effectiveVerdict(r: Pick<EvalResult, "human_verdict" | "provisional_verdict" | "status">) {
  if (r.status === "error") return { verdict: null, source: "error" as const };
  if (r.human_verdict) return { verdict: r.human_verdict, source: "human" as const };
  return { verdict: r.provisional_verdict, source: "provisional" as const };
}

export function newSessionId(): string {
  const raw = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return raw.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
}

export const CHECK_LABELS: Record<string, string> = {
  terminology: "Beds / floor plans vocabulary",
  no_false_action_claim: "No claimed actions",
  no_invented_price: "No invented prices",
  no_invented_time: "No invented times",
  no_pii: "No PII",
  no_risky_diy: "No risky DIY",
  structured_output: "JSON contract",
};
