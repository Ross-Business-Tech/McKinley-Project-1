# McKinley Project 1: context-aware resident and leasing assistant

Team repository for the Business+Tech AI Sprint. Team workflow (Ross IT): [`START-HERE.md`](START-HERE.md),
[`PROMPTS.md`](PROMPTS.md), [`CLAUDE.md`](CLAUDE.md). Documentation index: [`docs/README.md`](docs/README.md).
Handoff for the next developer or Claude Code session: [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md).

## What it does

A **synthetic-data prototype** of a McKinley customer-service assistant, with two front-ends:

- **Customer chat (`/`)**: residents report repairs, check request status, ask about renewal and policies, or reach a
  person; prospects ask about communities and request tours. Every action is a read-back card the person confirms
  before it is saved to a clearly labelled **prototype store** (`DEMO-WO-…`, `DEMO-TOUR-…`, `DEMO-TASK-…`). Safety
  messages (fire, gas, medical, threats, self-harm…) get fixed 911 / 988 guidance before anything else.
- **Staff / demo console (`/staff/`)**: saved requests, live conversations with "needs action" markers, a
  step-by-step conversation inspector, workflow coverage, usability results, an A/B/C model comparison and the
  five-case evaluation.

## Status

> **NOT PRODUCTION READY.** It is a prototype for demonstration and evaluation only.

- **Safety:** on a fresh, independent test set the emergency rules gave a full alert for 64.5% of emergencies and
  some guidance for 78.5%; 14 immediate-danger messages got nothing. This is release-blocking
  ([safety evaluation](docs/safety/safety-evaluation.md)). McKinley has not approved the emergency scripts.
- **Identity:** the demo sign-in (`persona_id`) is chosen by the browser. It is not authentication.
- **No integrations:** no Yardi, CRM, work orders, paging, SMS/email or calendar. Nobody is ever notified.
- **Models:** exactly one historical run used a real model (2026-11-01, sprint-1 pipeline). Everything since is the
  deterministic **mock**. The live A/B/C comparison and the semantic safety classifier are built but **blocked** until
  an OpenRouter key is configured ([live-LLM status](docs/evaluation/live-llm.md)).
- **Static preview:** the here.now link has no backend; it replays recorded conversations (see below).

## Workflows (F1–F9)

| | Workflow | State |
| --- | --- | --- |
| F1 | Phone / voice | Not implemented |
| F2 | SMS / email channel rules | Simulated (opt-out keywords, length rules; nothing is sent) |
| F3 | Caller type (resident, prospect, vendor, unverified) | Working on the demo identity |
| F4 | FAQs from approved content | Working; unapproved topics say so |
| F5 | Tour request | Simulated (a request, never a booking) |
| F6 | Maintenance intake, emergency first | Working with draft rules; emergency detection not production ready |
| F7 | Work orders | Simulated (prototype store) |
| F8 | Request status | Working on synthetic records and the prototype store |
| F9 | Human handoff note | Simulated (prototype queue) |

Details per instruction and data input: [docs/workflows/traceability.md](docs/workflows/traceability.md).

## Stack and architecture

- **Frontend:** Next.js 16 (static export), React 19, TypeScript, Tailwind 4, Base UI / shadcn, Vitest.
- **Backend:** Python ≥ 3.12, FastAPI, Pydantic v2, httpx, SQLite, uv, pytest, ruff.

```
frontend/src/components/customer   customer chat (CustomerApp, ActionCard, StatusPill)
frontend/src/components/staff      staff console; components/mckinley = comparison + evaluation tabs
backend/app/chat_engine.py         one turn: receive → identity → SAFETY → privacy → context → gate → plan → generate
                                   → validate → handoff → persist (11 traced steps)
backend/app/risk/                  safety: rules → optional semantic classifier → policy R1–R9e → approved text
backend/app/gates/                 decision gate (rules always; optional LLM / Jev may only add risk)
backend/app/actions.py             planner: questions, read-back cards, notes, status (F2–F9)
backend/app/intake.py, templates.py, content/knowledge_base.json   detectors, wording, FAQ content
backend/app/context.py, personas.py  workbook adapter, allowlisted context, demo identity
backend/app/llm/                   OpenRouter | Ollama | Anthropic (optional) | Mock, one gateway
backend/app/evals.py, gate_evals.py, journey_evals.py, usability/, live_eval/   evaluation tooling
```

More: [architecture overview](docs/architecture/overview.md) and [diagrams](docs/diagrams/).

## Set up

Requirements: Node ≥ 20.9, Python ≥ 3.12, [uv](https://docs.astral.sh/uv/).

```bash
npm install                      # root; postinstall installs frontend/ dependencies
cd backend && uv sync            # add --extra anthropic only if you want the optional Anthropic provider
cp .env.example .env             # backend/.env is git-ignored; never commit it
```

The synthetic resident workbook `backend/data/um_ai_sprint_sample_residents.xlsx` is git-ignored; ask the project
owner for it. Without it, resident sign-ins find no record (prospects and guests still work).

### Configure OpenRouter (optional; the app runs on the mock without it)

1. Get a free key at <https://openrouter.ai/keys> and set `OPENROUTER_API_KEY=` in `backend/.env`.
2. Defaults: `LLM_PROVIDER=openrouter`, `LLM_MODEL=nvidia/nemotron-3.5-super-vl:free`, temperature 0.2, 4000 max
   tokens, 60 s timeout, 2 same-model retries. A different served model is rejected (`MODEL_SWITCHED`), never used.
3. Check without spending: `cd backend && uv run python -m app.live_eval.preflight` (exit code 3 = blocked).
4. To develop without a key: `LLM_PROVIDER=mock` and `LLM_MODEL=mock-deterministic-v1`. Without a key and without the
   mock, chat answers `NEEDS_API_KEY`; nothing silently falls back to the mock.

Free hosted models may log prompts: send synthetic data only. All settings, with comments:
[`backend/.env.example`](backend/.env.example) (gate provider, `GATE_OVERRIDE_ENABLED` — set `false` on any shared
deployment, `SAFETY_CLASSIFIER`, `STAFF_API_TOKEN`, `EVAL_TARGETS`, `CORS_ORIGINS`, paths). The frontend has one
setting, `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), fixed at build time.

## Run

```bash
npm run backend:dev    # FastAPI on http://localhost:8000  (health: /api/health)
npm run dev            # Next.js on http://localhost:3000  (customer /, staff /staff/)
```

**Interactive mode** = both running locally; the page origin must be listed in `CORS_ORIGINS`.

**Static replay mode** = the here.now build (`npm run build` → `dist/`) with no backend. The customer view replays
17 recorded journeys from `frontend/public/demo/snapshot.json` (mock model, rules gate) with typing turned off; the
staff console opens on the Conversation inspector and its live tabs say they need a backend. After backend changes,
re-record with `cd backend && uv run python -m app.export_demo`. Preview links come only from
`npm run publish:preview` (see `CLAUDE.md`).

### Staff / demo console

Staff, evaluation, gate, records and context-preview routes answer only direct requests from this machine. Set
`STAFF_API_TOKEN` for anything shared; requests then need the `X-Staff-Token` header (the browser console does not
send it, so its staff tabs work only locally). Any proxy-forwarding header or non-local `Host` is refused. This is a
demo boundary, not sign-in.

## Test

```bash
cd backend && uv run pytest && uv run ruff check .          # ~670 tests, offline, mock / fake providers only
npm run lint && npm run typecheck && npm test && npm run build   # from the repo root (frontend)
npm run smoke                                                # headless browser check of dist/ (needs Playwright)
```

Evaluation suites (results, live vs mock, commands): [docs/evaluation/README.md](docs/evaluation/README.md).

## Data and privacy

**This repository is public.** Synthetic or properly de-identified data only. The backend forwards to a model only
an allowlisted, redacted, topic-relevant summary — never contact details, rent, balances, raw staff notes or
transcripts. `.env` files, keys, SQLite databases and the workbook are git-ignored; only `.env.example` placeholders
are tracked. Team reference material in `docs/references/` stays local.

## Contributing

Feature branches → pull request into `development` → (staff only) `main`. Never push to `main`, never force-push.
Project guide for developers and Claude Code: [docs/development/CLAUDE_PROJECT_GUIDE.md](docs/development/CLAUDE_PROJECT_GUIDE.md).
