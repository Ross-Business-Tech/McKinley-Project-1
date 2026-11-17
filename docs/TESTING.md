# Testing and evaluation

Three kinds of evidence, never mixed:
- **Deterministic tests** (offline, every commit): the guarantees the backend owns, such as safety rules, privacy,
  consent, task state and persistence. They use the **mock** provider or scripted fakes, so they say nothing about
  conversation quality.
- **Live evaluations** (bounded, on demand, needing approval): the real model and classifier on a written test set.
- **Regression checks**: re-runs of known failing cases after a fix. These are **not** independent evidence.

## Run the suites

```bash
cd backend && uv run pytest && uv run ruff check .        # offline; tests never read backend/.env
npm run lint && npm run typecheck && npm test && npm run build   # from the repo root (frontend)
npm run smoke                                               # headless browser check, when the UI changed
```

For a disposable database in manual testing, add `DATABASE_URL=" " DB_PATH="$(mktemp -d)/mvp.sqlite3"` to the backend
command.

| Suite (`backend/tests/` unless noted) | Covers |
| --- | --- |
| `test_acceptance.py` | MVP requirements as multi-turn conversations: own history, emergencies, privacy refusals, consent and Send-once, handoff and guest notes |
| `test_safety_detection.py`, `test_safety_pipeline.py`, `test_risk_policy_table.py` (+ `safety_devset.py`) | Detection rules, framing, the policy table, incident state, approved wording |
| `test_remediation.py` | Provider failures never remove crisis guidance; emergency continuity; task and consent fixes. Includes 3 strict `xfail`s for known gaps. |
| `test_acceptance_remediation.py` | Tour and note routing, Send only for the card on screen, the legal / fair-housing boundary (EN, ES, positive and negative), decision-log diagnostics |
| `test_history_retrieval.py` | History matched by the thing named (EN, ES), own records only |
| `test_authorization.py` | Principals, scoped store, session binding, hosted vs local, staff guard, generated attack combinations |
| `test_api_persistence.py` | API contract, SQLite / Postgres persistence (Postgres needs `TEST_DATABASE_URL`), migrations |
| `test_llm_providers.py` | Every provider adapter over fake transports, structured output, error mapping without leaking keys |
| `test_render_blueprint.py` | `render.yaml`: the pinned hosted configuration, no fallback, no committed secrets, refused unapproved start |
| `test_experiment_safety_v2.py`, `test_experiment_legal_v2.py` | The **offline** experiments in `backend/experiments/`: what they may and may never change |
| `frontend/src/**/*.test.ts(x)`, `frontend/e2e/mobile-acceptance.mjs` | Website components and API client; Chromium and WebKit at phone, tablet and desktop sizes against a mock backend |

`tests/fakes.py` holds the one scripted model provider used by the multi-turn tests.

## Evaluations so far

All outputs are local and git-ignored, under `evals/`. The commit given is the code each one ran against.

| Date | What | Code | Result | Where |
| --- | --- | --- | --- | --- |
| 2026-11-15 | **Fresh regression evaluation**: 278 cases written by AI test authors isolated from the code; live U-M Toolkit `gpt-6.1-sol` plus classifier; 731 model calls | `537410a` | Emergency full-alert recall 106/107; any guidance 113/115 (misses E086, E091: content-filter rejections); 6/50 benign full alerts and 10/50 calm lines; privacy 0/45 failures; 0 unauthorized or duplicate saves | `evals/final/` (`RUN.md`, workbook) |
| 2026-11-15/16 | Post-fix regression for PR #18 | `cc6f002`, `b397aa3` | The PR #18 fixes hold; not independent evidence | `evals/postfix_*` |
| 2026-11-17 | **Acceptance**: the team's 25-case workbook plus 10 pre-written "must never" cases, live, independent of the 278-case set | `ea734af` | Original 25: 11 pass / 4 fail / 10 review. Must-never 10: 7 / 2 / 1. Fails: T1a, T1b, T1c, T3c, MN6, MN9. | `evals/acceptance/` (`SUMMARY.md`, completed workbook) |
| 2026-11-17 | Post-fix regression for PR #20 (MN6, MN9, plus new wording) | `fe10460` | 11/11 as expected; labelled regression | `evals/regression_2026-11-17/` |

**Status of the acceptance failures:**
- **Fixed on `development`:** MN6 (tour and note routing) and MN9 (legal boundary).
- **Changed only on the unmerged feature branch:** T1a/T1b (history matching).
- **Still open:** T1c (a false 988 line on an angry message); T3c (the entry window on file not used); the REVIEW
  cases, which need human adjudication of the expected answers.

**Limits of the evidence:**
- The test sets are AI-authored or team-authored, not written by an independent person.
- Each live run is one run of a non-deterministic model.
- Grading is automated, with documented adjudications.
- Multilingual coverage is thin.
- No real phone or screen reader has been in the loop.
- Measure any safety change on a **fresh** holdout written by someone else; never tune on one.

## Known gaps (do not hide)
- **False alarms from low-precision rules**, which the classifier can't remove:
  - full alerts on B015, B016, B026, B049, B050;
  - calm 988 / 911 lines on everyday wording ("I'm done with this place", "by tomorrow", "ceiling leak").
- **Some self-harm method-seeking phrasings** are still missed by the rules. They depend on the classifier; under a
  provider content-filter block they get only the calm 988 line.
- **Three strict expected failures** in `test_remediation.py`: two false-alarm look-alikes, and a news-plus-smoke
  message that gets only a calm line.
- **Legal boundary:** a fresh Spanish paraphrase ("deben eximirle de la cuota") gets past the patterns. It is pinned
  in `test_experiment_legal_v2.py`.
- **Provider safety blocks:** Gemini and Anthropic blocks map to `MODEL_REFUSAL`; content-filter handling covers the
  U-M Toolkit and OpenRouter.
- **Experiments are offline only:** `backend/experiments/README.md` gives their results and what adoption would need.
