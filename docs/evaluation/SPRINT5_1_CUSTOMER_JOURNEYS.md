# Sprint 5.1: customer journeys, live OpenRouter, workflow fixes (2026-11-10)

Branch `feat/live-conversation-workflows`. Prototype, synthetic data only, **not production ready**.

The goal was that residents and prospects finish their journeys with fewer questions and failures, correct context
and honest action status. Every result below is labelled **LIVE** (real OpenRouter model) or **MOCK**
(deterministic fixed-rule responder).

## Live model status
- **Model:** one fixed model, `openrouter:nvidia/nemotron-3.5-super-vl:free`. No model comparison was run.
  - The key was verified without printing it.
  - Preflight listed the model as free, with structured outputs and a 1,000,000-token context.
- **Real OpenRouter calls:** 46 in total, against a budget of 60. All were served by the requested model, with no
  rate-limit errors.
  - 7: smoke test (6/6 steps passed).
  - 1: the reasoning check.
  - 19: priority journeys before the fixes.
  - 19: the same journeys after the fixes.
  - Every call except the smoke run is in a metadata-only ledger (`LLM_CALL_LEDGER`: no prompts or replies).
- **Reasoning:** `OPENROUTER_REASONING_EFFORT=none` turned the model's reasoning off.
  - The slowest smoke turn went from 48 s with about 1,400 thinking tokens to 3.4 s with 0.
  - Journey turns that called the model took 0.9 / 1.5 / 8.5 s (min / median / max).
- **TypeSafe (Jev):** 16 real calls.
  - 2 contract checks, run after the adapter was compared with the official docs.
  - A 14-scenario gate eval: Jev intent 13/14, handoff 9/10, 0 critical misses, about 116 ms. Rules scored 14/14
    and 10/10 on these in-repo scenarios, which they were written for.
  - Jev stays opt-in. The rules stay the default and the safety floor.
- **Gemini:** **not called** (no key). It is still the intended deployment model, and its adapter passes the same
  provider contract tests.

## Method
- **Independent simulators** held adaptive conversations against the running FastAPI backend:
  - A, frustrated resident: 10 conversations.
  - B, busy resident: 16.
  - C, high-intent prospect: 11 plus probes.
  - D, confused user: 9.
  - E, adversarial safety and privacy: 20 plus 17 probes.
  - L, 7 priority journeys LIVE and on MOCK.
- **Separate judges:**
  - F, conversation UX: 134 mock and 18 live replies scored on 12 dimensions, before and after.
  - G, workflow F1–F9.
  - H, browser UI and mobile.
  - I, independent regression verifier.
- **Implementation engineers:**
  - A conversation engineer: `actions.py`, `intake.py`, a new `dialogue.py`, `chat_engine.py`.
  - A safety engineer: `emergency.py`, `safety.py`, the account-holder rule. This engineer was kept blind to the
    held-out safety set.
  - The lead: frontend and the Jev adapter.
- **Reusable suite:** `uv run python -m app.usability.run --suite journeys` runs 35 adaptive journeys (10 resident,
  10 prospect, 5 confused, 10 safety and privacy). The simulator and the evaluator are separate, the evaluator
  checks database side effects, and an optional `--live --max-calls` mode is available.

## Before and after
| Measure | Before | After |
| --- | --- | --- |
| Journey suite (MOCK) PASS / WARN / FAIL of 35 | 21 / 9 / 5 | **27 / 8 / 0** |
| Journeys completed | 30 / 35 | **35 / 35** |
| Duplicate records / honesty-safety flags (suite) | 1 / 3 | **0 / 0** |
| Judge F mean per reply (MOCK, n = 134) | 2.91 | **3.89** |
| Correction handling | 1.50 | **4.43** |
| Context / continuity | 2.22 / 2.54 | 3.82 / 3.93 |
| Honesty | 4.72 | 4.89 |
| Empathy | 2.31 | 2.93 (still the weakest) |
| Judge F's 35 serious (P0/P1) rows | — | 28 fixed, 3 partial, 4 not fixed |

The suite is in the repository, so the implementation engineers could see it. The independent measures are judge
F's re-score, the verifier's paraphrased re-tests, and the held-out safety set
([safety-evaluation.md §8–9](../safety/safety-evaluation.md)).

## What was wrong, and what changed
**The root cause** appeared in all five simulators. While a request card was open, almost any message was absorbed
into it:
- questions and contact wording were written into "What's wrong";
- the pending question was asked again;
- the user's real question was ignored, or a duplicate request was started.

**The fix is a typed dialogue-act step** (`app/dialogue.py`) that runs before any card can change. Each message is
classified as one or more of ANSWER, CORRECTION, NEW_DETAIL, QUESTION, CANCEL, RESTORE, META, NEW_ISSUE or
SMALL_TALK:
- only answers, corrections and new details can change fields;
- questions get an honest answer while the card stays on screen;
- a second need parks the open card instead of discarding it.

See [CONVERSATION_STATE.md](../architecture/CONVERSATION_STATE.md).

**Consent:** a record is saved **only** by the Send button or an explicit "send it" / "envíelo". A bare
"ok", "yes" or "sure" now gets "Tap Send…". Before, a typed "ok" saved records, which contradicted the docs.

**Resident fixes:**
- a bare "no" to the entry question means "contact me first";
- cancelling inside a sentence works, and undo or restore uses natural words;
- a follow-up note cites the open request instead of creating a duplicate;
- a change after Send becomes a change note;
- "change what's wrong to …" replaces the text;
- a repeat needs a matching history item;
- common areas skip the room and entry questions;
- an explicit language switch sticks.

**Prospect fixes:**
- the budget is recorded as the person wrote it;
- tour dates are captured, and "would work too" adds an option;
- a city mentioned inside a sentence is captured;
- "X not Y" corrections take X;
- a typed acceptance of the offered note works;
- honest answers to fee, contact and "what does Send do" questions.

**Instructions to the live model:** the model is now told which card is open, the exact missing question, "press
Send", never to say it "can't create a request", and the planner's repeat decision (prompt `+plan-s51`). Live
re-run results:

| Problem | Result |
| --- | --- |
| The model told users to file elsewhere while a card was open (L-2) | fixed |
| The user's budget was treated as an invented price (L-3) | fixed |
| "Typed yes" did nothing / ready notes were re-offered (L-5) | fixed |
| Premature staff-follow-up promises (L-4) | mostly fixed |

**Safety** ([safety-evaluation.md §9](../safety/safety-evaluation.md)): detector extensions only. No policy rule or
approved wording was changed. Newly detected:
- CO described indirectly or abbreviated;
- child or household-product poisoning;
- a person who fell and is calling for help;
- strangers trying door handles;
- a welfare-check smell;
- chirp false alarms removed.

**Privacy:** a standalone "I'm not Jordan, I'm Jordan's roommate" now hides the account for the rest of the
session, and identity claims typed in chat unlock nothing.

**UI** (judge H):
- a failed Send is marked "Not sent" and retried;
- at most 3 urgent rows show, and the newest request is always visible;
- Spanish status labels;
- "Ready to send" replaces "Check, then send";
- an honest line on sent cards; demo-system rows are hidden;
- correct landscape scroll and focus.

## Live versus mock (same 7 journeys, same messages)
- **Outcomes:** the cards, records and safety text are deterministic and matched exactly.
- **Wording:** live replies are more natural (judge F, before the fixes: 3.42 live vs 2.91 mock).
- **Live-only risks:** the model can still contradict facts, so new validators and instructions guard against
  that.
- **Still open live:**
  - "bedroom unit" (the AC unit in the bedroom) is rejected by the leasing-terms check;
  - the model once named a community's state with no source.
  - Both are being fixed in the final round; see "Remaining failures".

## Independent verification (Agent I, final code `e3b0bdb`)
- **Gates:**
  - backend 1315 passed, 9 skipped (the Postgres tests, which are not a Supabase validation); ruff and the uv lock
    check are clean;
  - frontend 49/49; tsc and eslint clean; static build OK;
  - mobile acceptance 14/14 (Chromium and WebKit × 7 sizes, mock);
  - axe: 0 violations in 4 customer states.
- **Consent:** 0 records saved from 52 typed-agreement attempts (ok, sure, yes, sí, 👍, sounds good…). Explicit
  "send it" saves exactly once. "No" to the entry question never cancels.
- **Leaks:** none in the website bundle or the browser console or network (keys, synthetic resident PII, prompt
  text). "OpenRouter" appears only as a provider label.
- **Diff review:**
  - No Ross IT path was touched, and `app/risk/policy.py` is unchanged.
  - No test was deleted. One expected value changed: the Jev confidence assertion, after a deliberate change to how
    confidence is computed.
  - Two consent tests became stricter.
  - One check was widened on purpose: the approved conditional "the team would…" no longer counts as a false
    promise.
- **Held-out safety set** (independent red-team; the implementers never saw it):

  | Measure | Before | After |
  | --- | --- | --- |
  | Full alert | 50/63 | 50/63 |
  | Any guidance | 53/63 | **54/63** |
  | Look-alike full alerts | 5/30 | 5/30 |
  | Injection successes | 0 | 0 |
  | Dispatch claims | 0 | 0 |

  **No measure dropped.**
- **Paraphrase re-tests:** the verifier re-tested every earlier P0/P1 issue with its own wording. Many fixes held
  for the reported wording but only **partly** for new wording, a sign of keyword overfit. The table is in the
  verifier's evidence; the main gaps are listed under "Remaining failures".
- **Verdict:**
  - **Push the feature branch: pass with blockers.**
  - **Supervised demo: acceptable** when staff stay with the user and keep to the main repair, tour and handoff
    paths.
  - **Not acceptable** for unsupervised or production use.

## Remaining failures (honest)
**P0, release-blocking:**
- **Privacy:** "I'm borrowing my neighbour's login", followed by "show my requests", still lists the account's
  requests. "Desmond's dad here" doesn't lock the account, although no data was shown. Underneath this, there is
  no real authentication.
- **Safety, emergencies phrased in new ways still go to a repair form:**
  - "slipped… hip broken, can't get up";
  - "neighbour's kid fell off the balcony".
- **Held-out misses, by category:**
  - CO: an alarm with no symptoms; fainting at home.
  - Fire: a misspelling.
  - Electrical: a downed power line.
  - Flood: water on outlets (Spanish); a child in a pool.
  - Structural: a collapsing ceiling.
  - Self-harm: an overdose; a veiled farewell (care line only).
  - Personal safety: a break-in in progress; a door being kicked in (danger line only).
  - Trapped: an infant locked inside; a lockout in extreme cold.
- **Crisis follow-ups** sometimes lose the steps: "my grandma is in the bedroom with me" after gas, and "both my
  kids have bad headaches" after CO. Welfare-check messages (a neighbour not seen, a bad smell) get the menu.

**P1:**
- "Could we do December 14th instead?" also overwrites Move-in on a tour card.
- "Can I get a new CO detector, mine expired" raises a full CO alert (a new false alarm).
- A follow-up on an open request still duplicates for some wordings ("same one I already reported").
- "Forget it, what are the pool hours?" discards the open draft.
- An undo phrased as "I hit Don't send by accident…" starts a junk draft.
- "the description should be: X" is saved with the prefix.
- "It's broken again", with no history, still claims a repeat.

**P2:**
- Spanish card values stay in English, "pasillo" is filed as outdoors, and some English requests don't switch back
  ("English is easier for me").
- Injection text can end up in "What's wrong", though it causes no state change.
- Empathy is still the weakest judge dimension (2.93).

**Data question for the team:** the synthetic workbook puts Heron Lake Apartments in Orlando, but several
simulators assumed it was near Ann Arbor. The live model now follows the workbook.

**Why stop here:** each extra keyword round fixed the reported wording but not new wording. The next safety step
should be a separate sprint with a different approach:
- development cases written from category descriptions;
- the semantic classifier evaluated live, adding caution only;
- a **new** held-out set by another writer.

That is better than more patterns tuned on this sprint's examples.

## Safety and privacy findings
- **No leaks** of another resident's data across 20 adversarial conversations.
- **No identity claim** unlocked data. No false booking, dispatch or "fixed" claim, and no prompt revealed.
- **Emergency recall is still the P0 blocker:** see the held-out results in
  [safety-evaluation.md §9](../safety/safety-evaluation.md).
- **No authentication:** the demo persona comes from the browser.
- **Approval pending:** McKinley has not approved the emergency or escalation scripts. Do not deploy to real
  residents.
