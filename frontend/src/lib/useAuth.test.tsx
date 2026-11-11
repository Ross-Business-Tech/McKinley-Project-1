import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Sess = null | { user: { email: string }; access_token: string };
// vi.mock is hoisted above everything else, so the shared state it reads has to be hoisted too
const shared = vi.hoisted(() => ({ configured: true, session: { current: null as Sess }, listeners: [] as ((s: Sess) => void)[] }));
const { session, listeners } = shared;

vi.mock("./auth", () => ({
  get AUTH_CONFIGURED() {
    return shared.configured;
  },
  getSession: vi.fn(async () => session.current),
  getAccessToken: vi.fn(async () => session.current?.access_token ?? null),
  onSessionChange: vi.fn(async (cb: (s: typeof session.current) => void) => {
    listeners.push(cb);
    return () => listeners.splice(listeners.indexOf(cb), 1);
  }),
  requestCode: vi.fn(), confirmCode: vi.fn(), signOut: vi.fn(),
}));
const me = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ LIVE_BACKEND_CONFIGURED: true, api: { me: () => me() }, setTokenProvider: vi.fn() }));

import { useAuth } from "./useAuth";

beforeEach(() => {
  shared.configured = true;
  session.current = null;
  listeners.length = 0;
  me.mockReset();
});
afterEach(cleanup);

describe("useAuth", () => {
  it("is off, and immediately ready, when sign-in is not configured", () => {
    shared.configured = false;
    const { result } = renderHook(() => useAuth());
    expect(result.current).toMatchObject({ status: "off", ready: true, role: null });
  });

  it("settles to signed out with no session", async () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current).toMatchObject({ status: "loading", ready: false, key: null });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ status: "signedOut", email: null, key: "out" });
  });

  it("is not ready until the backend has said who the signed-in person is, then reports the role", async () => {
    session.current = { user: { email: "Me@Example.com" }, access_token: "t" };
    let answer: (v: unknown) => void = () => undefined;
    me.mockReturnValue(new Promise((r) => (answer = r)));
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.status).toBe("signedIn"));
    expect(result.current).toMatchObject({ email: "me@example.com", ready: false, key: null, role: null });
    await act(async () => answer({ auth_enabled: true, status: "signed_in", role: "resident", persona_id: "R001" }));
    expect(result.current).toMatchObject({ ready: true, role: "resident", key: "in:me@example.com:signed_in:resident" });
  });

  it("gives no role to someone the backend says is not invited", async () => {
    session.current = { user: { email: "x@example.com" }, access_token: "t" };
    me.mockResolvedValue({ auth_enabled: true, status: "not_invited", role: null, persona_id: null });
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.role).toBeNull();
    expect(result.current.me?.status).toBe("not_invited");
  });

  it("stays usable when the backend cannot be reached", async () => {
    session.current = { user: { email: "x@example.com" }, access_token: "t" };
    me.mockRejectedValue(new Error("down"));
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current).toMatchObject({ status: "signedIn", role: null, me: null });
  });

  it("follows a sign-out and a new sign-in, with a different key each time", async () => {
    session.current = { user: { email: "a@example.com" }, access_token: "t" };
    me.mockResolvedValue({ auth_enabled: true, status: "signed_in", role: "staff", persona_id: null });
    const { result } = renderHook(() => useAuth());
    await waitFor(() => expect(result.current.role).toBe("staff"));
    const first = result.current.key;
    await act(async () => listeners.forEach((l) => l(null)));
    expect(result.current).toMatchObject({ status: "signedOut", key: "out", role: null });
    me.mockResolvedValue({ auth_enabled: true, status: "signed_in", role: "resident", persona_id: "R001" });
    await act(async () => listeners.forEach((l) => l({ user: { email: "b@example.com" }, access_token: "u" })));
    await waitFor(() => expect(result.current.role).toBe("resident"));
    expect(result.current.key).not.toBe(first);
  });
});
