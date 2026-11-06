# Customer workflows (F1–F9 as implemented)

The order of checks in `actions.plan_turn`. Earlier checks win. Every branch ends in either an answer, one question, a read-back card the person must confirm, or a note for the office.

```mermaid
flowchart TD
  M["Message + trusted identity<br/>(demo sign-in)"] --> O{"SMS and an<br/>opt-out keyword?"}
  O -- yes --> OO["F2: confirm opt-out<br/>(no model call)"]
  O -- no --> EM{"Emergency wording?<br/>(any audience)"}
  EM -- yes --> EE["F6+F9: 911 / leave / emergency line first<br/>urgent note saved once (prototype queue)"]
  EM -- no --> R{"Card ready and<br/>person says yes / no?"}
  R -- yes --> RC["F7/F5/F9: write prototype record<br/>reference + status"]
  R -- no --> RD["Clear the draft:<br/>nothing sent"]
  R -- "neither" --> L{"Script without<br/>approved templates?"}
  L -- yes --> H
  L -- no --> S{"Vendor, steering, sensitive data,<br/>accommodation/legal, unverified status,<br/>asks for a person or the office,<br/>unsure twice, change/cancel request?"}
  S -- yes --> H["F9: note for the office<br/>(read-back, person confirms)"]
  S -- no --> ST{"Matched resident<br/>asks for status?"}
  ST -- yes --> STL["F8: open items, no timing<br/>(+ office note if frustrated)"]
  ST -- no --> MT{"Maintenance, or answering<br/>an open repair card?"}
  MT -- "guest" --> MG["Ask to sign in;<br/>911 if dangerous"]
  MT -- "unmatched resident" --> H
  MT -- "matched resident" --> MI["F6: issue, room, entry permission<br/>(contact + visit window from account)<br/>one question at a time"]
  MI --> MR{"All fields?"}
  MR -- no --> MI
  MR -- yes --> MC["F7 read-back card:<br/>Send repair request"]
  MT -- no --> TR{"Prospect or guest asks to tour,<br/>or answers an open tour card?"}
  TR -- yes --> TI["F5: community/city, days, time of day<br/>changes overwrite earlier answers"]
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
