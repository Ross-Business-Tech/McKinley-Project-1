import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, loadDemoSnapshot, parseError } from "./api";

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

  it("sends an optional gate provider override with chat requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ reply: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.chat({ message: "hi", persona_id: null, mode: "prompt_only", session_id: "s", target: "mock:m", gate_provider: "llm" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ mode: "prompt_only", gate_provider: "llm" });
  });

  it("posts gate providers to the gate evaluation endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ note: "", summary: {}, rows: [] })));
    vi.stubGlobal("fetch", fetchMock);
    await api.evaluateGates(["rules", "llm"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/gates\/evaluate$/);
    expect(JSON.parse(init.body)).toEqual({ providers: ["rules", "llm"] });
  });

  it("loads the root-relative demo snapshot and rejects unexpected shapes", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ kind: "static_demo_snapshot", responses: {}, cases: [] })),
    ).mockResolvedValueOnce(new Response(JSON.stringify({ hello: 1 })));
    vi.stubGlobal("fetch", fetchMock);
    await expect(loadDemoSnapshot()).resolves.toMatchObject({ kind: "static_demo_snapshot" });
    expect(fetchMock.mock.calls[0][0]).toBe("/demo/snapshot.json");
    await expect(loadDemoSnapshot()).rejects.toMatchObject({ code: "SNAPSHOT_INVALID" });
  });

  it("ApiError is an Error", () => {
    expect(new ApiError("X", "y")).toBeInstanceOf(Error);
  });
});
