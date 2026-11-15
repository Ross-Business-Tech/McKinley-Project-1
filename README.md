# McKinley Project 1: context-aware resident and leasing assistant

Team repository for the Business+Tech AI Sprint. Team workflow (Ross IT): [`START-HERE.md`](START-HERE.md),
[`PROMPTS.md`](PROMPTS.md), [`CLAUDE.md`](CLAUDE.md).

> **NOT PRODUCTION READY.** A prototype on **synthetic data only**, for demonstration and evaluation. There is no
> real sign-in, no integration (no Yardi, CRM, work orders, paging, SMS/email or calendar), and nobody is ever
> notified. Safety scripts are team drafts, not McKinley-approved, and some emergencies are still missed.

## What it does

- **Customer chat (`/`):** residents report repairs, check their own requests, ask questions or reach a person;
  prospects ask about communities and request tours; visitors who are not signed in can leave a note for the office.
  Every request is a read-back card that is saved only when the person presses **Send** (or types "send it"), to a
  clearly labelled prototype store (`DEMO-WO-…`, `DEMO-TOUR-…`, `DEMO-TASK-…`). Emergencies (gas, fire, CO, water
  on electrics, medical, threats, self-harm) get fixed 911 / 988 / gas-company guidance before anything else, and an
  unsent card comes back unchanged once a responder says it is safe.
- **Staff queue (`/staff/`):** saved requests and live conversations (on a shared site, after entering the staff
  token).

How it works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — one chat turn is identity → safety → **one** model call
→ task controller → reply checks.

## Documentation
| File | What it covers |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, the five-part chat turn, safety pipeline, data, providers, key decisions |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local, here.now preview, Render + Supabase; settings; checklist |
| [docs/SECURITY.md](docs/SECURITY.md) | Identity, data access, staff access, hosted safeguards, secrets, known gaps |
| [docs/TESTING.md](docs/TESTING.md) | Test suites, how to run them, the latest evaluation results and missed cases |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Current status, known P0/P1, next steps, how to work in this repository |

## Set up

Requirements: Node ≥ 20.9, Python ≥ 3.12, [uv](https://docs.astral.sh/uv/).

```bash
npm install                      # root; postinstall installs frontend/ dependencies
cd backend && uv sync            # add --extra anthropic only for the optional Anthropic provider
cp .env.example .env             # backend/.env is git-ignored; never commit it
```

The synthetic resident workbook `backend/data/um_ai_sprint_sample_residents.xlsx` is git-ignored; ask the project
owner for it. Without it, the workbook residents are missing (the built-in fixture personas, prospects and visitors
still work).

**Model (optional; the app runs on the mock without one):** set `LLM_PROVIDER` and the matching key in
`backend/.env`, for example `LLM_PROVIDER=um_toolkit` + `UM_TOOLKIT_API_KEY` (model `gpt-6.1-sol`), or
`LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`. Check without spending tokens:
`cd backend && uv run python -m app.live_eval.preflight`. Common settings, with comments: `backend/.env.example`;
the complete list (including `DEMO_PERSONAS_ENABLED`, rate limits, `MAX_REQUEST_BYTES`) is `Settings` in
`backend/app/config.py`. The
website has one setting, `NEXT_PUBLIC_API_BASE_URL`, fixed at build time and public.

## Run

```bash
npm run backend:dev    # FastAPI on http://localhost:8000 (health: /api/health)
npm run dev            # Next.js on http://localhost:3000 (customer /, staff /staff/)
```

A disposable database for a test session (leaves `backend/data/*.sqlite3` untouched):
`cd backend && DATABASE_URL=" " DB_PATH="$(mktemp -d)/mvp.sqlite3" uv run uvicorn app.main:app --reload --port 8000`.

Preview links for the team come only from `npm run publish:preview` (see [CLAUDE.md](CLAUDE.md)); a preview has no
backend and replays recorded conversations. Hosting: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Test

```bash
cd backend && uv run pytest && uv run ruff check .                   # offline; mock and fake providers only
npm run lint && npm run typecheck && npm test && npm run build        # from the repo root (frontend)
npm run smoke                                                         # headless browser check (needs Playwright)
```

Latest results and the evaluation method: [docs/TESTING.md](docs/TESTING.md).

## Data and privacy

**This repository is public.** Synthetic data only. The model receives only an allowlisted, redacted, topic-relevant
summary — never contact details, rent, balances, raw staff notes or transcripts. `.env` files, keys, SQLite databases,
the workbook and evaluation outputs (`evals/`) are git-ignored; only `.env.example` placeholders are tracked. Team
reference material in `docs/references/` stays local.

## Contributing

Feature branch → pull request into `development` → (staff only) `main`. Never push to `main`, never force-push. How
to work here: [docs/HANDOFF.md](docs/HANDOFF.md#working-on-this-repository).
