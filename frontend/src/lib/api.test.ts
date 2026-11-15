import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, demoSignInAvailable, loadDemoSnapshot, parseError } from "./api";
import type { Health, Persona } from "./types";

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

  it("keeps the message of structured HTTPException details (e.g. staff-only 403)", async () => {
    const body = { detail: { code: "STAFF_ONLY", message: "Staff tools are local only.", retryable: false } };
    const e = await parseError(new Response(JSON.stringify(body), { status: 403 }));
    expect(e.code).toBe("STAFF_ONLY");
    expect(e.message).toBe("Staff tools are local only.");
    expect(e.status).toBe(403);
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

  it("loads the root-relative demo snapshot and rejects unexpected shapes", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ kind: "static_demo_snapshot", personas: [] })),
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

describe("demo sign-in availability (backend decides)", () => {
  const persona: Persona = { id: "R001", label: "R001 · Marisol (synthetic resident)", kind: "resident", description: "d", synthetic: true };
  const health = (demo?: boolean) => ({ status: "ok", provider: "mock", model: "m", provider_ready: true, provider_status: "ok",
    prompt_version: "v", data_loaded: true, data_error: null, resident_count: 1, interaction_count: 1, demo_personas_enabled: demo }) as Health;

  it("is off when the backend says demo personas are disabled, even if personas were returned", () => {
    expect(demoSignInAvailable([persona], health(false))).toBe(false);
  });
  it("is off when there are no personas (hosted backend)", () => {
    expect(demoSignInAvailable([], health(undefined))).toBe(false);
    expect(demoSignInAvailable([], null)).toBe(false);
  });
  it("is on for a local backend with personas (older backends omit the field)", () => {
    expect(demoSignInAvailable([persona], health(true))).toBe(true);
    expect(demoSignInAvailable([persona], health(undefined))).toBe(true);
    expect(demoSignInAvailable([persona], null)).toBe(true);
  });
});
