# Project handoff (2026-11-10)

For the next developer or Claude Code session. Read with [`../README.md`](../README.md) and
[`development/CLAUDE_PROJECT_GUIDE.md`](development/CLAUDE_PROJECT_GUIDE.md); old chat history is not needed.

## Where things are
- **Branches:** sprints 1–3 + consolidation were merged into `development` (PR #1) and then into `main` (PR #2).
  Deployment preparation is on **`feat/gemini-supabase-deployment`** (from `development`, includes the teammate
  branch `claude/epic-brahmagupta-f1jrlx`: Supabase storage, Vercel/Render setup, legal-threat routing). Older
  branches `feat/workflow-customer-experience`, `feat/context-aware-ai-assistant`, `feat/agentic-workflow-gates` and
  `sprint3/live-eval` are fully merged and can be deleted by the owner.
- **Target hosting (prepared, not deployed):** Render (website + backend) + Supabase (database + sign-in); replies
  from the rules responder now, Gemini later (Ross IT approved hosting on Render) — see
  [`DEPLOYMENT_READINESS.md`](DEPLOYMENT_READINESS.md) for status, missing access and the checklist.
- **Verdict:** a working **prototype on synthetic data; NOT production ready.**

## What works (tested, mock model)
- Customer chat: maintenance intake with read-back and confirm, tour requests, status, FAQ, office notes, renewal
  questions, English/Spanish, corrections, several problems per message, lockout, false-premise and
  not-the-account-holder handling; static replay on here.now.
- Safety pipeline (`backend/app/risk/`): rules, optional semantic classifier, policy R1–R9e, approved text,
  escalation; persistent care line after a disclosure.
- Staff console: saved requests, live conversations with needs-action markers, inspector, coverage, usability,
  A/B/C comparison, five-case evaluation.
- Deployment code (offline-tested): Gemini provider, Alembic migrations + synthetic seed, residents from the
  database, `APP_ENV=hosted` safety checks, Render Blueprint (website + backend), Supabase sign-in (token check, invite list,
  sign-in form; tested against a stand-in, never against a real Supabase project), live/mock labels in both views.
- Evaluation tooling: five cases, gate scenarios, 17 journeys, 48-scenario persona suite, live A/B/C runner.
- Sprint 6 (`feat/robust-workflow-safety-auth`): structured understanding layer, workflow state machine, server-side
  principal with deny-by-default data access, concept-based safety with persistent incident state
  ([evaluation/SPRINT6_RESULTS.md](evaluation/SPRINT6_RESULTS.md)).
- Tests (Sprint 6 branch): 2350 backend (+9 skipped: Postgres-only, need TEST_DATABASE_URL; not a Supabase validation), 54 frontend;
  build, smoke and the Chromium/WebKit phone test (`frontend/e2e/mobile-acceptance.mjs`, 14/14, mock backend) pass.
- Sprint 4: McKinley blue brand system and mobile-first chat ([design/](design/), [IMPLEMENTATION_CHANGELOG.md](IMPLEMENTATION_CHANGELOG.md)). See [`evaluation/README.md`](evaluation/README.md).

## Known P0 / P1 (do not hide these)
| | Issue | Where documented |
| --- | --- | --- |
| P0 | Missed emergencies: fresh independent holdout 64.5% full alert / 78.5% any guidance; 14 immediate-danger misses listed verbatim for human review | [safety/safety-evaluation.md](safety/safety-evaluation.md) §6 |
| P0 | Semantic safety classifier never run on a real model (no key) | [evaluation/live-llm.md](evaluation/live-llm.md) |
| P0 | Sign-in is built (Supabase emailed code, invite list, staff sign-in) but **never run against a real Supabase project or real email delivery**; the demo persona is still chosen in the browser wherever demo personas are on, and hosted mode turns it off. Real resident data must stay disconnected | [security/SUPABASE_AUTH.md](security/SUPABASE_AUTH.md), [security/AUTHORIZATION_BOUNDARIES.md](security/AUTHORIZATION_BOUNDARIES.md) |
| P0 | Emergency and safety scripts (I-17/I-18) are team drafts, not McKinley-approved; nobody is paged | [workflows/traceability.md](workflows/traceability.md) |
| P1 | No Yardi / CRM / work-order / messaging integration (prototype store only) | README |
| P1 | No live-model evaluation since one sprint-1 run; all later results are mock | [evaluation/README.md](evaluation/README.md) |
| P1 | One open card per conversation; Spanish multi-issue merge; Spanish wording unreviewed; ~10% false safety alerts | [evaluation/ux-review.md](evaluation/ux-review.md) |
| P1 | No real-device test (iPhone/Android, screen reader) and no public URL: the phone requirement is unmet | [INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md) |
| P1 | Live OpenRouter verified on one fixed model (46 real calls, Sprint 5.1); Gemini still never called; no A/B/C real-model comparison yet | [evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md](evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md) |
| P0 | Emergency recall: Sprint 6 independent holdout 80/105 full alert, 93/109 any guidance; **16 immediate-danger messages get no guidance** (release-blocking); crisis wording needs McKinley review | [safety/SAFETY_STATE_AND_EVALUATION.md](safety/SAFETY_STATE_AND_EVALUATION.md) §7 |
| P0 | Semantic safety layer and model understanding not evaluated live in Sprint 6 (OpenRouter free tier rate-limited, HTTP 429) | [evaluation/SPRINT6_RESULTS.md](evaluation/SPRINT6_RESULTS.md) §6 |
| P1 | Policy decision: the semantic layer may still remove the broad R7 care line; the Sprint 6 brief says it may never suppress | [evaluation/SPRINT6_RESULTS.md](evaluation/SPRINT6_RESULTS.md) §8 |
| P1 | Open Sprint 6 conversation items (prospect callback replaced by a tour card, "weird noise" routing, "is someone coming?" after Send, some paraphrases and dates) | [evaluation/SPRINT6_RESULTS.md](evaluation/SPRINT6_RESULTS.md) §8 |
| P2 | Remaining conversation backlog after Sprint 5 (stitched wording, Spanish card values, a few partial fixes) | [evaluation/SPRINT5_LIVE_CONVERSATION.md](evaluation/SPRINT5_LIVE_CONVERSATION.md) |
| P1 | `/api/chat` returns staff diagnostics (`risk`, `gate`, `pipeline`) to the browser; decide whether to strip them for non-staff callers | [architecture/overview.md](architecture/overview.md) |

## Recommended next priorities
1. Follow [`DEPLOYMENT_READINESS.md`](DEPLOYMENT_READINESS.md): Gemini key → preflight → a small live A/B/C run
   (`--allow-paid --max-calls 30`) and a `--with-safety-classifier` run; human review of the records; Supabase
   migrations + seed; Postgres tests (`TEST_DATABASE_URL`); Render (website and backend); then check Supabase sign-in
   end to end on a real project ([development/deploy-render-supabase.md](development/deploy-render-supabase.md)).
2. Have a separate person write a **fresh** safety holdout and measure the semantic classifier on the real target;
   McKinley risk/legal reviews every failure and the safety scripts.
3. Decide production identity (server-side session binding) and whether diagnostics leave the API for customers.
4. Lower-risk refactors still open (from the consolidation audit, not done to avoid behaviour risk):
   split `actions.plan_turn` (~780 lines) into its three largest leaf blocks without reordering, with a
   characterization snapshot first; split `CustomerApp.tsx` / `StaffConsole.tsx` (add StaffConsole tab tests
   first); unify status-colour maps; move inline `lang == "en"` strings in `actions.py` into `templates.py`;
   consolidate sprint-named test files by behaviour area (mapping in the consolidation PR description).

## How to verify quickly
```bash
cd backend && uv sync && uv run pytest && uv run ruff check .
cd .. && npm install && npm run lint && npm run typecheck && npm test && npm run build
```
