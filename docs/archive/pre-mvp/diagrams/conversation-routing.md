# Conversation routing

Two views of `actions.plan_turn`: the order of checks (section 1) and who receives a note (section 2).

## 1. Order of checks (F1–F9 as implemented)

The order of checks in `actions.plan_turn`. Earlier checks win. Every branch ends in either an answer, one question, a read-back card the person must confirm, or a note for the office.

```mermaid
flowchart TD
  M["Message + trusted identity<br/>(demo sign-in)"] --> O{"SMS and an<br/>opt-out keyword?"}
  O -- yes --> OO["F2: confirm opt-out<br/>(no model call)"]
  O -- no --> EM{"Safety policy: full alert?<br/>(risk/: rules, window, optional semantic)"}
  EM -- yes --> EE["F6+F9: 911 / leave / emergency line first<br/>urgent note saved once (prototype queue)<br/>refusing to leave: steps repeated"]
  EM -- no --> DS{"Policy care: distress?"}
  DS -- yes --> DSA["Calm reply + 988 care line<br/>no form; staff check-in recommended"]
  DS -- no --> CF{"Earlier self-harm / personal-safety /<br/>medical alert in this session?"}
  CF -- "short follow-up" --> CFA["Privacy + status of the urgent note<br/>(their words withheld, nobody notified);<br/>policy care line still shown (988 after self-harm)"]
  CF -- no --> SI{"Policy: safety info<br/>(hypothetical / past hazard)?"}
  SI -- yes --> SIA["Steps shown calmly;<br/>'Is it happening now?'"]
  SI -- no --> OP{"Not the account holder? Pasted instructions?<br/>Lockout? 'Did that go in / just notes?'"}
  OP -- yes --> OPA["No account details / refuse instructions /<br/>after-hours line / what this chat actually saved"]
  OP -- no --> AS{"Question about something<br/>already sent, or 'send it' again?"}
  AS -- yes --> ASA["Plain answer with the reference:<br/>nobody notified, no time set"]
  AS -- no --> DA{"Card open? classify the turn<br/>(app/dialogue.py TurnAct: ANSWER, CORRECTION,<br/>NEW_DETAIL, QUESTION, CANCEL, RESTORE, META)"}
  DA -- "QUESTION (who sees it, cost, Send,<br/>status, renewal, number…)" --> DAQ["Honest answer; card re-shown unchanged<br/>(never written into a field)"]
  DA -- "bare yes/ok/sure on a ready card" --> DAY["'Tap Send…' (only Send or 'send it' saves)"]
  DA -- "ANSWER / CORRECTION / NEW_DETAIL /<br/>CANCEL / RESTORE / no card" --> LF{"Lost or frustrated with the chat,<br/>or 2 unproductive turns in a row?"}
  LF -- "first time, card open" --> LFA["One apology + the single next step<br/>+ 'Talk to a person'"]
  LF -- "again / no card" --> H
  LF -- no --> R{"Card ready and<br/>person says yes / no?"}
  R -- yes --> RC["F7/F5/F9: write prototype record<br/>reference + status"]
  R -- no --> RD["Not sent; kept once so<br/>'send it after all' restores it"]
  R -- "neither" --> L{"Script without<br/>approved templates?"}
  L -- yes --> H
  L -- no --> S{"Vendor, steering, sensitive data,<br/>accommodation/legal, unverified status,<br/>asks for a person or the office,<br/>contact-preference change, change/cancel request?<br/>(policy topic: 'not approved yet' + Ask the office;<br/>unsure twice: offer the office, no note)"}
  S -- yes --> H["F9: note for the office<br/>(read-back, person confirms)"]
  S -- "claims a prior decision" --> PC["Not agreed with; note for staff to check"]
  S -- no --> ER{"Refers to an existing request?<br/>('the one for the sink leak')"}
  ER -- yes --> ERA["Answer about that request<br/>(reference, status, nobody notified)"]
  ER -- no --> ST{"Matched resident<br/>asks for status?"}
  ST -- yes --> STL["F8: open items, no timing<br/>(+ office note if frustrated)"]
  ST -- no --> MT{"Maintenance, or answering<br/>an open repair card?"}
  MT -- "guest" --> MG["Ask to sign in;<br/>911 if dangerous"]
  MT -- "unmatched resident" --> H
  MT -- "matched resident" --> MI["F6: issue, room, entry permission<br/>(contact + visit window from account)<br/>one question at a time; vague issue: ask what first<br/>corrections replace, not append ('the hall one')<br/>several problems: one request each, next offered after Send"]
  MI --> MR{"All fields?"}
  MR -- no --> MI
  MR -- yes --> MC["F7 read-back card:<br/>Send repair request"]
  MT -- no --> TR{"Prospect or guest asks to tour,<br/>or answers an open tour card?"}
  TR -- yes --> TI["F5: community/city, days, time of day<br/>changes overwrite earlier answers; 'not Saturday' removes it<br/>'no tour' is respected"]
  TI --> TC["Read-back card:<br/>Send tour request (not a booking)"]
  TR -- no --> RN{"Renewal from<br/>a resident?"}
  RN -- yes --> H
  RN -- no --> FQ{"FAQ topic?"}
  FQ -- yes --> FA["F4: approved answer, or<br/>'not approved yet' / 'no live prices'"]
  FQ -- no --> GH{"Gate requires a person?<br/>(frustration, owed follow-up, voucher,<br/>lease or billing)"}
  GH -- yes --> H
  GH -- no --> GQ["F3: welcome / one clarifying question<br/>+ suggested next steps"]
```

Not shown because they're not built: F1 voice (rejected at the API), real verification (I-10), live calendar slots (D-09), notifications (D-13).

## 2. Handoff: who gets a note, at what priority

Who gets a note, at what priority, and how it's delivered. Built from `risk/policy.py`, `risk/escalation.py`, `gates/rules.py`, `gates/policy.py`, `handoff.py` and `actions.py`. A model can **add** reasons to hand off; it can never remove one.

```mermaid
flowchart TD
  T["Turn classified by the safety policy first (risk/: rules + optional semantic, R1-R9),<br/>then the rules gate (optional LLM/Jev gate may only add risk)"] --> E{"Policy: full alert?<br/>(R1 rules or window, R2 semantic)"}
  E -- "yes: building hazard" --> E1["Team: emergency maintenance<br/>Priority: urgent<br/>Saved immediately as DEMO-TASK (urgent)<br/>Customer told: 911 + emergency line first"]
  E -- "yes: person at risk<br/>(self-harm, medical, violence,<br/>poison, trapped)" --> E2["Team: property management<br/>Priority: urgent<br/>988 only for self-harm; 911 otherwise"]
  E1 --> RF{"Next message refuses to leave<br/>or says 'just send someone'?"}
  E2 --> RF
  RF -- yes --> RF1["Repeat the safety steps; say nobody has been sent<br/>(no second urgent note)"]
  E -- no --> PR{"Policy: care line / safety info?"}
  PR -- "distress (R3/R4/R6) or<br/>earlier self-harm alert (R9)" --> PR1["Calm care line with 988 above the reply<br/>No form, no urgent note<br/>Handoff RECOMMENDED: management, high (not sent)"]
  PR -- "feeling unwell / danger words" --> PR2["Care line: 911 if worse / if anyone is in danger<br/>Conversation continues"]
  PR -- "hypothetical or past hazard (R5)" --> PR3["Safety info: same steps, calm, no note<br/>'Is it happening now?' chips"]
  PR -- no --> LK{"Lockout? Claims something was already decided?<br/>Rent withholding / legal? Not the account holder?"}
  LK -- "lockout" --> LK1["After-hours line, no repair form<br/>Handoff recommended: maintenance, high"]
  LK -- "'manager waived it', 'you approved'" --> LK2["Not agreed with; note for staff to check<br/>(financial_or_lease)"]
  LK -- "withholding rent / legal" --> LK3["Manager note; nothing advised or decided"]
  LK -- "someone else's account" --> LK4["No account details shared"]
  LK -- no --> F{"fair_housing_or_legal, steering,<br/>sensitive_data_request,<br/>unverified_private_request,<br/>vendor?"}
  F -- yes --> F1["Team: property management<br/>Priority: normal"]
  F -- no --> MT{"Intent maintenance?"}
  MT -- yes --> RP{"Repeat issue AND<br/>follow-up still owed?"}
  RP -- yes --> RP1["Team: property management<br/>Priority: high (service recovery)"]
  RP -- no --> RP2["Team: maintenance<br/>Priority: high if repeat or urgent wording"]
  MT -- no --> LR{"Leasing or renewal?"}
  LR -- yes --> L1["Team: leasing<br/>(high-intent prospects: leasing follow-up)"]
  LR -- no --> FI{"financial_or_lease?"}
  FI -- yes --> A1["Team: accounting"]
  FI -- no --> D1["Prospect: leasing<br/>Others: property management"]

  F1 --> C
  RP1 --> C
  RP2 --> C
  L1 --> C
  A1 --> C
  D1 --> C
  C["Customer sees 'Note for the office' read-back<br/>(topic, what they said, account, contact preference)"] --> K{"Person presses<br/>Send note to the office?"}
  K -- yes --> Q["Saved as DEMO-TASK in the prototype queue<br/>No one is paged, called or notified"]
  K -- no --> N["Not sent. Kept once: 'send it after all' restores it"]
  Q --> AS{"Later: 'when will they call?',<br/>'so a tech is coming?', 'send it'"}
  AS --> AS1["Plain answer with the reference:<br/>nobody notified, no time set, no new note"]
  T --> U{"Not understood twice?"}
  U -- yes --> U1["Offer the office (buttons). No note is filed<br/>until the person asks; a note made from a button<br/>carries their last messages, not the button text"]
```

Always-human flags (`gates/base.ALWAYS_HUMAN_FLAGS`): emergency_hazard, human_requested, sensitive_data_request, fair_housing_or_legal, financial_or_lease, voucher_eligibility, unverified_private_request, context_repeat_issue, context_open_commitment, repeat_with_history, repeated_low_confidence, complaint_or_frustration.

Routing (I-26) and response times (I-05) are team drafts. Customers are never promised when someone will respond.
