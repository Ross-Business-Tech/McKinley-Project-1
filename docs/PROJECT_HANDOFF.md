# Project handoff (2026-11-10)

For the next developer or Claude Code session. Read with [`../README.md`](../README.md) and
[`development/CLAUDE_PROJECT_GUIDE.md`](development/CLAUDE_PROJECT_GUIDE.md); old chat history is not needed.

> **Sprint 10 (2026-11-12):** independent prototype review remediated on `feat/review-remediation`; read
> [`evaluation/PROTOTYPE_REVIEW_REMEDIATION.md`](evaluation/PROTOTYPE_REVIEW_REMEDIATION.md) first. New behaviour to
> know: hosted rate limits (30/min per visitor, 15/min per conversation; `RATE_LIMIT_PER_MINUTE`,
> `RATE_LIMIT_PER_SESSION_MINUTE`), 64 KB body cap (`MAX_REQUEST_BYTES`), a retried confirm returns
> `ALREADY_SAVED` with the same reference, `/api/health` reports `version` and `commit`, and
> `KNOWLEDGE_CONTENT_MODE=demo_samples` shows labelled SAMPLE answers locally only (refused when hosted). Set
> `LLM_CALL_BUDGET`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` in the Render dashboard; `render.yaml` alone does not
> change the live service.

> **Repository simplification (2026-11-13):** the staff console is the staff queue only; evaluation frameworks,
> dev-only API routes (`/api/evals`, `/api/gates`, `/api/context/preview`), committed eval outputs (`evals/`) and
> sprint reports were removed (Git history `59c155c`); tests are organized by behaviour area. See
> [`evaluation/README.md`](evaluation/README.md) for what remains.

## Where things are
- **Branches:** sprints 1–3 + consolidation were merged into `development` (PR #1) and then into `main` (PR #2).
  Deployment preparation is on **`feat/gemini-supabase-deployment`** (from `development`, includes the teammate
  branch `claude/epic-brahmagupta-f1jrlx`: Supabase storage, Vercel/Render setup, legal-threat routing). Older
  branches `feat/workflow-customer-experience`, `feat/context-aware-ai-assistant`, `feat/agentic-workflow-gates` and
  `sprint3/live-eval` are fully merged and can be deleted by the owner.
- **Hosting (2026-11-11, public guest-only demo):** Render static site `mckinley-frontend` + Render web service
  `mckinley-backend` (both free, both deploy `development`), development Supabase project (synthetic), OpenRouter
  free model. Vercel stays an option. Status, tested journeys and blockers:
  [`DEPLOYMENT_READINESS.md`](DEPLOYMENT_READINESS.md). Render dashboard access: the team workspace owner.
- **Verdict:** a working **prototype on synthetic data; NOT production ready.**

## What works (tested, mock model)
- Customer chat: maintenance intake with read-back and confirm, tour requests, status, FAQ, office notes, renewal
  questions, English/Spanish, corrections, several problems per message, lockout, false-premise and
  not-the-account-holder handling; static replay on here.now.
- Safety pipeline (`backend/app/risk/`): rules, optional semantic classifier, policy R1–R9e, approved text,
  escalation; persistent care line after a disclosure.
- Staff queue (`/staff/`): saved requests and live conversations with needs-action markers. The former
  "Demo and evaluation" tools (inspector, coverage, usability, A/B/C comparison, five-case evaluation) were removed
  in the repository simplification (Git history `59c155c`).
- Deployment code (offline-tested): Gemini provider, Alembic migrations + synthetic seed, residents from the
  database, `APP_ENV=hosted` safety checks, Render Blueprint, Vercel config, live/mock labels in both views.
- Dev tools kept: `app.live_eval.preflight` and `app.live_eval.smoke` (budgeted manual provider checks) and
  `app.export_demo` (the static demo snapshot). Regression coverage lives in the domain test modules in
  `backend/tests/` (conversation, workflow, safety, authorization, API/persistence, LLM providers, decision gate).
- Sprint 6 (`feat/robust-workflow-safety-auth`): structured understanding layer, workflow state machine, server-side
  principal with deny-by-default data access, concept-based safety with persistent incident state
  (`docs/evaluation/SPRINT6_RESULTS.md` (Git history `59c155c`)).
- Sprint 9 (`feat/warm-conversational-ux`, on top of PR #6): warm, concise customer wording; one honest status
  ("Saved in demo") from `models.STATUS_LABEL` on every read; the demo limit said once per step (persistent demo
  strip, one line on each card, short confirmation); validator check `_demo_status_claim`; compact saved cards
  (`docs/evaluation/SPRINT9_WARM_VOICE.md` (Git history `59c155c`)).
- Sprint 8 (`feat/emergency-ux-maintenance-enhancements`, on top of `feat/s7-safety-regression-fixes`): no persistent
  911 control; backend `safety_state` + category-specific `safety_contacts` (normal / concern / active); R5c
  conditional questions with a confirmation escalation (R5f); repeat-issue history with community-manager review
  metadata; draft quick-fix tips behind `QUICKFIX_CONTENT_MODE` (default approved_only = none shown; hosted never
  drafts) (`docs/evaluation/SPRINT8_EMERGENCY_UX_MAINTENANCE.md` (Git history `59c155c`),
  `docs/design/EMERGENCY_UX_REVIEW.md` (Git history `59c155c`), [workflows/QUICKFIX_DRAFT_KB.md](workflows/QUICKFIX_DRAFT_KB.md)).
- Sprint 7 (`feat/s7-safety-regression-fixes`, on top of `development` / PR #4): compositional risk frame with a
  monotone "decorations never lower" invariant, structural utterance analysis and a shared field resolver, a
  customer view without diagnostics, server-issued sessions, and property-based invariant tests
  (`docs/evaluation/SPRINT7_GENERALIZATION.md` (Git history `59c155c`)). **Merge it soon:** `development`
  carries the first candidate's safety regressions.
- The test suite never reads `backend/.env`. Earlier, a real `DATABASE_URL` added there reached the seed test, so the
  owner should check that database.
- Tests (Sprint 6 branch): 2350 backend (+9 skipped: Postgres-only, need TEST_DATABASE_URL; not a Supabase validation), 54 frontend;
  build, smoke and the Chromium/WebKit phone test (`frontend/e2e/mobile-acceptance.mjs`, 14/14, mock backend) pass.
- Sprint 4: McKinley blue brand system and mobile-first chat ([design/](design/), `docs/IMPLEMENTATION_CHANGELOG.md` (Git history `59c155c`)). See [`evaluation/README.md`](evaluation/README.md).

## Known P0 / P1 (do not hide these)
| | Issue | Where documented |
| --- | --- | --- |
| P0 | Missed emergencies: fresh independent holdout 64.5% full alert / 78.5% any guidance; 14 immediate-danger misses listed verbatim for human review | [safety/safety-evaluation.md](safety/safety-evaluation.md) §6 |
| P0 | Semantic safety classifier never run on a real model (no key) | `docs/evaluation/live-llm.md` (Git history `59c155c`) |
| P0 | No real sign-in: the demo persona is chosen in the browser. Since Sprint 6 a server-side principal, session binding and a deny-by-default store limit what it reaches, and hosted mode turns it off; staff boundary is loopback / token only | [security/AUTHORIZATION_BOUNDARIES.md](security/AUTHORIZATION_BOUNDARIES.md) |
| P0 | Emergency and safety scripts (I-17/I-18) are team drafts, not McKinley-approved; nobody is paged | [workflows/traceability.md](workflows/traceability.md) |
| P1 | No Yardi / CRM / work-order / messaging integration (prototype store only) | README |
| P1 | No live-model evaluation since one sprint-1 run; all later results are mock | [evaluation/README.md](evaluation/README.md) |
| P1 | One open card per conversation; Spanish multi-issue merge; Spanish wording unreviewed; ~10% false safety alerts | `docs/evaluation/ux-review.md` (Git history `59c155c`) |
| P1 | No real-device test (iPhone/Android, screen reader) and no public URL: the phone requirement is unmet | [INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md) |
| P1 | Live OpenRouter verified on one fixed model (46 real calls, Sprint 5.1); Gemini still never called; no A/B/C real-model comparison yet | `docs/evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md` (Git history `59c155c`) |
| P0 | Emergency recall: Sprint 8 independent holdout 89.5% full alert, 91.7% any guidance (rules only); critical cases with no full alert remain (release-blocking); a few cases worse than before Sprint 7; crisis wording, contact labels and the R7 draft policy need McKinley review | `docs/evaluation/SPRINT8_EMERGENCY_UX_MAINTENANCE.md` (Git history `59c155c`) |
| P0 | No persistent 911 control (product-owner decision): a missed emergency now gets only the plain-text footer line; keep or remove that line is a product decision | `docs/design/EMERGENCY_UX_REVIEW.md` (Git history `59c155c`) |
| P1 | Quick-fix tips and the legacy checks are drafts: nothing is shown in real modes until McKinley approves entries | [workflows/QUICKFIX_DRAFT_KB.md](workflows/QUICKFIX_DRAFT_KB.md) |
| P1 | `development` (PR #4) has the first Sprint 7 candidate with known safety regressions until `feat/s7-safety-regression-fixes` is merged | `docs/evaluation/SPRINT7_GENERALIZATION.md` (Git history `59c155c`) |
| P0 | Semantic safety layer and model understanding not evaluated live in Sprint 6 (OpenRouter free tier rate-limited, HTTP 429) | `docs/evaluation/SPRINT6_RESULTS.md` (Git history `59c155c`) §6 |
| P1 | Policy decision: the semantic layer may still remove the broad R7 care line; the Sprint 6 brief says it may never suppress | `docs/evaluation/SPRINT6_RESULTS.md` (Git history `59c155c`) §8 |
| P1 | Open Sprint 6 conversation items (prospect callback replaced by a tour card, "weird noise" routing, "is someone coming?" after Send, some paraphrases and dates) | `docs/evaluation/SPRINT6_RESULTS.md` (Git history `59c155c`) §8 |
| P2 | Remaining conversation backlog after Sprint 5 (stitched wording, Spanish card values, a few partial fixes) | `docs/evaluation/SPRINT5_LIVE_CONVERSATION.md` (Git history `59c155c`) |
| P1 | `/api/chat` returns staff diagnostics (`risk`, `gate`, `pipeline`) to the browser; decide whether to strip them for non-staff callers | [architecture/overview.md](architecture/overview.md) |

## Recommended next priorities
1. Follow [`DEPLOYMENT_READINESS.md`](DEPLOYMENT_READINESS.md): provider key → preflight → budgeted smoke
   (`app.live_eval.smoke --allow-paid`), supervised workflow conversations; Supabase migrations + seed; Postgres
   tests (`TEST_DATABASE_URL`); Render; Vercel.
2. Have a separate person write a **fresh** safety holdout and measure the semantic classifier on the real target;
   McKinley risk/legal reviews every failure and the safety scripts.
3. Decide production identity (server-side session binding) and whether diagnostics leave the API for customers.
4. Lower-risk refactors still open (from the consolidation audit, not done to avoid behaviour risk):
   split `actions.plan_turn` (~780 lines) into its three largest leaf blocks without reordering, with a
   characterization snapshot first; split `CustomerApp.tsx` / `StaffConsole.tsx` (add StaffConsole tab tests
   first); unify status-colour maps; move inline `lang == "en"` strings in `actions.py` into `templates.py`.
   (Test files are now organized by behaviour area.)

## How to verify quickly
```bash
cd backend && uv sync && uv run pytest && uv run ruff check .
cd .. && npm install && npm run lint && npm run typecheck && npm test && npm run build
```
