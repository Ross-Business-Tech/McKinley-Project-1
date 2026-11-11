import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A stand-in for the Supabase browser library: no network, and we can see exactly what the page asks of it.
const auth = {
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
  signOut: vi.fn(),
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
};
const createClient = vi.fn(() => ({ auth }));
vi.mock("@supabase/supabase-js", () => ({ createClient }));

async function load(configured = true) {
  vi.resetModules();
  if (configured) {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://abcdefgh.supabase.co/");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example");
  } else {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "");
  }
  return import("./auth");
}

beforeEach(() => {
  for (const fn of Object.values(auth)) fn.mockReset();
  auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  createClient.mockClear();
});
afterEach(() => vi.unstubAllEnvs());

describe("sign-in is off unless both public settings exist", () => {
  it("is off without them and never loads the library", async () => {
    const a = await load(false);
    expect(a.AUTH_CONFIGURED).toBe(false);
    expect(await a.getSession()).toBeNull();
    expect(await a.getAccessToken()).toBeNull();
    expect(createClient).not.toHaveBeenCalled();
  });

  it("is on with them, trims the address, and keeps the session in this browser only", async () => {
    const a = await load();
    expect(a.AUTH_CONFIGURED).toBe(true);
    auth.getSession.mockResolvedValue({ data: { session: { access_token: "tok" } } });
    expect(await a.getAccessToken()).toBe("tok");
    expect(createClient).toHaveBeenCalledWith("https://abcdefgh.supabase.co", "sb_publishable_example",
      expect.objectContaining({ auth: expect.objectContaining({ persistSession: true, autoRefreshToken: true, detectSessionInUrl: false }) }));
  });

  it("treats a failing session lookup as signed out", async () => {
    const a = await load();
    auth.getSession.mockRejectedValue(new Error("storage blocked"));
    expect(await a.getSession()).toBeNull();
  });
});

describe("emailing a code", () => {
  it("never creates an account (invite-only) and trims the email", async () => {
    const a = await load();
    auth.signInWithOtp.mockResolvedValue({ error: null });
    await a.requestCode("  me@example.com ");
    expect(auth.signInWithOtp).toHaveBeenCalledWith({ email: "me@example.com", options: { shouldCreateUser: false } });
  });

  it("answers the same way for an email that is not on the list (no way to find out who is)", async () => {
    const a = await load();
    for (const error of [{ code: "otp_disabled", message: "x" }, { message: "Signups not allowed for otp" }]) {
      auth.signInWithOtp.mockResolvedValue({ error });
      await expect(a.requestCode("stranger@example.com")).resolves.toBeUndefined();
    }
  });

  it("explains a rate limit in plain words and keeps the library's wording out of it", async () => {
    const a = await load();
    auth.signInWithOtp.mockResolvedValue({ error: { status: 429, code: "over_email_send_rate_limit", message: "email rate limit exceeded" } });
    await expect(a.requestCode("me@example.com")).rejects.toMatchObject({ code: "RATE_LIMITED", message: expect.stringContaining("wait a minute") });
  });

  it("explains a network problem", async () => {
    const a = await load();
    auth.signInWithOtp.mockResolvedValue({ error: { status: 0, message: "Failed to fetch" } });
    await expect(a.requestCode("me@example.com")).rejects.toMatchObject({ code: "NETWORK" });
  });
});

describe("checking the code", () => {
  it("sends the code without spaces as an email code", async () => {
    const a = await load();
    auth.verifyOtp.mockResolvedValue({ error: null });
    await a.confirmCode("me@example.com", "123 456");
    expect(auth.verifyOtp).toHaveBeenCalledWith({ email: "me@example.com", token: "123456", type: "email" });
  });

  it("a wrong or expired code gets one clear message", async () => {
    const a = await load();
    auth.verifyOtp.mockResolvedValue({ error: { status: 403, message: "Token has expired or is invalid" } });
    await expect(a.confirmCode("me@example.com", "000000")).rejects.toMatchObject({ code: "BAD_CODE", message: expect.stringContaining("did not work") });
  });
});

describe("signing out and watching for changes", () => {
  it("signs out even if Supabase cannot be reached", async () => {
    const a = await load();
    auth.signOut.mockRejectedValue(new Error("offline"));
    await expect(a.signOut()).resolves.toBeUndefined();
  });

  it("reports session changes and can stop listening", async () => {
    const a = await load();
    const unsubscribe = vi.fn();
    let listener: (e: string, s: unknown) => void = () => undefined;
    auth.onAuthStateChange.mockImplementation(((cb: typeof listener) => {
      listener = cb;
      return { data: { subscription: { unsubscribe } } };
    }) as never);
    const seen: unknown[] = [];
    const stop = await a.onSessionChange((s) => seen.push(s));
    listener("SIGNED_IN", { access_token: "t" });
    listener("SIGNED_OUT", null);
    expect(seen).toEqual([{ access_token: "t" }, null]);
    stop();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
