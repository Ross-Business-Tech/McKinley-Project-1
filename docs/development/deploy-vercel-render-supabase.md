# Deploy: Vercel (website) + Render (backend) + Supabase (database)

This puts a typeable version of the prototype online. It is **in addition to** the team's here.now pipeline, which
still serves the static replay. Ross IT owns hosting, so get their OK before creating accounts for the team.

```
Phone/browser ──► Vercel (the website, static files)
                     │  calls NEXT_PUBLIC_API_BASE_URL
                     ▼
                  Render (Python backend, rules + safety checks)
                     │  DATABASE_URL
                     ▼
                  Supabase (Postgres: saved chats and requests)
```

The data is made up, the repository is public, and the app is **not production ready** (see the README). Never paste
a key, password or connection string into a file, a commit, a pull request or a chat. They go only in the settings
pages below.

## 1. Supabase (the database), about 5 minutes

1. Create a project at supabase.com. Save the database password somewhere private.
2. Click **Connect**, choose **Session pooler**, and copy the connection string (it starts with `postgresql://`).
   Replace `[YOUR-PASSWORD]` with the database password. If the password has symbols such as `@` or `/`, URL-encode
   them (`@` becomes `%40`).
   - Use the **pooler** string, not "Direct connection": Render cannot reach Supabase's direct address.
3. From your own computer, create the tables and load the **synthetic** sample residents (the backend on Render has
   no copy of the workbook):
   ```bash
   cd backend
   DATABASE_URL='postgresql://…' uv run alembic upgrade head
   DATABASE_URL='postgresql://…' uv run python -m app.seed_synthetic
   ```
   Row-level security is on with no policies, so Supabase's public Data API cannot read the tables. Details:
   [../deployment/supabase.md](../deployment/supabase.md).

## 2. Render (the backend), about 10 minutes

1. At render.com choose **New > Blueprint**, connect the GitHub repository and pick the branch to deploy.
   Render reads `render.yaml` in the repository root.
2. When asked, fill in:
   - `DATABASE_URL`: the Supabase string from step 1.
   - `GEMINI_API_KEY`: the Google AI Studio key ([../deployment/gemini.md](../deployment/gemini.md)).
   - `CORS_ORIGINS`: leave a placeholder for now (for example `https://placeholder.vercel.app`). You set the real
     value in step 4.
3. Wait for the deploy. Open `https://<your-service>.onrender.com/api/health`. It should show `"status":"ok"`.
4. Copy the service address (`https://<your-service>.onrender.com`).

The Blueprint uses Gemini (`LLM_PROVIDER=gemini`). **Until a key exists**, set `LLM_PROVIDER=mock` and
`LLM_MODEL=mock-deterministic-v1` in Render: replies then come from the approved wording and rules, not a language
model, and the website says so. `APP_ENV=hosted` makes the backend refuse to start with unsafe settings
([../deployment/render.md](../deployment/render.md)).

## 3. Vercel (the website), about 5 minutes

1. At vercel.com choose **Add New > Project** and import the same repository.
2. Set **Root Directory** to `frontend`. Everything else is read from `frontend/vercel.json` (a static build into
   `out/`; the normal Next.js server build currently fails on a session-id issue, so the static build is used).
3. Add an environment variable `NEXT_PUBLIC_API_BASE_URL` = the Render address from step 2.4, with no trailing
   slash. It is baked in at build time, so **changing it needs a redeploy**.
4. Deploy and copy the website address (`https://<project>.vercel.app`).

## 4. Connect them

Back in Render, set `CORS_ORIGINS` to the exact Vercel address (comma-separate more than one, for example a custom
domain) and let it redeploy. Without this the browser blocks every chat message. Vercel preview URLs for other
branches are different addresses and need adding if you want typing to work on them.

## 5. Check it

Open the Vercel address on a phone, type "Can I tour this week?" and confirm a tour request. In Supabase, open
**Table Editor > prototype_records** to see the saved request.

## What to expect

- **Free plans sleep.** Render's free plan pauses when idle, and the first message after a pause can take about a
  minute (the page shows a "can't reach the backend" message until it wakes, then recovers). Supabase's free plan can
  pause a project after about a week with no activity; restore it from the dashboard.
- **Resident sign-in needs the synthetic seed.** The resident spreadsheet is git-ignored and is not on Render, so the
  backend reads residents from the database (`RESIDENT_DATA_SOURCE=database`) after `app.seed_synthetic` has loaded
  them (step 1.3). Without the seed, prospects and guests work but residents find no record.
- **The staff console tabs won't work online.** By design the staff, evaluation and records routes only answer
  requests from the same machine and refuse anything arriving through a proxy such as Render. The page itself loads.
- **Anyone with the link can use the chat.** It is a demo with made-up data only.
- **AI model.** To use a real model later, add `LLM_PROVIDER=openrouter`, `LLM_MODEL=...` and `OPENROUTER_API_KEY` in
  Render (see the README). Free hosted models may log prompts; synthetic data only.

## Running locally against Supabase (optional)

Put `DATABASE_URL=...` in `backend/.env` (git-ignored). Without it, the backend keeps using the local SQLite file.

## Tests

SQLite always runs. The same Store checks run on Postgres when you point them at a throwaway database (they empty
its tables, so never use the real one):

```bash
cd backend
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/scratch uv run pytest tests/test_store_backends.py
```
