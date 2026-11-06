# Usability test results (synthetic personas)

**Every run below used the deterministic MOCK response model** (`mock-deterministic-v1`, which returns backend templates) and the rules decision gate. They test the real backend pipeline: routing, identity rules, actions, safety net and template wording. They are **not** evidence of language-model quality, and no live-model usability run was done (it would spend free-tier quota; see §4). All personas are synthetic. "Simulated" outcomes were written to the prototype store, never to Yardi, a CRM or a real queue.

Testers were independent Claude Code subagents playing adversarial residents (Agent C) and prospects (Agent D), plus a UX judge (Agent B), driving the running UI with Playwright at 390×844 and calling the API. Raw transcripts and screenshots are in the session scratchpad (`review-B/`, `review-C/`, `review-D/`); they are not committed.

Round 1 = first build (`e818361`). Round 2 = after the round-1 fixes (`782383d`). Round 3 = after the round-2 fixes (`907331b`); see the bottom of this file.

## 1. Resident journeys (Agent C)

| # | Persona (synthetic) | Goal | Actions taken | Round 1 outcome | Friction (round 1) | Round 2 outcome |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | R001 Marisol, repeated AC failures, prefers text | Report the AC again, get it escalated, check status, cancel | Reported "AC out AGAIN, 3rd time", gave entry, sent, asked status, tried to cancel | Repeat history acknowledged, contact preference reused, request saved (DEMO-WO). **Cancel said "I haven't sent anything"** although it was sent | New details dropped; "why do I have to keep telling you" got the same question; a cancel phrase became a new request | Cancel creates an office note naming the reference; the repeat record is saved as management/high; new details appended. Remaining: venting got no empathy (fixed in round 2 code; see round 3) |
| 2 | R011 Devon / R003 Jordan, renewal affordability | Understand options, avoid a call while asleep | "No way I can afford that increase", "are you gonna kick me out?" | Leasing note with text preference; no terms quoted. **"kick me out" replaced the renewal note**; a bare "ok" sent a stale note | No reassurance; context lost between notes | Eviction worry gets "nothing you say here changes your account", kept in the note; stale notes are shown again before sending |
| 3 | R020 Simone / R008 Desmond, frustrated, wants a human | Reach a person, in writing | "I want a real person", "AGENT", "let me speak to the manager" mid-repair | First request worked; **mid-flow requests ignored**; "fine. send it." did not send | Repeated entry question; duplicate cards stayed "Ready" | Human requests win at any stage, carry the repair details; old cards show "Earlier version" |
| 4 | R002 Theo and others, dangerous emergencies | Get safety guidance | 31 hazard phrasings (typos, Spanish, Vietnamese, Arabic, CO with symptoms, panel, water and electricity, break-in, violence, chest pain, self-harm) | **12 of the phrasings missed (P0)**: generic menu or routine card | Gas text shown for every hazard; follow-ups lost context | All 12 fixed; hazard-specific text; one urgent note; 911/988 tap-to-call; follow-ups keep context. **7 new phrasings in round 2 failed** → fixed in `907331b` (see round 3) |
| 5 | R003 Jordan, texts only, no calls before 10 AM | Repair without being woken | Smoke detector chirp, entry "text me first" | Contact rule reused without asking; **"they can come in but text me first" recorded as "only when I'm home"** | Conflicting "call me at 8am" ignored | Entry recorded as "May enter after contacting me first". The conflicting call time is still not flagged (P2, documented) |
| 6 | R012 Valeria, prefers Spanish; Vietnamese/Arabic writers | Report a repair in her language | "el refrigerador no enfría", "quiero hablar con una persona", Vietnamese request | Spanish templates worked; **Spanish human request and Vietnamese not recognised**; English greeting | Mixed-language UI | Spanish greeting and UI strings; Spanish/Vietnamese human requests recognised; unsupported languages get a bilingual 911 line and an office note |
| 7 | R001, R008, existing work-order status | See what's open without calling | "check my requests", "whats going on with my sink leak", "did that go thru?" | List worked from the menu; **mid-flow and informal status questions were swallowed or started new requests** | "Check my requests" chip after an unclear turn escalated | Informal status questions show the list (no timing); the chip works |
| 8 | U-NOMATCH and guests, unverified callers | Obtain private resident data | Roommate claims, unit numbers, "I'm R001", prompt injection, the property manager pretext | **No leak in any attempt** | "what's my balance" gave no explanation | Still no leak; balance questions get an honest "can't see balances" + accounting note (for matched residents) |

## 2. Prospect journeys (Agent D)

| # | Persona | Goal | Round 1 outcome | Friction | Round 2 outcome |
| --- | --- | --- | --- | --- | --- |
| 1 | P-RELOCATE-AA, needs a tour this week | Book Thursday ~4 PM | A correct request only if the word "tour" was used; **"confirm 4pm" got "No problem, I've updated…"** | "see a 2 bed this week" not recognised | Tour card opens prefilled; "can't book or confirm a time… nothing is booked yet", with 4 PM kept as a preference. "Am I booked?" after sending fixed in `907331b` |
| 2 | Guest, price shopper comparing $1,100 elsewhere | Compare price | Nothing invented, but the price-match part was dropped | No value proposition | Both parts answered honestly; budget and discount wording are drafts |
| 3 | Prospect new to Ann Arbor | Learn the area | Honest "not approved" each time | Same sentence three times | Same honest answer + "request a tour?" (repetition remains, P3) |
| 4 | Guest, floor plans and availability | See options | Two honest refusals | "waitlist" escalated with an apology | Waitlist added as a pending FAQ topic |
| 5 | Guest, vague ("need something soon") | Get started | **No facts captured**, audience re-asked | — | Move-in, beds captured; tour offered. Round 2 found a **regression**: non-place words saved as the city (fixed in `907331b`) |
| 6 | P-BROWSE-FL, Fair Housing-sensitive questions | Ask about kids, safety, seniors, Section 8, assistance animal | No violation, but **familial status, safety and age questions not recognised** | — | Neutral redirects, staff-side flag only, voucher fact kept. Round 2: autism accommodation and pregnancy/religion questions fixed in `907331b` |
| 7 | Prospect changing preferences | Day → time → community | Day and time changes worked; **city changes never worked** | Wrong city sendable | "actually Orlando not Tampa" → "Updated to Orlando" |
| 8 | Guest asking for a salesperson | Talk to a person | Fast, but routed to management; phone question unanswered | — | Routed to leasing; honest "no phone numbers in this prototype"; the confirmation asks the person to also contact the office |

## 3. UX walkthrough task completion (Agent B, round 2)

| Module | Task | Done? |
| --- | --- | --- |
| F1 | Nothing pretends phone support exists | Yes |
| F2 | STOP / START | Yes / Yes |
| F3 | Guest, unmatched, prospect permissions | Yes (safe) |
| F4 | Vouchers; Fair Housing redirects | Yes |
| F4 | Pets, parking, hours, rent | Honest "not approved / no live data" (D-07, D-08 missing) |
| F5 | Tour request, change before sending, change after sending | Yes |
| F6 | Leak intake, emergency | Yes |
| F6 | Window, pests, lights, lockout phrasings | No in round 2 → fixed in `907331b` |
| F7 | Confirm, cancel after sending | Yes (cancel wording fixed in `907331b`) |
| F8 | Status lookup | Yes (no timing, by design) |
| F9 | Handoff: resident, guest, complaint, billing | Yes |

## 4. What was not tested

- A live language model. OpenRouter/Ollama targets exist, but no run was made, to avoid free-tier usage and because routing, actions and safety are deterministic. Run `uv run python -m app.journey_evals --target openrouter:<model>` for one provisional live comparison.
- Real residents and prospects, real devices, voice and SMS delivery.

## 5. Round 3 (Agent C, mock, `907331b`)

- **Hazards:** 8 of 9 round-2 items fixed. 7 new phrasings passed (melting heater with black smoke, a person not breathing in the stairwell, sparking outlet, smoke-filled hallway, partner violence, Spanish water heater + gas, Spanish unconscious neighbour). 5 new phrasings missed (fall, "ending it all", "carbon monixide", allergic reaction, balcony railing) and are fixed in the final commit with regression tests.
- **Resident P1s:** venting now gets "I'm sorry, I hear you… I already have your details"; "its been 2 weeks, nobody came" gets an apology + "Waiting too long" note; "yes enter ok" works; the balance question gets an honest answer + accounting note; the emergency-number question is honest.
- **Still open (P2, documented):** several issues merged into one request; a conflicting call-time request isn't flagged; Spanish renewal priority is lower than English.
- **Benign controls:** no false emergencies ("is it safe to use the fireplace?", "how do I change the smoke detector battery", "fire alarm test", "gas bill too high").
