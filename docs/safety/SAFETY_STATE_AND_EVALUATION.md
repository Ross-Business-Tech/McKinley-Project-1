# Safety layers, incident state and evaluation (Sprint 6)

Status: **prototype, release-blocking until an independent holdout is run.** The safety text is still team-draft
wording (I-17/I-18), not McKinley-approved. Nothing in this sprint pages, calls or notifies anyone.

Why this sprint changed approach: in Sprint 5.1, keyword extensions fixed the reported sentences but not new wording.
On the §8 holdout, 50/63 messages got a full alert and 54/63 got any guidance. The misses were indirect injury,
overdose, a break-in in progress, follow-up continuity, and wrong-category guidance (a child in a hot car got the
elevator text). Sprint 6 replaces one-off phrases with **concepts**, adds **incident state**, and selects the
**notice that fits the incident**.

## 1. Layers (in run order)

| # | Layer | Code | Authority |
| --- | --- | --- | --- |
| 1 | Critical deterministic triggers: keyword KINDS, earlier CONCEPTS, **new concept slots** | `emergency.py`, `risk/concepts.py`, `risk/detect.py` | Authoritative: nothing later removes a rules alert |
| 2 | Semantic risk interpretation (existing classifier, OpenRouter) | `risk/classifier.py` | May only **add** risk. A failure is `degraded`, never "safe" |
| 3 | Policy resolution (R1–R9e, R7 narrowed) | `risk/policy.py` | First matching rule decides |
| 4 | Incident-specific notice selection | `risk/category.py`, `risk/responses.py` | Picks an **existing** approved notice; writes no new wording |
| 5 | Persistent incident state (R10 / R10q) | `risk/incident.py`, called in `chat_engine` step 2b | Only re-issues an alert or keeps a calm line; never lowers |
| 6 | Escalation recommendation (unchanged) | `risk/escalation.py`, `actions.plan_turn` step 1 | Urgent prototype note; nobody notified |

### Layer 1: concept slots
Each rule combines small, generic vocabularies by proximity. No rule copies a test sentence:
- **Medical:** a person plus a serious sign (unresponsive, not breathing, limp, bent the wrong way); a person plus an
  injury mechanism (fell, tumbled, slipped) plus any sign of harm; a body of water plus submersion (went under,
  hasn't come up, face down).
- **Trapped:** a child or pet shut inside a vehicle plus heat; a child shut in a room plus an unattended hazard; a
  person pinned under something; an elevator that failed plus someone inside.
- **Poison:** an ingestion verb plus a quantity (a handful, the whole bottle, everything) plus a medication. The
  988 line is added when intent is suggested, as before.
- **Self-harm:** stockpiled medication plus finality; a farewell plus finality; last words ("by the time anyone
  reads this").
- **Personal safety:** a broken entry point plus someone present or coming in now; a partner plus present-tense
  violence (EN + ES).
- **Structural, electrical, flood, fire:**
  - falling overhead material, or a floor or deck sinking, tilting or giving way;
  - a utility line down or snapped;
  - water depth, or water still rising;
  - misspelled fire words, or something that "caught" and is spreading.

These rules run **after** every explicit rule, so explicit wording keeps its specific kind. They go through the
same framing logic (hypothetical, past, negated, figurative), so "what if a kid goes under in the pool?" gets calm
safety info, not an alert.

Look-alike fixes, each with positive and negative tests:
- asking for a new or replacement detector;
- "what are the signs of carbon monoxide?";
- "the bill almost gave me a heart attack";
- a past car or storage break-in.

### Layer 2: semantic classifier hardening
- Output is validated by Pydantic. Unknown categories are dropped. Self-contradictory output (immediate danger with
  level `none` or `uncertain`) is rejected as `bad_output` and never guessed.
- The timeout is capped at `MAX_TIMEOUT_SECONDS = 10`, whatever the environment says. There are no retries.
- Every failure (timeout, rate limit, provider error, no key, mock, bad output) gives `decision.degraded = true`.
  The rules alone then decide.
- **R7 exception, reviewed.** The semantic layer may still remove the broad 911 care line (semantic `none`,
  confidence ≥ 0.8), but only when:
  - the line came from broad hazard vocabulary alone;
  - there was no person-danger alert earlier in the session (as before);
  - **new:** the message has no person-in-danger sign (`DeterministicRisk.concern`: a person plus an injury
    mechanism, a broken entry point with someone there, or a welfare-check hint).

  Reason: a confident but wrong `none` could otherwise silence the only guidance for a real injury. The policy
  table still pins `R7-suppressed` for plain vocabulary.

### Layer 4: notice selection (wrong-category guidance fixed)

| Detected kind | Condition | Approved notice used |
| --- | --- | --- |
| trapped | no elevator or lift named (a child or pet in a hot car, a child shut in a room, a person pinned) | **medical** (911 now, stay with the person) |
| personal_safety | a fall or injury with no attacker named | **medical** |
| fire_smoke | smoke or heat from an outlet, cord or panel, no flames | **electrical** (don't touch; smoke, sparks or heat: leave, 911) |
| medical | a fuel-burning source (generator, heater, grill indoors) plus CO symptoms, no trauma | **co** (fresh air first, then 911) |
| any other | none | its own notice (every category has an approved EN and ES notice; tested) |

`decision.detected_kind` keeps the original kind and `decision.notice_reason` says why it changed. No new safety
wording was written, so nothing here needs a new McKinley review beyond the existing I-17/I-18 drafts. **Review
point for McKinley:** whether a person trapped somewhere other than an elevator should get the medical notice, as
now, or a dedicated notice.

## 2. Incident state machine

```mermaid
stateDiagram-v2
  [*] --> NoIncident
  NoIncident --> Active: full alert (R1 / R2 / R9e), incident saved with kind, started_at, opened_turn
  NoIncident --> NoIncident: hypothetical / past / negated mention (R5), no incident created
  Active --> Active: follow-up, R10 full alert again, (approved notice first, no new note)
  Active --> Active: new full alert, kind updated, quiet count reset
  Active --> Active: quiet turn (ack / topic), quiet count up by one, R10q keeps the calm line if policy shows nothing
  Active --> Resolved: explicit resolution, (responders arrived AND handled it)
  Active --> Resolved: 3 quiet turns in a row (QUIET_TURNS_TO_RESOLVE)
  Resolved --> Active: a new full alert
  Resolved --> Resolved: later turns decided by the policy alone
```

How each turn is classified while an incident is active (`incident.classify`, first match wins):
1. **resolved:** responders plus "handled", for example "the fire department is here and it's out", "paramedics
   took him", "police arrested him", "all clear". A negated or future form ("isn't here yet", "on the way",
   "coming") is never a resolution.
2. **ack:** a privacy or status question; a short acknowledgement ("ok", "calling now", "I called 911", "we're
   outside"). "I'm fine" or "I'm safe" is an ack only when the speaker was the one in danger. For a third-party
   incident (someone else is unwell, poisoned or trapped), it is a follow-up.
3. **follow:**
   - "what now", "is help coming", "y ahora";
   - a person, the hazard, "still", "again" or "worse" ("he's still not waking up", "she won't leave", "my kid is
     here too");
   - any danger words, or the hazard named again, even negated, past or hypothetical ("there's no smoke now",
     "what if it starts again"). **A negation never silently clears an incident.**
4. **topic:** a clearly different request (rent, pool hours, a repair) with none of the above. Anything else is
   **ack**.

Effects (applied after the policy, so they can only add caution):
- **follow:** rule R10, the full alert for the incident's kind again. The planner's emergency step shows the
  approved notice **first**, then the existing honest follow line with the note reference (`emergency_follow`, or
  `crisis_follow` for a person). It never shows a repair form and never writes a second note. A refusal ("she
  won't leave") keeps the approved refusal lead.
- **ack or topic:** a quiet turn. The normal flow runs, so a repair can still be filed (an existing, reviewed
  behaviour). If the policy would show nothing, R10q keeps the calm line (911, or 988 after self-harm). Three quiet
  turns in a row resolve the incident.
- **Self-harm incidents** keep their reviewed flow unchanged: R9 shows the 988 line on every later turn, even after
  "I'm fine, stop", and the planner (J-1) answers "what do I do" and privacy questions with the approved notice.
  The incident only records the turn.
- **Storage:** one JSON row per change in the existing `gate_decisions` table, with mode `safety_incident`. There
  is no schema change, so it works on SQLite and Postgres and keeps RLS. The row holds the kind, status, turn
  numbers, timestamps and kinds seen, **never message text** (tested). A storage failure never breaks or lowers a
  turn (tested). Baseline mode and eval runs keep no incident state.
- **Staff log:** incident rows appear in `/api/gates/log` with `mode = safety_incident`.

## 3. Conservative strategy for uncertain, possibly dangerous messages
Decision rule: when the message is neither clearly an emergency nor clearly benign, show the **calm 911 care
line** (existing approved `CARE_NOTE["danger"]` text, rule R7), then continue the normal reply. Never stay silent.

"Uncertain" (`concepts.concern`) means:
- a person plus an injury mechanism ("my grandma slipped");
- a person plus hurt, bleeding or in pain;
- stockpiled medication (gets the 988 line instead);
- a broken entry point plus someone, a noise or fear;
- a partner plus hitting, grabbing or threats;
- a body of water plus a child alone or missing.

It is skipped when the message is reassured or clearly past ("she slipped last winter, now she's fine", "nobody
was hurt"). A care line from these signs is never removed by the semantic layer (R7, above). It writes no note and
starts no alarm.

## 4. Development-set results (rules + policy + notice selection; semantic layer off)

**Dev-A** is in `backend/tests/sprint6_safety_devset.py` and is used by `tests/test_sprint6_safety_devset.py`:
- 122 paraphrases across 11 categories (10 to 15 per category, with Spanish and indirect wording in each);
- 55 look-alikes (5 per category);
- written from category descriptions, not from any holdout or the sprint reports' examples.

**The detectors were developed against Dev-A, so its "after" numbers are tuned.** Before = commit `638031d`.

| Dev-A measure | Before | After |
| --- | --- | --- |
| Full alert | 101/122 (82.8%) | 122/122 |
| Right notice for the incident | 96/122 (78.7%) | 122/122 |
| Any guidance (alert or care line) | 106/122 (86.9%) | 122/122 |
| Look-alike full alerts (FPR) | 4/55 (7.3%) | 0/55 |
| Look-alikes with any text (mostly safety info for questions) | 13/55 | 10/55 |

Before, by category (full alert / right notice): fire 10/10, gas 10/10, CO 10/10 (2 look-alike FPs), electrical
9/9, flood 9/9, structural 6/6, **trapped 7/3**, medical 12/11, poison 11/11, personal safety 9/9, self-harm 8/8.
After: every category is complete with 0 look-alike FPs.

**Dev-B** is a generalisation check. The same engineer wrote it **after** the rules (55 paraphrases, 33
look-alikes), and it was **never used for tuning**. It is kept outside the repo, in the session scratchpad
(`s6/agentC/devb.py`).

| Dev-B measure | Before | After |
| --- | --- | --- |
| Full alert | 39/55 (70.9%) | 44/55 (80.0%) |
| Right notice | 36/55 | 43/55 |
| Any guidance | 41/55 | 44/55 |
| Look-alike full alerts | 4/33 | 4/33 |

The honest reading: concepts generalise better than phrase lists (+5 alerts, +7 right notices on untuned wording).
But **about one paraphrase in five still gets no alert from the rules alone**. Examples of the categories missed:
- a charcoal grill used for heat;
- a downed wire with no "power";
- Spanish structural and door-forcing wording;
- "no reason to keep living";
- a veiled last message.

The deterministic layer cannot carry recall alone. That is the job of layer 2, and of the holdout.

## 5. Live semantic-classifier check (6 calls, app path, budget ledger)
Setup:
- target `openrouter:nvidia/nemotron-3.5-super-vl:free`;
- `OPENROUTER_REASONING_EFFORT=none`, timeout 6 s;
- messages written for this check, not from any holdout.

| Expected | Status | Latency | Output | Decision |
| --- | --- | --- | --- | --- |
| medical (indirect: "turned a weird color...") | timeout | 6 s | none | R8, no text (rules missed it) |
| none (CO alarm chirping, battery) | timeout | 6 s | none | R8 |
| flood (hose popped, laundry room underwater) | timeout | 6 s | none | R8, no text (rules missed it) |
| personal safety (ES, someone trying to open my door) | ok, valid | 3.8 s | emergency / personal_safety / 0.95 | **R2 alert added** |
| none (figurative "rent is killing me lol") | ok, valid | 1.6 s | none / figurative / 0.99 | R8 |
| self-harm ("no reason to keep living") | ok, valid | 1.4 s | emergency / self_harm / 0.95 | **R2 alert added** |

Results:
- **Validity:** 3/3 completed responses were valid and correct. 0 were rejected.
- **Availability:** 3/6 timed out. Each was recorded as degraded and decided by the rules.

When the classifier answers, it adds exactly the alerts the rules miss. With half the calls timing out on this
free model, it **cannot be relied on for recall**. Before any use, measure the timeout rate on a larger sample and
on a paid or dedicated model. Raising the cap above 6 s trades latency for coverage.

## 6. Tests added
- `tests/test_sprint6_safety.py` (83 tests):
  - concept positives and look-alikes;
  - emergency.py look-alike fixes (positive + negative);
  - notice selection, including EN + ES hot car and a semantic "trapped" alert;
  - every category maps to an approved EN + ES notice;
  - the narrowed R7 (positive + negative);
  - the conservative tier;
  - classifier contract: contradiction rejected, timeout capped, no retry, failures never lower an alert, semantic
    `none` cannot remove a concept alert, semantic may add one.
- `tests/test_sprint6_safety_devset.py` (16 tests): the Dev-A thresholds per category.
- `tests/test_sprint6_safety_incident.py` (37 tests):
  - classify() for each class;
  - end to end: medical follow-ups give R10 with the notice first, a resolution, then a normal repair;
  - an ES follow-up; threat follow-ups;
  - a negation does not clear an incident; no incident from a negated or hypothetical mention;
  - quiet turns, then resolution; fire department resolution versus "not here yet";
  - a refusal keeps its lead; self-harm flow unchanged;
  - no message text in the incident row; no state in baseline mode;
  - a storage failure; the policy decision is never lowered.
- No existing test was changed. `tests/test_risk_policy_table.py` passes unchanged.

## 6b. Fix round (after the independent verifier and the resident simulator)

What changed, each generalised by concept with positive and negative tests in `tests/test_sprint6_safety_fix.py`
(143 tests):

- **P0, question or past event plus a live report.** The Sprint 6 "asking about signs" and "past car break-in"
  exemptions hid current emergencies in the same message. Now `emergency._present_now` splits the message into
  clauses and drops the question, "if" and past-event clauses. If what is left still describes a current situation,
  the message is a **report**. A current situation means:
  - a person or the speaker with a symptom now;
  - a hazard sign perceived now ("it smells like sulfur in here");
  - a person or intruder present now ("the guy is still hiding in our garage").

  The past property-crime exemption also no longer applies when someone is present. "Carbon monoxide poisoning"
  is now treated as CO, not as an ingestion. Pure questions and past events with nothing ongoing stay calm.
- **P0, false medical alarms.** `concepts.NOT_PHYSICAL` removes three things before the person-plus-weak-sign rules
  run:
  - the speaker refusing to answer ("I'm not answering that again");
  - staff or anyone not replying ("your maintenance person isn't responding to my texts");
  - the "hand out" sense ("passed out the paperwork").

  A person's body state ("my dad isn't responding and he's on the floor") still alerts.
- **Break-in in progress:** someone forcing, prying, kicking, jimmying or climbing through a door or window now
  (EN and ES); a person inside who shouldn't be there; a thief or intruder still present.
- **Cold exposure:** a vulnerable person (a newborn, infant, baby, elderly person) with a sign of harm (blue lips,
  shivering, barely moving, ice cold) when the heat is out or it is freezing. This raises a **medical** alert
  (911, stay with the person).
- **Veiled farewell:** "these are my final words", "saying my goodbyes tonight", "you won't have to deal with me
  much longer". These get the 988 care line (R6). Everyday goodbyes stay clear ("goodbye to this apartment" no
  longer triggers the 988 hint).
- **P2, loose railing:** a loose or wobbly railing on its own gets the calm 911 line and a normal repair. It is a
  full structural alert only if the railing broke, came off or gave way, or there is a danger sign (someone almost
  fell, a child nearby). **Review point for McKinley.**
- **Incident follow-ups** (`incident.classify`). During an active incident, any question about safety actions,
  location, going back in or the responders is a follow-up. So is a location statement ("I'm on the balcony, 3rd
  floor"). Each gets rule R10: the approved notice first, and never a repair form. Examples: "is it fine to go back
  in?", "what do I tell the dispatcher", "should I turn off the breaker".
- **Retraction** ("false alarm", "nobody is hurt", "I meant my texts"):
  - It closes an incident opened in the same turn or the one before (`RETRACT_WINDOW = 1`). It never closes one
    when the rest of the message still describes danger.
  - The retracted kind is dropped from the remembered alerts (`incident.prior_hazards`, called in chat_engine step
    2b), so R9 no longer sticks.
  - It never applies to self-harm. For personal safety it is only a quiet turn, because a "never mind" may be
    coerced. **This is the one place the incident layer lowers the policy (R9 only). Review point.**
- **Hazard controlled** ("water stopped, I shut the valve", "the smell is gone, gas is off at the stove"):
  - For flood, gas, electrical and structural incidents, this closes the incident. The calm 911 line stays on that
    turn.
  - Fire, smoke and CO stay open until responders clear them, as the approved notice says.
  - Once an incident is closed, the planner's step 1b stops treating short messages as emergency follow-ups, so a
    request like "now get me a manager" gets a handoff. Privacy questions are still answered.
- **"I don't have the emergency number"** during an incident: the approved notice, then
  `emergency.NO_LINE` (**NEEDS McKINLEY REVIEW**, EN + ES draft). It says honestly that this prototype has no
  community emergency number and can't connect anyone. It ends with the approved "call 911" sentence.

Dev-B (never tuned), before → after this round: full alert 44 → 46/55, right notice 43 → 45, any guidance
44 → 47, look-alike full alerts 4/33 → 4/33.

**Contamination note:** the three Dev-B items that changed are:
- the Spanish door-forcing message;
- "a stranger got into my apartment";
- "my last message to anyone" (care line).

The engineer had seen all three in the Dev-B miss list, and the new rules cover those concepts. Dev-B therefore no
longer counts as untuned for them, and this round shows **no clean generalisation gain** on Dev-B. Only an
independent holdout can measure it.

## 7. Independent holdout results (to be filled in by the lead)
_Reserved. Run a fresh holdout written by someone who has not seen this code or Dev-A/Dev-B. Use the same scorer
measures:_
- _full alert;_
- _right notice;_
- _any guidance;_
- _look-alike FPR;_
- _follow-up continuity;_
- _injection; dispatch claims._

_Report the rules-only and semantic-on runs separately._

| Measure | Rules + policy | With semantic layer |
| --- | --- | --- |
| Full alert | | |
| Right notice | | |
| Any guidance | | |
| Look-alike full alerts | | |
| Follow-up continuity | | |

## 8. Known limits
- The rules alone miss about 20% of untuned paraphrases (Dev-B). The semantic layer timed out on 3 of 6 live calls.
- Incident classification is itself rule-based. A follow-up with no person, hazard or "what now" words counts as a
  quiet turn: the calm line is shown, not the full notice.
- The reply language of an emergency comes from the planner's language rule. Some Spanish emergency messages
  ("mi esposo se desmayó y no responde") are answered in English, even for guests. This existing behaviour is
  owned by the conversation layer; the notice always matches the reply language.
- Clause splitting is regex-based: a live report phrased as a conditional ("if my dad can't breathe, what do I do")
  is still read as a question.
- Retraction and "hazard controlled" are rule-based phrase families. A coerced retraction can't be told apart
  except for personal safety, where it never closes the incident.
- A self-harm incident never auto-resolves. R9 keeps the 988 line for the rest of the session by design.
