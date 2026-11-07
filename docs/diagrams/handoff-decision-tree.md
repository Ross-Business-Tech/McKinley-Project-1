# Handoff decision tree

Who gets a note, at what priority, and how it's delivered. Built from `gates/rules.py`, `gates/policy.py`, `handoff.py` and `actions.py`. A model can **add** reasons to hand off; it can never remove one.

```mermaid
flowchart TD
  T["Turn classified by the rules gate<br/>(optional LLM/Jev gate may only add risk)"] --> E{"emergency_kind()?<br/>layer 1 keywords, layer 2 word combinations"}
  E -- "yes: building hazard" --> E1["Team: emergency maintenance<br/>Priority: urgent<br/>Saved immediately as DEMO-TASK (urgent)<br/>Customer told: 911 + emergency line first"]
  E -- "yes: person at risk<br/>(self-harm, medical, violence,<br/>poison, trapped)" --> E2["Team: property management<br/>Priority: urgent<br/>988 only for self-harm; 911 otherwise"]
  E1 --> RF{"Next message refuses to leave<br/>or says 'just send someone'?"}
  E2 --> RF
  RF -- yes --> RF1["Repeat the safety steps; say nobody has been sent<br/>(no second urgent note)"]
  E -- no --> PR{"possible_risk()?"}
  PR -- "distress" --> PR1["Calm care line with 988 above the reply<br/>No form, no urgent note"]
  PR -- "feeling unwell" --> PR2["Care line: call 911 if it gets worse<br/>Conversation continues"]
  PR -- no --> F{"fair_housing_or_legal, steering,<br/>sensitive_data_request,<br/>unverified_private_request,<br/>vendor?"}
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
