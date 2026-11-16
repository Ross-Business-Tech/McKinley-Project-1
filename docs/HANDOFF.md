# Handoff and how to work here

For the next developer or Claude Code session. Read [README.md](../README.md), then
[ARCHITECTURE.md](ARCHITECTURE.md). The root [CLAUDE.md](../CLAUDE.md) (Ross IT) wins on publishing, branches and the
staff-owned paths (`scripts/`, `.github/`, `.claude/`, `admin/`, `CLAUDE.md`).

## Where things stand (2026-11-16)
- **Verdict:** a working **prototype on synthetic data; not production ready.**
- **Code:** the simplified MVP is on `development` (PR #14, the "MVP reset": identity → safety → one model call →
  task controller → guardrails). Staff token sign-in on the hosted staff page: PRs #15 and #16. Docs consolidated: PR #17. Safety and workflow
  remediation (crisis guidance survives provider failures, emergency continuity, task and consent fixes): PR #18,
  merged 2026-11-15 as `ea734af`. `main` shows the Ross IT "Coming soon" page until staff reveal it. PR #13 (guest
  repairs on the removed planner) was closed, superseded by #14.
- **Live demo:** Render website + backend from `development`, Supabase (development project, synthetic), running
  with `APP_ENV=local` and `DEMO_PERSONAS_ENABLED=true` for the sample-resident switcher (observed 2026-11-15 and
  2026-11-16; this turns off the hosted safeguards, see
  [SECURITY.md](SECURITY.md#5-hosted-vs-local-and-the-current-render-state)). Details: [DEPLOYMENT.md](DEPLOYMENT.md).
- **Model:** U-M GPT Toolkit `gpt-6.1-sol` with the semantic safety classifier on the same model: the model of the
  full evaluation and of `render.yaml`. The live Render backend served it on 2026-11-16 (OpenRouter's free Nemotron
  earlier that day); its classifier setting is not visible from outside. University approval for a public site is
  **not** confirmed, so the Blueprint's hosted configuration will not start yet. OpenRouter's free model was verified
  end to end locally as an alternative.
- **Latest evaluation:** a fresh regression evaluation of this MVP on 2026-11-15 — results and missed cases in
  [TESTING.md](TESTING.md).

## Requirements coverage (McKinley brief, F1–F9)
| | Function | State |
| --- | --- | --- |
| F1 | Phone / voice | Not built |
| F2 | SMS / email channel rules | Not in the MVP |
| F3 | Caller type (resident, prospect, visitor) | Demo identity only (no vendors, no real sign-in) |
| F4 | FAQs from approved content | Approved knowledge-base answers only; unapproved topics say so and offer a note |
| F5 | Tour request | A request card, never a booking |
| F6 | Maintenance intake, emergency first | Working with draft rules; emergency detection not production ready |
| F7 | Work orders | Prototype store only ("saved in demo") |
| F8 | Request status | The person's own synthetic history and prototype records |
| F9 | Human handoff | A note card for the office (prototype queue); never claims staff were contacted |

## Known P0 / P1 (do not hide or downgrade)
| | Issue |
| --- | --- |
| P0 | Missed emergencies remain (exact cases in [TESTING.md](TESTING.md)); release-blocking |
| P0 | Emergency and safety scripts are team drafts, not McKinley-approved; nobody is paged |
| P0 | No real sign-in: the demo persona is chosen in the browser; synthetic data only |
| P1 | The Render demo runs with `APP_ENV=local`: public API docs, no startup checks or rate limits, Toolkit approval check skipped |
| P1 | No Yardi / CRM / work-order / messaging integration |
| P1 | Conversation quality depends on the live model; evaluated only in bounded runs |
| P1 | No real-device or screen-reader test on a deployed phone yet |
| P1 | Spanish wording is a draft (NEEDS McKINLEY REVIEW) |

## Recommended next steps
1. Get (or rule out) university approval for the Toolkit on a public site. With it: set
   `UM_TOOLKIT_HOSTED_APPROVED=true` in Render. Without it: choose another provider deliberately and run a live check.
2. A small change so a hosted backend can allow the synthetic persona switcher while keeping every other hosted
   safeguard; then return Render to `APP_ENV=hosted`.
3. Have McKinley risk/legal review every missed emergency in [TESTING.md](TESTING.md) and the safety scripts.
4. Real-phone and screen-reader test on the deployed site.
5. For production: real resident sign-in, staff accounts and audit, real integrations, retention controls, vendor and
   legal review.

## Working on this repository
**Before starting:** `git status`; `git fetch origin development` and merge if behind; never lose uncommitted work.
Work on a feature branch; pull requests go into `development`. Never push to `main`, never force-push, never rewrite
shared history. Don't merge your own PR unless the team asked.

**Stack:** Next.js static export + React + TypeScript (strict) + Tailwind in `frontend/`; Python 3.12 + FastAPI +
Pydantic v2 + uv in `backend/`. `uv` only for Python (`uv sync`, `uv add`, `uv run`), `npm` for the website; lock
files are committed.

**Conventions**
- Pydantic models for every request/response; one error envelope (`HTTPException(detail={"code", "message"})`);
  ruff line length 120. Types in `frontend/src/lib/types.ts` mirror the backend models.
- **Conversation:** the model proposes, the backend decides. Don't add natural-language regexes to steer the
  conversation; change the instructions in `backend/app/assistant.py` (`RULES`) or the task rules in
  `backend/app/tasks.py`. Deterministic code is for safety, privacy, consent and task state only.
- **Safety-critical changes** (`app/risk/`, `emergency.py`, safety wording, staff guard, identity rules): the semantic
  layer only ever adds caution; safety text is fixed approved wording; never claim anyone was dispatched or notified.
  Every change gets positive and negative tests, the policy table (`tests/test_risk_policy_table.py`), the full suite
  and an **independent** review. Measure recall only on a fresh holdout written by someone else; never tune on it.
- **Database:** schema changes only through a new Alembic migration in `backend/migrations/versions/`, raw SQL for
  SQLite and Postgres, RLS on for every new Postgres table. Only the synthetic workbook may be seeded.
- **Wording:** fixed backend text lives as constants in `chat_engine.py`, `tasks.py`, `guardrails.py` and
  `emergency.py` (safety wording, chosen by `app/risk/responses.py`); website text in `frontend/src/lib/customer.ts` (EN + draft ES). Add a new string rather
  than splitting one.
- **Providers:** one fixed `provider:model` per run; never fall back to the mock silently; label mock results MOCK.
  Keys only in `backend/.env` (git-ignored) or host secrets; check presence as booleans only.

**UI standards:** WCAG 2.2 AA (keyboard, visible focus, 44 px targets, reflow at 320 px); phones first — the composer
stays pinned at every phone height, "Talk to a person" is always visible, emergency contacts appear only inside a
safety state (no persistent 911 button; one muted footer line). Brand: McKinley blue `#4e6f92` and Barlow headings
through the `mk-*` tokens in `frontend/src/app/globals.css`; status colours are not the brand (green saved, amber a
person should help, red emergency), and every status also has an icon and words. Read-back before any save; say
plainly what was and was not sent.

**Definition of done:** behaviour with tests; backend and frontend suites, lint, typecheck and build pass (commands in
[TESTING.md](TESTING.md)); smoke and the phone check when the UI changed; no secrets or real data; mock and live
results separated; the docs your change makes untrue updated in the same PR (these six files); focused commits and a
PR into `development` saying what changed, what was tested, and that it is a prototype.

**Subagents:** give a precise brief (goal, files, what not to touch, expected output). Reviewers must not grade their
own work; holdout writers must be separate from implementers. Never let a subagent edit Ross IT paths or secrets.
Optional local code index: `codegraph` (`.codegraph/`, not committed).

## History
Sprint reports, the pre-MVP planner / decision-gate / quick-fix design, older evaluations, audits and the former
`docs/` tree are in Git history, not in the tree: `git show 537410a:docs/<path>` (the last commit with the old docs,
for example `git show 537410a:docs/safety/safety-evaluation.md`) and `git show 59c155c:<path>` for sprint reports.
