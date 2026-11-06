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

  subgraph Model["Response model"]
    SC["SAFE_CONTEXT: first name, community,<br/>tenure band, language, contact channel,<br/>contact clauses of notes, topic-matched<br/>history subjects + status, repeat / owed flags"]
  end

  subgraph Customer["Customer view"]
    CARD["Read-back card fields:<br/>what they said, room, entry permission,<br/>contact preference, visit window (own account only)"]
    STAT["Status list (own account only):<br/>reference, short title, status, opened date"]
  end

  subgraph Staff["Staff console"]
    DIAG["Per-turn diagnostics:<br/>context field NAMES + provenance,<br/>gate, workflow, checks, model, cost"]
    RECS["Saved requests:<br/>summary, fields, team, priority,<br/>hashed session id"]
  end

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
```

Never forwarded anywhere: last name, email, phone, unit type, rent, balance, late payments, autopay, household, roommates, vehicles, pets, lead source, default entry permission, raw staff notes, interaction transcripts.

Known prototype limitations

- **Identity is a demo selector.** The browser sends `persona_id`; production must bind identity to an authenticated session server-side (I-10, I-11).
- **Staff notes contain a redacted snippet of what the person typed** (max 160 characters), because staff need it to avoid asking again. It is redacted for email, phone, SSN, card and DOB patterns.
- **The static snapshot** contains only the minimized fields above, for synthetic personas.
