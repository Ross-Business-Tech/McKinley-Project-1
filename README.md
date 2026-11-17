# McKinley Project 1: context-aware resident and leasing assistant

Team repository for the Business+Tech AI Sprint. Team workflow (Ross IT): [`START-HERE.md`](START-HERE.md),
[`PROMPTS.md`](PROMPTS.md), [`CLAUDE.md`](CLAUDE.md).

> **NOT PRODUCTION READY: a prototype on synthetic data only.**
> - **No real sign-in:** demo personas are synthetic, not authentication.
> - **No integrations:** no Yardi, Databricks, CRM, work orders, paging, SMS/email or voice.
> - **Nothing reaches a person:** notes for the office notify nobody, emergencies dispatch nobody, and tour requests
>   are not bookings.
> - **Safety wording is a team draft,** not McKinley-approved, and some emergencies are still missed. Known issues:
>   [docs/HANDOFF.md](docs/HANDOFF.md#known-issues).

## What it does
- **Customer chat (`/`):**
  - residents report repairs, check their own requests, ask questions or reach a person;
  - prospects ask about communities and request tours;
  - visitors can leave a note for the office.

  Every request is a read-back card, saved to a labelled prototype store only when the person presses **Send** (or
  types "send it"). Emergencies get fixed 911 / 988 / gas-company guidance before anything else.
- **Staff queue (`/staff/`):** saved requests and conversations, behind a staff token on a shared site.

**How it works:** the model understands and proposes; the backend authorizes, enforces policy, manages state and
persists. One chat turn runs identity → safety → **one** structured model call → task controller → reply checks.

**Stack:** Next.js (static export) + TypeScript in `frontend/`; Python 3.12 + FastAPI in `backend/`; SQLite locally,
Supabase Postgres on Render. Models go through one gateway: the Render demo uses U-M GPT Toolkit `gpt-6.1-sol`;
Gemini, OpenRouter, Anthropic, Ollama and a mock are also supported.

| Document | Covers |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, one chat turn, safety assessment, key decisions |
| [docs/SECURITY.md](docs/SECURITY.md) | Identity, data access, guards, hosted protections, known gaps |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Render + Supabase, settings, deploy checklist, troubleshooting |
| [docs/TESTING.md](docs/TESTING.md) | Test suites, evaluations and their limits |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Current state, known issues, approvals, next actions, how to work here |

## Run locally

Requirements: Node ≥ 20.9, Python ≥ 3.12, [uv](https://docs.astral.sh/uv/).

```bash
npm install                                  # root; also installs frontend/
cd backend && uv sync && cp .env.example .env && cd ..   # backend/.env is git-ignored
npm run backend:dev                          # API on http://localhost:8000 (health: /api/health)
npm run dev                                  # website on http://localhost:3000 (customer /, staff /staff/)
```

**Without a model key:** the copied `.env` uses `LLM_PROVIDER=mock`, a keyword stand-in, not a language model. To use a
real model, set `LLM_PROVIDER` and its key in `backend/.env`, then check it without spending tokens:
`cd backend && uv run python -m app.live_eval.preflight`. Settings: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#3-backend-settings).

**Resident data:** the synthetic resident workbook (`backend/data/um_ai_sprint_sample_residents.xlsx`) is
git-ignored; ask the project owner for it. Without it, only the built-in fixture personas are available.

**Preview links** for the team come only from `npm run publish:preview` ([CLAUDE.md](CLAUDE.md)). A preview replays
recorded conversations and has no backend.

## Test

```bash
cd backend && uv run pytest && uv run ruff check .
npm run lint && npm run typecheck && npm test && npm run build   # from the repo root
```

Details and evaluation results: [docs/TESTING.md](docs/TESTING.md).

## Data and contributing
- **This repository is public:** synthetic data only. `.env` files, keys, databases, the workbook and evaluation
  outputs (`evals/`) are git-ignored, and `docs/references/` stays local.
- **Workflow:** feature branch → pull request into `development` → (staff only) `main`. Never push to `main` or
  force-push. See [docs/HANDOFF.md](docs/HANDOFF.md#working-on-this-repository).
