import { describe, expect, it } from "vitest";

import { effectiveVerdict, formatCost, formatLatency, formatTokens, newSessionId } from "./format";

describe("format helpers", () => {
  it("formats tokens, cost and latency", () => {
    expect(formatTokens(null, null)).toBe("not reported");
    expect(formatTokens(120, 30)).toBe("120 in / 30 out");
    expect(formatCost(null)).toBe("n/a");
    expect(formatCost(0)).toBe("$0 (free/local)");
    expect(formatCost(0.00123)).toBe("$0.00123");
    expect(formatLatency(850)).toBe("850 ms");
    expect(formatLatency(2400)).toBe("2.4 s");
  });

  it("prefers human verdict over provisional", () => {
    expect(effectiveVerdict({ status: "ok", human_verdict: "BAD", provisional_verdict: "GOOD" })).toEqual({
      verdict: "BAD",
      source: "human",
    });
    expect(effectiveVerdict({ status: "ok", human_verdict: null, provisional_verdict: "GOOD" }).source).toBe("provisional");
    expect(effectiveVerdict({ status: "error", human_verdict: null, provisional_verdict: null }).source).toBe("error");
  });

  it("creates backend-compatible session ids", () => {
    const id = newSessionId();
    expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(newSessionId()).not.toBe(id);
  });
});
