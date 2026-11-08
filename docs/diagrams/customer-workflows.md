# Customer workflows (F1–F9 as implemented)

The order of checks in `actions.plan_turn`. Earlier checks win. Every branch ends in either an answer, one question, a read-back card the person must confirm, or a note for the office.

```mermaid
flowchart TD
  M["Message + trusted identity<br/>(demo sign-in)"] --> O{"SMS and an<br/>opt-out keyword?"}
  O -- yes --> OO["F2: confirm opt-out<br/>(no model call)"]
  O -- no --> EM{"Safety policy: full alert?<br/>(risk/: rules, window, optional semantic)"}
  EM -- yes --> EE["F6+F9: 911 / leave / emergency line first<br/>urgent note saved once (prototype queue)<br/>refusing to leave: steps repeated"]
  EM -- no --> DS{"Policy care: distress?"}
  DS -- yes --> DSA["Calm reply + 988 care line<br/>no form; staff check-in recommended"]
  DS -- no --> SI{"Policy: safety info<br/>(hypothetical / past hazard)?"}
  SI -- yes --> SIA["Steps shown calmly;<br/>'Is it happening now?'"]
  SI -- no --> OP{"Not the account holder? Pasted instructions?<br/>Lockout? 'Did that go in / just notes?'"}
  OP -- yes --> OPA["No account details / refuse instructions /<br/>after-hours line / what this chat actually saved"]
  OP -- no --> AS{"Question about something<br/>already sent, or 'send it' again?"}
  AS -- yes --> ASA["Plain answer with the reference:<br/>nobody notified, no time set"]
  AS -- no --> R{"Card ready and<br/>person says yes / no?"}
  R -- yes --> RC["F7/F5/F9: write prototype record<br/>reference + status"]
  R -- no --> RD["Not sent; kept once so<br/>'send it after all' restores it"]
  R -- "neither" --> L{"Script without<br/>approved templates?"}
  L -- yes --> H
  L -- no --> S{"Vendor, steering, sensitive data,<br/>accommodation/legal, unverified status,<br/>asks for a person or the office,<br/>contact-preference change, change/cancel request?<br/>(policy topic: 'not approved yet' + Ask the office;<br/>unsure twice: offer the office, no note)"}
  S -- yes --> H["F9: note for the office<br/>(read-back, person confirms)"]
  S -- "claims a prior decision" --> PC["Not agreed with; note for staff to check"]
  S -- no --> ST{"Matched resident<br/>asks for status?"}
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
