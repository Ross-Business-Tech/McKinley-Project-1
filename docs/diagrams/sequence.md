# Request / response sequence (`POST /api/chat`)

Matches `run_turn` in `backend/app/chat_engine.py`. Step numbers match the `pipeline` trace returned to the UI.

```mermaid
sequenceDiagram
  autonumber
  participant U as Browser (Next.js static)
  participant A as FastAPI /api/chat
  participant E as chat_engine.run_turn
  participant C as context + personas
  participant G as DecisionGateService
  participant X as External gate (LLM / Jev, optional)
  participant W as workflows + handoff
  participant L as LLMGateway → provider
  participant S as SQLite

  U->>A: {message, persona_id, mode, session_id, target?, gate_provider?}
  A->>A: Pydantic validation (extra=forbid, length limits), target allowlist
  A->>E: run_turn(...)
  E->>E: 1 receive: strip delimiter tags, redact PII patterns
  E->>C: 2 identity: build_context(persona_id) → trusted audience, verified?
  E->>E: 3 privacy: record which PII types were redacted
  E->>C: 4 context: allowlisted, topic-gated, injection-screened SAFE_CONTEXT (aware only)
  alt mode = baseline
    E->>E: 5 and 6 skipped
  else prompt_only / aware
    E->>S: last gate decision for this session (low-confidence memory)
    E->>G: 5 classify(message, GateContext)
    G->>G: rules decision (always)
    opt DECISION_GATE_PROVIDER = llm or jev
      G->>X: typed classification (timeout, no retries)
      alt success
        X-->>G: decision
        G->>G: apply_safety_floor(external, rules)
      else timeout / no key / bad output
        G->>G: fall back to rules (fallback_reason recorded)
      end
    end
    G-->>E: GateDecision
    E->>W: 6 select_workflow + triage / lead / renewal → system prompt section
  end
  E->>S: session history (same session, mode and target only)
  E->>L: 7 one response-generation call (JSON schema)
  L-->>E: reply + model handoff opinion + usage (or LLMError → HTTP error to UI)
  E->>E: 8 output checks, redact reply, emergency safety notice
  E->>W: 9 build_handoff → recommendation (NOT sent)
  E->>S: 10 store turns and gate metadata (no message text in the gate log)
  E-->>A: ChatResponse (reply, gate, workflow, handoff, pipeline, checks, usage)
  A-->>U: JSON → reply card + Diagnostics panel
```

If the backend is unreachable (as on the hosted static site), the UI loads `/demo/snapshot.json` instead and labels every response as pre-computed MOCK output.
