# Data access: who can see what

What flows from the synthetic workbook and the prototype store to the model, the customer and staff. Anything not listed is withheld (`context.NEVER_FORWARDED`).

```mermaid
flowchart LR
  subgraph Source["Synthetic sources"]
    R[("Residents sheet<br/>name, contact, unit, rent, balance,<br/>notes, preferences, entry window")]
    I[("Interactions sheet<br/>category, subject, status,<br/>full transcript")]
    P[("prototype_records<br/>DEMO-WO / TOUR / TASK")]
    D[("action_drafts<br/>redacted slot values")]
  end

  subgraph Gate["Backend boundary"]
    ID{"Matched resident?<br/>(trusted demo sign-in)"}
    AL["Allowlist + redaction +<br/>injection screen + topic gate"]
  end

  subgraph Risk["Semantic risk classifier (optional; same provider gateway)"]
    RC["Customer's last message + up to 3 earlier<br/>customer messages (redacted).<br/>NO resident record, NO SAFE_CONTEXT"]
  end

  subgraph Model["Response model"]
    SC["SAFE_CONTEXT: first name, community,<br/>tenure band, language, contact channel,<br/>contact clauses of notes, topic-matched<br/>history subjects + status, repeat / owed flags"]
  end

  subgraph Customer["Customer view"]
    CARD["Read-back card fields:<br/>what they said, room, entry permission,<br/>contact preference, visit window (own account only)"]
    STAT["Status list (own account only):<br/>reference, short title, status, opened date"]
  end

  subgraph Staff["Staff console (loopback-only, or X-Staff-Token when STAFF_API_TOKEN is set)"]
    DIAG["Per-turn diagnostics:<br/>context field NAMES + provenance,<br/>gate, workflow, checks, model, cost"]
    RECS["Saved requests:<br/>summary, fields, team, priority,<br/>hashed session id"]
    LIVE["Live conversations:<br/>redacted transcript by session hash"]
  end
  T[("chat_turns<br/>what was typed + replies")]

  R --> ID
  I --> ID
  ID -- "yes" --> AL
  ID -- "no: nothing from the record" --> X["Public info + office note only"]
  AL --> SC
  AL --> CARD
  I --> STAT
  P --> STAT
  P --> RECS
  D --> CARD
  SC --> DIAG
  T -- "redact() on read" --> LIVE
  T -- "last 3 user turns" --> RC
  P --> LIVE
```

Never forwarded anywhere: last name, email, phone, unit type, rent, balance, late payments, autopay, household, roommates, vehicles, pets, lead source, default entry permission, raw staff notes, interaction transcripts.

Known prototype limitations

- **Identity is a demo selector.** The browser sends `persona_id`; production must bind identity to an authenticated session server-side (I-10, I-11).
- **Staff notes contain a redacted snippet of what the person typed** (max 240 characters; when the note was created from a button, the person's last three messages), because staff need it to avoid asking again. It is redacted for email, phone, SSN, card number, card expiry/CVV and DOB patterns.
- **The staff boundary is demo-only.** Without `STAFF_API_TOKEN`, staff, evaluation, gate and records routes answer only direct requests from this machine; since sprint 3 any proxy-forwarding header (X-Forwarded-For, X-Real-IP, Forwarded, Via, ...) makes the request non-local. A shared deployment must still set a token, and real staff sign-in is still required.
- **The safety decision is visible to staff only** (`risk` on each response: rule, layers, conflict, degraded). The customer sees only the approved safety text.
- **The static snapshot** contains only the minimized fields above, for synthetic personas.
