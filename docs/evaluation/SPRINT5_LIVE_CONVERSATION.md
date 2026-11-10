# Sprint 5: live conversation, workflow fixes and Gemini readiness (2026-11-10)

Branch `feat/live-conversation-workflows`. It is built on `feat/mckinley-mobile-brand-redesign`, which is PR #3 into
`development` and not merged yet. Prototype, synthetic data, **not production ready**.

## Status at a glance

| Item | Label | Evidence |
| --- | --- | --- |
| OpenRouter live calls | **BLOCKED**: no `backend/.env`, so no `OPENROUTER_API_KEY` | `preflight`: keys all false; 0 real API calls this sprint |
| Gemini live calls | **BLOCKED**: no `GEMINI_API_KEY`; no call has ever been made | [GEMINI_ACCEPTANCE_CHECKLIST.md](../development/GEMINI_ACCEPTANCE_CHECKLIST.md) |
| A/B/C real-model comparison (5 scenarios × 3 modes = 15 calls) | **BLOCKED**. The runner was verified offline: budget, balanced cases, stop on 429, every field logged | `tests/test_live_smoke_abc.py`; mock dry run 15/15 would-be comparable |
| Provider-independent contract | **VERIFIED offline** (fake SDK and HTTP responses, no network) | `tests/test_provider_contract.py`, 102 tests |
| Gemini adapter | **Gemini-ready, not live tested** | the same contract suite |
| Conversation workflow fixes | **VERIFIED with Mock** | 1002 backend tests; resident, prospect and judge simulations; regression verifier |
| Interactive chat in the browser | **VERIFIED with Mock** (local backend) | phone test 14/14 (Chromium and WebKit × 7 sizes); WebKit flow screenshots |
| Public deployment | **Pending deployment** | [DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md) |
| Emergency recall | **Known safety blocker**: 10 of 63 new immediate-danger cases got nothing | [safety-evaluation.md §8](../safety/safety-evaluation.md) |

## OpenRouter model (pinned, not changed)
`openrouter:nvidia/nemotron-3.5-super-vl:free`. It was checked against the public `/api/v1/models` list (465
models) on 2026-11-10:
- listed and free;
- context 1,000,000;
- supports `response_format` and `structured_outputs`.

The other `EVAL_TARGETS` entries:
- `google/gemma-4-31b-it:free` has no structured outputs;
- `dots-studio/dots-3-note-preview:free` expires on 2026-12-31.

**Real API calls: 0** (no key).

## Provider-independent interface (Workstream A2 / F)
- Every provider implements `complete(system, messages, target, cfg, schema)` and returns a normalised
  `LLMResult`.
- `app/llm/contracts.py` names the three application uses, which delegate to the gateway:
  - `generate_response` uses the reply schema;
  - `decide_gate` uses the gate schema;
  - `classify_risk` uses the classifier schema.
- **Field extraction stays deterministic** (`intake.py`) so that it can be audited. The model never fills or
  overwrites card fields.
- The contract suite asserts the same results on OpenRouter and Gemini for: system prompts, history roles, the
  exact model, the three schemas, parsing, usage including thinking tokens, the served-model check, and 10 error
  kinds.
- Real differences are asserted, not hidden (details in [gemini.md](../deployment/gemini.md)):
  - temperature is sent to OpenRouter only;
  - cost is reported by OpenRouter only;
  - retries happen in the app for OpenRouter and in the SDK for Gemini;
  - errors inside a 200 response and HTTP 402 are OpenRouter-only;
  - `API_KEY_INVALID` and prompt blocks are Gemini-only.

## Conversation fixes (Workstream B)
Details: [../architecture/CONVERSATION_STATE.md](../architecture/CONVERSATION_STATE.md). These are all
deterministic planner changes with tests (`tests/test_sprint5_conversation.py`, `tests/test_sprint5_round2.py`).

**Frustration and people**
- A frustrated or lost user gets one apology and the single next step, then an office note with the details
  already given (D-12).
- A request for a person or manager is recognised in any state (D-11).
- Questions about another resident get a clear boundary (R-4).

**After a send**
- Questions are answered from the saved request (D-9, R-5).
- Changes attach to the sent request instead of creating a duplicate (P-2, J-5).
- "Is my tour confirmed?" gets "nothing is booked yet".
- "Did it go through?" during a draft lists what's missing (D-10).

**Tours**
- Move-in is kept separate from tour timing (D-8, P-1).
- No question is asked a third time.
- Contact details are never stored and the reply says so (P-6). The card has a contact-route line.
- Floor plans and budget get an honest one line, with the tour pitch at most once (D-21, P-3).
- Leasing notes list every unanswered topic (P-4).

**Repairs**
- Corrections never overwrite the problem text (R-1).
- User-stated repeats are flagged for manager review (R-3, J-6).
- Lock repairs offer Front door and are high priority (D-13).
- Baby or extreme temperature raises priority (R-7).
- Contact preference typed in chat wins (D-20).
- Early move-out is not treated as a renewal (D-14).
- "The one for the sink leak" matches the existing request (D-15).

**Spanish**
- Switching to Spanish keeps the card (R-2).
- Spanish entry answers are understood. "no pueden entrar" used to be read as permission to enter.
- Spanish meta questions and knowledge-base topics are recognised.

**Crisis follow-ups (J-1, NEEDS McKINLEY REVIEW)**
- After a self-harm, personal-safety or medical alert, follow-ups no longer get the maintenance wording.
- Direct "what do I do / call someone" asks get that hazard's approved notice verbatim.
- Privacy questions get the note's real label ("Self-harm risk"), and are told the person's words are withheld.

## Simulations and judge (Mock only; not model quality)
| Reviewer (independent) | Before the round-2 fixes | After (regression verifier, replayed) |
| --- | --- | --- |
| Resident simulator: 16 conversations, 76 calls | 5 pass, 8 partial, 3 fail; 0 false claims; 0 leaks | R-1–R-7 and R-9 fixed; R-8 and R-10 partial; R-11 deferred (needs approved wording) |
| Prospect simulator: 15 conversations, 94 turns | 12/15 goals; 0 false booking claims; 7 lost-info cases | P-1, P-3, P-4, P-6, P-8 and P-12 fixed; P-2, P-5, P-7, P-9, P-10 and P-11 partial; P-13 open |
| UX judge: 91 replies, 41 conversations | Honesty 4.90, empathy 3.05, context 3.65, progress 3.71, clarity 4.11, questions 4.80 (out of 5) | J-2, J-4, J-5 and J-6 fixed; J-3, J-7 and J-9 partial; J-8 and J-10 open |
| Sprint 4 list (D-8 to D-22) | open | all fixed except D-18 (no heat-safety tip) |

**Usability suite** (48 scenarios, mock), comparing before Sprint 5 with after round 1. Round 2 left these numbers
unchanged, because none of the scenarios exercise those fixes:

| Measure | Before | After round 1 |
| --- | --- | --- |
| Repeated questions | 11 | 4 |
| Questions asked | 80 | 67 |
| Unnecessary questions | 7 | 5 |
| Friction | 1.06 | 0.85 |
| Outcomes | unchanged | unchanged |
| False claims, safety violations | 0 | 0 |

**Honesty scan** (469 replies): every "sent / notified / booked / confirmed" phrase is a negation, and no prices
were invented.

## Safety (Workstream C)
- **Holdout:** an independent red-team set of 123 new cases (63 immediate danger), deterministic layer only. The
  semantic classifier is `degraded` without a key.
  - Full alert 50/63, any guidance 53/63.
  - Look-alikes given a full alert: 5/30.
  - Injection successes 0/15; dispatch claims 0.
- **10 immediate-danger messages with no guidance are RELEASE-BLOCKING.** They are listed by category in
  [safety-evaluation.md §8](../safety/safety-evaluation.md), and the holdout is kept outside the repo.
- **Before vs after:** the same holdout re-run on the final code gave identical scores, so the conversation
  changes did not weaken safety.
- **Not tuned:** no safety rule changed in this sprint. The holdout must not be reused for tuning.
- **Still open:**
  - wrong guidance inside some alerts (hot car → elevator text);
  - the `no_invented_time` output check flags times the user typed (`safety.py`, needs a safety-owned change);
  - no approved wording for "lock won't lock tonight".
  - the crisis follow-up P2s from the re-verification:
    - the Spanish privacy reply quotes the English label ("Self-harm risk"), while the Spanish note says only
      "Posible emergencia";
    - "is this private?" is not recognised as a privacy question;
    - "what should I do right now?" asked after an unrelated message gets the generic menu (the care line still
      shows).

## UI and browser (Workstream G)
- **Reply source:** "About this demo" names the source, e.g. "OpenRouter: model-id", "Gemini: …", fixed rules for
  the mock, or approved wording on a live provider.
- **Phone test:** `frontend/e2e/mobile-acceptance.mjs` 14/14 against the Sprint 5 backend. It fills the box, sends,
  takes replies, sends a follow-up and refreshes.
- **WebKit 390px flow:** a frustrated resident's office note appears with "Check, then send". After Send it shows
  "DEMO-TASK-…" with "In the office queue", and the reply says nobody is notified automatically.

## What a human does with a key (from `backend/`)
1. Put `OPENROUTER_API_KEY=…` in `backend/.env` (git-ignored). Never in chat, commits or the website.
2. `uv run python -m app.live_eval.preflight`: the pinned model must show as listed and ready.
3. `uv run python -m app.live_eval.smoke --provider openrouter --max-calls 8`. It stops on the first 429 and writes
   `evals/live/smoke-*.json`.
4. `uv run python -m app.live_eval.abc --target recommended --scenarios none --max-calls 15 --label live-abc-1`.
   That is 5 scenarios × 3 modes = 15 calls; then a person reviews the records.
5. Record the results here. The smoke and A/B/C runs are smoke evidence, **not** proof of safety or quality.

For Gemini, follow [GEMINI_ACCEPTANCE_CHECKLIST.md](../development/GEMINI_ACCEPTANCE_CHECKLIST.md).
