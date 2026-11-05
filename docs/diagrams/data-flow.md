# Data flow and privacy boundaries

Mirrors `backend/app/context.py` (allowlist, `NEVER_FORWARDED`), `backend/app/safety.py` (redaction and injection screen) and `backend/app/db.py`.

```mermaid
flowchart LR
  subgraph Sources["Sources (synthetic only)"]
    XL[("Workbook: Residents (31 cols)<br/>Interactions (10 cols)")]
    FX[("Fictional fixtures<br/>(prospects, unmatched,<br/>injection test)")]
    MSG["Customer message<br/>(untrusted)"]
  end

  subgraph Server["Backend trust boundary"]
    RED["Redaction: email, phone, SSN,<br/>card, DOB · tag stripping"]
    ALLOW["Allowlist + topic gating<br/>first name, community, tenure band,<br/>language, channel; plus topic-gated:<br/>renewal status, open requests, entry window,<br/>contact clause of staff note,<br/>history subject/status summaries, derived flags"]
    INJ["Injection screen<br/>drops matching notes and subjects"]
    WITH["NEVER forwarded:<br/>last name, email, phone, unit type, rent,<br/>balance, late payments, autopay, household,<br/>pets, vehicles, lead source, entry permission,<br/>raw staff notes, full_text transcripts"]
    GATE["Decision gate<br/>(sees message + flag names only)"]
    HO["Handoff summary<br/>built from approved fields only"]
  end

  subgraph Out["Leaves the server"]
    LLM["LLM provider<br/>system prompt + SAFE_CONTEXT + message"]
    JEVX["Jev API (only if configured)<br/>message + audience + flag names"]
    UI["Browser: reply, field names with provenance,<br/>gate result, recommendation"]
  end

  subgraph Store["Local SQLite (git-ignored)"]
    T[("chat_turns: redacted text,<br/>session memory")]
    GL[("gate_decisions: intent, urgency,<br/>flags, source; NO message text")]
    ER[("eval results")]
  end

  XL --> ALLOW
  FX --> ALLOW
  XL -.-> WITH
  MSG --> RED --> GATE
  RED --> LLM
  ALLOW --> INJ --> LLM
  INJ --> HO --> UI
  GATE --> UI
  GATE -.-> JEVX
  LLM --> UI
  RED --> T
  GATE --> GL
  LLM --> ER
```

| Boundary | Rule | Where enforced |
|---|---|---|
| Identity | Audience and verification come from the demo persona only; models cannot change them | `chat_engine.py` step 2, `gates/policy.py` |
| Mode B (prompt_only) | No resident fields reach the model or the gate's record flags | `chat_engine.identity_only` |
| Free hosted models | Synthetic or de-identified data only; free endpoints may log prompts | `docs/ENGINEERING_RULES.md` |
| Static demo snapshot | Contains only minimized SAFE_CONTEXT values (same as UI), no raw rows | `export_demo.py` |
| Keys | Server-side `backend/.env` only; never in responses or the static site | `config.py`, tests in `test_api.py` |
