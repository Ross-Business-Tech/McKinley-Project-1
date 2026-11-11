# Supabase sign-in (residents and staff)

Real sign-in for the prototype: a person gets an **emailed one-time code** (no passwords) and the backend decides
who they are. Companion to [AUTHORIZATION_BOUNDARIES.md](AUTHORIZATION_BOUNDARIES.md).

> **Status: built and tested, never run against a real Supabase project, nothing deployed.** The backend checks,
> the invite list, the website's sign-in form and a full browser journey were tested against a **stand-in** for
> Supabase's sign-in service (a local fake that issues signed tokens). The first real run needs the setup below. It
> is still a prototype on made-up data: sign-in does not make it production ready.

## What a signed-in person can do

| Who | How they are recognised | What changes |
| --- | --- | --- |
| **Anyone** (default) | no token | Public information, tour requests, notes to the office. Unchanged. |
| **Resident** | a valid token **and** the email is on the invite list as a resident linked to ONE **synthetic** resident id | The chat acts as that resident (their own repairs, status, renewal). The browser's demo picker is ignored. |
| **Staff** | a valid token **and** the email is on the invite list as staff | The staff console's live tools on a hosted backend; staff-only chat overrides and diagnostics. A staff sign-in never makes the **chat** act as a resident. |
| Signed in, **not** on the list | a valid token, no invite | Treated exactly like anyone else, and told so on the page. |

## How a request is trusted (all server-side)

1. The website sends `Authorization: Bearer <access token>` with every backend call (from `src/lib/api.ts`).
2. **The token is checked** (`backend/app/supabase_auth.py`): signature (Supabase's published signing key for new
   projects, or `SUPABASE_JWT_SECRET` for legacy ones; no other algorithm, never "none"), audience, issuer, expiry,
   a subject, a verified email, not an anonymous sign-in, and signed in by email code. The public anon key and the
   service-role key are refused.
3. **The invite list is checked** (`backend/app/identity.py`, table `user_profiles`): the email must be on it, not
   disabled, and be the same Supabase account that first signed in as that email (a deleted-and-recreated account must
   be re-invited on purpose). A resident invite without a linked resident id grants nothing.
4. The result becomes the principal (`backend/app/auth.py`). Message text, the model and the browser's persona never
   change it. Data access is still deny-by-default, per session and per resident.

Fail-safe behaviour:
- **A bad, expired or missing token never blocks a chat message** (an emergency must always be answered): the caller
  is anonymous. Signing out mid-conversation starts a new one; the old history is never shown.
- If the backend cannot reach Supabase's signing keys it keeps using the keys it already has; with none, sign-in
  reports "temporarily unavailable" and everyone is anonymous. It never grants access on an error.
- Disabling or removing an invite takes effect on the **next request** (the list is checked every time), even though
  the person's token may stay valid for up to an hour.
- Tokens and secrets are never logged and never appear in any response. `/api/me` returns only a status, a role and
  the synthetic resident id.
- The invite-only reply never reveals whether an email is on the list: "If you@example.com is on the invite list, a
  code is on its way" is shown for every address.

## One-time Supabase setup (about 15 minutes, in the Supabase dashboard)

1. **Authentication > Sign In / Providers > Email**: enabled. Leave **password** sign-in off if you can.
2. **Turn off "Allow new users to sign up"** (invite-only). Otherwise anyone could make a Supabase account and make
   your project send them email.
3. **Authentication > Email Templates > Magic Link**: the body must contain the code, `{{ .Token }}`. The default
   template only has a link. Example body: `Your McKinley prototype sign-in code is {{ .Token }}. It expires soon.`
   (An existing user's code email uses this template.)
4. **Email sending.** Supabase's built-in sender is for testing only: very few emails per hour and, on new projects,
   only to members of your Supabase organization. For testers outside it, set up **custom SMTP**
   (Authentication > Emails > SMTP Settings). Check Supabase's current limits.
5. **Keys** (Project Settings > API Keys):
   - the **publishable** key (`sb_publishable_…`, or the older `anon` key) goes in the website as
     `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. It is public by design.
   - **never** put the secret / `service_role` key anywhere in this project. The backend does not need it.
   - New projects sign tokens with an asymmetric key: nothing else to set. Only a **legacy** project (shared JWT
     secret) needs `SUPABASE_JWT_SECRET` in Render (a secret).
6. The same project address (`https://<ref>.supabase.co`) is `SUPABASE_URL` (Render backend) and
   `NEXT_PUBLIC_SUPABASE_URL` (website). Both are public.

## Inviting and removing people (two steps)

Real email addresses live **only** in Supabase and in the `user_profiles` table. Never put one in the repository, a
pull request or a chat. A resident is linked to a **made-up** resident id, never to a real person's record.

1. **Supabase:** Authentication > Users > **Add user** (tick *Auto confirm user*, no password needed).
2. **The invite list**, from `backend/` with `DATABASE_URL` set to the Supabase connection string:

```bash
uv run python -m app.manage_users add --email name@example.com --role resident --persona R001
uv run python -m app.manage_users add --email name@example.com --role staff
uv run python -m app.manage_users list
uv run python -m app.manage_users disable --email name@example.com     # also: enable, remove
```

`--persona` is checked against the synthetic resident data; run `uv run python -m app.seed_synthetic` first on a new
database. To stop someone: `disable` (instant) and delete the user in Supabase.

## Not covered (be honest about these)

- Never run against a real Supabase project or real email delivery; the fake sign-in service in the browser test
  matches the documented behaviour, not Supabase's live responses. Verify the first real sign-in end to end.
- Supabase's library keeps the session in this browser's local storage. There is no multi-factor sign-in and no
  rate limiting beyond Supabase's own.
- The shared `STAFF_API_TOKEN` still works for scripts (and Render requires it). Treat it as a secret.
- Residents are linked to **synthetic** records only. Real resident data must stay disconnected until the safety and
  approval blockers in [../PROJECT_HANDOFF.md](../PROJECT_HANDOFF.md) are resolved.
- Ross IT should confirm that storing team members' real email addresses (Supabase + `user_profiles`) is acceptable
  for this project's data rules.

## Troubleshooting

| What you see | Likely cause |
| --- | --- |
| The page says "not on the invite list" after sign-in | The email is a Supabase user but not in `user_profiles` (step 2), or it is disabled |
| No code email arrives | Built-in sender limits or recipient not in your Supabase organization (set up SMTP); sign-ups off and no Supabase user (step 1) |
| The email has a link but no code | The *Magic Link* template lacks `{{ .Token }}` |
| "That code did not work or has expired" | Use the newest email; codes are short-lived |
| Signed in but acting as a guest | `SUPABASE_URL` missing or different on Render, or the token expired: sign out and in |
| Every call is refused after a sign-in | `CORS_ORIGINS` does not list the website's exact address |
