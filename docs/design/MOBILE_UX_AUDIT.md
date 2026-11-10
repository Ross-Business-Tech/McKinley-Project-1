# Mobile UX audit: customer chat and staff console (Sprint 4)

The requirement is "a link anyone can open on their phone and ask a question". This file records how the phone
experience was tested, what was wrong, what changed and what is still open. All runs used a **local backend with
the deterministic mock responder** (fixed rules, not an AI model) and made-up data. Public hosting has **not** been
tested ([../INTERACTIVE_DEMO_READINESS.md](../INTERACTIVE_DEMO_READINESS.md)).

Status labels: **VERIFIED** (reproduced in a real browser engine), **IMPLEMENTED BUT NOT VERIFIED**, **MOCK ONLY**,
**BLOCKED**, **NOT IMPLEMENTED**.

## How it was tested
- **Engines:** Playwright **Chromium** (Android-like: `isMobile` and touch) and **WebKit** (Safari's engine, touch),
  both headless. Neither is a real phone.
- **Script:** `frontend/e2e/mobile-acceptance.mjs`, which is in the repo and works against a built folder or a
  deployed URL. For each size it opens the page, checks for sideways scrolling, taps the message box, enters
  text with Playwright's `fill()` (not key-by-key typing), taps Send, waits for the reply, sends a second message
  and refreshes. Agent F separately typed key by key (`keyboard.type`) at 5 sizes, and that also passed.
- **Keyboard stand-in:** the viewport height is cut to 55% after the box is tapped. This applies to portrait phone
  and tablet sizes only. The script then checks that the composer and the 911 link are inside the visible area,
  and how much of the screen the composer takes. The newest-reply check runs **after** full height is restored: the
  top of the reply must not be below the top of the composer. A
  real on-screen keyboard **cannot be opened headless**.
- **Independent reviewers:** none of them wrote the code. Each was given only the running app and its screenshots.
  - B (mobile UX)
  - C (strict UI/UX judge, before and after)
  - D (resident and prospect simulator, 9 scenarios plus 5 variants)
  - E (accessibility)
  - F (final verifier)

## Viewport matrix (final build, 2026-11-10)

| Size | Chromium before → after | WebKit before → after | Composer share while "typing" | Notes |
| --- | --- | --- | --- | --- |
| 320×568 | FAIL → **PASS** | FAIL → **PASS** | 38% (baseline: the composer covered the whole screen) | chips hide while typing on short screens |
| 375×667 | FAIL → **PASS** | FAIL → **PASS** | 32% | |
| 390×844 | FAIL → **PASS** | FAIL → **PASS** | 25% | |
| 430×932 | PASS → **PASS** | PASS → **PASS** | 28–40% (chips shown above 480px tall) | |
| 768×1024 | PASS → **PASS** | PASS → **PASS** | 25–36% | |
| 1440×900 | PASS → **PASS** | PASS → **PASS** | — | |
| 844×390 landscape | PASS → **PASS** | PASS → **PASS** | not measured by the script (about 30% from the screenshots, judge C) | the composer used to stop being sticky in landscape |

Checked in every run, all **VERIFIED (MOCK ONLY)**:
- no sideways scroll;
- the message box can be focused and filled;
- the send button is at least 44px. Other controls under 44px are only listed, not failed;
- a reply arrives, and a second message works;
- the top of the newest reply is not below the composer (checked at full height);
- refresh restores the conversation (3 assistant messages);
- tap-to-call 911 is visible.

Screenshots: [screenshots/](screenshots/). Each `before-*` has a matching `after-*`: phone open, phone with the
keyboard stand-in, landscape, desktop, and the staff console on phone and desktop.

## The 16 questions from the brief

| # | Question | Result |
| --- | --- | --- |
| 1 | Loads without sideways overflow? | VERIFIED: all 14 runs. The staff Usability tab overflowed at 320–390px; fixed (E-4) |
| 2 | Chat input visible and usable? | VERIFIED |
| 3 | Can the user focus the input? | VERIFIED (tap) |
| 4 | Does the keyboard hide the composer? | VERIFIED with the 55%-height stand-in. iOS uses `visualViewport` lifting and Android uses `interactive-widget=resizes-content`: **IMPLEMENTED BUT NOT VERIFIED on a real phone** |
| 5 | Type and send? | VERIFIED |
| 6 | Message appears correctly? | VERIFIED |
| 7 | Assistant replies? | VERIFIED, **MOCK ONLY** (no Gemini call) |
| 8 | Another message? | VERIFIED |
| 9 | Long replies scroll correctly? | VERIFIED: a reply taller than the free space is shown from its first line (B-3) |
| 10 | Action cards reviewed and confirmed? | VERIFIED by Agent D: Send / Don't send, then a green "Submitted, waiting for staff review" and a reference |
| 11 | Does the user know if it was really done? | VERIFIED: the press shows as the user's own turn ("Send repair request"), then the saved message. Green is used only after a real save. Drafts read "Check, then send" |
| 12 | Human help? | VERIFIED by Agents D, F and the consolidation reviewer (not by the script): "Talk to a person" is under the composer at the sizes they tried. **OPEN:** a frustrated user is not offered a person automatically (D-12) |
| 13 | Loading and API errors understandable? | VERIFIED: "Waking the assistant up…" after 4s; a failed send shows "Not sent" with "Send again", and the text is kept |
| 14 | Touch and keyboard navigation? | VERIFIED: send button 44px by the script; other targets by Agent E's audit; keyboard paths by Agent E. WebKit's default Tab setting skips links (Safari behaviour) |
| 15 | Works after refresh? | VERIFIED: same-tab restore with sessionStorage |
| 16 | Focus and scroll after new messages? | VERIFIED: focus stays in the box after sending and moves to the outcome after Send. The first screen no longer auto-scrolls (B-5) |

## Findings and fixes

| ID | Sev. | Finding | Fix | Status |
| --- | --- | --- | --- | --- |
| C-1 / B-1 | P0 | Composer off-screen when the keyboard opens (320–390). A `max-height:480px` rule made it static | Sticky at every height; keyboard lift via `visualViewport`; `interactive-widget=resizes-content` | VERIFIED (stand-in) |
| C-2 | P0 | Composer overlapped the start options at 320×568 | Compact composer; solid background | VERIFIED |
| C-3 | P1 | Demo sign-in plus hint took about 137px | One 56px demo row; the hint moved to the select's description | PARTIAL: band plus row is 105px, not the judge's 64px. The picker stays visible so testers can switch personas |
| C-4 / C-R3 | P1 | Footer said "fixed rules" while the greeting said "I'm an AI" | Greeting says "automated assistant, not a person" (I-01 team draft, for McKinley to approve). Reply source moved to "About this demo" | VERIFIED |
| C-5 | P1 | Brand was evergreen green | McKinley blue `#4e6f92`, Barlow ([BRAND_SYSTEM.md](BRAND_SYSTEM.md)) | VERIFIED |
| C-6 | P1 | Send looked the same whether ready or empty | Blue when ready; grey with an outline when empty | VERIFIED |
| C-7 / B-4 | P1 | Landscape composer scrolled away | Sticky; about 30% of 390px | VERIFIED |
| C-8 | P1 | Progress chip looked like a spinner | Static checklist icon plus plain text | VERIFIED |
| C-R1 | P1 | Translucent composer let chat text show through | Solid background | VERIFIED |
| C-R2 | P1 | Composer took 56% at 320 while typing | Chips hide while typing on short screens: 38% | VERIFIED |
| C-R4 / E-2 | P1 | 911 line hidden (and a hidden focusable link) on short screens | Tap-to-call **911** in the action row at every height | VERIFIED |
| C-R6 | P2 | End of a reply hidden after the keyboard closes | Stays at the end if you were there | VERIFIED |
| B-3 | P1 | Auto-scroll hid the start of long replies and cards | Shown from the first line when taller than the free space | VERIFIED |
| B-5 | P1 | Small phones opened already scrolled | No auto-scroll on the first screen | VERIFIED |
| B-8 | P2 | Safe-area padding did nothing | `viewport-fit=cover`, plus insets on the band, rows and composer | IMPLEMENTED BUT NOT VERIFIED (no notched device) |
| C-12 | P2 | No start-over control | "Start over" (asks first, then puts focus in the box) | VERIFIED |
| S-1 | P1 | Staff tabs on 3 wrapped rows | One row that scrolls sideways, with an edge fade | VERIFIED |
| S-2 / S-4 | P1/P2 | Staff status was one running line; staff looked like the customer page | Labelled status grid; deep-blue band with a "Staff" tag | VERIFIED |
| E-1 | P1 | Focus lost after Start over | Focus goes to the message box | VERIFIED (unit test) |
| E-3 | P1 | Send / Don't send outcome not announced | One polite announcement that includes the reference | VERIFIED (unit test); real screen reader NOT VERIFIED |
| E-4 | P2 | Staff Usability select overflowed at 320 | Width limited | VERIFIED |
| E-5…E-8 | P2 | Demo row outside landmarks; label `lang`; Escape on the toggle; label-in-name | Fixed | VERIFIED |
| D-1 | P1 | Prospects offered "Report a repair" after a tour | Suggestions after Send depend on persona and kind | VERIFIED (unit test) |
| D-2 | P2 | Saved message ran into the previous bubble | The press shows as the user's own turn | VERIFIED |
| D-7 | **P0** | Name and email typed into a tour draft overwrote "Community or city" | Backend: contact details are never read as a place | VERIFIED (tests and API replay) |
| C-11 | P2 | Speaker label on every turn | Kept on purpose: in a chat that alternates, each reply gets its avatar and name, which is the usual pattern | NOT CHANGED |
| C-10 | P2 | Empty paper on a tablet before the first message | Not changed (a chat's empty state); options are limited to 448px | NOT CHANGED |

## Open: conversation logic (backend planner, not this UI sprint)
Agent D found these while using the mock responder. They are real and **not fixed**. Planner changes need their own
ordered-check tests (`docs/development/CLAUDE_PROJECT_GUIDE.md`).

**P1:**
- **D-12:** a frustrated user ("what do I do now??", "this isn't helping") loops and is never offered a person
  automatically. "Talk to a person" is visible, but the bot doesn't suggest it.
- **D-11:** "actually yes I want a person", said after declining a note, is missed.
- **D-8:** tour timing is confused with move-in ("tour this week" became Move-in = this week), and some questions
  get the same prompt repeated.
- **D-9:** a question asked after a tour is sent ("will someone email me?") gets the generic greeting.
- **D-10:** "Did it go through?" during an incomplete draft says "press Send", but no Send button exists.
- **D-13:** a door-lock repair is offered only room choices (no entry door) and gets no security priority.
- **D-14:** "move out early" is filed as a renewal question.
- **D-15:** "the one for the sink leak" starts a new repair instead of matching the existing request.

**P2:**
- D-16 (later symptoms dropped);
- D-17 (a bare "ok" taken as entry permission);
- D-18 (two templates joined; no heat-safety tip);
- D-19 (Spanish repeat issues not detected);
- D-20 (a contact preference typed in chat is ignored);
- D-21 (no floor-plan content; a tour pitch on every turn);
- D-22 (awkward wording such as "Updated: preferred days" on the first value);
- D-6 (Spanish cards show English values from the backend: status labels, contact preference).

## Not verified (needs people or devices)
- A real iPhone (Safari) and a real Android phone (Chrome): keyboard, safe areas, tap-to-call.
- A real screen reader (VoiceOver, TalkBack, NVDA). Agent E inferred announcements from the accessibility tree.
- Live Gemini replies, which will be longer than the mock's. The scroll-to-start logic should handle them, but this
  is untested.
- The public URL (nothing is deployed).
