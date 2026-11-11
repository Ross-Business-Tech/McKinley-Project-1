"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { LIVE_BACKEND_CONFIGURED, api, setTokenProvider } from "./api";
import * as supabase from "./auth";
import type { Me } from "./types";

export type AuthStatus = "off" | "loading" | "signedOut" | "signedIn";

export interface Auth {
  /** off = no sign-in on this site | loading | signedOut | signedIn (a Supabase session exists) */
  status: AuthStatus;
  email: string | null;
  /** What the backend makes of the sign-in: invited resident, invited staff, or not on the invite list. */
  me: Me | null;
  /** Settled: not loading, and for a signed-in person the backend has answered. Safe to react to changes. */
  ready: boolean;
  /** Changes whenever who is signed in (or what they are allowed to be) changes; null until ready. */
  key: string | null;
  role: "resident" | "staff" | null; // only when the backend confirmed an invited person
  requestCode: (email: string) => Promise<void>;
  confirmCode: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
}

if (supabase.AUTH_CONFIGURED) setTokenProvider(supabase.getAccessToken);

/** One place that knows who is signed in. When sign-in is not configured it is "off" and costs nothing. */
export function useAuth(): Auth {
  const [status, setStatus] = useState<AuthStatus>(supabase.AUTH_CONFIGURED ? "loading" : "off");
  const [email, setEmail] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [meDone, setMeDone] = useState(false);

  useEffect(() => {
    if (!supabase.AUTH_CONFIGURED) return;
    let cancelled = false;
    let unsubscribe: (() => void) | null = null;
    const apply = (session: { user?: { email?: string | null } } | null) => {
      if (cancelled) return;
      setEmail(session?.user?.email?.toLowerCase() ?? null);
      setStatus(session ? "signedIn" : "signedOut");
      setMe(null);
      setMeDone(!session); // a signed-in person is not "ready" until the backend has answered
    };
    supabase.getSession().then(apply);
    supabase.onSessionChange(apply).then((u) => {
      if (cancelled) u();
      else unsubscribe = u;
    });
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  // Ask the backend who it thinks this is, once per sign-in. It never returns the token or the email.
  useEffect(() => {
    if (status !== "signedIn") return;
    let cancelled = false;
    (LIVE_BACKEND_CONFIGURED ? api.me() : Promise.resolve(null))
      .catch(() => null)
      .then((m) => {
        if (cancelled) return;
        setMe(m);
        setMeDone(true);
      });
    return () => {
      cancelled = true;
    };
  }, [status, email]);

  const requestCode = useCallback((e: string) => supabase.requestCode(e), []);
  const confirmCode = useCallback((e: string, c: string) => supabase.confirmCode(e, c), []);
  const signOut = useCallback(() => supabase.signOut(), []);

  return useMemo(() => {
    const ready = status === "off" || (status !== "loading" && meDone);
    const role = me?.status === "signed_in" ? me.role : null;
    const key = !ready ? null : status === "signedIn" ? `in:${email}:${me?.status ?? "unknown"}:${role ?? "none"}` : "out";
    return { status, email, me, ready, key, role, requestCode, confirmCode, signOut };
  }, [status, email, me, meDone, requestCode, confirmCode, signOut]);
}
