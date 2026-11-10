# Implementation changelog

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
