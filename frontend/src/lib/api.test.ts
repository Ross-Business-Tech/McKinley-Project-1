import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, parseError } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("maps backend error envelopes", async () => {
    const res = new Response(JSON.stringify({ error: { code: "NEEDS_API_KEY", message: "set key", retryable: false } }), {
      status: 503,
    });
    const e = await parseError(res);
    expect(e.code).toBe("NEEDS_API_KEY");
    expect(e.status).toBe(503);
  });

  it("maps validation errors", async () => {
    const e = await parseError(new Response(JSON.stringify({ detail: [{ msg: "bad" }] }), { status: 422 }));
    expect(e.code).toBe("VALIDATION_ERROR");
  });

  it("reports unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(api.health()).rejects.toMatchObject({ code: "BACKEND_UNREACHABLE" });
  });

  it("never sends credentials or keys in chat requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ reply: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.chat({ message: "hi", persona_id: null, mode: "aware", session_id: "s", target: "mock:m" });
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.stringify(init)).not.toMatch(/api[_-]?key|authorization/i);
    expect(JSON.parse(init.body)).toEqual({ message: "hi", persona_id: null, mode: "aware", session_id: "s", target: "mock:m" });
  });

  it("ApiError is an Error", () => {
    expect(new ApiError("X", "y")).toBeInstanceOf(Error);
  });
});
