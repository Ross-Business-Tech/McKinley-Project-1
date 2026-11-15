# Workflow traceability: McKinley AI Agent Flow → prototype

Source: the team's "McKinley AI Agent Flow" checklist (kept locally in `docs/references/`, not in the public repository; ask the project owner for a copy) (nine function modules, 27 instruction inputs I-01…I-27, 14 data inputs D-01…D-14). Earlier analysis and the team's MVP recommendations: [`WORKFLOW_REVIEW.md`](source-review.md). Updated for the simplified MVP (`mvp-reset`); the pre-MVP design is archived in [../archive/pre-mvp/](../archive/pre-mvp/).

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
| F1 | Phone and voice support | **Unavailable** | Nothing voice-specific. `channel="voice"` is rejected (422). The same conversation logic is exercised over web chat. | `models.py` `Channel` | none since the MVP reset (the pre-MVP channel test was removed) | Telephony + STT/TTS; I-01 disclosure + recording consent (legal); I-02, I-03, I-04; D-01–D-03 |
| F2 | SMS and email | **Unavailable since the MVP reset** | `channel` = `sms` / `email` is still accepted and recorded, but no longer changes the reply: the pre-MVP channel rules (I-07 draft) and the deterministic SMS opt-out (I-06 draft) were removed with the planner. Nothing is sent. | `models.py` `Channel` (pre-MVP: `actions.py` step 0, `chat_engine.CHANNEL_RULES`, `intake.is_sms_opt_out`, all removed) | none | SMS/email gateways; opt-in consent records; approved opt-out wording (I-06), to be rebuilt; D-04 thread matching |
| F3 | Caller type classification | **Working (prototype identity)** | Audience = trusted demo sign-in, never message text. Matched resident → resident permissions; anyone else → public info + office note (a visitor's repair becomes a note that needs community and unit). Vendors and "who are you?" are now handled by the model's wording only (`assistant.RULES`), not by a deterministic rule (I-09 draft). | `auth.derive_principal`, `personas.build_context`, `chat_engine._apply_proposal` (guest repair → note), `guardrails.denied` | `test_authorization.py`, `tests/test_acceptance.py` (`test_d_*`, `test_g_*`) | Real verification (I-10) and permission matrix (I-11); vendor list (D-06). **The demo sign-in is not authentication** (see §4). |
| F4 | Property and leasing FAQs | **Working for approved entries, Pending otherwise** | Topic list (I-12 draft) in `knowledge_base.json`. Only `status: approved` entries are given to the model as facts (housing vouchers); every other topic is passed as "no approved answer; say so and offer a note". Prices/availability: "can't see live data". Steering questions are now left to the model under `assistant.RULES` (no deterministic redirect since the MVP reset; I-13 draft). | `app/content/knowledge_base.json`, `guardrails.property_facts`, `safety.output_checks` | none dedicated since the MVP reset (pre-MVP FAQ test removed) | D-07 approved per-property knowledge base; D-08 live pricing/availability; I-13 legal approval; I-14 approval |
| F5 | Tour scheduling | **Simulated + Draft** | The model collects community/city, preferred days, time of day (+ beds / move-in if given); preferences can change mid-way (`update`); read-back card; saves `DEMO-TOUR-…` with status "Saved in demo" only through Send or an explicit typed send. Nothing reaches the leasing team; never confirms a booking. | `tasks.REQUIRED["tour_request"]`, `tasks.apply`, `tasks.confirm` | `tests/test_acceptance.py` (`test_e_*`) | D-09 tour calendar; D-10 CRM lead record; I-15 required tour questions/tour types; I-16 confirmation + reminder (consent) |
| F6 | Maintenance request intake | **Working + Draft rules; emergency detection NOT production ready**. An open request for the same object on the resident's own record is attached to the card (`history`); the earlier repair task waits, unsent, during an emergency and comes back afterwards. Sprint 8 note (pre-MVP): fresh holdout 64.5% full alert, release-blocking misses: [safety-evaluation](../safety/safety-evaluation.md) | Emergency check first, for every audience (I-17 draft list), fixed safety text (I-18 draft), no model call. Verified residents: issue, room, entry permission, asked one at a time by the model; repeat issues acknowledged from the resident's own record. Quick-fix tips (I-20) were removed in the MVP reset. | `app/risk/`, `app/emergency.py`, `tasks.pause_for_emergency`, `tasks.REQUIRED["maintenance_request"]`, `chat_engine._open_related` | `tests/test_acceptance.py` (`test_a_*`, `test_b_*`), `test_safety_pipeline.py`, `test_safety_detection.py` | I-17/I-18/I-20 McKinley maintenance approval; I-19 categories and fields; D-03 on-call |
| F7 | Create / update work orders | **Simulated** | Confirmed request → `DEMO-WO-…` with status "Saved in demo" (the record's code stays `submitted_for_review`, the conservative default for I-21). A repair needs a verified resident (`NOT_AUTHORIZED` otherwise); a second record for the same repair needs the person to say it is a different problem. Saving twice returns the same record. Failed writes say "nothing was sent". | `tasks.confirm`, `api/actions.py`, `db.add_record` | `tests/test_acceptance.py` (`test_e_*`), `test_authorization.py` | D-11 Yardi write access; I-21 approval rules; D-12 approvers; I-22 templates (draft in `tasks.CONFIRMED`); I-23 timing; I-24 change rules |
| F8 | Request status lookup | **Working (read-only, synthetic) / Simulated** | Matched residents see open items from synthetic history + their own prototype requests and office notes: reference, short title, status, opened date. No entry windows, no notes, **no timing** (I-23 missing). Unverified → prototype records of this session only. | `tasks.my_requests` (shown when the model sets `show_my_requests`) | `tests/test_acceptance.py` (`test_d_own_status_still_works`), `test_authorization.py` | D-11 live status; I-22/I-23; D-13 notifications with consent + quiet hours |
| F9 | Human handoff and escalation | **Simulated + Draft** | Handoff recommendation (team, priority, reasons) when the model names a team or safety needs a person; the customer sees a read-back "Note for the office" and presses Send; saved as `DEMO-TASK-…`, carrying what they said earlier (`earlier`) and, for a verified resident, their own related history. Emergencies are saved immediately as one urgent note per incident. Staff see a "not sent / prototype queue" delivery note. | `chat_engine.run_turn` (handoff), `chat_engine._apply_proposal`, `tasks.save_urgent_note`, `risk/escalation.py` | `tests/test_acceptance.py` (`test_f_*`), `test_safety_pipeline.py` | I-25 trigger list approval; I-26 routing table; I-27 summary review; I-05 response times; D-01/D-02/D-03 transfer + on-call; D-14 a real monitored queue |

Global handoff triggers from the source ("any step"). Since the MVP reset only the emergency and privacy triggers
are deterministic; the others are decided by the one conversation call (`assistant.RULES`: `handoff.team`, a
`staff_handoff` card) and are only evaluated live. The pre-MVP flag-based triggers (`ALWAYS_HUMAN_FLAGS`,
`intake.is_*`) were removed with the decision gate.

| Trigger | Implementation | Test |
| --- | --- | --- |
| Emergency | `app/risk/` + `app/emergency.py` → fixed safety text (no model) → one urgent note per incident (`tasks.save_urgent_note`) | `test_safety_pipeline.py`, `test_safety_detection.py`, `tests/test_acceptance.py` (`test_b_*`) |
| Asks for a person | model: `staff_handoff` card / `handoff.team` | `tests/test_acceptance.py` (`test_f_*`, mock only) |
| Complaint or upset caller | model: `staff_handoff` (named in `assistant.RULES`) | live only |
| Legal, billing or rent dispute | model: answer what it can, offer a note | live only |
| Fair Housing sensitive | model under `assistant.RULES`; no deterministic steering check since the MVP reset | live only |
| AI unsure twice | removed with the decision gate (`repeated_low_confidence`); a failed model call gets a fixed "say it another way" line | none |
| Vendor contact | model wording only; no vendor data is ever available | live only |
| Unverified caller asking for private info | `guardrails.denied` (before the model) + scoped store | `tests/test_acceptance.py` (`test_d_*`), `test_authorization.py` |

## 2. Instruction inputs (I-01–I-27)

| ID | What it is | Status | Where | Needs |
| --- | --- | --- | --- | --- |
| I-01 | Greeting + AI disclosure | Draft (web chat greeting): "I'm McKinley's automated assistant, not a person" (true for the mock and for a live model; replaced "I'm an AI" in Sprint 4) | `frontend/src/lib/customer.ts` `greeting()` | McKinley + legal; recording consent for voice |
| I-02 | When to transfer a call | Unavailable (voice) | — | Voice channel |
| I-03 | Voice reply style | Unavailable | — | Voice channel |
| I-04 | End-of-call summary + SMS confirmation | Unavailable | — | Voice + texting consent |
| I-05 | Response-time promises | **Not supplied → no times promised** | `safety.output_checks` `no_invented_time`; `assistant.RULES` forbids promising follow-ups | McKinley |
| I-06 | SMS opt-out keywords + consent | Removed in the MVP reset (was a draft: `intake.SMS_OPT_OUT`) | — | McKinley compliance + legal (add opt-in) |
| I-07 | SMS/email tone, length, signature | Removed in the MVP reset (was a draft: `chat_engine.CHANNEL_RULES`) | — | McKinley approval |
| I-08 | Topic and status tags | Draft | task kinds (`tasks.FIELDS`), handoff teams (`tasks.TEAM`), `functions` on every response | Team |
| I-09 | "Who are you?" question | Draft, model-led since the MVP reset (no fixed template) | `assistant.RULES` | Team |
| I-10 | Resident verification rules | **Not supplied** | Demo sign-in only (`personas.build_context`). Sprint 2: staff and records routes are loopback-only unless `STAFF_API_TOKEN` is set (`api/staff_guard.py`); a demo boundary, not authentication. Sprint 3: requests carrying any proxy-forwarding header are never treated as local; "this is someone else's account" gets no account details. Identity is still client-asserted (`persona_id`): **production blocker** | McKinley + legal |
| I-11 | Permission matrix | Draft (conservative) | `auth.derive_principal` + `ScopedStore`; `tasks.confirm` (repairs need a verified resident); `chat_engine._apply_proposal` (a visitor's repair becomes an office note): matched resident → own requests/status; everyone else → public info + office note | McKinley |
| I-12 | FAQ topic list | Draft | `app/content/knowledge_base.json` | Team |
| I-13 | Fair Housing topics + approved response | Draft; model-led since the MVP reset (the deterministic steering redirect and accommodation templates were removed) | `assistant.RULES`; `safety` `fair_housing_or_legal` signals are not used in the turn | McKinley legal |
| I-14 | Answer rules: approved info only | Enforced | `knowledge_base.json` `status`, `output_checks` price/offer/time | McKinley approval |
| I-15 | Required tour questions + tour types | Draft minimum (area, days, time of day) | `tasks.REQUIRED["tour_request"]` | McKinley leasing |
| I-16 | Tour confirmation + reminder templates | Draft confirmation only; no reminders | `tasks.CONFIRMED["tour_request"]` | Team + consent |
| I-17 | Emergency definition list | Draft, 11 hazard kinds: gas, CO, fire/smoke, electrical, flood, structural, personal safety, medical, poisoning, entrapment, self-harm; typo-, spacing- and multi-language-tolerant. Sprint 2: second layer that reads word combinations (person + unresponsive, substance + ingestion, symptoms + heat source, threat actor + act, means + intent); a third "possible risk" tier adds a calm care line (988 for distress, 911-if-worse when unwell) without an urgent note. Sprint 3: layered pipeline in `app/risk/` (rules with framing / negation / conversation window → optional semantic LLM classifier → explicit policy R1–R9 → approved text → escalation recommendation); hypothetical / past mentions get calm safety info; the semantic layer never removes a rules alert (it may drop only the broad 911 care line, R7) and is **not live-verified** (no key). Fresh independent holdout: 64.5% full alert / 78.5% any guidance, release-blocking misses remain (`docs/safety/safety-evaluation.md`). Still a deterministic floor, not a guarantee | `app/risk/*`, `app/emergency.py` `KINDS`, `CONCEPTS`, `scan`, `possible_risk`, used by `chat_engine` part B (safety) | McKinley maintenance + risk/legal |
| I-18 | Safety instructions per emergency | Draft text per hazard (EN + draft ES); `tel:911` / `tel:988` in the UI. Sprint 3: selected by `risk/responses.py` from the policy decision; 988 added to possible deliberate overdoses; gas/CO button reads "Get outside, then call 911"; a calm care line persists after "I'm fine, stop" following a person-danger alert | `app/emergency.py` `NOTICE`, `risk/responses.py`, `CustomerApp` alert | McKinley maintenance + risk/legal; fluent review of Spanish |
| I-19 | Maintenance categories + intake fields | Draft minimum (issue, room, entry permission); an open related request from the resident's own record on the card (`history`) | `tasks.REQUIRED["maintenance_request"]`, `chat_engine._open_related` (the pre-MVP `maintenance_history.py` repeat-history record was removed) | McKinley maintenance |
| I-20 | Approved self-troubleshooting | **Removed in the MVP reset**: the draft quick-fix tips (never approved; local `demo_drafts` only) are no longer served. Pre-MVP design: [QUICKFIX_DRAFT_KB.md](../archive/pre-mvp/workflows/QUICKFIX_DRAFT_KB.md) | — (`safety.output_checks` `no_risky_diy` still blocks risky DIY in model replies) | McKinley maintenance |
| I-21 | Which requests need staff sign-off | **Not supplied → all reviewed** | record status `submitted_for_review` | McKinley |
| I-22 | Work-order notification templates | Draft ("saved in demo" only) | `tasks.CONFIRMED` | Team |
| I-23 | Target timing + overdue threshold | **Not supplied → no timing, no "overdue"** | `tasks.my_requests` (no timing fields); `no_invented_time` | McKinley maintenance |
| I-24 | What residents may change/cancel | **Not supplied → staff handle all changes** to saved requests; an unsent card can be changed or cancelled (`tasks.apply`) | `assistant.RULES` → `staff_handoff` | McKinley maintenance |
| I-25 | Handoff trigger list | Draft (table above) | `assistant.RULES`, `guardrails.denied`, `app/risk/` | McKinley approval |
| I-26 | Routing table: issue → team | Draft | model's `handoff.team`, limited to `tasks.TEAM` in `chat_engine.run_turn`; emergencies → `emergency_maintenance` / `management` | McKinley must confirm (renewal, accommodation, vendor routes) |
| I-27 | Handoff summary format | Draft | `tasks` `staff_handoff` fields (topic, message, earlier, history) + customer-visible card | Staff review |

## 3. Data inputs (D-01–D-14)

| ID | What it is | Status | Where | Needs |
| --- | --- | --- | --- | --- |
| D-01 | Office hours per property | Pending (FAQ says not approved) | `knowledge_base.json` `office_hours` | McKinley |
| D-02 | Staff transfer numbers | Unavailable (no numbers shown, ever) | — | McKinley (fictional for demo only) |
| D-03 | On-call schedule | Unavailable; emergency text says "call your community's emergency maintenance line" | `app/emergency.py` `NOTICE` | McKinley |
| D-04 | Contact records | Synthetic workbook; **never sent to the model or UI** | `context.NEVER_FORWARDED` | Yardi |
| D-05 | Resident + unit records | Synthetic workbook (20 residents) via allowlisted context | `context.build_resident_context` | Yardi |
| D-06 | Vendor list | Unavailable; vendors are given no data (no deterministic vendor detection since the MVP reset) | — | Yardi |
| D-07 | Approved knowledge base | Structure ready; 1 approved entry | `knowledge_base.json` | McKinley documents |
| D-08 | Live availability + pricing | Unavailable; never quoted | `knowledge_base.json` `live_data_unavailable`, `no_invented_price` | Yardi |
| D-09 | Tour calendar | Unavailable; requests only, no slots | — | McKinley |
| D-10 | Lead record fields | Simulated (tour request record fields) | `prototype_records` kind `tour_request` | Yardi CRM |
| D-11 | Work-order system | Simulated (prototype store) + read-only synthetic history | `db.add_record`, `tasks.my_requests` | Yardi |
| D-12 | Approver list | Unavailable | — | McKinley |
| D-13 | Contact preferences | Synthetic (`preferred_contact`, contact clauses of staff notes) in the allowlisted context; no notifications sent | `context.contact_note_clauses` | Yardi + quiet hours/consent |
| D-14 | Staff task queue | Simulated (prototype store, staff console "Saved requests") — **not monitored** | `prototype_records` kind `staff_handoff` | Team for prototype; real queue later |

## 4. Per-function analysis

For each module: user goal · required information · data available / missing · decision points · validation · error states · escalation · user-facing outcome · real/simulated.

**F1 Phone and voice.** Goal: get help by calling. Needs speech-to-text and transfer. Available: nothing voice-related; missing D-01–D-03, I-01–I-04. Decisions: transfer? (I-02). Validation/errors: misheard twice. Escalation: always available by transfer. Outcome now: not offered. **Unavailable.**

**F2 SMS and email.** Goal: ask by text/email without an app. Needs: channel, sender match (D-04), opt-out. Available: the `channel` field only (the draft channel rules and opt-out keywords were removed in the MVP reset). Missing: gateways, consent records, opt-out handling. Errors: none sent. Escalation: same rules as chat. Outcome: same replies as web chat. **Unavailable.**

**F3 Caller type.** Goal (business): give each person the right permissions. Needs: trusted identity. Available: demo sign-in, synthetic records. Missing: real verification (I-10), permission matrix (I-11), vendor list. Decision: resident matched? otherwise public info + office note (vendor and "who are you?" wording is left to the model). Validation: identity is never read from message text; "I'm Marisol in 12B" unlocks nothing. Errors: no record → office note. Escalation: unverified + private info. Outcome: correct permissions, or a note. **Working for the demo; real authentication is a production blocker.** In this prototype the browser sends `persona_id`; a deployment must bind identity to a signed-in session server-side.

**F4 FAQs.** Goal: quick, accurate answers before deciding to tour. Needs: approved per-property facts. Available: one approved fact. Missing: D-07, D-08, I-13 approval. Decision: approved entry? live data? steering? Validation: price/offer/time checks on every model reply. Errors: no approved answer → say so + leasing. Escalation: voucher, accommodation, steering (model-led since the MVP reset). Outcome: honest answer + next step (tour or leasing). **Working but thin until McKinley supplies content.**

**F5 Tours.** Goal: see a home soon with minimum hassle. Needs: where, when (days, time of day). Available: prospect profile (area, beds), message slots. Missing: calendar, CRM, required questions. Decisions (model-proposed, validated by `app/tasks.py`): missing slot → ask one; ready → read-back; changed preference → update. Validation: no clock times; saving only by the Send button or an explicit typed "send it" (a bare "yes" never saves). Errors: write failure → "nothing was sent". Escalation: high intent → leasing follow-up recommended. Outcome: tour **request** saved, explicitly not a booking. **Simulated.**

**F6 Maintenance intake.** Goal: report a problem once and get it fixed. Needs: issue, room, entry permission. Missing: approved categories/fields, emergency list, troubleshooting guides, on-call. Decisions: emergency (deterministic, part B)? repeat? missing field (model)? Validation: the safety pipeline runs before everything, for all audiences; risky DIY blocked in model output. Errors: unmatched resident or guest → office note that needs community and unit. Escalation: emergency, repeat, frustration. Outcome: read-back → send. **Working with draft rules.**

**F7 Work orders.** Goal: know the request is really in. Needs: confirmed draft, verified identity. Missing: Yardi write, approval rules, change rules. Decisions: confirmed? identity matched? all fields? Validation: server-side draft only; identity re-checked; a second Send returns the same record (`ALREADY_SAVED`). Errors: save failure → explicit "nothing was sent". Escalation: changes/cancellations → staff. Outcome: reference number + "submitted for staff review". **Simulated.**

**F8 Status.** Goal: "where is my repair?" without calling. Needs: verified identity, open items. Missing: live status, timing rules, notifications. Decision: verified? Validation: no timing; no entry windows. Errors: none on record → offer to report. Escalation: the model can offer a note. Outcome: list of open items + option to reach the office. **Read-only synthetic.**

**F9 Handoff.** Goal: reach the right person without repeating yourself. Needs: trigger, team, summary. Missing: routing approval, response times, transfer/on-call/queue. Decision: which team, priority. Validation: the note holds what the person said and backend-built history lines from their own record; the model never writes that history. Errors: write failure → not claimed. Outcome: note in the (prototype) office queue with reference; emergencies saved immediately, one per incident. **Simulated.** Customers are never told *when* someone will respond.

## 5. Renewal (no module in the source)

The source has no renewal module, but the sprint's eval case 5 and the brief require it. Renewal questions from residents get the allowlisted renewal status (topic-gated, `context.py`) and, when they accept or ask for a person, an F9 note (model-led since the MVP reset; the pre-MVP `renewal` workflow was removed). No renewal terms, prices or offers are ever stated.
