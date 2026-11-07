# UX review: design, independent reviews, fixes and verification

> **Sprint 2 (November 2026)** is summarised first; the sprint-1 review follows unchanged below the line.
> Full evidence, scores and remaining blockers: [SPRINT_REVIEW_REPORT.md](SPRINT_REVIEW_REPORT.md). Design skills:
> [DESIGN_SKILL_USAGE.md](DESIGN_SKILL_USAGE.md).

## Sprint 2 at a glance

**Reviewers** (fresh, session-scoped subagents; no `.claude/` files changed): A UI critic, B UX/product critic,
C frustrated resident, D ordinary resident, E prospect, F accessibility, G safety/security adversary, H
independent regression verifier (implemented nothing). A–G ran round 1 on `d3d64d6` and round 2 on `a9154ac`.
The frontend fixes were made by a separate implementer agent; backend fixes by the main agent. Nobody scored
their own work.

| Score (0–10, strict) | Round 1 | Round 2 |
| --- | --- | --- |
| Visual design, customer (A) | 7 | 7 |
| Visual design, staff (A) | 5 | 6 |
| Customer usability (B) | 4 | 5 |
| Conversational quality (B) | 3 | 4 |
| Staff console usefulness (B) | 3 | 5 |
| Accessibility customer / staff (F) | 7 / 6 | 8 / 6.5 |
| Safety (G) | 3 | 4 |
| Security / privacy (G) | 5 | 6 |

**What the design questions in the brief turned into:**

| Question | Answer from the reviews | Change |
| --- | --- | --- |
| Does every request need an action card? Is it shown at the right moment? | No: a card on every collecting turn, stacked "Earlier version" stubs (A7, B12) | Card only at read-back; a one-line "Still needed" progress note before that; superseded cards hidden |
| Confirming things that don't need it? | Office notes were filed for misunderstandings nobody asked to escalate (D F3) | "Not understood twice" offers the office; a note exists only if the person says yes |
| Too many questions before helping? | Vague issues led straight to "which room?" (D F7) | Ask *what* first, once; corrections replace instead of append |
| Can customers recover from misunderstandings? | Declines were final; corrections silently ignored (B1–B4) | Decline is kept once ("send it after all"); every applied change is said out loud |
| Too many internal status indicators? | Status list unbounded, urgent in green (A1, A2) | One status colour map; urgent/owed first (max 3), 3 most recent, Show all |
| Can customers reach a human quickly? | Manager requests ignored while a form was open (C-2) | Person/manager phrasings win at any stage and carry the details |
| Staff dashboard: decisions or noise? | Unfiltered list of 70 machine rows; no live view (B5, B6) | Work queue (urgent first, filters, readable rows, stacked on phones) + Live conversations + Usability tab |
| Mobile composer always usable? | Hid focused buttons at high zoom (F1) | Scroll padding follows the composer; not sticky on short screens |
| Draft vs submitted vs completed clear? | Sent cards kept live Send buttons (A N1, B17, C R-5, D F12) | Fixed in `8fdf0d3` (a hidden card state was being coerced to "current") |

**Suggestions not adopted (with reason):** collecting guest phone numbers in the tour card (E F7): we don't store
contact details from guests in a public-repo prototype; the honest "contact the office" note remains and this is
listed as a product decision. Full-screen detail view for staff conversations on phones (A N3): focus now moves to
the transcript instead; a separate route was out of scope.

---

## Sprint 1 review (unchanged)


Branch `feat/workflow-customer-experience`. Covers the customer view (`/`) and the staff and demo console (`/staff/`). Usability transcripts: [USABILITY_TEST_RESULTS.md](USABILITY_TEST_RESULTS.md). Accessibility: [ACCESSIBILITY_REVIEW.md](ACCESSIBILITY_REVIEW.md).

## 1. Design skills: what was actually used

| Skill | Status | How it was used |
| --- | --- | --- |
| **oil-ui** (`~/.claude/skills/oil-ui`) | Installed, used | Product facts → one main element per screen → build → real screenshots → independent review. Reviewer A followed its `reviewer-manual.md` rubric (score 1–10) and Reviewer B its `ux-reviewer.md` walkthrough. Its visual-language rules shaped one-family typography, fixed colour roles, "every state looks different", and "no build notes in the UI". The one exception: the brief requires the prototype to say clearly what is simulated, so prototype notes stay visible on cards. |
| **frontend-design** (Claude plugins marketplace, `frontend-design/SKILL.md`) | Read from the marketplace copy (plugin not enabled) | Two-pass token plan (below). I checked it against the skill's list of generated-UI defaults: no cream/terracotta, no ALL-CAPS eyebrows, no "→" on buttons, no middot meta strings in the customer view. Copy rules: buttons say what happens ("Send repair request"), errors say what went wrong and what to do. |
| **ui-ux-pro-max** | **Not installed; not available** | Not used. Reviewer A noted it would have used it to benchmark chat-widget patterns. |
| **web-accessibility** | **Not installed; not available** | Not used. Reviewer E worked directly against WCAG 2.2 AA with axe-core 4.x and Playwright (see ACCESSIBILITY_REVIEW.md). |

### Design direction (frontend-design pass 1, checked in pass 2)

- **Subject:** a help desk for affordable garden-style apartment communities. The users are working residents and prospects, mostly on phones, some not fluent in English.
- **Job:** get the next step done and know exactly what happened.
- **One memorable element:** the request "slip". It reads back each detail with where it came from ("You told us", "On your account", "Added by the assistant"), and has an explicit state and send button. Everything around it stays quiet.
- **Colour tokens (verified contrast in `globals.css`):**
  - ink `#14231C`, muted `#4B5D54`, paper `#F6F7F5`, surface `#FFFFFF`, line `#D9E1DC`, input border `#7C8D84` (3.4:1);
  - evergreen brand `#1D5C45`: primary action and "sent";
  - blue `#1D4F91`: "check, then send";
  - amber `#7A4206`: "a person should help" and "follow-up owed";
  - red `#A3241C`: emergency only;
  - neutral: draft, "Not sent" and "Earlier version".
- **Type:** Atkinson Hyperlegible Next, one family, chosen because it was designed for low-vision legibility. 16px body text, sentence case. Its slashed zero is intentional: it keeps 0 and O apart in reference numbers.
- **Layout:** a single 672px conversation column; a sticky composer with suggestion chips (one scrolling row on phones); tap targets of 44px or more.
- **Pass-2 revisions:** the first plan used green for "ready to send". Reviewer A showed green reads as "done", so ready became blue and sent became green. The cyan "MOCK" banner was replaced by a neutral note.

## 2. Reviewers (session-scoped Claude Code subagents; no `.claude/` files changed)

| Agent | Role | Evidence they produced |
| --- | --- | --- |
| A | Senior UI design judge | 58 screenshots at 390 / 768 / 1280 px, live and preview |
| B | Senior UX / product judge | Live walkthroughs + API runs across F1–F9, task-completion table |
| C | Resident simulator (adversarial) | ~75 API conversations + 4 personas in the UI at phone size |
| D | Prospect / leasing simulator | ~75 turns + 3 phone-UI scenarios |
| E | Accessibility judge | axe-core in 20+ states, keyboard / focus / accessibility-tree / reflow checks |
| F | Backend / AI safety reviewer | Code review + live probes, a race test, regex corpus |

Each reviewer got only the running app, its tools and its role. They did not get the main agent's analysis, and each worked independently before consolidation. All replies came from the deterministic **mock** model, so the reviews judge backend routing, actions, safety and template wording, not LLM prose.

## 3. Round 1: highest-priority findings and fixes

Severity: P0 = unsafe, privacy leak, or false completion; P1 = a real user is blocked or misled; P2 = noticeable; P3 = minor.

| # | Sev | Found by | Finding | Fix (commit `782383d`) | Round 2 |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 | C, F, E | Hazards missed: typos ("smels like gass"), hot or buzzing panel, CO with symptoms, water in a light fixture, Spanish flooding and "Huelo a gas", Vietnamese/Arabic gas, break-in, domestic violence, chest pain, self-harm | New `app/emergency.py`. It classifies by hazard (gas, CO, fire/smoke, electrical, flood, structural, personal safety, medical, self-harm), collapses spaced-out letters, covers 5 languages, and keeps a benign low-battery chirp as non-emergency. 31 phrasings + 5 benign controls in `test_review_regressions.py` | Fixed (round 2) |
| 2 | P0 | F | Model text could claim "technician on the way" in an emergency (the action-claim check was cleared because a note had been written) | Emergencies skip the model (fixed template). A completion claim is accepted only from a backend template that actually wrote a record | Fixed (round 2) |
| 3 | P0 | F | Urgent note de-duplicated by session only: another persona was shown someone else's note, and a second hazard was never saved | De-duplication is per (session, persona, hazard) | Fixed (round 2) |
| 4 | P0 | B | An upset resident was told "I've written a note", but none existed | The template no longer claims a note. Frustration is shown on the repair card as "high priority" and carried to the saved record. Status complaints show a real note card | Fixed (round 2) |
| 5 | P0 | A | A declined card stayed sendable; old cards kept "Ready to send" | Cards get a final state: "Not sent" (declined) or "Earlier version" (replaced). Only the newest open card has buttons | Fixed (round 2) |
| 6 | P0 | A | No tap-to-call during an emergency | A full-width `tel:911` button (`tel:988` / `sms:988` for a crisis). The text says the community's emergency number is not connected in the prototype; no fake number is shown | Fixed (round 2) |
| 7 | P1 | F, C | "yes but don't send", "ok wait the room is wrong", "ok thanks", "ok can someone talk to me" all submitted cards | Consent must be the whole message or an explicit unhedged "send it". Hedges block it. A card set aside for other turns is shown again before any send | Fixed (round 2) |
| 8 | P1 | F | Parallel confirms wrote 4–8 duplicate records | `Store.take_draft` (atomic `DELETE … RETURNING`); a failed write restores the draft | Fixed (round 2) |
| 9 | P1 | F | Unformatted phone numbers, SSNs, DOBs and obfuscated emails stored unredacted | New redaction patterns; Luhn check, so long non-card numbers are not mangled (E-14) | Fixed (round 2) |
| 10 | P1 | B, C | Corrections ignored ("bathroom, not kitchen"); "no wait…" discarded the card; "never mind" became a new request | "Not X" segments are ignored when extracting; correction lead-ins edit the card; cancel phrases close the card | Fixed (round 2) |
| 11 | P1 | B, C | Change or cancel after sending was impossible ("haven't sent anything", or a new duplicate tour) | Change/cancel after send creates an office note naming the reference (tours go to leasing) | Fixed (round 2) |
| 12 | P1 | C | "AGENT", "let me speak to the manager" and Spanish/Vietnamese human requests were ignored mid-repair | Human requests win at any stage and carry the repair details into the note | Fixed (round 2) |
| 13 | P1 | B, C | "hello", "thanks" and the bot's own chips triggered "I'm sorry I'm not getting this right" plus an escalation | Small talk is answered and never counts as unsure. A recognised intent beats the unsure-twice rule | Fixed (round 2) |
| 14 | P1 | C | Status questions mid-flow ("did that go thru?", "cuándo vienen") were swallowed | Broader status detection, checked before repair intake | Fixed (round 2) |
| 15 | P1 | D | "yes please" saved as the community; city corrections ignored; "see a 2 bed this week" not a tour; "confirm 4pm?" not answered honestly | Filler is rejected; "actually Orlando not Tampa" updates the city; broader tour intent; clock times stored as a preference; booking questions get an explicit "nothing is booked" | Fixed (round 2) |
| 16 | P1 | D, B | Fair Housing: "fewest kids", "safe for a single woman", "seniors only", "families with kids" not detected; customer shown a "Fair Housing" note card | Broader steering detection → neutral redirect + tour/leasing chips. The compliance flag stays on the staff side only (no customer card) | Fixed (round 2) |
| 17 | P1 | A | On phones the newest card's send button sat under the composer | The page scrolls to the true end, so the newest card sits above the sticky composer | Fixed (round 2) |
| 18 | P1 | A | The error state looked like a normal reply | Amber error panel with an icon, the unsent message marked "Not sent", and "Send again" | Fixed (round 2) |
| 19 | P1 | A, C, E | Spanish users saw a mixed-language UI; user text was tagged `lang="en"` | All UI strings in EN/ES (draft translations); greeting in the preferred language; `lang` on every message and on the chips | Fixed (round 2) |
| 20 | P1 | A, E | Staff tabs wrapped onto the panel heading on phones | One scrolling tab row, a 2px underline for the selected tab, the 3px app focus ring | Fixed (round 2) |
| 21 | P1 | E | Focus fell to `<body>` after "Don't send" | Focus moves to the new message; composer sends keep focus in the textarea | Fixed (round 2) |
| 22 | P2 | E | The live region re-read whole cards; focus moves caused double reads | The transcript is no longer a live region. One short polite announcement per reply (reply + card title + stage); emergencies are announced once via `role=alert` | Fixed (round 2) |
| 23 | P2 | F | `<backend_draft_reply>` smuggling; unscreened injected text in records | All tag-like markup is stripped from user text; injection-like issue text is stored with a "[flagged …]" prefix | Fixed (round 2) |
| 24 | P2 | F | Many false-completion, time, price and offer phrasings, and Spanish claims, passed validation | Extended regexes; 11 regression phrasings | Fixed (round 2) |
| 25 | P2 | D, B | Salesperson requests went to management; "what's the phone number?" unanswered | Prospect and visitor handoffs go to leasing; an honest "no phone numbers in this prototype" | Fixed (round 2) |
| 26 | P2 | E | Staff contrast 4.0–4.3:1; table not keyboard-scrollable; heading levels skipped | Darker muted and destructive tokens; focusable table region; h3 per step, h4 diagnostics | Fixed (round 2) |
| 27 | P2 | A | Disclaimer pile-up ("Yardi", repeated "prototype") | One short note per card; no internal system names | Fixed (round 2) |
| 28 | P2 | F | Paid gate override on by default | `GATE_OVERRIDE_ENABLED` defaults to False | Fixed (round 2) |

## 4. Rounds 2 and 3: independent re-verification

Every reviewer re-ran its own reproductions against the rebuilt app (round 2, commit `782383d`). The two safety-critical reviewers, C (resident simulator) and F (backend), ran a third round on `907331b`. "Fixed" in §3 means the reviewer who found it confirmed it, not that code was changed. Each round also produced new findings, listed here.

### Round 2 verdicts

| Reviewer | Round-1 items | Verdict | Score |
| --- | --- | --- | --- |
| A (UI) | 14 | 9 fixed, 5 partly, 0 not fixed; all three P0s fixed | **6 → 7 / 10** |
| B (UX) | 15 | 4 fixed, 9 partly, 2 not fixed (common repair phrasings, language switching); its P0 fixed | — |
| C (residents) | 12 hazard P0s + 11 P1s | All 12 hazards fixed; 8 of 11 P1s fixed or partly | — |
| D (prospects) | 5 P1s, 5 P2s, 4 P3s | 4 fixed, 6 partly | — |
| E (accessibility) | 14 | 13 fixed or mostly fixed; axe 0 everywhere | — |
| F (safety) | 3 P0s, 5 P1s, 4 P2s | All P0s fixed; races fixed; identity binding open (expected) | — |

### New findings in round 2, all fixed in `907331b`

| Sev | Found by | Finding | Fix |
| --- | --- | --- | --- |
| P0 | C | 7 new hazard phrasings missed (wires + "smokin", rotten-egg smell, Turkish gas, "don't wanna be here", a neighbour being hit, a child swallowing cleaner, stuck in an elevator) | New kinds (poison, trapped) + broader patterns |
| P1 | F | "Can I go ahead and paint my walls?" submitted a ready card | Send commands must be the whole message |
| P1 | D | Non-place words saved as the tour city ("Utilities", "March", "Spanish") | Place names only (capitalised, not months, languages or common nouns) |
| P1 | B | "I need to cancel that request" hit a dead end (operator-precedence bug) | Fixed precedence; any cancel wording after sending → note with reference |
| P1 | B | Rent and discount questions turned into tour requests ("sign today" saved as a day) | Price questions never fill tour fields |
| P1 | C | Promise and credit demands written into the work order | Kept in a separate "Also asked for (office decides)" field + "can't promise" reply |
| P1 | D | Autism accommodation treated as a complaint | Disability vocabulary → accommodation route |
| P1 | A | Tablet/desktop card listed the answer before its label | Explicit grid columns |
| P2 | F | Email redaction mangled words and took ~250 ms on 4000 characters | Strict address pattern (7–12 ms) |
| P2 | F | "Is smoking allowed?", "knife block" etc. triggered emergencies | Policy and figurative exclusions |
| P2 | F | Stale marking could resurrect a sent draft; emergency duplicate race | `mark_stale` (UPDATE only), `add_record_once` |
| P2 | F | Honest templates failed the system's own checks | Negation-aware claim check; test that every template passes |
| P2 | E | Chip and tab focus rings clipped; double announcements; live region without `lang` | Padding, single announcement, `lang` on live region and heading |

### Round 3 (C and F, on `907331b`)

- **Verified fixed:** 8/9 of C's round-2 hazard items, promises and credits, venting empathy, status follow-ups, broken English, Spanish pests and hot water, balance questions (C); N1–N7 and N9, both races, email speed (F).
- **New, fixed in the final commit, verified by regression tests that encode the reviewer's exact reproduction (not independently re-reviewed):**
  - **P1 (F), my regression:** narrowing the patterns in round 2 made them miss "waving a gun", "someone is following me" and "I think it's a stroke". Restored, plus gunshots, threats, a stranger in the apartment, stroke signs, drank/ate poison, entrapment, "end it", and Spanish crisis wording.
  - **P0 (C):** a fall where the person can't get up, "thinking about ending it all", "carbon monixide", an allergic reaction to stings, a loose balcony railing.
  - **P1 (C):** a repair with a credit request was saved to accounting, so the repair now stays with maintenance.
  - **N1 (C):** "send all of it" dropped earlier unsent notes, so unsent notes are now merged and listed in status.
  - **P2 (F):** a second room rewrote the first room's description; a bare "no" after sending prepared a change note.

### Assessment

No P0 or P1 found by any reviewer is knowingly left open, **with two documented exceptions**:

1. **Identity binding (F P1-4).** The browser sends `persona_id`, and staff routes have no authentication. This is by design for a demo with synthetic personas and is a **deployment blocker**.
2. **Keyword emergency detection is a safety floor, not a guarantee.** Every round, the adversarial resident found new phrasings, and the misses fell from 12 to 7 to 5. The prototype shows a 911 line in the footer of every screen, and an LLM gate can only *add* urgency. A production system needs McKinley-approved I-17 lists, a model-assisted classifier run in parallel, and live monitoring.

## 5. Reviewer suggestions deliberately not adopted

| Suggestion | Reviewer | Decision and reason |
| --- | --- | --- |
| Show a sample community emergency-maintenance number | A, B | **Not adopted.** D-03 is not supplied. A fake number in an emergency could be dialled. The UI says the number is not connected in the prototype and gives a real `tel:911`. |
| Add sample "approved" FAQ answers (pets, parking, office hours) | B | **Not adopted.** That would invent McKinley policy. Only the voucher fact is approved; other topics say so honestly and offer a tour or leasing note. The structure is ready in `knowledge_base.json`. |
| Promise a reply time ("usually within 1 business day") | B | **Not adopted.** I-05 is not supplied, and the output check rejects invented times. |
| Collect a guest's name and phone before sending a note or tour | B | **Deferred.** Synthetic-data rule: the prototype collects no contact details. The confirmation says so and asks the person to contact the office directly. |
| Treat water-only leaks as non-911 | C | **Partly adopted.** The flood text now leads with emergency maintenance and keeps 911 only for electrical contact or danger. Urgency stays "emergency", so the urgent note is still saved (conservative until I-17 is approved). |
| Plain zero instead of the font's slashed zero | A | **Not adopted.** Slashed zero is a legibility feature of the chosen face, keeping 0 and O apart in references like DEMO-WO-1001. |
| Sticky header so identity stays visible | A | **Not adopted** (P3). It would cost about 150px of phone height; the identity sits at the top of the conversation. |

## 6. Remaining P2/P3 items (documented, not blocking)

- Spanish translations are drafts. Workbook values such as visit windows ("afternoons (1-5 PM)") stay in English.
- Guests cannot leave contact details (by design for synthetic data).
- Staff console: the existing A/B/C comparison and evaluation tabs keep their older shadcn styling (button styles differ from the customer view).
- Repeated identical "not approved yet" FAQ answers in a row (D P3-2).
- Multiple different issues in one repair are merged into one request with "Also: …" rather than split into separate requests (C P1-9).
- A requested call time that conflicts with the contact rule on file isn't flagged (C P2-2).
- A Spanish renewal concern routes with normal priority where the English one gets high (C P1-10, partly fixed).
- The staff console's existing comparison and evaluation tabs keep the older shadcn buttons and raw flag names (A P2-14).
- The three-second test still reads as a generic support chat (A: 7/10). A McKinley-specific visual signature is open design work.
