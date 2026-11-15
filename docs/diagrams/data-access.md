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

  subgraph Gate["Backend boundary (Sprint 6: app/auth.py)"]
    PR{"Principal resolved server-side:<br/>anonymous / demo_persona / staff<br/>(authenticated_resident: not built)"}
    BIND{"Session bound to this persona?<br/>(session_bindings, else 403)"}
    ID{"Matched resident?<br/>and not disclaimed as holder"}
    SS["ScopedStore: deny by default<br/>records by owner, history + drafts by session"]
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

  PR -- "anonymous, or hosted mode<br/>(demo personas off)" --> X
  PR -- "demo_persona (local / dev only)" --> BIND
  BIND -- "yes" --> ID
  BIND -- "no: 403 SESSION_PERSONA_MISMATCH" --> X
  R --> ID
  I --> ID
  ID -- "yes" --> AL
  ID -- "yes" --> SS
  ID -- "no: nothing from the record" --> X["Public info + office note only"]
  AL --> SC
  AL --> CARD
  SS --> STAT
  I --> SS
  P --> SS
  P --> RECS
  D --> CARD
  SC --> DIAG
  T -- "redact() on read" --> LIVE
  T -- "last 3 user turns" --> RC
  P --> LIVE
```

Never forwarded anywhere: last name, email, phone, unit type, rent, balance, late payments, autopay, household, roommates, vehicles, pets, lead source, default entry permission, raw staff notes, interaction transcripts.

Known prototype limitations

- **Identity is a demo selector, now behind a server-side principal (Sprint 6).** The browser still picks `persona_id`, but only a `demo_persona` principal may use it, a session is bound to its first persona, and the data layer (`ScopedStore`) refuses anything else. Hosted mode turns demo personas off, so a public deployment serves public information only. A demo persona is **not** authentication; production must add real sign-in that produces `authenticated_resident` (I-10, I-11). See [../security/AUTHORIZATION_BOUNDARIES.md](../security/AUTHORIZATION_BOUNDARIES.md).
- **Staff notes contain a redacted snippet of what the person typed** (max 240 characters; when the note was created from a button, the person's last three messages), because staff need it to avoid asking again. It is redacted for email, phone, SSN, card number, card expiry/CVV and DOB patterns.
- **The staff boundary is demo-only.** Without `STAFF_API_TOKEN`, staff, evaluation, gate and records routes answer only direct requests from this machine; since sprint 3 any proxy-forwarding header (X-Forwarded-For, X-Real-IP, Forwarded, Via, ...) makes the request non-local. A shared deployment must still set a token, and real staff sign-in is still required.
- **The safety decision is visible to staff only** (`risk` on each response: rule, layers, conflict, degraded). The customer sees only the approved safety text.
- **The static snapshot** contains only the minimized fields above, for synthetic personas.
