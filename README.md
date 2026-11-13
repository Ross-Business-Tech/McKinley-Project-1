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
- **Identity:** the demo sign-in (`persona_id`) is chosen by the browser. It is not authentication. Since Sprint 6
  the server decides what a caller may see (deny by default), binds each conversation to one persona, and turns
  demo sign-in off in hosted mode (public information only).
- **No integrations:** no Yardi, CRM, work orders, paging, SMS/email or calendar. Nobody is ever notified.
- **Models:** exactly one historical run used a real model (2026-11-01, sprint-1 pipeline). Everything since is the
  deterministic **mock**. **Gemini** is the intended provider for deployments; its adapter is built and tested offline
  only (no key yet). The live A/B/C comparison and the semantic safety classifier are built but **blocked** until a
  Gemini or OpenRouter key is configured (live-LLM status (removed; in Git history at `59c155c`)).
- **Sprint 8 (2026-11-11):**
  - **Calmer screen:** the always-visible 911 button is gone.
    - Normal chats show nothing safety-related.
    - Worrying or "what if" messages get a calm note with the right contact.
    - Real emergencies get a clear alert with labelled "Call 911 / 988 / Poison Help" links that never dial by
      themselves.
    - One plain-text 911 line stays in the footer.
  - **Repeat repairs:** the reply names the real count and time span from the resident's own history, and the request
    is marked for community-manager review. Nobody is notified in this demo.
  - **Quick-fix tips:** draft tips for a breaker, a GFCI outlet, a disposal and a slow drain. They are pending
    McKinley approval, off by default, never on hosted, and safety checks run first.
  - **Safety holdout:** full alerts 88.1% → 89.5%, any guidance 90.7% → 91.7%; unsafe tips 2 → 0 of 40. **Missed
    emergencies remain release-blocking.**
  - Sprint 8 report (removed; in Git history at `59c155c`).
- **Sprint 7 (2026-11-10):**
  - **Safety:**
    - Emergencies are now detected by structure (who, what state, what hazard, whether it is happening now) instead of
      single phrases.
    - Adding words like "lol", "I think" or "my neighbour smokes" to a real emergency can never weaken the response.
    - The AI layer can no longer remove safety guidance. This policy is a DRAFT for McKinley approval.
  - **Safety holdout:** on a new independent test set of 216 emergency turns, full alerts went 81% → 88% and any
    guidance 84% → 91%; Spanish full alerts went 75% → 100%. **20 emergencies still get no guidance, which is
    release-blocking.**
  - **Conversation:** one structural reading of each message, corrections by field name, two different requests in
    one message both kept, changes after Send as notes, and randomised rule tests. Customer journeys went 30 → 40 of
    45.
  - **Privacy:** customers no longer receive staff diagnostics; the hosted version issues its own session ids. 0 leaks
    in 2,200+ attacks.
  - **Live OpenRouter:** 21 calls through the real pipeline, all valid.
  - **Merge state:** the first Sprint 7 candidate was merged to `development` early (PR #4) with known safety
    regressions; the fixes are on `feat/s7-safety-regression-fixes`.
  - Fit for a supervised demo only (Sprint 7 report (removed; in Git history at `59c155c`)).
- **Sprint 6 (2026-11-10):**
  - **Conversation:** each message is understood once into a typed object, and an explicit state machine decides
    what may change. Corrections replace the field that was named, a side question never corrupts the open
    request, and only Send or "send it" saves (never twice).
  - **Privacy:** a server-side principal with deny-by-default data access. 41/41 independent API attacks were
    blocked at the data layer.
  - **Safety:** on a new independent holdout of 109 emergencies, full alert went 70% → 76% and any guidance 79% →
    85%. **16 immediate-danger messages still get nothing, which is release-blocking.**
  - **Journeys:** 29 of 35 PASS with 0 FAIL (Sprint 5.1: 27).
  - **Live OpenRouter: BLOCKED.** The free model's daily limit returned HTTP 429 all sprint.
  - **Fit for a supervised demo only** (Sprint 6 report (removed; in Git history at `59c155c`)).
- **Sprint 5.1 (2026-11-10):**
  - **Live OpenRouter verified:** 46 real calls, all on `nvidia/nemotron-3.5-super-vl:free`.
  - **Conversation reworked:** independent simulators drove two fix rounds and a typed dialogue-act step was
    added. Only Send or "send it" saves.
  - **Results:** the journey suite went 21 → 27 of 35 PASS with 0 FAIL, and the held-out safety set went 53 → 54
    of 63 any-guidance.
  - **Fit for a supervised demo only**; safety and privacy blockers remain
    (Sprint 5.1 report (removed; in Git history at `59c155c`)).
- **Sprint 5 (2026-11-10):**
  - The conversation workflows were reworked from simulator findings, verified with the **mock** only.
  - OpenRouter and Gemini share a tested provider contract.
  - **No live model call was made**, because there is no key. See Sprint 5 report (removed; in Git history at `59c155c`).
  - A new independent safety holdout found **10/63 immediate-danger messages with no guidance**, which is release-blocking.
- **Deployment (2026-11-11):** a public, guest-only demo runs on Render: website
  https://mckinley-frontend.onrender.com, backend https://mckinley-backend.onrender.com, data in the development
  Supabase project (synthetic), replies from a free OpenRouter model (live, not mock). Resident features need a
  sign-in that does not exist, so they are off there. Option A (Vercel website) stays supported
  ([deployment readiness](docs/DEPLOYMENT_READINESS.md)).
- **Static preview:** the here.now link has no backend; it replays recorded conversations (see below). It is not
  interactive.
- **Phones:** the redesigned chat passes a Chromium/WebKit phone test at 7 sizes against a local **mock** backend;
  no real-device or real screen-reader test yet ([interactive demo readiness](docs/INTERACTIVE_DEMO_READINESS.md)).

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
- **Backend:** Python ≥ 3.12, FastAPI, Pydantic v2, httpx, SQLite (local) or Postgres/Supabase (`DATABASE_URL`), uv, pytest, ruff.

```
frontend/src/components/customer   customer chat (CustomerApp, ActionCard, StatusPill)
frontend/src/components/staff      staff queue (saved requests, live conversations)
backend/app/chat_engine.py         one turn: receive → identity → SAFETY → privacy → context → gate → plan → generate
                                   → validate → handoff → persist (11 traced steps)
backend/app/risk/                  safety: rules → optional semantic classifier → policy R1–R9e → approved text
backend/app/gates/                 decision gate (rules always; optional LLM / Jev may only add risk)
backend/app/actions.py             planner: questions, read-back cards, notes, status (F2–F9)
backend/app/intake.py, templates.py, content/knowledge_base.json   detectors, wording, FAQ content
backend/app/context.py, personas.py  workbook adapter, allowlisted context, demo identity
backend/app/llm/                   Gemini | OpenRouter | Ollama | Anthropic (optional) | Mock, one gateway
backend/migrations/, app/seed_synthetic.py   Alembic migrations (SQLite + Postgres) and the synthetic seed
backend/app/live_eval/, export_demo.py   dev-only: provider preflight + budgeted smoke, static demo snapshot
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

### Configure a model (optional; the app runs on the mock without one)

- **Gemini (intended for deployments):** `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=` (Google AI Studio),
  `GEMINI_MODEL=gemini-3.6-flash`, `LLM_MODEL=` empty. See [docs/deployment/gemini.md](docs/deployment/gemini.md).
- **OpenRouter (free models, evaluations):** `LLM_PROVIDER=openrouter`, `LLM_MODEL=nvidia/nemotron-3.5-super-vl:free`,
  `OPENROUTER_API_KEY=` (<https://openrouter.ai/keys>).
- Shared settings: temperature 0.2 (not sent to Gemini or Anthropic, which ignore or reject it), 4000 max tokens, 60 s timeout, 2 same-model retries. A different served model is
  rejected (`MODEL_SWITCHED`), never used. Check without generating anything:
  `cd backend && uv run python -m app.live_eval.preflight` (exit code 3 = blocked).
- Without a key: `LLM_PROVIDER=mock`, `LLM_MODEL=mock-deterministic-v1` (the `.env.example` default). With a provider
  but no key, chat answers `NEEDS_API_KEY`; nothing silently falls back to the mock.

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

**Deployed interactive mode** (live since 2026-11-11, guest-only) = website on Render (or Vercel), backend on
Render, database on Supabase, replies from OpenRouter (Gemini adapter kept):
[docs/DEPLOYMENT_READINESS.md](docs/DEPLOYMENT_READINESS.md), [Render website](docs/deployment/render-frontend.md),
[Render backend](docs/deployment/render.md) and the walkthrough
[docs/development/deploy-vercel-render-supabase.md](docs/development/deploy-vercel-render-supabase.md).
Database tables come from migrations (`cd backend && uv run alembic upgrade head`); a hosted backend reads the
synthetic residents from the database after `uv run python -m app.seed_synthetic`.

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
cd backend && uv run pytest && uv run ruff check .          # ~705 tests, offline, mock / fake providers only (Postgres tests need TEST_DATABASE_URL)
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
