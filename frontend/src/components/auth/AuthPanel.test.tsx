import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthUiError } from "@/lib/auth";
import type { Auth } from "@/lib/useAuth";

import { AuthButton, AuthForm, NotInvitedNote } from "./AuthPanel";

afterEach(cleanup);

function fake(over: Partial<Auth> = {}): Auth {
  return {
    status: "signedOut", email: null, me: null, ready: true, key: "out", role: null,
    requestCode: vi.fn().mockResolvedValue(undefined), confirmCode: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined), ...over,
  };
}
const me = (status: "signed_in" | "not_invited", role: "resident" | "staff" | null = null) =>
  ({ auth_enabled: true, status, role, persona_id: null }) as Auth["me"];

describe("AuthButton", () => {
  it("renders nothing when this site has no sign-in", () => {
    const { container } = render(<AuthButton auth={fake({ status: "off" })} open={false} onToggle={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("offers Sign in when signed out and announces the form it controls", async () => {
    const toggle = vi.fn();
    render(<AuthButton auth={fake()} open={false} onToggle={toggle} />);
    const btn = screen.getByRole("button", { name: /sign in/i });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(btn).toHaveAttribute("aria-controls");
    await userEvent.click(btn);
    expect(toggle).toHaveBeenCalled();
  });

  it("says who is signed in and signs out", async () => {
    const auth = fake({ status: "signedIn", email: "me@example.com", role: "resident", me: me("signed_in", "resident"), key: "k" });
    render(<AuthButton auth={auth} open={false} onToggle={() => undefined} />);
    expect(screen.getByText("me@example.com")).toBeInTheDocument();
    expect(screen.getByText(/\(resident\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(auth.signOut).toHaveBeenCalled();
  });

  it("shows a status while the sign-in state is still loading", () => {
    render(<AuthButton auth={fake({ status: "loading", ready: false, key: null })} open={false} onToggle={() => undefined} />);
    expect(screen.getByRole("status")).toHaveTextContent(/checking sign-in/i);
  });
});

describe("AuthForm", () => {
  it("emails a code, then signs in with it, then closes and returns focus", async () => {
    const auth = fake();
    const onClose = vi.fn();
    const onSignedIn = vi.fn();
    const onReturnFocus = vi.fn();
    render(<AuthForm auth={auth} onClose={onClose} onSignedIn={onSignedIn} onReturnFocus={onReturnFocus} />);
    const email = screen.getByLabelText(/email address/i);
    expect(email).toHaveFocus();
    await userEvent.type(email, "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /email me a code/i }));
    expect(auth.requestCode).toHaveBeenCalledWith("me@example.com");
    // the reply never claims the email is on the list
    expect(await screen.findByRole("status")).toHaveTextContent(/if me@example.com is on the invite list/i);
    const code = screen.getByLabelText(/code from your email/i);
    await waitFor(() => expect(code).toHaveFocus());
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await userEvent.type(code, "12a3 456");
    expect(code).toHaveValue("123 456"); // only digits (and spaces) are accepted
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    expect(auth.confirmCode).toHaveBeenCalledWith("me@example.com", "123 456");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onSignedIn).toHaveBeenCalled();
    await waitFor(() => expect(onReturnFocus).toHaveBeenCalled());
  });

  it("shows a wrong-code message as an alert and stays open for another try", async () => {
    const auth = fake({ confirmCode: vi.fn().mockRejectedValue(new AuthUiError("That code did not work or has expired.", "BAD_CODE")) });
    const onClose = vi.fn();
    render(<AuthForm auth={auth} onClose={onClose} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /email me a code/i }));
    await userEvent.type(await screen.findByLabelText(/code from your email/i), "000000");
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/did not work/i);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeEnabled(); // not left stuck on "Checking…"
  });

  it("shows a friendly alert when the email step fails and never advances", async () => {
    const auth = fake({ requestCode: vi.fn().mockRejectedValue(new AuthUiError("Too many codes were requested.", "RATE_LIMITED")) });
    render(<AuthForm auth={auth} onClose={() => undefined} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /email me a code/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many codes/i);
    expect(screen.queryByLabelText(/code from your email/i)).not.toBeInTheDocument();
  });

  it("lets someone go back and use a different email, and cancel with a button or Escape", async () => {
    const onClose = vi.fn();
    const onReturnFocus = vi.fn();
    render(<AuthForm auth={fake()} onClose={onClose} onReturnFocus={onReturnFocus} />);
    await userEvent.type(screen.getByLabelText(/email address/i), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /email me a code/i }));
    await userEvent.click(await screen.findByRole("button", { name: /use a different email/i }));
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
    expect(onReturnFocus).toHaveBeenCalled();
  });

  it("does nothing with an empty email", async () => {
    const auth = fake();
    render(<AuthForm auth={auth} onClose={() => undefined} />);
    expect(screen.getByRole("button", { name: /email me a code/i })).toBeDisabled();
  });
});

describe("NotInvitedNote", () => {
  it("only appears for someone who signed in but is not on the invite list", () => {
    const { rerender } = render(<NotInvitedNote auth={fake()} />);
    expect(screen.queryByTestId("not-invited")).not.toBeInTheDocument();
    rerender(<NotInvitedNote auth={fake({ status: "signedIn", me: me("signed_in", "resident") })} />);
    expect(screen.queryByTestId("not-invited")).not.toBeInTheDocument();
    rerender(<NotInvitedNote auth={fake({ status: "signedIn", me: me("not_invited") })} />);
    expect(screen.getByTestId("not-invited")).toHaveTextContent(/not on the invite list/i);
  });
});
