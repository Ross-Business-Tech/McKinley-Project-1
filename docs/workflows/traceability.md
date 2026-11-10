# Workflow traceability: McKinley AI Agent Flow → prototype

Source: the team's "McKinley AI Agent Flow" checklist (kept locally in `docs/references/`, not in the public repository; ask the project owner for a copy) (nine function modules, 27 instruction inputs I-01…I-27, 14 data inputs D-01…D-14). Earlier analysis and the team's MVP recommendations: [`WORKFLOW_REVIEW.md`](source-review.md). Branch: `feat/workflow-customer-experience`.

**Status words used below**

| Status | Meaning |
| --- | --- |
| **Working** | Real behaviour on synthetic data. Would carry over to production once the listed McKinley inputs are approved. |
| **Simulated** | Works end to end, but writes to the clearly labelled **prototype store** (`prototype_records` in SQLite) instead of Yardi, a CRM, a pager or a real queue. Nobody is notified. |
| **Draft** | Uses a team-drafted rule, list or template that McKinley has **not approved**. Marked in code comments. |
| **Pending** | A placeholder exists; the assistant explicitly says it has no approved information. |
| **Unavailable** | Not built. Needs an integration or a decision that doesn't exist. |

Nothing in this prototype claims an approval McKinley hasn't given. Where the source says "McKinley approves", the code uses a draft and says so.

## 1. Function modules (F1–F9)

| F | Module | Status | What works now | Code | Tests | Outstanding dependencies |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | Phone and voice support | **Unavailable** | Nothing voice-specific. `channel="voice"` is rejected (422). The same conversation logic is exercised over web chat. | `models.py` `Channel` | `test_sms_channel_opt_out_is_deterministic` (voice rejected) | Telephony + STT/TTS; I-01 disclosure + recording consent (legal); I-02, I-03, I-04; D-01–D-03 |
| F2 | SMS and email | **Simulated + Draft** | `channel` = `sms` / `email` changes reply rules (I-07 draft). SMS opt-out keywords (I-06 draft) are answered deterministically with no model call. Conversation context is kept per session. Nothing is sent. | `actions.py` step 0; `chat_engine.py` `CHANNEL_RULES`; `intake.is_sms_opt_out` | `test_sms_channel_opt_out_is_deterministic` | SMS/email gateways; opt-in consent records; approved opt-out wording (I-06); D-04 thread matching |
| F3 | Caller type classification | **Working (prototype identity)** | Audience = trusted demo sign-in, never message text. Matched resident → resident permissions; "says they're a resident" with no record → public info + office note; vendors → management, no access data; unknown → one question (I-09 draft). | `personas.build_context`, `gates/rules.py`, `actions.plan_turn` steps 3–4, `templates["who_are_you"]` | `test_unverified_claims_unlock_nothing`, `test_steering_vendor_and_language`, `test_gates.py` | Real verification (I-10) and permission matrix (I-11); vendor list (D-06). **The demo sign-in is not authentication** (see §4). |
| F4 | Property and leasing FAQs | **Working for approved entries, Pending otherwise** | Topic list (I-12 draft) in `knowledge_base.json`. Only `status: approved` entries are stated (housing vouchers). Pending topics say so and point to leasing. Prices/availability: "can't see live data". Steering questions get a neutral redirect + staff note (I-13 draft). | `app/content/knowledge_base.json`, `intake.match_faq`, `actions._faq_text` | `test_faq_uses_only_approved_answers`, `test_steering_vendor_and_language` | D-07 approved per-property knowledge base; D-08 live pricing/availability; I-13 legal approval; I-14 approval |
| F5 | Tour scheduling | **Simulated + Draft** | Collects community/city, preferred days, time of day (+ beds if given), one question at a time; reuses the prospect profile; preferences can change mid-way; read-back; saves `DEMO-TOUR-…` with status "Requested; leasing team to confirm a time". Never offers clock times or confirms a booking. | `actions.plan_turn` step 7, `intake.extract_*` | `test_tour_request_change_midway_is_never_a_booking` | D-09 tour calendar; D-10 CRM lead record; I-15 required tour questions/tour types; I-16 confirmation + reminder (consent) |
| F6 | Maintenance request intake | **Working + Draft rules; emergency detection NOT production ready** (fresh holdout 64.5% full alert, release-blocking misses: [safety-evaluation](../safety/safety-evaluation.md)) | Emergency check first, for every audience (I-17 draft list), fixed safety text (I-18 draft). Verified residents: issue, room (inferred from appliance where obvious), entry permission; contact preference and visit window reused from the account; one question at a time; approved low-risk tips (I-20 draft) passed to the model only; repeat issues acknowledged and flagged for a manager. | `safety.pre_model_gates`, `workflows.maintenance_triage`, `actions.plan_turn` steps 1 and 6 | `test_maintenance_intake_readback_confirm_and_status`, `test_emergency_for_every_audience_writes_one_urgent_note`, `test_short_answers_do_not_count_as_unsure` | I-17/I-18/I-20 McKinley maintenance approval; I-19 categories and fields; D-03 on-call |
| F7 | Create / update work orders | **Simulated** | Confirmed request → `DEMO-WO-…` with status "Submitted, waiting for staff review" (conservative default for I-21: every request reviewed). Change/cancel requests → staff note (I-24 not approved). Confirmation re-reads the server-side draft and re-checks identity. Failed writes say "nothing was sent". | `actions.confirm`, `api/actions.py`, `db.add_record` | `test_affirmative_reply_submits_only_when_ready`, `test_confirm_reuses_server_draft_and_rechecks_identity` | D-11 Yardi write access; I-21 approval rules; D-12 approvers; I-22 templates (draft in `templates.CONFIRM`); I-23 timing; I-24 change rules |
| F8 | Request status lookup | **Working (read-only, synthetic) / Simulated** | Matched residents see open items from synthetic history + prototype requests and office notes: reference, short title, status, opened date. No entry windows, no notes, **no timing** (I-23 missing). Unverified → refused + office note. Frustration → office note offered. | `actions.status_items`, `actions.plan_turn` step 5 | `test_maintenance_intake_readback_confirm_and_status`, `test_unverified_claims_unlock_nothing` | D-11 live status; I-22/I-23; D-13 notifications with consent + quiet hours |
| F9 | Human handoff and escalation | **Simulated + Draft** | Structured handoff (team, priority, category, reasons, minimal summary, contact guidance) for every global trigger. Customer sees a read-back "Note for the office" and confirms; saved as `DEMO-TASK-…`. Emergencies are saved immediately as urgent. Staff see a "not sent / prototype queue" delivery note. | `handoff.build_handoff`, `actions._handoff_draft`, `actions.synthesize_handoff` | `test_complaint_is_a_handoff_trigger`, `test_emergency_…`, `test_gates.py` | I-25 trigger list approval; I-26 routing table; I-27 summary review; I-05 response times; D-01/D-02/D-03 transfer + on-call; D-14 a real monitored queue |

Global handoff triggers from the source ("any step"), all deterministic, none decided by a model alone:

| Trigger | Implementation | Test |
| --- | --- | --- |
| Emergency | `app/emergency.py` → urgency emergency → fixed safety text (no model) → one urgent note per person and hazard | `test_emergency_for_every_audience_writes_one_urgent_note`, `test_review_regressions.py` (~70 phrasings + benign controls) |
| Asks for a person | `human_requested` / `explicit_human_request` flags, `intake.is_staff_request` | `test_gates.py`, journeys `res-human`, `pro-human` |
| Complaint or upset caller | `complaint_or_frustration` flag (now in `ALWAYS_HUMAN_FLAGS`) | `test_complaint_is_a_handoff_trigger` |
| Legal, billing or rent dispute | `financial_or_lease`, `fair_housing_or_legal` | `test_gates.py` |
| Fair Housing sensitive | `fair_housing_or_legal` (accommodation), `intake.is_steering_question` (steering) | `test_steering_vendor_and_language` |
| AI unsure twice | `repeated_low_confidence` (two consecutive low-confidence turns; short answers to the assistant's own questions don't count) | `test_short_answers_do_not_count_as_unsure`, `test_gates.py` |
| Vendor contact | `intake.is_vendor_contact` → management | `test_steering_vendor_and_language` |
| Unverified caller asking for private info | `unverified_private_request`, `intake.is_status_request` for unmatched residents | `test_unverified_claims_unlock_nothing` |

## 2. Instruction inputs (I-01–I-27)

| ID | What it is | Status | Where | Needs |
| --- | --- | --- | --- | --- |
| I-01 | Greeting + AI disclosure | Draft (web chat greeting) | `frontend/src/lib/customer.ts` `greeting()` | McKinley + legal; recording consent for voice |
| I-02 | When to transfer a call | Unavailable (voice) | — | Voice channel |
| I-03 | Voice reply style | Unavailable | — | Voice channel |
| I-04 | End-of-call summary + SMS confirmation | Unavailable | — | Voice + texting consent |
| I-05 | Response-time promises | **Not supplied → no times promised** | `safety.output_checks` `no_invented_time`; templates avoid times | McKinley |
| I-06 | SMS opt-out keywords + consent | Draft | `intake.SMS_OPT_OUT`, `templates["sms_opt_out"]` | McKinley compliance + legal (add opt-in) |
| I-07 | SMS/email tone, length, signature | Draft | `chat_engine.CHANNEL_RULES` | McKinley approval |
| I-08 | Topic and status tags | Draft | gate intents, handoff categories, `workflows.LABELS`, `functions` on every response | Team |
| I-09 | "Who are you?" question | Draft | `templates["who_are_you"]` + chips | Team |
| I-10 | Resident verification rules | **Not supplied** | Demo sign-in only (`personas.build_context`). Sprint 2: staff, evaluation, gate and records routes are loopback-only unless `STAFF_API_TOKEN` is set (`api/staff_guard.py`); a demo boundary, not authentication. Sprint 3: requests carrying any proxy-forwarding header are never treated as local; "this is someone else's account" gets no account details. Identity is still client-asserted (`persona_id`): **production blocker** | McKinley + legal |
| I-11 | Permission matrix | Draft (conservative) | `actions.plan_turn`: matched resident → own requests/status; everyone else → public info + office note | McKinley |
| I-12 | FAQ topic list | Draft | `app/content/knowledge_base.json` | Team |
| I-13 | Fair Housing topics + approved response | Draft (split: steering → neutral redirect; accommodation → staff) | `intake._STEERING`, `safety` `fair_housing_or_legal`, `templates["steering"/"accommodation"]` | McKinley legal |
| I-14 | Answer rules: approved info only | Enforced | `knowledge_base.json` `status`, `output_checks` price/offer/time | McKinley approval |
| I-15 | Required tour questions + tour types | Draft minimum (area, days, time of day) | `actions.REQUIRED["tour_request"]` | McKinley leasing |
| I-16 | Tour confirmation + reminder templates | Draft confirmation only; no reminders | `templates.CONFIRM["tour_request"]` | Team + consent |
| I-17 | Emergency definition list | Draft, 11 hazard kinds: gas, CO, fire/smoke, electrical, flood, structural, personal safety, medical, poisoning, entrapment, self-harm; typo-, spacing- and multi-language-tolerant. Sprint 2: second layer that reads word combinations (person + unresponsive, substance + ingestion, symptoms + heat source, threat actor + act, means + intent); a third "possible risk" tier adds a calm care line (988 for distress, 911-if-worse when unwell) without an urgent note. Sprint 3: layered pipeline in `app/risk/` (rules with framing / negation / conversation window → optional semantic LLM classifier → explicit policy R1–R9 → approved text → escalation recommendation); hypothetical / past mentions get calm safety info; the semantic layer never removes a rules alert (it may drop only the broad 911 care line, R7) and is **not live-verified** (no key). Fresh independent holdout: 64.5% full alert / 78.5% any guidance, release-blocking misses remain (`docs/safety/safety-evaluation.md`). Still a deterministic floor, not a guarantee | `app/risk/*`, `app/emergency.py` `KINDS`, `CONCEPTS`, `scan`, `possible_risk`, used by `chat_engine` step 2b and the gate | McKinley maintenance + risk/legal |
| I-18 | Safety instructions per emergency | Draft text per hazard (EN + draft ES); `tel:911` / `tel:988` in the UI. Sprint 3: selected by `risk/responses.py` from the policy decision; 988 added to possible deliberate overdoses; gas/CO button reads "Get outside, then call 911"; a calm care line persists after "I'm fine, stop" following a person-danger alert | `app/emergency.py` `NOTICE`, `risk/responses.py`, `CustomerApp` alert | McKinley maintenance + risk/legal; fluent review of Spanish |
| I-19 | Maintenance categories + intake fields | Draft minimum (issue, room, entry permission) | `actions.REQUIRED["maintenance_request"]`, `workflows.APPROVED_TROUBLESHOOTING` categories | McKinley maintenance |
| I-20 | Approved self-troubleshooting | Draft (trivially safe checks only) | `workflows.APPROVED_TROUBLESHOOTING` | McKinley maintenance |
| I-21 | Which requests need staff sign-off | **Not supplied → all reviewed** | record status `submitted_for_review` | McKinley |
| I-22 | Work-order notification templates | Draft ("created" only) | `templates.CONFIRM` | Team |
| I-23 | Target timing + overdue threshold | **Not supplied → no timing, no "overdue"** | `templates["status_some"]` | McKinley maintenance |
| I-24 | What residents may change/cancel | **Not supplied → staff handle all changes** | `intake.is_change_request` → staff note | McKinley maintenance |
| I-25 | Handoff trigger list | Draft (table above) | `gates/base.ALWAYS_HUMAN_FLAGS`, `actions.plan_turn` | McKinley approval |
| I-26 | Routing table: issue → team | Draft | `handoff._team`, `actions.handoff_plan` overrides | McKinley must confirm (renewal, accommodation, vendor routes) |
| I-27 | Handoff summary format | Draft | `handoff.build_handoff` summary + customer-visible note fields | Staff review |

## 3. Data inputs (D-01–D-14)

| ID | What it is | Status | Where | Needs |
| --- | --- | --- | --- | --- |
| D-01 | Office hours per property | Pending (FAQ says not approved) | `knowledge_base.json` `office_hours` | McKinley |
| D-02 | Staff transfer numbers | Unavailable (no numbers shown, ever) | — | McKinley (fictional for demo only) |
| D-03 | On-call schedule | Unavailable; emergency text says "call your community's emergency maintenance line" | `templates["emergency"]` | McKinley |
| D-04 | Contact records | Synthetic workbook; **never sent to the model or UI** | `context.NEVER_FORWARDED` | Yardi |
| D-05 | Resident + unit records | Synthetic workbook (20 residents) via allowlisted context | `context.build_resident_context` | Yardi |
| D-06 | Vendor list | Unavailable; vendors detected from wording only, given no data | `intake.is_vendor_contact` | Yardi |
| D-07 | Approved knowledge base | Structure ready; 1 approved entry | `knowledge_base.json` | McKinley documents |
| D-08 | Live availability + pricing | Unavailable; never quoted | `knowledge_base.json` `live_data_unavailable`, `no_invented_price` | Yardi |
| D-09 | Tour calendar | Unavailable; requests only, no slots | — | McKinley |
| D-10 | Lead record fields | Simulated (tour request record fields) | `prototype_records` kind `tour_request` | Yardi CRM |
| D-11 | Work-order system | Simulated (prototype store) + read-only synthetic history | `db.add_record`, `actions.status_items` | Yardi |
| D-12 | Approver list | Unavailable | — | McKinley |
| D-13 | Contact preferences | Synthetic (`preferred_contact`, contact clauses of staff notes) reused in cards and handoffs; no notifications sent | `context.contact_note_clauses`, `actions._prefers` | Yardi + quiet hours/consent |
| D-14 | Staff task queue | Simulated (prototype store, staff console "Saved requests") — **not monitored** | `prototype_records` kind `staff_handoff` | Team for prototype; real queue later |

## 4. Per-function analysis

For each module: user goal · required information · data available / missing · decision points · validation · error states · escalation · user-facing outcome · real/simulated.

**F1 Phone and voice.** Goal: get help by calling. Needs speech-to-text and transfer. Available: nothing voice-related; missing D-01–D-03, I-01–I-04. Decisions: transfer? (I-02). Validation/errors: misheard twice. Escalation: always available by transfer. Outcome now: not offered. **Unavailable.**

**F2 SMS and email.** Goal: ask by text/email without an app. Needs: channel, sender match (D-04), opt-out. Available: channel rules, opt-out keywords (drafts). Missing: gateways, consent records. Decision: opt-out keyword? → stop. Validation: whole-message keyword match only (so "cancel my request" is not an opt-out). Errors: none sent. Escalation: same rules as chat. Outcome: shorter replies; opt-out confirmed. **Simulated.**

**F3 Caller type.** Goal (business): give each person the right permissions. Needs: trusted identity. Available: demo sign-in, synthetic records. Missing: real verification (I-10), permission matrix (I-11), vendor list. Decision: resident matched? prospect? vendor? unclear → one question. Validation: identity is never read from message text; "I'm Marisol in 12B" unlocks nothing. Errors: no record → office note. Escalation: unverified + private info. Outcome: correct permissions, or a note. **Working for the demo; real authentication is a production blocker.** In this prototype the browser sends `persona_id`; a deployment must bind identity to a signed-in session server-side.

**F4 FAQs.** Goal: quick, accurate answers before deciding to tour. Needs: approved per-property facts. Available: one approved fact. Missing: D-07, D-08, I-13 approval. Decision: approved entry? live data? steering? Validation: price/offer/time checks on every model reply. Errors: no approved answer → say so + leasing. Escalation: voucher, accommodation, steering. Outcome: honest answer + next step (tour or leasing). **Working but thin until McKinley supplies content.**

**F5 Tours.** Goal: see a home soon with minimum hassle. Needs: where, when (days, time of day). Available: prospect profile (area, beds), message slots. Missing: calendar, CRM, required questions. Decisions: missing slot → ask one; ready → read-back; changed preference → update. Validation: no clock times; confirmation only by button or clear "yes" when ready. Errors: write failure → "nothing was sent". Escalation: high intent → leasing follow-up recommended. Outcome: tour **request** saved, explicitly not a booking. **Simulated.**

**F6 Maintenance intake.** Goal: report a problem once and get it fixed. Needs: issue, room, entry permission (+ contact preference, visit window from the account). Missing: approved categories/fields, emergency list, troubleshooting guides, on-call. Decisions: emergency? repeat? routine? missing field? Validation: emergency regex runs before everything, for all audiences; risky DIY blocked in model output. Errors: unmatched resident → office note; guest → sign in. Escalation: emergency, repeat, frustration. Outcome: read-back → send. **Working with draft rules.**

**F7 Work orders.** Goal: know the request is really in. Needs: confirmed draft, verified identity. Missing: Yardi write, approval rules, change rules. Decisions: confirmed? identity matched? all fields? Validation: server-side draft only; identity re-checked; double submit returns "nothing waiting". Errors: save failure → explicit "nothing was sent". Escalation: changes/cancellations → staff. Outcome: reference number + "submitted for staff review". **Simulated.**

**F8 Status.** Goal: "where is my repair?" without calling. Needs: verified identity, open items. Missing: live status, timing rules, notifications. Decision: verified? frustrated? Validation: no timing; no entry windows. Errors: none on record → offer to report. Escalation: frustration or unverified. Outcome: list of open items + option to reach the office. **Read-only synthetic.**

**F9 Handoff.** Goal: reach the right person without repeating yourself. Needs: trigger, team, summary. Missing: routing approval, response times, transfer/on-call/queue. Decision: which team, priority. Validation: summary built from minimized context, never model free text (except a capped, redacted model reason). Errors: write failure → not claimed. Outcome: note in the (prototype) office queue with reference; emergencies saved immediately. **Simulated.** Customers are never told *when* someone will respond.

## 5. Renewal (no module in the source)

The source has no renewal module, but the sprint's eval case 5 and the brief require it. Renewal questions from residents route to the `renewal` workflow → F9 note to the leasing team with the contact preference on the account. No renewal terms, prices or offers are ever stated.
