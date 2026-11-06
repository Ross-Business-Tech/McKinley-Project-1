# UX review: design, independent reviews, fixes and verification

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
| 1 | P0 | C, F, E | Hazards missed: typos ("smels like gass"), hot or buzzing panel, CO with symptoms, water in a light fixture, Spanish flooding and "Huelo a gas", Vietnamese/Arabic gas, break-in, domestic violence, chest pain, self-harm | New `app/emergency.py`. It classifies by hazard (gas, CO, fire/smoke, electrical, flood, structural, personal safety, medical, self-harm), collapses spaced-out letters, covers 5 languages, and keeps a benign low-battery chirp as non-emergency. 31 phrasings + 5 benign controls in `test_review_regressions.py` | see §4 |
| 2 | P0 | F | Model text could claim "technician on the way" in an emergency (the action-claim check was cleared because a note had been written) | Emergencies skip the model (fixed template). A completion claim is accepted only from a backend template that actually wrote a record | see §4 |
| 3 | P0 | F | Urgent note de-duplicated by session only: another persona was shown someone else's note, and a second hazard was never saved | De-duplication is per (session, persona, hazard) | see §4 |
| 4 | P0 | B | An upset resident was told "I've written a note", but none existed | The template no longer claims a note. Frustration is shown on the repair card as "high priority" and carried to the saved record. Status complaints show a real note card | see §4 |
| 5 | P0 | A | A declined card stayed sendable; old cards kept "Ready to send" | Cards get a final state: "Not sent" (declined) or "Earlier version" (replaced). Only the newest open card has buttons | see §4 |
| 6 | P0 | A | No tap-to-call during an emergency | A full-width `tel:911` button (`tel:988` / `sms:988` for a crisis). The text says the community's emergency number is not connected in the prototype; no fake number is shown | see §4 |
| 7 | P1 | F, C | "yes but don't send", "ok wait the room is wrong", "ok thanks", "ok can someone talk to me" all submitted cards | Consent must be the whole message or an explicit unhedged "send it". Hedges block it. A card set aside for other turns is shown again before any send | see §4 |
| 8 | P1 | F | Parallel confirms wrote 4–8 duplicate records | `Store.take_draft` (atomic `DELETE … RETURNING`); a failed write restores the draft | see §4 |
| 9 | P1 | F | Unformatted phone numbers, SSNs, DOBs and obfuscated emails stored unredacted | New redaction patterns; Luhn check, so long non-card numbers are not mangled (E-14) | see §4 |
| 10 | P1 | B, C | Corrections ignored ("bathroom, not kitchen"); "no wait…" discarded the card; "never mind" became a new request | "Not X" segments are ignored when extracting; correction lead-ins edit the card; cancel phrases close the card | see §4 |
| 11 | P1 | B, C | Change or cancel after sending was impossible ("haven't sent anything", or a new duplicate tour) | Change/cancel after send creates an office note naming the reference (tours go to leasing) | see §4 |
| 12 | P1 | C | "AGENT", "let me speak to the manager" and Spanish/Vietnamese human requests were ignored mid-repair | Human requests win at any stage and carry the repair details into the note | see §4 |
| 13 | P1 | B, C | "hello", "thanks" and the bot's own chips triggered "I'm sorry I'm not getting this right" plus an escalation | Small talk is answered and never counts as unsure. A recognised intent beats the unsure-twice rule | see §4 |
| 14 | P1 | C | Status questions mid-flow ("did that go thru?", "cuándo vienen") were swallowed | Broader status detection, checked before repair intake | see §4 |
| 15 | P1 | D | "yes please" saved as the community; city corrections ignored; "see a 2 bed this week" not a tour; "confirm 4pm?" not answered honestly | Filler is rejected; "actually Orlando not Tampa" updates the city; broader tour intent; clock times stored as a preference; booking questions get an explicit "nothing is booked" | see §4 |
| 16 | P1 | D, B | Fair Housing: "fewest kids", "safe for a single woman", "seniors only", "families with kids" not detected; customer shown a "Fair Housing" note card | Broader steering detection → neutral redirect + tour/leasing chips. The compliance flag stays on the staff side only (no customer card) | see §4 |
| 17 | P1 | A | On phones the newest card's send button sat under the composer | The page scrolls to the true end, so the newest card sits above the sticky composer | see §4 |
| 18 | P1 | A | The error state looked like a normal reply | Amber error panel with an icon, the unsent message marked "Not sent", and "Send again" | see §4 |
| 19 | P1 | A, C, E | Spanish users saw a mixed-language UI; user text was tagged `lang="en"` | All UI strings in EN/ES (draft translations); greeting in the preferred language; `lang` on every message and on the chips | see §4 |
| 20 | P1 | A, E | Staff tabs wrapped onto the panel heading on phones | One scrolling tab row, a 2px underline for the selected tab, the 3px app focus ring | see §4 |
| 21 | P1 | E | Focus fell to `<body>` after "Don't send" | Focus moves to the new message; composer sends keep focus in the textarea | see §4 |
| 22 | P2 | E | The live region re-read whole cards; focus moves caused double reads | The transcript is no longer a live region. One short polite announcement per reply (reply + card title + stage); emergencies are announced once via `role=alert` | see §4 |
| 23 | P2 | F | `<backend_draft_reply>` smuggling; unscreened injected text in records | All tag-like markup is stripped from user text; injection-like issue text is stored with a "[flagged …]" prefix | see §4 |
| 24 | P2 | F | Many false-completion, time, price and offer phrasings, and Spanish claims, passed validation | Extended regexes; 11 regression phrasings | see §4 |
| 25 | P2 | D, B | Salesperson requests went to management; "what's the phone number?" unanswered | Prospect and visitor handoffs go to leasing; an honest "no phone numbers in this prototype" | see §4 |
| 26 | P2 | E | Staff contrast 4.0–4.3:1; table not keyboard-scrollable; heading levels skipped | Darker muted and destructive tokens; focusable table region; h3 per step, h4 diagnostics | see §4 |
| 27 | P2 | A | Disclaimer pile-up ("Yardi", repeated "prototype") | One short note per card; no internal system names | see §4 |
| 28 | P2 | F | Paid gate override on by default | `GATE_OVERRIDE_ENABLED` defaults to False | see §4 |

## 4. Round 2: independent re-verification

Filled in from the reviewers' round-2 reports (they re-ran their own reproductions; nothing was marked fixed without them).

_See below; updated after round 2._

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
- Multiple different issues in one repair are merged into one request with "Also: …" rather than split into separate requests (C P1-9, partly addressed).
