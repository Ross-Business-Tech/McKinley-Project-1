# Deploy: Render (website + backend) and Supabase (database + sign-in)

Puts a typeable, signed-in version of the prototype online. Ross IT approved hosting outside here.now on Render for
both the website and the backend, with Supabase for the database and for sign-in. The team's **here.now pipeline is
unchanged** and still serves the recorded replay (no backend, no sign-in), so keep it as the fallback until this site
is checked on real phones.

```
Phone/browser ──► Render static site  (the website; NEXT_PUBLIC_* settings are public)
   │  sign-in code by email           │  calls NEXT_PUBLIC_API_BASE_URL with the sign-in token
   ▼                                  ▼
Supabase Auth                      Render web service (Python backend; checks the token + the invite list)
                                      │  DATABASE_URL (backend only)
                                      ▼
                                   Supabase Postgres (saved chats and requests, the invite list)
```

The data is made up, the repository is public, and this is **not production ready** (see the README). Never paste a
key, password or connection string into a file, commit, pull request or chat. They go only in the settings pages
below. Sign-in design and limits: [../security/SUPABASE_AUTH.md](../security/SUPABASE_AUTH.md).

## 1. Supabase (about 20 minutes)

1. Create a project at supabase.com. Save the database password privately.
2. **Database address.** Click **Connect**, choose **Session pooler**, copy the `postgresql://…` string and replace
   `[YOUR-PASSWORD]` (URL-encode symbols: `@` becomes `%40`). Use the **pooler**, not "Direct connection": Render
   cannot reach Supabase's direct address. This is `DATABASE_URL` (a secret).
3. **Sign-in settings** (the checklist in [SUPABASE_AUTH.md](../security/SUPABASE_AUTH.md#one-time-supabase-setup-about-15-minutes-in-the-supabase-dashboard)):
   turn **off** "Allow new users to sign up", put `{{ .Token }}` in the **Magic Link** email template, and set up
   custom SMTP if testers are outside your Supabase organization.
4. Note two public values for later: the **project address** (`https://<ref>.supabase.co`) and the **publishable
   key** (`sb_publishable_…`, or the older `anon` key). Never use the secret / `service_role` key.

The backend creates its own tables on first start (migrations run before every start) with row-level security on and
no policies, so Supabase's public Data API can read nothing.

## 2. Render: apply the Blueprint (about 10 minutes)

1. At render.com choose **New > Blueprint**, connect the GitHub repository and pick the branch to deploy. Render
   reads `render.yaml` and proposes two services: **mckinley-backend** and **mckinley-site**.
2. Enter the values it asks for. Anything you do not know yet can be a placeholder (you fix it in step 4):

   | Service | Setting | Value |
   | --- | --- | --- |
   | backend | `DATABASE_URL` | the Supabase Session pooler string (secret) |
   | backend | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | backend | `CORS_ORIGINS` | placeholder for now, e.g. `https://placeholder.onrender.com` |
   | site | `NEXT_PUBLIC_API_BASE_URL` | placeholder for now |
   | site | `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
   | site | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | the publishable key |

3. Wait for the deploy. Open `https://<backend>.onrender.com/api/health`: it should show `"status":"ok"`. Copy the
   backend address and the website address (`https://<site>.onrender.com`).
4. **Connect them.** Set the site's `NEXT_PUBLIC_API_BASE_URL` to the backend address (no trailing slash) and
   **redeploy the site** (it is baked in at build time). Set the backend's `CORS_ORIGINS` to the exact website
   address (comma-separate more than one) and let the backend redeploy. Without the second step the browser blocks
   every message.

The Blueprint uses the built-in rules responder (`LLM_PROVIDER=mock`), so no AI key is needed. Replies come from the
approved wording and rules, not a language model. To use Gemini later: set `LLM_PROVIDER=gemini`, delete `LLM_MODEL`,
add `GEMINI_API_KEY` (a secret) in Render, and follow [../deployment/gemini.md](../deployment/gemini.md).

## 3. Load the made-up residents and invite people

Run these once from your own computer, in `backend/`, with `DATABASE_URL` set to the same Supabase string
(`export DATABASE_URL=...`; do not commit it):

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.seed_synthetic          # the made-up residents (needs the synthetic workbook, see the README)
uv run python -m app.manage_users add --email name@example.com --role resident --persona R001
uv run python -m app.manage_users add --email name@example.com --role staff
```

Each invited person also needs a Supabase user (Authentication > Users > **Add user**, *Auto confirm*). Details and
the removal steps are in [SUPABASE_AUTH.md](../security/SUPABASE_AUTH.md#inviting-and-removing-people-two-steps).

## 4. Check it (on a phone)

1. Open the website address. It should be signed out, with a **Sign in** button. Ask "Can I tour this week?".
2. **Sign in** with an invited resident's email, enter the code from the email, and report a repair: the reply should
   use that resident's own history. Sign out: a fresh conversation starts.
3. Sign in as staff and open `/staff`: the live tabs load, and the header says (staff).
4. Sign in with an email that is **not** invited: the page says so, and general questions still work.
5. In Supabase, **Table Editor > prototype_records** shows the saved request.

## What to expect

- **Free plans sleep.** The backend's free plan pauses when idle, so the first message after a pause can take about a
  minute (the page shows a waking-up message). Supabase's free plan can pause a project after about a week with no
  activity; restore it from the dashboard. The static site has no such delay.
- **Everything saved is made-up data**, but anyone with the link can use the chat as a guest. Do not put real
  personal information into it.
- **The here.now replay is separate**: it is built without the sign-in and backend settings, so it shows no sign-in.
- **Staff tools on Render** need a staff sign-in (or the `STAFF_API_TOKEN` for scripts). By design the staff routes
  never trust "from this machine" on a hosted backend.

## Running locally against Supabase (optional)

Put `DATABASE_URL=...` (and `SUPABASE_URL=...`) in `backend/.env` and `NEXT_PUBLIC_SUPABASE_URL` /
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `frontend/.env.local` (both git-ignored). Without them, the backend keeps using
the local SQLite file and the website shows no sign-in.

## Tests

SQLite always runs. The same Store, migration and invite-list checks run on Postgres when you point them at a
**throwaway** database (they empty its tables, so never use the real one):

```bash
cd backend
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/scratch uv run pytest tests/test_store_backends.py tests/test_migrations.py
```
