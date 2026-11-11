// Supabase sign-in from the browser: an emailed one-time code, no passwords. Only the PUBLIC project address and the
// publishable (anon) key live here; both are meant to be public. The secret keys and the database address never
// reach the website. The backend is what decides who someone is (it checks the token and the invite list); this
// file only gets a token. `process.env.NEXT_PUBLIC_*` must be read literally so Next.js can inline it at build time.
import type { Session, SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").replace(/\/$/, "");
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

/** False on the here.now replay and on any build without both settings: the page then shows no sign-in at all. */
export const AUTH_CONFIGURED = Boolean(SUPABASE_URL && SUPABASE_KEY);

/** A problem with a plain-words message that is safe to show a customer. */
export class AuthUiError extends Error {
  constructor(
    message: string,
    public code: "RATE_LIMITED" | "BAD_CODE" | "NETWORK" | "OTHER",
  ) {
    super(message);
    this.name = "AuthUiError";
  }
}

let clientPromise: Promise<SupabaseClient> | null = null;

// Loaded on first use, so a build or page that never signs in never downloads the library.
function client(): Promise<SupabaseClient> {
  clientPromise ??= import("@supabase/supabase-js").then(({ createClient }) =>
    createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false, storageKey: "mckinley-auth" },
    }),
  );
  return clientPromise;
}

export async function getSession(): Promise<Session | null> {
  if (!AUTH_CONFIGURED) return null;
  try {
    const { data } = await (await client()).auth.getSession();
    return data.session;
  } catch {
    return null;
  }
}

export async function getAccessToken(): Promise<string | null> {
  return (await getSession())?.access_token ?? null;
}

function describe(e: { status?: number; message?: string; code?: string } | null | undefined, fallback: AuthUiError["code"]): AuthUiError {
  const msg = (e?.message ?? "").toLowerCase();
  if (e?.status === 429 || e?.code === "over_email_send_rate_limit" || msg.includes("rate limit") || msg.includes("seconds")) {
    return new AuthUiError("Too many codes were requested. Please wait a minute and try again.", "RATE_LIMITED");
  }
  if (e?.status === 0 || msg.includes("fetch") || msg.includes("network")) {
    return new AuthUiError("Could not reach the sign-in service. Check your connection and try again.", "NETWORK");
  }
  if (fallback === "BAD_CODE") {
    return new AuthUiError("That code did not work or has expired. Use the newest email, or ask for a new code.", "BAD_CODE");
  }
  return new AuthUiError("Something went wrong. Please try again.", "OTHER");
}

/** Email a one-time code. Sign-up is invite-only: this never creates an account, and it never says whether the email
 * is on the list (so nobody can use it to find out who is), it always reads the same. */
export async function requestCode(email: string): Promise<void> {
  const { error } = await (await client()).auth.signInWithOtp({ email: email.trim(), options: { shouldCreateUser: false } });
  if (!error) return;
  const code = (error as { code?: string }).code ?? "";
  const msg = (error.message ?? "").toLowerCase();
  if (code === "otp_disabled" || code === "signup_disabled" || msg.includes("signups not allowed")) return; // unknown email: same reply
  throw describe(error, "OTHER");
}

export async function confirmCode(email: string, code: string): Promise<void> {
  const { error } = await (await client()).auth.verifyOtp({ email: email.trim(), token: code.replace(/\s+/g, ""), type: "email" });
  if (error) throw describe(error, "BAD_CODE");
}

export async function signOut(): Promise<void> {
  try {
    await (await client()).auth.signOut();
  } catch {
    /* the local session is cleared even if Supabase could not be told */
  }
}

/** Calls back whenever the session changes (sign in, sign out, refresh). Returns the unsubscribe function. */
export async function onSessionChange(cb: (session: Session | null) => void): Promise<() => void> {
  const { data } = (await client()).auth.onAuthStateChange((_event, session) => cb(session));
  return () => data.subscription.unsubscribe();
}
