# Sprint 9: warm, concise replies and honest demo status

Branch `feat/warm-conversational-ux` (stacked on PR #6, `feat/render-dual-deploy-supabase`). Prototype on synthetic
data; nothing reaches McKinley staff. All new customer wording is a TEAM DRAFT marked NEEDS McKINLEY REVIEW; Spanish
is a draft translation.

## 1. Where the robotic, repetitive text came from
Most customer replies are **not** written by the model. A turn's reply is a backend draft (`backend/app/templates.py`,
composed by `actions.plan_turn`); the live model only rewrites it, and often it is skipped.

| Layer | Problem found |
| --- | --- |
| Templates (`T`, `CONFIRM`) | Each confirmation and follow-up restated every limitation ("in this prototype nobody is notified automatically", "no McKinley staff will see it", "the office's real contact details aren't connected") |
| Planner read-back (`field_first` / `field_updated`) | "Community or city: Ann Arbor. Preferred days: Next week." before each question |
| `after_send_text` | "What happens next?" and "Will someone call me?" got the same 95-word paragraph with the field list and reference |
| Confirm suffix (`NO_CONTACT_SUFFIX`) | Appended to every guest confirmation |
| Live-model instruction (`plan_prompt_section`) | "Keep every fact and every limitation" + 2-4 sentences, so long drafts stayed long |
| Record status labels | "Requested; leasing team to confirm a time", "Submitted, waiting for staff review", "In the office queue": untrue in a demo where nobody receives anything |
| Card (`ActionCard`) | Reference, "What was sent" and a long demo sentence competed with the status; the backend note and a frontend note said the same thing |

## 2. What changed
- **One authoritative status.** `models.STATUS_LABEL` ("Saved in demo", "Urgent · saved in demo") is applied on every
  record read and write (`db.Store`), so the chat, card, request history and staff console agree, and rows saved
  before Sprint 9 are relabelled. The model never writes a status.
- **Layered disclosure.** Persistent "Demo · Sample data · No requests sent to staff" (strip; on phones also
  "Demo · sample data" in the footer once the strip scrolls away), full text in "About this demo"; one line on the
  card at the point of Send (`CARD_NOTE.open`, e.g. "Sending saves a demo request. It won't notify McKinley staff,
  and no time is booked.") and after it (`CARD_NOTE.saved`); a short confirmation. Follow-ups answer the actual
  question from the real record. Safety, consent and authorization text is unchanged.
- **Voice.** About 45 templates rewritten (tour, maintenance, notes, follow-ups, FAQ referrals, corrections);
  corrections are one sentence; side questions don't repeat the same question twice in a row; one leasing referral
  per reply; situational empathy (frustration and repeat issues acknowledged once, none for status questions).
- **Live model.** System prompt v0.2 "Answer style" (1–3 short sentences for routine replies, answer first, never
  shorten emergency steps or limits, no repeated apologies, no read-backs); plan section `plan-s9`.
- **Validator.** `safety._demo_status_claim`: a model reply may never say a request was sent to, received by,
  waiting with or about to be confirmed by staff (EN + ES), negated in the same sentence or framed "in the real
  service" excepted. The model reply is replaced by the backend draft when it fails.
- **Card.** Type → status → one-line summary ("Ann Arbor · Next week · Morning") → action; reference on the
  secondary demo line; "You told us" no longer on every row; 320 px gets the full width.

## 3. Before / after (the product owner's example, MOCK = backend wording)
| Turn | Before | After |
| --- | --- | --- |
| "Request a tour" | I'd be glad to set up a tour request for you. Which city or McKinley community would you like to see? | I'd be happy to help you plan a visit! Which McKinley community, or which city, are you interested in? |
| "Ann Arbor, next week" | Community or city: Ann Arbor. Preferred days: Next week. What time of day is easiest: morning, afternoon or evening? | Sounds good! What time of day works best: morning, afternoon or evening? |
| "Morning" | Time of day: Morning. Here's your tour request. The leasing team picks the exact time, so this isn't a booking yet. Send it when it looks right. | Perfect, I've put together your tour request for next week in the morning. Take a look below, then send it when it looks right. |
| Send | Tour request DEMO-TOUR-1001 is saved in this demo. It isn't a booking yet: in the real service … no McKinley staff will see it. This prototype doesn't collect a way to reach you, and the office's real contact details aren't connected here yet. (59 words) | Your tour request for next week in the morning is saved in this demo! The time isn't confirmed, and it hasn't been sent to the leasing team. (26 words) |
| Card status | Requested; leasing team to confirm a time | Saved in demo |
| "What happens next?" | Tour request DEMO-TOUR-1001 is saved for the leasing team, with: Community or city: Ann Arbor; … (86 words) | Your tour request (DEMO-TOUR-1001) is saved in this demo, but it hasn't been sent to the leasing team, so no time is confirmed. In the real service, they'd reach out to set up a time with you. |
| "Will someone call me?" | (the same 86-word paragraph again) | No, nobody will call or email from this demo, because your tour request (DEMO-TOUR-1001) wasn't sent to the leasing team, and no time is booked. In the real service, they'd reach out to set up a time. |

## 4. Measurements (matched scenarios: 4 prospect, 3 resident journeys)
Words per assistant message and sentences that state the demo limit, per journey. MOCK and LIVE are separate.

| Run | Avg words | Demo-limit sentences / journey |
| --- | --- | --- |
| MOCK before (`5707c1d`) | 41.9 | 4.6 |
| MOCK after (final, `c04a562`) | 30.0 | 2.0 (each one answers the step or the question) |
| LIVE before (OpenRouter `nvidia/nemotron-3.5-super-vl:free`, 5 journeys) | 48.8 | 2.8 |
| LIVE after (same model; **first sprint commit `6b44303`**) | 31.9 | 1.0 |

A separate session ran the 35-journey suite live on `f6a32a7` with **Gemini** (`gemini-3.6-flash`, reasoning effort
low, through its gateway branch `feat/gemini-gateway-default`): 35/35 completed, 31 PASS, 4 WARN, 0 FAIL; in 11 of 63
model-written replies Gemini framed Send as delivery ("press Send to submit it to our maintenance team", "so our team
can follow up"). The validator now rejects those phrasings (`90d1aa7`), so such replies fall back to the backend
wording. Re-run live on `90d1aa7` (same session, Gemini): 35/35 completed, 31 PASS, 4 WARN, 0 FAIL, 0 duplicate
records, reply p90 4.3 s; staff-delivery claims 1/56 (was 11/63), but `template_after_validation` 14 per run (was 7),
about 20% of Gemini replies replaced. `4047176` adds the rule to the live-model instructions (plan-s9b) to cut that
at the source. Re-run on `4047176`: 35/35, 31 PASS, 4 WARN, 0 FAIL; `template_after_validation` 4 per run; claim
attempts 8/71 (about half of the previous run). The 3 that slipped through were offers or questions presuming staff
contact ("so the leasing staff can reach out", "a phone number … for a call", "for a manager to review it with
you"); the validator catches them from the next commit ("Would you like…" no longer counts as a real-service
hypothetical; "Would you like me to pass it along…" stays an allowed offer).

The final-commit OpenRouter run was **rate-limited** (`MODEL_RATE_LIMITED` on every call; replies were the labelled
`template_after_model_error` fallback), so the final wording has not been measured on the live model.

## 5. Independent reviews (subagents that did not write the change)
| Agent | Result |
| --- | --- |
| A Conversation designer | 18 rewrites; found replies that still implied staff action ("already sent", "pass it on", "the office will confirm"): fixed |
| B Workflow engineer | Status path verified end to end; found the model could still claim a status (fixed with the validator), an over-broad "will someone call me?" detector (narrowed), list-of-days phrases (fixed) |
| C Frontend UX | axe 0 violations (WCAG 2.2 AA, both engines, 4 sizes), contrast ≥ 5.2:1; demo line lost after scrolling on phones, saved card hid its details, cramped 320 px: fixed |
| D Resident simulator (18 journeys) | No false booking/visit/callback/price claims; safety text never shortened; issues below |
| E Prospect simulator (17 journeys) | No invented prices or bookings; contradiction "is waiting for the leasing team" after Send: fixed |
| F UX judge | MOCK before → after: warmth 4→7, naturalness 3→6, clarity 5→8, brevity 3→8, empathy 4→6, task 6→6, honesty 6→8, repetition 2→6, visual 5→8. LIVE (earlier commit): clarity 6→8, brevity 4→7, honesty 7→9, empathy 7→5 (model parroted card instructions: instruction changed after review) |
| G Safety & truthfulness | PASS WITH ISSUES: emergency/risk code byte-identical, safety templates unchanged, consent and authorization unchanged; validator negation could be fooled by "No problem! I've sent it…": fixed and pinned by tests |
| H Regression verifier (43 new scenarios, old vs new) | 3 regressions (time not read back, a time correction named the wrong field, an offer to guests with no working path) and one lint error: all fixed |

## 6. Open issues (not fixed in this sprint)
- **P0 (pre-existing, safety):** after "water is pouring from my ceiling", the follow-up "it's getting near the light
  fixture" opens a routine repair card without re-showing the safety guidance. Same on the pre-sprint code. Needs a
  safety-reviewed change in `app/risk` (not a wording change).
- **Safety follow-ups (pre-existing, needs safety review):** after an active alert, a follow-up question is not
  answered directly. a question about opening a window and staying inside (carbon-monoxide signs) re-shows the whole block
  with 911 twice instead of a plain "No, please go outside"; asking what to do now after water at a
  light fixture gets only "your urgent note is saved … call the emergency line" without the steps again. Fixing this
  changes which approved safety text is shown, so it belongs in a safety PR with an independent review.
- Understanding gaps seen by the simulators, all also on the pre-sprint code: ordinal dates ("the 14th") and unknown
  community names ("Arbor Landing") are not captured; "can you cancel that?", "so it's confirmed?", "who got it?",
  small talk and several Spanish follow-ups get the generic fallback; "yeah same as last time" is read as entry
  permission; emotion mid-flow ("I don't want another ticket that goes nowhere") gets only the next question.
- The fixed emergency text says "an urgent note is saved in the staff queue"; it is true of the prototype but reads
  as if staff will see it. Approved safety wording: change only with McKinley review.
- All Sprint 9 wording needs McKinley review; Spanish needs a fluent reviewer.

## 7. Tests
Backend 4,667 passed, 11 skipped; ruff clean. Frontend 74 tests, lint and typecheck clean, static build OK.
`npm run smoke` passed. `frontend/e2e/mobile-acceptance.mjs` 14/14 (Chromium and WebKit, 7 sizes, including the four
safety states) on a local MOCK build. New tests: `backend/tests/test_sprint9_voice.py` (56), honesty helper
`backend/tests/wording.py`.
