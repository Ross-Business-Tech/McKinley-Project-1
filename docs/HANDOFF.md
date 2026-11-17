# Handoff: current state

For the next developer or Claude Code session. Read the [README](../README.md), then
[ARCHITECTURE.md](ARCHITECTURE.md). The root [CLAUDE.md](../CLAUDE.md) (Ross IT) wins on publishing, branches and the
staff-owned paths (`scripts/`, `.github/`, `.claude/`, `admin/`, `CLAUDE.md`).

## Where things stand (2026-11-17)

| | State |
| --- | --- |
| Verdict | A working **prototype on synthetic data; not production ready** |
| `development` (deployed to Render) | The MVP (one model call + task controller), the safety and workflow remediation, the pinned Render Blueprint, and the acceptance fixes for tour/note routing and the legal boundary. `main` shows the Ross IT "Coming soon" page until staff reveal it. |
| Feature branch `refactor/post-mvp-simplification` (**not merged, not deployed**) | (1) dead code and duplicates removed; (2) `run_turn` split into steps, no behaviour change; (3) Safety V2 and (4) Legal V2 as **offline-only** experiments in `backend/experiments/`; (5) history matched by the thing named (a behaviour change); these docs |
| Live demo | Render website + backend from `development`, Supabase with synthetic data, running `APP_ENV=local` with demo personas on ([DEPLOYMENT.md](DEPLOYMENT.md#2-environments)) |
| Model | U-M GPT Toolkit `gpt-6.1-sol`, with the classifier on the same model. **University approval for a public site is not confirmed.** |

## Requirements coverage (McKinley brief, F1–F9)
| | Function | State |
| --- | --- | --- |
| F1 | Phone / voice | Not built |
| F2 | SMS / email channel rules | Not built |
| F3 | Caller type (resident, prospect, visitor) | Demo identity only; no real sign-in |
| F4 | FAQs from approved content | Approved knowledge-base answers only; other topics say so and offer a note |
| F5 | Tour request | A request card, **never a booking** |
| F6 | Maintenance intake, emergency first | Working with draft rules; emergency detection not production ready |
| F7 | Work orders | Prototype store only ("saved in demo"); no Yardi |
| F8 | Request status | The person's own synthetic history and prototype records |
| F9 | Human handoff | A note card for the office. **Nobody is notified**, and it never claims staff were contacted. |

## Known issues
| | Issue |
| --- | --- |
| P0 | Some emergencies are still missed by the rules ([TESTING.md](TESTING.md#known-gaps-do-not-hide)); release-blocking |
| P0 | Safety wording is team draft, **not McKinley-approved**; nobody is paged or dispatched |
| P0 | **No real authentication**: the demo persona is chosen in the browser; synthetic data only |
| P1 | False alarms from low-precision rules: 5 full-alert look-alikes, and calm 988 / 911 lines on everyday wording |
| P1 | Render runs `APP_ENV=local`: public API docs, no startup checks or rate limits, Toolkit approval check skipped |
| P1 | The legal boundary is pattern matching (EN / ES) with a known Spanish miss; the referral wording is provisional |
| P1 | No Yardi, Databricks, CRM, work-order, SMS or voice integration |
| P1 | Conversation quality depends on the live model; evaluated only in bounded runs |
| P1 | No real-device or screen-reader test on the deployed site |
| P1 | Spanish wording is a draft (NEEDS McKINLEY REVIEW) |

## Pending approvals
- **University:** written confirmation that the U-M Toolkit key may serve a public website. Only then set
  `UM_TOOLKIT_HOSTED_APPROVED=true`.
- **McKinley:**
  - the safety scripts;
  - the fair-housing referral wording (`fair_housing`, `pending_approval`);
  - Spanish wording;
  - the acceptance workbook's expected answers (the REVIEW cases).
- **The project owner:**
  - live checks for the experiments: about 60 classifier calls for Safety V2, plus a label-accuracy run for Legal V2;
  - whether to fix the known Spanish legal miss now.

## Recommended next actions
1. **Review and merge the feature branch's behaviour-preserving parts** (cleanup, the `run_turn` split) and the
   history change; keep the experiments offline.
2. **Get, or rule out, the Toolkit approval.** Then either set the flag or choose another provider deliberately and
   run a live check.
3. **Allow the synthetic persona switcher on a hosted backend** while keeping every other hosted check, then return
   Render to `APP_ENV=hosted`.
4. **Safety false alarms:** before adopting Safety V2, a reviewer splits the "finality" wording group, the classifier
   is checked live (with approval), and the policy is tested on a fresh holdout (`backend/experiments/README.md`).
5. **Before any production use:** real sign-in, staff accounts and an audit log, real integrations, retention
   controls, and legal and vendor review.

## Working on this repository
- **Before starting:** run `git status` and `git fetch origin development`, and merge if behind. Never lose
  uncommitted work.
- **Branches:** work on a feature branch and open pull requests into `development`. Never push to `main`, never
  force-push, never rewrite shared history, and don't merge your own PR unless asked.
- **Stack:**
  - `frontend/`: Next.js static export, React, TypeScript (strict), Tailwind; `npm` for the website.
  - `backend/`: Python 3.12, FastAPI, Pydantic v2; `uv` only for Python.
  - Lock files are committed.
- **Conversation:** the model proposes and the backend decides. Change behaviour through `assistant.RULES` or the
  task rules in `tasks.py`, **not** by adding natural-language regexes. Deterministic code is for safety, privacy,
  consent and task state only.
- **Safety-critical changes** (`risk/`, `emergency.py`, safety wording, staff guard, identity rules) need:
  - positive and negative tests;
  - the policy table (`test_risk_policy_table.py`);
  - the full suite;
  - an **independent** review.

  Measure recall only on a fresh holdout written by someone else.
- **Database:** schema changes only through a new Alembic migration, with row-level security on every new Postgres
  table. Seed only the synthetic workbook.
- **Wording:**
  - fixed backend text lives as constants in `chat_engine.py`, `tasks.py`, `guardrails.py` and `emergency.py`;
  - website text is in `frontend/src/lib/customer.ts` (EN plus draft ES);
  - knowledge-base answers are in `backend/app/content/knowledge_base.json`, where only `approved` entries may be
    stated.
- **UI:**
  - WCAG 2.2 AA, phones first;
  - "Talk to a person" is always visible, and emergency contacts appear only inside a safety state;
  - brand tokens are `mk-*` in `frontend/src/app/globals.css`;
  - read back before any save, and say plainly what was and wasn't sent.
- **Definition of done:**
  - behaviour with tests;
  - backend and frontend suites, lint, typecheck and build pass ([TESTING.md](TESTING.md));
  - smoke and a phone check when the UI changed;
  - no secrets or real data;
  - the docs your change makes untrue updated in the same PR;
  - a PR into `development` that says it's a prototype.
- **Subagents:** give a precise brief. Reviewers must not grade their own work. Never let a subagent edit Ross IT
  paths or secrets.

**History:** sprint reports, the pre-MVP planner design, older evaluations and the former `docs/` tree are in Git
history. Use `git show 537410a:docs/<path>` for the old docs and `git show 59c155c:<path>` for sprint reports.
