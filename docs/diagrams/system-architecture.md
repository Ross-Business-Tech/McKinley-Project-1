# System architecture

Reflects the code on `feat/workflow-customer-experience`. Two front-ends share one static build; the Python API is the only place with resident data, model keys or business rules.

```mermaid
flowchart LR
  subgraph Browser["Browser (static Next.js export in dist/)"]
    CV["Customer view /<br/>CustomerApp + ActionCard"]
    SC["Staff and demo console /staff/<br/>Inspector, Saved requests, Coverage,<br/>Model comparison, Evaluation"]
    SNAP[("demo/snapshot.json<br/>recorded journeys + evals")]
  end

  subgraph API["FastAPI backend (backend/app)"]
    CHAT["POST /api/chat"]
    ACT["POST /api/actions/confirm | cancel"]
    REC["GET /api/prototype/records"]
    EV["/api/evals/* , /api/gates/*"]
    ENG["chat_engine.run_turn<br/>(10-step pipeline)"]
    PLAN["actions.plan_turn<br/>(F2-F9 behaviour)"]
    GATE["DecisionGateService<br/>rules always + optional LLM / Jev"]
    SAFE["safety.py<br/>redaction, emergency + policy gates,<br/>output checks"]
    CTX["context.py + personas.py<br/>allowlisted SAFE_CONTEXT"]
    TPL["templates.py + knowledge_base.json<br/>(team drafts)"]
    LLM["LLMGateway<br/>OpenRouter | Ollama | Anthropic | Mock"]
  end

  subgraph Data["Local data (synthetic)"]
    XLSX[("Resident workbook<br/>(XLSX, not committed)")]
    DB[("SQLite<br/>chat_turns, gate_decisions,<br/>action_drafts, prototype_records,<br/>eval_runs")]
  end

  CV -- "live mode" --> CHAT
  CV -- "send / don't send" --> ACT
  CV -. "no backend: replay" .-> SNAP
  SC --> REC
  SC --> EV
  SC -. "no backend" .-> SNAP
  CHAT --> ENG
  ACT --> PLAN
  ENG --> SAFE
  ENG --> CTX
  ENG --> GATE
  ENG --> PLAN
  PLAN --> TPL
  ENG --> LLM
  GATE -. "optional, falls back to rules" .-> LLM
  CTX --> XLSX
  ENG --> DB
  PLAN --> DB
  REC --> DB
```

Notes

- **here.now hosts only `dist/`.** On the preview link there is no backend, so both views fall back to `demo/snapshot.json`, which `uv run python -m app.export_demo` records by running the real pipeline (mock model, rules gate) over 17 multi-turn journeys.
- **Providers never receive workbook rows.** They get the system prompt, trusted workflow instructions, a backend draft reply and the minimized SAFE_CONTEXT block.
- **Prototype store ≠ Yardi.** `prototype_records` stands in for work orders (D-11), CRM tour requests (D-10) and the staff queue (D-14). Nothing leaves SQLite.
