# One chat turn, and the Send button

The simplified MVP (`backend/app/chat_engine.py`, `run_turn`). The pre-MVP 11-step version is archived in
[../archive/pre-mvp/diagrams/chat-turn-sequence.md](../archive/pre-mvp/diagrams/chat-turn-sequence.md).

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant E as chat_engine.run_turn
  participant A as A. auth + ScopedStore
  participant S as B. risk (safety)
  participant G as guardrails
  participant C as C. assistant (one model call)
  participant T as D. tasks
  participant DB as Store

  B->>E: POST /api/chat {message, session_id, persona_id?}
  E->>A: derive principal (server-side), scope the store
  E->>S: assess(message, recent messages)
  alt emergency (full alert)
    S-->>E: fixed approved text (911 / gas company / maintenance line)
    E->>T: pause the open task (unsent, unchanged)
    E->>DB: one urgent prototype note per incident (nobody is paged)
    E-->>B: safety notice, no card, no model call
  else privacy request or explicit "send it"
    E->>G: denied() / explicit_send()
    G-->>E: fixed refusal, or confirm the active card
    E-->>B: reply (task unchanged, or saved once)
  else ordinary turn
    E->>C: system prompt (rules, minimized context, own requests, approved facts, task state) + last messages
    C-->>E: reply + at most one proposed op (start / update / suspend / resume / cancel)
    E->>T: validate and apply the op (never "complete")
    E->>G: check the reply (unsupported claims, output checks)
    G-->>E: pass, or the backend's own plain sentence instead
    E->>DB: save task state (if changed) + the turn
    E-->>B: reply + card (+ own status items)
  end

  B->>T: POST /api/actions/confirm (Send button)
  T->>DB: save the card as a prototype record (same record if pressed twice)
  T-->>B: "Saved in demo", the next waiting card comes back
```

After a grounded resolution of an emergency ("the gas company fixed the leak"), the incident closes, a calm line
replaces the alert, and the paused card comes back exactly as it was. A vague "it's fine now", or danger still
present, keeps the incident open. Details: [safety-architecture.md](safety-architecture.md).
