# Implementation changelog

## Sprint 6: robust workflow orchestration, safety and authorization hardening (2026-11-10)
Branch `feat/robust-workflow-safety-auth`. Report: [evaluation/SPRINT6_RESULTS.md](evaluation/SPRINT6_RESULTS.md).

- **Conversation:**
  - `app/understanding.py` reads each message once into a typed `Understanding`. Rules are the default; the
    optional model pass is validated and may only add.
  - `app/workflow_state.py` is an explicit state machine of 8 states with a transition table.
  - Field-targeted corrections, two-issue splits, partial cancel, hold, offer acceptance, history questions and
    changes after Send all go through these two layers. Saving stays idempotent.
- **Authorization:**
  - `app/auth.py` resolves the principal on the server; `ScopedStore` is deny-by-default.
  - `session_bindings` (migration 0003, RLS on) binds a session to its persona.
  - Hosted mode is public-information only, and a non-holder statement cuts account data at the store.
- **Safety:**
  - Concept co-occurrence detection, and incident-specific notices (no elevator text for an injury).
  - A persistent incident state machine (follow-ups R10, calm line R10q), and clause splitting for live reports
    inside questions.
  - A stricter retraction rule in the final round.
- **Tests:**
  - backend 1315 → 2350 passed (9 skipped); frontend 49 → 54; phone test 14/14; axe 0 violations;
  - journeys 27/8/0 → 29/6/0;
  - independent holdout (109 emergencies) full alert 70% → 76%, any guidance 79% → 85%, security 40/41 → 41/41.
- **Live OpenRouter: BLOCKED** by the free tier's daily limit (HTTP 429). 11 development calls succeeded or timed
  out before the limit; no live journey ran.
- **Verdict:** supervised demo only. 16 immediate-danger holdout misses are release-blocking, and there is no real
  sign-in.

## Sprint 5.1: live OpenRouter, customer-journey simulation, workflow fixes (2026-11-10)
Branch `feat/live-conversation-workflows`. Report: [evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md](evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md).

- **Live calls:**
  - 46 real OpenRouter calls on one fixed model, `nvidia/nemotron-3.5-super-vl:free`, with no rate limits.
  - A central call budget and a metadata-only ledger.
  - `OPENROUTER_REASONING_EFFORT=none` made the slowest reply 48 s → 3.4 s.
  - 16 TypeSafe/Jev calls; the adapter now matches the official contract.
- **Conversation:** a typed dialogue-act step (`app/dialogue.py`) runs before any card changes. Only Send or an
  explicit "send it" saves. Corrections, side questions, undo, changes after Send and language switching are all
  reworked.
- **Safety:** CO, poisoning, fall, door-handle and welfare detection; a session-long non-holder disclaimer;
  validator fixes for the live model.
- **UI:** failed Send, the status list, Spanish labels, clearer card wording, landscape scroll and focus.
- **Tests:**
  - a 35-journey adaptive suite (`--suite journeys`): 21/9/5 → 27/8/0 (PASS/WARN/FAIL);
  - judge F mean per reply 2.91 → 3.89;
  - backend 1315 passed, 9 skipped; frontend 49; phone test 14/14;
  - holdout full alert 50/63 → 50/63, any guidance 53/63 → 54/63.
- **Verdict:** a supervised demo only. Release-blocking safety and privacy gaps remain.

## Sprint 5: conversation workflows, provider contracts, Gemini readiness (2026-11-10)
Branch `feat/live-conversation-workflows`. Full report: [evaluation/SPRINT5_LIVE_CONVERSATION.md](evaluation/SPRINT5_LIVE_CONVERSATION.md).

- **No live model call.** There is no OpenRouter or Gemini key here, so the smoke and A/B/C runners are built,
  tested offline and BLOCKED.
- **Provider contract:** 102 tests show identical application behaviour on OpenRouter and Gemini. Error mapping
  now matches across adapters. `app/llm/contracts.py` gives a named facade.
- **Live scripts:** `app.live_eval.smoke` (8 calls at most) and `docs/development/GEMINI_ACCEPTANCE_CHECKLIST.md`.
- **Conversation:** two rounds of deterministic planner fixes from the resident and prospect simulators and the UX
  judge, re-verified by an independent replay. See [architecture/CONVERSATION_STATE.md](architecture/CONVERSATION_STATE.md).
- **UI:** "About this demo" names the reply source (OpenRouter, Gemini or Mock, plus the served model).
- **Safety:** an independent red-team holdout gave full alert 50/63 and any guidance 53/63. 10 misses are
  release-blocking. No safety rule changed, and the crisis follow-up wording needs McKinley review.
- **Tests:**
  - backend 1002 passed, 9 skipped; frontend 46;
  - phone test 14/14 (mock);
  - red-team holdout unchanged before and after the conversation changes.

## Sprint 4: McKinley brand redesign and mobile-first chat (2026-11-10)
Branch `feat/mckinley-mobile-brand-redesign`. It is built on `feat/gemini-supabase-deployment`, which carries the
Gemini, Supabase, Render and Vercel preparation, and `origin/development` had nothing newer. Prototype, made-up data.

### What changed
**Design system** ([design/BRAND_SYSTEM.md](design/BRAND_SYSTEM.md))
- Evergreen `#1d5c45` was replaced by McKinley's own blue `#4e6f92`, verified from mckinley.com's stylesheet and
  app icon.
- Links use `#3f5b79`, because McKinley's link blue `#4681c7` fails AA.
- Status colours are separate from the brand: green means saved, amber means a person should help, red means
  emergency, and each also has an icon and words.
- Barlow (McKinley's font) for headings and buttons; Atkinson Hyperlegible stays for reading.

**Customer chat** (`frontend/src/components/customer/`)
- Layout:
  - a blue header band;
  - the demo sign-in as one compact row with an "About this demo" panel, which holds the reply source (fixed
    rules or AI) and the staff link;
  - "Start over";
  - a tap-to-call **911** link and "Talk to a person", visible at every height.
- Phones:
  - the composer stays pinned at every height (it used to drop out of view under 480px tall, for example with a
    keyboard open);
  - keyboard lift through `visualViewport` (iOS) and `interactive-widget=resizes-content` (Android);
  - `viewport-fit=cover` with safe-area insets;
  - the first screen no longer auto-scrolls; long replies and cards are shown from their first line;
  - when the keyboard closes, you stay at the end of the conversation;
  - the composer is compact while typing on short screens: 38% of a 320px phone, down from 100%.
- Clarity:
  - Send has distinct ready and empty states;
  - progress shows a static checklist icon, not a spinner;
  - pressing Send or Don't send appears as your own turn;
  - suggestions after Send fit the person (no "Report a repair" for prospects);
  - Spanish dates use Spanish order.
- Honesty: the greeting says "automated assistant, not a person" (I-01 draft) instead of "I'm an AI", which was
  untrue while the mock answers.
- Accessibility:
  - focus goes to the message box after Start over;
  - Send outcomes are announced once, with the reference number;
  - the demo row is a labelled region;
  - Escape closes the About panel;
  - the visible placeholder matches the box's accessible name;
  - side padding at every width.

**Staff console**
- A deep-blue band with a **Staff** tag.
- The backend status became a labelled grid (Replies, Database, Residents from, Environment).
- One tab row that scrolls sideways on phones, with an edge fade (it used to wrap onto 3 rows).
- Saved records turn green.
- The Usability select no longer overflows at 320px.

**Backend** (one fix, from the simulator)
- Contact details typed into an open tour request ("Alex Rivera, alex.rivera@example.com") no longer overwrite
  "Community or city". Tests: `backend/tests/test_contact_not_place.py`.

**Tests and tools**
- `frontend/e2e/mobile-acceptance.mjs`: Chromium and WebKit, 7 sizes, typing, sending, replies, the keyboard
  stand-in, composer share, 911 visibility and refresh restore. It works on a built folder or a deployed URL.
- New unit tests:
  - the 911 link and the "not a person" greeting;
  - the About panel keyboard behaviour;
  - the Send announcement;
  - focus after Start over;
  - the user-side Send turn;
  - after-send suggestions.

**Docs**
- [INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md)
- [design/MOBILE_UX_AUDIT.md](design/MOBILE_UX_AUDIT.md)
- [design/TASTE_SKILL_REVIEW.md](design/TASTE_SKILL_REVIEW.md)
- a new "what the customer page shows" diagram in `diagrams/system-architecture.md`
- the project guide's UI standards
- the I-01 row in `workflows/traceability.md`

### Test results (final, on the branch head)
- **Frontend:** vitest 45/45; `tsc --noEmit` and `eslint` clean.
- **Backend:** pytest 728 passed, 9 skipped (Postgres tests; there is no Postgres here); ruff clean.
- **Builds:** root build passes. The smoke test passed on desktop and phone for `/` and `/staff/`, and the here.now
  replay was re-checked on the head commit.
- **Phone acceptance:** 14/14 PASS (Chromium and WebKit × 7 sizes) against a local backend running the **mock**
  responder. The baseline failed 6/14.
- **axe-core:** 0 violations on the customer first screen, with About open, after messages, on the review card,
  after Send, after an emergency message, and on the staff console (1440, and the Usability tab at 320).
  Verified by Agent F.
- **Independent reviews:**
  - Judge C: visual 4 → 6.5/10, usability 3 → 6/10 after round 2. The round-3 fixes addressed its new issues; it
    did not re-score after round 3.
  - Mobile B, accessibility E, simulator D (9 scenarios) and final verifier F: **approve with blockers** (the
    blocker was committing these docs).
- **Secrets:** none in the branch diff or the built bundles.

### Still open
- **Public phone requirement: NOT met.** Nothing is deployed and Gemini has never been called.
- **No real-device checks yet:** no real iPhone or Android test, and no real screen reader test.
- **Conversation-logic findings** from the simulator (D-8 to D-22, frustration handling D-12, a request for a person
  after declining D-11, no floor-plan content), listed in [design/MOBILE_UX_AUDIT.md](design/MOBILE_UX_AUDIT.md).
- **Start over and switching sign-in** use the browser's `window.confirm`; an in-app confirmation would fit better
  (P2).
- **Header height:** the band plus demo row is 105px on a phone; the judge's target was 64px.
- **Unchanged P0s:** missed emergencies, no real sign-in, unapproved scripts.
