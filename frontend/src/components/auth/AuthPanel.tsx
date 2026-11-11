"use client";

import { LogIn, LogOut } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { AuthUiError } from "@/lib/auth";
import type { Auth } from "@/lib/useAuth";
import { cn } from "@/lib/utils";

/** The one-line sign-in control: "Sign in" when signed out, "Signed in as … / Sign out" when signed in. Renders
 * nothing when this site has no sign-in (the here.now replay). The form opens below it (AuthForm). */
export function AuthButton({
  auth,
  open,
  onToggle,
  onSignOut,
  tone = "light",
}: {
  auth: Auth;
  open: boolean;
  onToggle: () => void;
  onSignOut?: () => void;
  tone?: "light" | "band";
}) {
  const formId = useId();
  if (auth.status === "off") return null;
  const band = tone === "band";
  const buttonClass = cn(
    "mk-focus inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-md px-3 font-medium",
    band ? "border border-white/80 text-white hover:bg-white/10" : "text-mk-brand-hover hover:bg-mk-brand-soft aria-expanded:bg-mk-brand-soft",
  );
  if (auth.status === "loading") {
    return (
      <span role="status" className={cn("min-h-11 py-2.5 text-sm", band ? "text-white/90" : "text-mk-muted")}>
        Checking sign-in…
      </span>
    );
  }
  if (auth.status === "signedIn") {
    const who = auth.role === "staff" ? "staff" : auth.role === "resident" ? "resident" : null;
    return (
      <div className="flex min-w-0 items-center gap-1" data-testid="auth-signed-in">
        <p className={cn("min-w-0 truncate text-sm", band ? "text-white" : "text-mk-muted")} title={auth.email ?? undefined}>
          <span className="sr-only">Signed in as </span>
          <span className="font-medium">{auth.email}</span>
          {who ? <span> ({who})</span> : null}
        </p>
        <button type="button" onClick={onSignOut ?? (() => void auth.signOut())} className={buttonClass}>
          <LogOut aria-hidden className="size-5" />
          <span className="sr-only sm:not-sr-only">Sign out</span>
        </button>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 items-center gap-1">
      <p className={cn("min-w-0 truncate text-sm", band ? "text-white/90" : "text-mk-muted")}>Not signed in</p>
      <button type="button" aria-expanded={open} aria-controls={formId} onClick={onToggle} className={buttonClass}>
        <LogIn aria-hidden className="size-5" />
        <span>Sign in</span>
      </button>
    </div>
  );
}

type Step = "email" | "code";

/** The sign-in form: email, then the code we emailed. Invite-only (the reply never says whether an email is on the
 * list). Close with Escape or the Cancel button; on success it closes and tells the page. */
export function AuthForm({
  auth,
  onClose,
  onSignedIn,
  onReturnFocus,
}: {
  auth: Auth;
  onClose: () => void;
  onSignedIn?: () => void;
  /** Put keyboard focus back on the sign-in control once the form closes. */
  onReturnFocus?: () => void;
}) {
  const id = useId();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [problem, setProblem] = useState("");
  const emailRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    emailRef.current?.focus();
  }, []);
  useEffect(() => {
    if (step === "code") codeRef.current?.focus();
  }, [step]);

  const fail = (e: unknown) => setProblem(e instanceof AuthUiError ? e.message : "Something went wrong. Please try again.");

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !email.trim()) return;
    setBusy(true);
    setProblem("");
    try {
      await auth.requestCode(email);
      setStep("code");
      setCode("");
      setNotice(`If ${email.trim()} is on the invite list, a code is on its way. It can take a minute.`);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function checkCode(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !code.trim()) return;
    setBusy(true);
    setProblem("");
    try {
      await auth.confirmCode(email, code);
      onSignedIn?.();
      onClose();
      requestAnimationFrame(() => onReturnFocus?.());
    } catch (err) {
      fail(err);
      setBusy(false);
      codeRef.current?.select();
    }
  }

  const field = "mk-focus h-11 w-full rounded-md border border-mk-line-strong bg-mk-surface px-3 text-base";
  const primary = "mk-focus inline-flex min-h-11 items-center justify-center rounded-md bg-mk-brand px-4 font-semibold text-white hover:bg-mk-brand-hover disabled:opacity-60";
  const quiet = "mk-focus inline-flex min-h-11 items-center justify-center rounded-md px-3 font-medium text-mk-brand-hover underline underline-offset-2";

  return (
    <div
      role="group"
      aria-label="Sign in"
      data-testid="auth-form"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          onClose();
          onReturnFocus?.();
        }
      }}
      className="mx-auto w-full max-w-2xl px-[max(1rem,env(safe-area-inset-left))] pb-3 sm:px-4"
    >
      <div className="rounded-lg bg-mk-paper p-4 text-mk-ink">
        <p className="font-heading text-base font-semibold">Sign in</p>
        <p className="mt-1 text-sm text-mk-muted">
          Sign-in is by invitation. We email you a one-time code, so there is no password to remember.
        </p>
        {step === "email" ? (
          <form onSubmit={sendCode} className="mt-3 space-y-3" noValidate>
            <div>
              <label htmlFor={`${id}-email`} className="block text-sm font-medium">
                Email address
              </label>
              <input
                id={`${id}-email`}
                ref={emailRef}
                type="email"
                inputMode="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={field}
                aria-describedby={problem ? `${id}-problem` : undefined}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="submit" disabled={busy || !email.trim()} className={primary}>
                {busy ? "Sending…" : "Email me a code"}
              </button>
              <button type="button" onClick={onClose} className={quiet}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={checkCode} className="mt-3 space-y-3" noValidate>
            <div>
              <label htmlFor={`${id}-code`} className="block text-sm font-medium">
                Code from your email
              </label>
              <input
                id={`${id}-code`}
                ref={codeRef}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={10}
                required
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9\s]/g, ""))}
                className={cn(field, "tracking-widest")}
                aria-describedby={`${id}-notice${problem ? ` ${id}-problem` : ""}`}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="submit" disabled={busy || !code.trim()} className={primary}>
                {busy ? "Checking…" : "Sign in"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep("email");
                  setProblem("");
                  setNotice("");
                }}
                className={quiet}
              >
                Use a different email
              </button>
              <button type="button" onClick={onClose} className={quiet}>
                Cancel
              </button>
            </div>
          </form>
        )}
        {notice && step === "code" ? (
          <p id={`${id}-notice`} role="status" className="mt-3 text-sm text-mk-muted">
            {notice}
          </p>
        ) : null}
        {problem ? (
          <p id={`${id}-problem`} role="alert" className="mt-3 rounded-md border border-mk-danger bg-mk-danger-soft p-2 text-sm text-mk-danger">
            {problem}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** Shown to someone who signed in but is not on the invite list: they get the same general help as everyone. */
export function NotInvitedNote({ auth }: { auth: Auth }) {
  if (auth.status !== "signedIn" || auth.me?.status !== "not_invited") return null;
  return (
    <p role="note" data-testid="not-invited" className="mx-auto w-full max-w-2xl px-[max(1rem,env(safe-area-inset-left))] pb-2 text-sm text-mk-muted sm:px-4">
      You are signed in, but this email is not on the invite list yet, so I can only help with general questions. Ask the
      team to add you.
    </p>
  );
}
