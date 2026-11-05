# McKinley Project 1: Context-Aware AI Assistant

This is the team repository for the Business+Tech AI Sprint. New here? Read [`START-HERE.md`](START-HERE.md) for the team workflow and [`PROMPTS.md`](PROMPTS.md) for ready-made prompts.

## Overview

A working prototype of a **context-aware leasing and resident assistant for McKinley**. The same message goes through two modes with the same model and settings:

- **Generic baseline**: a plain assistant prompt with no McKinley context.
- **McKinley-aware**: the McKinley system prompt plus a small, allowlisted and redacted summary of the resident's relevant history. On top of that sit deterministic policy gates (emergencies, fair housing, lease/financial questions, requests for a person) and output checks.

The dashboard shows the two replies side by side. It also shows which context was used and whether a **human handoff** is recommended and why. A five-case evaluation tab runs both modes against real models and records Good/Bad verdicts.

**This is a synthetic-data prototype, not a production resident portal.** It never creates work orders, notifies staff, schedules anything or quotes live availability or pricing.

## Architecture

```
frontend/   Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · shadcn/ui (Base UI)
            Chat comparison, Context Preview, handoff panel, model picker, eval dashboard
   │  HTTP (NEXT_PUBLIC_API_BASE_URL, public URL only, no keys)
   ▼
backend/    Python 3.12 · FastAPI · Pydantic v2 · httpx · SQLite · uv
   app/context.py     workbook loader → allowlisted, topic-relevant, redacted SAFE_CONTEXT
   app/personas.py    fictional prospect personas (kept separate from resident data)
   app/safety.py      redaction, injection screening, pre-model policy gates, output checks
   app/prompts.py     versioned prompts (hash recorded on every response)
   app/chat_engine.py one turn: context → gates → LLM → checks → handoff merge
   app/llm/           provider-agnostic gateway: OpenRouter · Ollama · Mock · Anthropic (optional)
   app/evals.py       five-case harness, grading, re-grading, export
prompts/    mckinley_system_prompt.md
evals/      five_cases.md (scenarios + rubric), actual_results.json (real run), actual_results_review.md
docs/       PROJECT_SPEC.md, ARCHITECTURE.md (full design), BUILD_VS_BUY.md, ENGINEERING_RULES.md
scripts/, .github/, .claude/, CLAUDE.md   here.now publishing and Claude setup (maintained by Ross IT; don't edit)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the API, the data boundaries and the provider abstraction. Engineering rules for coding agents are in [`docs/ENGINEERING_RULES.md`](docs/ENGINEERING_RULES.md).

## Prerequisites

- **Node.js 20.9+** (CI uses 22) and npm
- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)** (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- An LLM provider for real responses: a free [OpenRouter](https://openrouter.ai/keys) key (default), or a local [Ollama](https://ollama.com). The Mock provider needs nothing but is not a language model.
- The synthetic workbook `um_ai_sprint_sample_residents.xlsx` from the sprint materials. Place it at `backend/data/um_ai_sprint_sample_residents.xlsx`; it is git-ignored. Without it, prospect scenarios still work and resident lookups report that no record was found.

## Setup

### Backend (FastAPI, uv)

```bash
cd backend
cp .env.example .env          # then add your key (see "Environment variables")
uv sync                       # add --extra anthropic only for the optional Anthropic provider
uv run uvicorn app.main:app --reload --port 8000
```

Check it at http://localhost:8000/api/health. It reports the configured provider and whether a key is present, never the key itself.

### Frontend (Next.js, npm)

```bash
cd frontend
cp .env.example .env.local    # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

From the repository root, `npm install` also installs the frontend. `npm run dev` and `npm run backend:dev` work from the root too.

## Environment variables

Everything lives in `backend/.env` (server-side only; git-ignored). The template is [`backend/.env.example`](backend/.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openrouter` | `openrouter` · `ollama` · `mock` · `anthropic` |
| `LLM_MODEL` | `nvidia/nemotron-3.5-super-vl:free` | Model ID for `/api/chat` |
| `OPENROUTER_API_KEY` | (none) | OpenRouter key. `LLM_API_KEY` also works for the default provider. |
| `LLM_BASE_URL` | (provider default) | Optional override for the default provider |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.2` / `4000` | Shared by baseline and aware modes. Reasoning models spend part of max tokens on hidden reasoning. |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `60` / `2` | Retries are same-model only (429/5xx/timeouts) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_EFFORT` | (none) / `medium` | Optional Anthropic provider |
| `EVAL_TARGETS` | mock, three OpenRouter free models, ollama | Comma-separated `provider:model` list offered in the dashboard. The browser can only pick from this list. |
| `DATA_PATH` / `DB_PATH` | `data/…xlsx` / `data/mckinley_demo.sqlite3` | Workbook and local SQLite (both git-ignored) |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Origins allowed to call the API |

The frontend has only `NEXT_PUBLIC_API_BASE_URL` (`frontend/.env.example`). Never put a key in any `NEXT_PUBLIC_*` variable or in frontend code.

## Running locally

1. Start the backend (port 8000), then the frontend (port 3000).
2. Open http://localhost:3000. The **Chat comparison** tab has a scenario/persona picker, the Context Preview, both replies side by side and the handoff panel. The **Five-case evaluation** tab runs and reviews evals.
3. A yellow banner marks everything as synthetic data, and Mock output is labelled MOCK.

Without a key, the API returns a clear `NEEDS_API_KEY` error. It never falls back to fake responses or to another model.

## Decision gates and workflows (pipeline v2)

Every McKinley-mode turn runs a typed **decision gate** (audience, intent, urgency, whether a human is needed, risk flags). The gate's result picks a **workflow**: leasing, resident support, maintenance, renewal, human handoff or general inquiry. The backend then builds a structured **handoff recommendation**, which is never sent anywhere.

- **Gate provider:** set `DECISION_GATE_PROVIDER` to `rules` (the default), `llm` or `jev` (experimental). The rules gate always runs as a safety floor that no model can lower.
- **Compare gates:** `uv run python -m app.run_gate_evals --providers rules,llm,jev`.
- **Three comparison modes:**
  - A: generic baseline;
  - B: McKinley prompt only (`prompt_only`);
  - C: McKinley prompt plus resident context (`aware`).
- **Static demo:** the hosted here.now site can't reach the backend, so it shows pre-computed **MOCK** responses from `frontend/public/demo/snapshot.json`. Regenerate the file with `cd backend && uv run python -m app.export_demo` after any backend change.
- **More detail:** [docs/GATE_DESIGN.md](docs/GATE_DESIGN.md), [docs/WORKFLOW_REVIEW.md](docs/WORKFLOW_REVIEW.md), [docs/DECISIONS.md](docs/DECISIONS.md), [docs/IMPLEMENTATION_CHANGELOG.md](docs/IMPLEMENTATION_CHANGELOG.md) and the diagrams in [docs/diagrams/](docs/diagrams/).

## Five evaluation scenarios

Defined in [`evals/five_cases.md`](evals/five_cases.md): (1) high-intent prospect, two-bed tour; (2) price shopper, Florida one-bed; (3) repeated AC problem, R001; (4) faucet drip, no matching record; (5) renewal and contact preference, R003.

**From the dashboard:** open **Five-case evaluation**, select one or more targets, click **Run**, then mark each result Good/Bad with notes. That writes the human verdict.

**From the CLI:**

```bash
cd backend
uv run python -m app.run_evals                                    # default target, 10 calls
uv run python -m app.run_evals --targets openrouter:nvidia/nemotron-3.5-super-vl:free
uv run python -m app.run_evals --cases case3_repeat_ac_R001       # one case only (2 calls)
uv run python -m app.run_evals --targets mock:mock-deterministic-v1   # free; plumbing check only, not evidence
uv run python -m app.run_evals --regrade <RUN_ID>                 # re-grade stored replies, no model calls
```

Each run of all five cases makes **10 model calls per target** (5 cases × 2 modes). Free OpenRouter keys have daily request limits, so use `--cases`, `--regrade` or the mock target while developing. Results are stored in SQLite and exported to `evals/actual_results.json`. Each result records:

- provider, plus requested and served model
- prompt version and temperature
- latency, tokens and estimated cost
- automated criteria and the human verdict

**Latest real run** (2026-11-01, `openrouter:nvidia/nemotron-3.5-super-vl:free`, same settings both modes):

| | Good (provisional) | Avg latency |
|---|---|---|
| McKinley-aware | 5/5 | 9.7 s |
| Generic baseline | 0/5 | 4.7 s |

The baseline failed on false action claims ("I'll escalate…", "we'll reach out…"), on "bedroom" wording and on tone. Details and rationale are in [`evals/actual_results_review.md`](evals/actual_results_review.md). These verdicts are automated checks plus an AI rubric review, **not human verdicts**; confirm them in the dashboard.

## Changing LLM providers

Set `LLM_PROVIDER` and `LLM_MODEL` in `backend/.env` and restart the backend:

| Provider | Settings | Notes |
|---|---|---|
| OpenRouter (default) | `LLM_PROVIDER=openrouter`, `LLM_MODEL=nvidia/nemotron-3.5-super-vl:free`, `OPENROUTER_API_KEY=…` | Free `:free` models change often; list them at `https://openrouter.ai/api/v1/models`. |
| Ollama | `LLM_PROVIDER=ollama`, `LLM_MODEL=llama3.2` | `ollama serve` then `ollama pull llama3.2`. No key. |
| Mock | `LLM_PROVIDER=mock`, `LLM_MODEL=mock-deterministic-v1` | Deterministic templates for UI and tests only |
| Anthropic (optional) | `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-opus-5-5`, `ANTHROPIC_API_KEY=…` | `uv sync --extra anthropic` |

To compare models, list them in `EVAL_TARGETS`. Each result is tied to exactly one `provider:model`. A failing model is recorded as an error and **never silently replaced**.

To add a provider:

1. Implement `LLMProvider.complete` in `backend/app/llm/`.
2. Register it in `FACTORIES`.
3. Add tests using `httpx.MockTransport`.

## Tests and checks

```bash
cd backend && uv run pytest && uv run ruff check .                        # 46 tests, no network
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
npm run build                                                               # (root) static export → dist/
```

## here.now and the team workflow

The staff pipeline (`.github/workflows/herenow.yml`) runs `npm ci && npm run build` at the root and publishes `dist/`.

- **What gets built:** the root `build` script makes a **static export** of the Next.js frontend (`frontend/scripts/export-static.mjs`). The dev site and previews therefore show the UI.
- **What isn't hosted:** here.now can't run the Python backend. When the hosted page can't reach a backend, it switches to a clearly labelled **static demo**: pre-computed MOCK responses for the 14 scenarios, with free-text chat disabled. To get live answers, point the page at a running backend, for example a teammate's local one with the page's origin added to `CORS_ORIGINS`.
- **Smoke test:** run `npm run smoke` after `npm run build` (it needs Playwright).

Branch rules from `CLAUDE.md` / `START-HERE.md` still apply: open pull requests into `development` and never push to `main`.

## Data and privacy

**This repository is public.**

- **Data:** use synthetic or properly de-identified data only.
- **What reaches the model:** the backend forwards only an allowlisted, redacted, topic-relevant summary. It never sends contact details, rent, balances, raw staff notes or transcripts. Free hosted model APIs may log prompts.
- **What's never committed:** `.env` files, keys, SQLite databases and the workbook are git-ignored. Only `.env.example` placeholders are tracked.

## Current limitations

- **Eval size:** five synthetic cases with one sample each. That demonstrates the system working; it isn't statistical evidence, and runs at temperature 0.2 can differ.
- **Grading:** the automated tone and personalization checks are keyword heuristics. A human needs to review them.
- **Models tested:** only one model has produced real outputs so far. `google/gemma-4-31b-it:free` returned upstream 429s; `dots-studio/dots-3-note-preview:free` passed a probe but hasn't been fully evaluated.
- **Untested live:** Spanish-language, emergency, prompt-injection and "connect me to a person" cases are covered by offline tests only. The nine extended scenarios and the LLM/Jev gates have not been run against a live model, because no key was configured during development.
- **Gate coverage:** the rules gate matches keywords in English and basic Spanish. It misses paraphrases and other languages (see GATE_DESIGN.md).
- **No integrations:** there is no live Yardi or Databricks connection, no work orders, no messaging and no real staff handoff. Handoffs are recommendations shown in the UI.
- **Hosting:** the backend is local-only, and the here.now build is UI-only (see above).
