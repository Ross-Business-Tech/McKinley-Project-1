# System architecture

Reflects the code on `feat/gemini-supabase-deployment`. Two front-ends share one static build; the Python API is the only place with resident data, model keys or business rules.

```mermaid
flowchart LR
  subgraph Browser["Browser (static Next.js export in dist/)"]
    CV["Customer view /<br/>CustomerApp + ActionCard"]
    SC["Staff and demo console /staff/<br/>Saved requests, Live conversations, Conversation inspector,<br/>Workflow coverage, Usability, Model comparison, Evaluation"]
    SNAP[("demo/snapshot.json<br/>recorded journeys + evals")]
  end

  subgraph API["FastAPI backend (backend/app)"]
    CHAT["POST /api/chat"]
    ACT["POST /api/actions/confirm | cancel"]
    REC["GET /api/prototype/records<br/>GET /api/staff/conversations"]
    EV["/api/evals/* , /api/gates/*"]
    GUARD["staff_guard: loopback-only<br/>or X-Staff-Token"]
    ENG["chat_engine.run_turn<br/>(11 steps: 1, 2, 2b safety, 3-10)"]
    PLAN["actions.plan_turn<br/>(F2-F9 behaviour)"]
    GATE["DecisionGateService<br/>rules always + optional LLM / Jev"]
    SAFE["safety.py + emergency.py<br/>redaction, output checks,<br/>emergency rules (KINDS + CONCEPTS + framing)"]
    RISK["risk/ (sprint 3)<br/>detect -> semantic classifier -> policy R1-R9<br/>-> approved responses -> escalation"]
    LIVE["live_eval/ (offline)<br/>preflight + controlled A/B/C runner<br/>BLOCKED without a key"]
    UX["usability/ (offline)<br/>personas, scenarios, simulator,<br/>independent evaluator"]
    CTX["context.py + personas.py<br/>allowlisted SAFE_CONTEXT"]
    TPL["templates.py + knowledge_base.json<br/>(team drafts)"]
    LLM["LLMGateway<br/>Gemini | OpenRouter | Ollama | Anthropic | Mock"]
  end

  subgraph Data["Local data (synthetic)"]
    XLSX[("Resident workbook<br/>(XLSX, not committed)")]
    DB[("SQLite (local) or Postgres / Supabase (DATABASE_URL)<br/>chat_turns, gate_decisions, action_drafts,<br/>prototype_records, eval runs, synthetic residents")]
  end

  CV -- "live mode" --> CHAT
  CV -- "send / don't send" --> ACT
  CV -. "no backend: replay" .-> SNAP
  SC --> GUARD
  GUARD --> REC
  GUARD --> EV
  UX -- "real HTTP" --> CHAT
  UX -- "real HTTP" --> ACT
  SC -. "no backend" .-> SNAP
  CHAT --> ENG
  ACT --> PLAN
  ENG --> RISK
  RISK --> SAFE
  RISK -. "optional semantic layer<br/>(only with a key; never lowers)" .-> LLM
  LIVE -. "fixed provider:model" .-> LLM
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
- **Safety runs first** (`risk/`, see `safety-architecture.md`): its decision can only raise the gate's urgency. The
  semantic classifier receives only the customer's last message and up to three earlier customer messages (never
  resident records). Without a provider key it does not run and every turn is marked `degraded`.
- **Prototype store ≠ Yardi.** `prototype_records` stands in for work orders (D-11), CRM tour requests (D-10) and the staff queue (D-14). Nothing leaves SQLite.

## Target deployment (prepared, not yet deployed)

```mermaid
flowchart LR
  P["Phone / browser"] --> V["Vercel<br/>static export of frontend/ (out/)<br/>NEXT_PUBLIC_API_BASE_URL only"]
  V -->|"HTTPS, CORS: exact Vercel origin"| R["Render web service<br/>FastAPI + uvicorn, APP_ENV=hosted<br/>alembic upgrade head on start"]
  R -->|"DATABASE_URL (Session pooler), backend only"| S[("Supabase Postgres<br/>RLS on every table, no policies<br/>synthetic residents via seed")]
  R -->|"GEMINI_API_KEY, backend only"| G["Gemini Developer API<br/>replies + optional gate / safety classifier"]
  H["here.now (team preview)<br/>static replay, no backend"] -.-> P
```

Secrets (`GEMINI_API_KEY`, `DATABASE_URL`, `STAFF_API_TOKEN`) live only in Render's settings. The browser never
talks to Supabase or Gemini. Status and checklist: [../DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md).

