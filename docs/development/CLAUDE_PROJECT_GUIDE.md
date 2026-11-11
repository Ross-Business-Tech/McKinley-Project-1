# Project guide for developers and Claude Code (McKinley AI)

Supplements the Ross IT root [`CLAUDE.md`](../../CLAUDE.md) (publishing, branches, protected paths — it wins on
those) and [`engineering-rules.md`](engineering-rules.md) (imported by `backend/CLAUDE.md` and `frontend/CLAUDE.md`).
Keep this file short; link to the authoritative documents instead of copying them.

## Before you start
1. Read `README.md`, [`docs/PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md) and this guide. For safety work also read
   [`docs/safety/safety-evaluation.md`](../safety/safety-evaluation.md).
2. `git status`; `git fetch origin development`; merge it if you are behind. Never lose uncommitted work.
3. Work on a feature branch. Pull requests go into `development`. Never push to `main`, never force-push, never
   rewrite shared history. Do not merge your own PR unless the team asked you to.

## Architecture in one breath
Next.js static export (customer `/`, staff `/staff/`) → FastAPI (`backend/app`). A chat turn is
`chat_engine.run_turn`: receive → identity → **2b safety (`app/risk`)** → privacy → context → gate → plan
(`actions.plan_turn`) → generate (one model call, often skipped) → validate → handoff → persist. Details:
[`architecture/overview.md`](../architecture/overview.md), [`diagrams/`](../diagrams/).

## Deployment stack (prepared, not deployed)
Website on **Vercel** (static export of `frontend/`), backend on **Render** (`render.yaml`, `APP_ENV=hosted`),
database on **Supabase** Postgres (`DATABASE_URL`; SQLite locally), replies from **Gemini** (`LLM_PROVIDER=gemini`).
Status and checklist: [`docs/DEPLOYMENT_READINESS.md`](../DEPLOYMENT_READINESS.md). The here.now preview
(`npm run publish:preview`) stays the team's default until Vercel is validated.

## Conventions
- **Python:** `uv` only (`uv sync`, `uv add`, `uv run …`); Pydantic models for every request/response; one error
  envelope `{"error": {code, message, retryable}}` (raise `HTTPException(detail={"code": …, "message": …})`);
  ruff line length 120.
- **TypeScript:** strict; types in `frontend/src/lib/types.ts` mirror the backend Pydantic models (keep literals in
  sync); colours through the `mk-*` tokens; customer text in `src/lib/customer.ts` (EN + draft ES).
- **Planner:** `plan_turn` is an ordered list of checks — the order is the specification. Add a branch at the right
  place, never reorder silently; add a test that pins the new behaviour.
- **Detectors and safety regexes** (`emergency.py`, `intake.py`): extend, don't merge similar-looking patterns; each
  change needs positive and negative tests.
- **Database:** schema changes only through a new Alembic migration in `backend/migrations/versions/` with raw SQL
  for both SQLite and Postgres; keep RLS on for every new Postgres table; test with `tests/test_migrations.py` (and
  `TEST_DATABASE_URL` on a throwaway Postgres). Only the synthetic workbook may be seeded (`app.seed_synthetic`).
- **Wording:** customer-facing text lives in `templates.py` / `customer.ts`; never split template strings to reuse
  part of them — add a key.

## LLM providers and secrets
- Provider-agnostic gateway (`app/llm/`): Gemini (deployments), OpenRouter, Ollama, Anthropic, Mock; configure with
  `LLM_PROVIDER`, `LLM_MODEL` / `GEMINI_MODEL` and the provider key in `backend/.env` (git-ignored) or Render
  secrets. Never print, log, commit or copy keys or `DATABASE_URL`; check presence as booleans only. Never put any
  key, database URL or Supabase service-role key in the website (`NEXT_PUBLIC_*` values are public).
- Do not change the model ID silently: one fixed `provider:model` per evaluation; verify with
  `python -m app.live_eval.preflight`; live Gemini runs need `--allow-paid` and a small `--max-calls`.
- Never silently switch models (`MODEL_SWITCHED`), never fall back to the mock without labelling it, never call the
  mock or a template "live".
- Free hosted models may log prompts: synthetic data only. The resident workbook is git-ignored; never commit
  real personal data, `.env` files or databases. The repository is public.

## Safety-critical changes (`app/risk`, `emergency.py`, safety templates, staff guard, identity rules)
- The semantic layer only adds caution: it never removes a rules alert or care line (Sprint 7; the R7 exception was removed, DRAFT policy pending McKinley approval); a failed classifier is never "safe"; safety text is fixed and approved
  wording, never model-written; never claim anyone was dispatched or notified.
- Every change: unit tests for the rule plus the policy table (`tests/test_risk_policy_table.py`), run the full
  suite, and ask for an **independent** review (a reviewer or subagent that did not write the change).
- Measure recall only on a **fresh holdout written by someone else**; keep it out of the repo; never tune on it and
  then report it as held-out. Do not remove a test because it encodes a known safety failure.
- Do not downgrade documented P0s (missed emergencies, client-asserted identity, unapproved scripts) in any doc.

## Tests (required before every commit)
```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
npm run smoke          # from the root, when the UI changed (open the phone screenshots)
```
Tests are offline: an autouse fixture removes provider keys and staff tokens from the environment.

## UI/UX standards
WCAG 2.2 AA (keyboard, visible focus, 44 px targets, live regions announce once, reflow at 320 px); customer UI stays
simple — diagnostics belong in `/staff/`; read-back before any save; say plainly what was and was not sent. Check
real screenshots at 375, 390, 768 and 1440 px for visible changes.
- **Brand:** McKinley blue `#4e6f92` and Barlow headings, through the `mk-*` tokens only. Status colours are not
  the brand: green means saved, amber means a person should help, red means emergency. Each status also has an
  icon and words. See [`docs/design/BRAND_SYSTEM.md`](../design/BRAND_SYSTEM.md).
- **Phones first:**
  - The composer stays pinned on every phone height, keyboard open or not (it scrolls with the page only at extreme zoom, 280px tall or less).
  - The tap-to-call 911 link and "Talk to a person" are always visible.
  - Run `frontend/e2e/mobile-acceptance.mjs` (Chromium and WebKit, 7 sizes, keyboard stand-in) before a UI PR; see
    [`docs/design/MOBILE_UX_AUDIT.md`](../design/MOBILE_UX_AUDIT.md).
- **Honesty:** never claim the public phone requirement is met until a deployed URL passes on a real phone
  ([`docs/INTERACTIVE_DEMO_READINESS.md`](../INTERACTIVE_DEMO_READINESS.md)).

## Docs and diagrams
- Update the docs your change makes untrue, in the same PR: README status, `docs/workflows/traceability.md`,
  `docs/safety/safety-evaluation.md`, `docs/evaluation/README.md`, [`docs/PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md).
- Mermaid diagrams must match the code; validate syntax after editing. Do not describe planned work as implemented;
  historical records go to `docs/archive/` unchanged.

## Subagents
Delegate independent work (reviews, audits, simulations) with a precise brief: goal, files, what not to touch,
expected output. Reviewers and verifiers must not grade their own work, and holdout writers must be separate from
implementers. Read-only audits report; the lead integrates. Never let a subagent edit Ross IT paths or secrets.

## Definition of Done
- Behaviour implemented with tests; backend and frontend suites, lint, typecheck and build pass; smoke run when UI
  changed.
- No secrets or real data; mock and live clearly separated in results.
- Affected docs and diagrams updated; known limitations still stated.
- Focused commits on a feature branch; PR into `development` with what changed, what was tested, and the
  production-readiness caveat.
