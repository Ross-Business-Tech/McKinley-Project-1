# Deployment readiness: Vercel + Render + Supabase + Gemini

Target agreed with Arihan: **Vercel** hosts the website, **Render** the Python backend, **Supabase** the database,
**Gemini** writes the replies. As of 2026-11-10 the code and configuration are prepared in the
repository (Sprint 3 deployment work, merged with the Sprint 4 mobile redesign), but **nothing has been deployed and no live Gemini or Supabase call has been
made** (no credentials yet). The product remains a **prototype on synthetic data, NOT production ready**.

Guides: [Gemini](deployment/gemini.md) · [Supabase + migrations](deployment/supabase.md) ·
[Render](deployment/render.md) · [Vercel](deployment/vercel.md) · step-by-step walkthrough:
[development/deploy-vercel-render-supabase.md](development/deploy-vercel-render-supabase.md).

## Status

| Piece | Ready in code | Tested | Not yet done |
| --- | --- | --- | --- |
| Gemini provider (official `google-genai` SDK) | yes | offline with a fake SDK client (errors, schema, retries, model check, usage) | no live call; model ID unverified on a key |
| Supabase / Postgres storage (teammate) | yes | SQLite paths; Postgres tests exist but need `TEST_DATABASE_URL` | never run on Postgres |
| Alembic migrations + synthetic seed | yes | SQLite upgrade/downgrade, adopt existing DB, seed guard, DB residents == file residents | never run on Postgres/Supabase |
| Render Blueprint (`render.yaml`) | yes | startup refusal of unsafe hosted settings; health endpoint | never deployed |
| Vercel config (`frontend/vercel.json`) | yes | static export builds; here.now build + smoke pass | never deployed |
| Live vs mock labels | yes (customer footer, staff status line) | unit tests | — |

## Missing credentials / access
- Google AI Studio project + `GEMINI_API_KEY` (and whether usage is free tier or billed).
- Supabase project (owner: Ross IT / project owner) + Session pooler connection string.
- Render account/workspace and permission to connect the GitHub repository.
- Vercel team/project and permission to connect the repository.
- Ross IT approval for new hosting (the team's current hosting is here.now; deploy scripts in `scripts/` are theirs).

## Checklist after access is granted
1. **Gemini key (local first).** Put `GEMINI_API_KEY` in `backend/.env`. Run
   `uv run python -m app.live_eval.preflight` → the configured model is listed for the key.
2. **One small live check.** `uv run python -m app.live_eval.abc --target gemini:gemini-3.6-flash --allow-paid
   --max-calls 30 --label gemini-v1`; read `evals/live/report-gemini-v1.md`; a person reviews the records.
3. **Supabase.** Create the project; from your machine run `alembic upgrade head` and `python -m app.seed_synthetic`
   with `DATABASE_URL` set (see the Supabase guide). In the Supabase dashboard confirm RLS is on for every table.
4. **Postgres tests.** Against a throwaway database (a second Supabase project or local Postgres):
   `TEST_DATABASE_URL=… uv run pytest tests/test_store_backends.py tests/test_migrations.py`.
5. **Render.** New Blueprint from the repo/branch; enter `GEMINI_API_KEY`, `DATABASE_URL`, a placeholder
   `CORS_ORIGINS`. Check `/api/health`: `database: postgres`, `resident_source: database (…)`, `is_mock: false`,
   `provider_ready: true`, `app_env: hosted`.
6. **Vercel.** Import the repo, Root Directory `frontend`, `NEXT_PUBLIC_API_BASE_URL` = Render address. Deploy.
7. **Connect.** Set Render `CORS_ORIGINS` to the exact Vercel address; redeploy.
8. **Smoke on the real site** (phone and desktop): a repair report → read-back → Send; status question; "I smell gas"
   (full alert, nothing dispatched); "I can't do this anymore" (988 line); Spanish message; the footer label; staff
   console shows the backend status line and refuses staff data (expected without staff sign-in).
9. **Logs.** Render logs contain no keys, connection strings or message text from the gate log.
10. **Record results** in `docs/evaluation/live-llm.md` and update this file. Keep the here.now preview working until
    the Vercel site is validated.

## Configuration
Backend variables and secrets: [Render guide](deployment/render.md) and `backend/.env.example`. Website: only
`NEXT_PUBLIC_API_BASE_URL` (public by design). Never put a key, database URL or Supabase service-role key in the
website, the repository, a pull request or a chat.

## Blockers before any real resident uses it (unchanged by this work)
- **Missed emergencies:** Sprint 6 independent holdout 76% full alert / 85% any guidance; 16 of 109
  immediate-danger messages got nothing ([SAFETY_STATE_AND_EVALUATION.md §7](safety/SAFETY_STATE_AND_EVALUATION.md);
  earlier holdouts: [safety evaluation](safety/safety-evaluation.md)). Gemini may run as the semantic safety
  classifier; it never removes a rules alert or care line (Sprint 7), and it has not been evaluated.
- **No authentication:** the demo sign-in (`persona_id`) is chosen by the browser; staff tools are protected only by a
  loopback/token boundary. Real resident and staff sign-in, enforced on the backend, is required. Since Sprint 6,
  `APP_ENV=hosted` turns demo personas off (`DEMO_PERSONAS_ENABLED`), so a hosted backend serves **public
  information only** and never reads resident records ([security/AUTHORIZATION_BOUNDARIES.md](security/AUTHORIZATION_BOUNDARIES.md)).
  Do not add a bypass; keep real resident data disconnected until real sign-in exists.
- **Unapproved scripts:** emergency and escalation wording (I-17/I-18) are team drafts; McKinley must approve them.
- **No live-model evaluation:** Gemini has never been called; the model ID is unverified on a real key; the Gemini
  semantic safety classifier and reply quality are unevaluated. All results so far are mock.
- **No integrations:** no Yardi, work orders, CRM, paging or messaging. Nobody is notified.
- **No real-device testing:** the phone checks ran in Playwright Chromium/WebKit against a local mock backend; no
  real iPhone/Android, no real screen reader, no public URL ([INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md)).
- **Public preview is not interactive:** the here.now link replays recorded conversations; typing is off.
- **Diagnostics in API responses:** `/api/chat` returns staff diagnostics to every caller; strip for non-staff callers.
- **Data:** synthetic only. No real McKinley data may be loaded without approval.
