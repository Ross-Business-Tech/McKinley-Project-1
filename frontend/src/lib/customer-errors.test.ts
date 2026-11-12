import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { UI, sendErrorText } from "./customer";

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
