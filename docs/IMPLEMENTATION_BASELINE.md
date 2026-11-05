# Implementation baseline (before the agentic-workflow-gates sprint)

This document records what existed at commit `c9c77c1`, on branch `feat/context-aware-ai-assistant`, which is one commit ahead of `origin/development` (`fb710d7`). It was inspected on 2026-11-05 before any changes. For what changed afterwards, see [IMPLEMENTATION_CHANGELOG.md](IMPLEMENTATION_CHANGELOG.md).

Legend: **WORKING** = implemented and tested · **MOCKED** = deterministic stand-in, labelled · **NOT IMPLEMENTED**

## Stack and deployment

| Area | Actual implementation |
|---|---|
| Frontend | **Next.js 16 / React 19 / TypeScript (strict) / Tailwind 4**, with shadcn-style components in `frontend/`. Not Vite. `npm run build` runs `frontend/scripts/export-static.mjs`: `next build` with `output: "export"`, copied to root `dist/` |
| Hosting | here.now (static only) through Ross IT's `scripts/herenow-publish.mjs` and the `.github/` workflows: a preview link from the session, and a dev site published by CI on merge to `development`. The hosted page calls `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), so **on the hosted site the AI features could not work** |
| Backend | **FastAPI on Python 3.12, managed with `uv`** (`backend/pyproject.toml`, `uv.lock`). Run with `npm run backend:dev`. **Local only**; no hosted backend exists |
| LLM providers | Provider-agnostic `LLMGateway` (`backend/app/llm/`): OpenRouter (default, `nvidia/nemotron-3.5-super-vl:free`), Ollama, Mock, and Anthropic as an optional extra. One pinned `provider:model` per call, same-model retries only, `MODEL_SWITCHED` on mismatch, JSON-schema output with lenient parsing |
| Persistence | SQLite (`backend/data/mckinley_demo.sqlite3`, git-ignored) for chat turns, eval runs and eval results. No logging of message content |

## Features found

| Feature | Files | Status |
|---|---|---|
| McKinley system prompt v0.1 (voice, beds/floor plans, fairness, no false actions, safety) | `prompts/mckinley_system_prompt.md`, `backend/app/prompts.py` | WORKING; version tag includes a content hash |
| Synthetic resident dataset (20 residents, 101 interactions) | `backend/data/*.xlsx` (git-ignored), `backend/app/context.py` | WORKING; validated on import |
| Fictional prospects ×2 and an unmatched resident | `backend/app/personas.py` | MOCKED fixtures, labelled |
| Context retrieval: allowlist, topic gating, redaction, injection screen, provenance, repeat and open-commitment flags | `backend/app/context.py`, `safety.py` | WORKING |
| Baseline vs McKinley-aware comparison (2 modes) | `chat_engine.py`, `ChatWorkbench.tsx` | WORKING |
| Pre-model policy patterns: emergency, human requested, sensitive data, fair housing/legal, financial, voucher, repeat language | `safety.py` | WORKING (English regex) |
| Human handoff: model OR deterministic signals, labelled recommendation-only | `chat_engine.merge_handoff`, `ResponseDetails.tsx` | WORKING; a flat category + reason string with no structured summary or team |
| Output checks: terminology, false action claims, invented prices/times, PII, risky DIY, JSON contract | `safety.py` | WORKING |
| Five evaluation cases, provisional grader, human review (PATCH), JSON export, re-grade without model calls | `backend/app/evals.py`, `EvalDashboard.tsx`, `evals/` | WORKING |
| Real eval run (2026-11-01): nemotron free; aware 5/5, baseline 0/5 by AI review | `evals/actual_results_review.md` | Recorded; **not human-reviewed** |
| Prompt versioning | `prompts.py` | WORKING |
| Tests | 46 backend pytest tests and vitest frontend tests; `ruff` clean | WORKING |

## Missing at baseline

- No explicit intent or urgency classification, decision-gate abstraction, or workflow selection. One prompt handled everything.
- No structured handoff (team, priority, summary, contact guidance).
- No "McKinley prompt without context" mode (B) for comparison.
- No diagnostics of routing decisions in the UI.
- No static demo for the hosted site.
- No emergency safety notice independent of model wording.
- English-only emergency detection, even though resident R012 prefers Spanish.
- Not implemented and out of scope: phone, SMS, work orders, tour booking, live pricing, Yardi/Databricks integration, authentication.

## Limitations noted

- Identity is a demo dropdown, not verification.
- Free hosted models may log prompts, so only synthetic data may be sent.
- The automated grader uses keyword heuristics.
- `backend/.env` was absent in this checkout, so no live model calls were possible during this sprint.
