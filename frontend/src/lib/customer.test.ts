import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { GUEST, UI, greeting, sendErrorText } from "./customer";
import { newSessionId } from "./format";

// Customer-facing text and small helpers (greeting, labels, send errors, session ids).

describe("sendErrorText", () => {
  const t = UI.en;
  it("tells a busy model apart from a switched-off assistant and from no connection", () => {
    expect(sendErrorText(new ApiError("ASSISTANT_BUSY", "x", true, 503), t)).toBe(`${t.busy} ${t.tryAgain}`);
    expect(sendErrorText(new ApiError("ASSISTANT_UNAVAILABLE", "x", false, 503), t)).toBe(`${t.unavailable} ${t.tryLater}`);
    expect(sendErrorText(new ApiError("BACKEND_UNREACHABLE", "x", true), t)).toBe(`${t.unreachable} ${t.tryAgain}`);
    expect(sendErrorText(new ApiError("HTTP_500", "x", true, 500), t)).toBe(`${t.serverError} ${t.tryAgain}`);
    expect(sendErrorText(new Error("boom"), t)).toBe(`${t.serverError} ${t.tryAgain}`);
  });
  it("never shows the server's own message", () => {
    const leaky = new ApiError("NEEDS_API_KEY", "OPENROUTER_API_KEY is not configured in backend/.env", false, 503);
    expect(sendErrorText(leaky, t)).not.toMatch(/OPENROUTER|\.env/);
    expect(sendErrorText(leaky, UI.es)).toContain("oficina");
  });
});

describe("greeting and labels", () => {
  it("keeps the greeting to one short line with the AI disclosure", () => {
    const g = greeting(GUEST);
    expect(g.split(/\s+/).length).toBeLessThanOrEqual(25);
    expect(g).toMatch(/automated assistant, not a person/);
  });

  it("labels the build in both languages", () => {
    expect(UI.en.buildLabel).toBe("Version");
    expect(UI.es.buildLabel).toBe("Versión");
  });
});

describe("session ids", () => {
  it("creates backend-compatible session ids", () => {
    const id = newSessionId();
    expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
    expect(newSessionId()).not.toBe(id);
  });
});
