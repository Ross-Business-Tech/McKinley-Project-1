# Request / response sequence

Matches `run_turn` in `backend/app/chat_engine.py` and `plan_turn` / `confirm` in `backend/app/actions.py`. Step numbers match the `pipeline` trace shown in the staff console.

## One chat turn: `POST /api/chat`

```mermaid
sequenceDiagram
  autonumber
  participant U as Customer view
  participant A as FastAPI /api/chat
  participant E as run_turn
  participant C as context + personas
  participant G as DecisionGateService
  participant P as plan_turn
  participant L as LLMGateway
  participant S as SQLite

  U->>A: {message, persona_id, mode:"aware", session_id, channel?}
  A->>A: Pydantic validation (extra=forbid, 4000 chars, channel enum)
  A->>E: run_turn(..., fallback_on_model_error=True)
  E->>E: 1 receive: NFKC fold, strip delimiter tags, redact PII
  E->>C: 2 identity: build_context(persona_id) gives trusted audience + verified
  E->>S: earlier user turns (last 3) + urgent notes already saved in this session
  E->>E: 2b safety: risk.detect (rules, framing, window)
  opt classifier configured (key present, not mock)
    E->>L: risk classifier (structured JSON, 6 s, no retry)
    L-->>E: SemanticRisk or failure status (never treated as safe)
  end
  E->>E: risk.policy.decide (R1-R9): full alert / care line / safety info / none
  E->>E: 3 privacy: note redacted PII types
  E->>C: 4 context: allowlisted, topic-gated, injection-screened fields
  E->>S: prior gate decision (ignored while a draft is open)
  E->>G: 5 classify(message, GateContext)
  G-->>E: GateDecision (rules floor, an external gate can only add risk)
  E->>E: safety full alert forces urgency=emergency (never the reverse)
  E->>P: 6 select_workflow + plan_turn(gate, ctx, draft, channel, lang)
  P->>S: read or save the action draft, write an urgent note on emergency
  P-->>E: TurnPlan (functions, template, action card, chips, handoff, records)
  alt deterministic reply (opt-out, status list, confirmed "yes")
    E->>E: 7 skipped: no model call, no cost
  else
    E->>L: 7 generate(system + workflow + backend draft reply, history, SAFE_CONTEXT)
    alt runtime model error (timeout, 5xx, rate limit)
      L-->>E: LLMError, so the backend template is used
    else
      L-->>E: JSON {reply, handoff, ...}
    end
  end
  E->>E: 8 output_checks, a critical failure means the template replaces the reply,<br/>approved safety text selected from the policy decision (risk.responses)
  E->>E: 9 handoff recommendation (gate flags or plan), delivery note
  E->>S: 10 session turns + gate metadata incl. safety rule / semantic status (no message text in gate log)
  E-->>U: ChatResponse (reply, action, status_items, suggested_replies, diagnostics)
```

## Confirming a card: `POST /api/actions/confirm`

```mermaid
sequenceDiagram
  autonumber
  participant U as Customer view
  participant A as /api/actions/confirm
  participant X as actions.confirm
  participant S as SQLite

  U->>A: {session_id, persona_id, kind}  (no fields accepted)
  A->>X: build_context(persona_id) re-checks identity
  X->>S: get_draft(session_id, persona_id)
  alt no draft or wrong kind
    X-->>U: ok=false NO_PENDING_ACTION
  else maintenance without a matched resident
    X-->>U: ok=false NOT_AUTHORIZED
  else required fields missing
    X-->>U: ok=false INCOMPLETE (+ card)
  else
    X->>S: add_record(DEMO-WO / DEMO-TOUR / DEMO-TASK)
    alt write fails
      X-->>U: ok=false SAVE_FAILED "nothing was sent"
    else
      X->>S: clear_draft
      X-->>U: ok=true, reference + status label + prototype note
    end
  end
```
