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
  P["Phone / browser"] --> V["Render static site<br/>static export of frontend/ (out/)<br/>public NEXT_PUBLIC_* settings only"]
  P -->|"emailed one-time code"| A["Supabase Auth<br/>invite-only, no passwords"]
  V -->|"HTTPS + sign-in token, CORS: exact website origin"| R["Render web service<br/>FastAPI + uvicorn, APP_ENV=hosted<br/>checks token + invite list<br/>alembic upgrade head on start"]
  R -->|"DATABASE_URL (Session pooler), backend only"| S[("Supabase Postgres<br/>RLS on every table, no policies<br/>synthetic residents via seed")]
  R -->|"GEMINI_API_KEY, backend only"| G["Gemini Developer API<br/>replies + optional gate / safety classifier"]
  H["here.now (team preview)<br/>static replay, no backend"] -.-> P
```

Secrets (`GEMINI_API_KEY`, `DATABASE_URL`, `STAFF_API_TOKEN`, a legacy `SUPABASE_JWT_SECRET`) live only in Render's
settings. The browser talks to Supabase **only** to sign in (public project address and publishable key) and never to
Supabase's database or to Gemini. The backend decides who someone is ([../security/SUPABASE_AUTH.md](../security/SUPABASE_AUTH.md)). Status and checklist: [../DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md).


## What the customer page shows (no silent substitution)

```mermaid
flowchart TD
  O["Phone opens the link"] --> B{"Built with<br/>NEXT_PUBLIC_API_BASE_URL?"}
  B -- "no (here.now)" --> RP["Recorded replay<br/>'Preview link' notice, typing off"]
  B -- yes --> W["GET /api/personas<br/>(after 4 s: 'Waking the assistant up…')"]
  W -- "answers" --> L["Live chat: type and send<br/>About this demo says: fixed rules or AI model"]
  W -- "unreachable (90 s timeout)" --> OFF["'The live assistant can't be reached'<br/>Try again + recorded replay"]
  L --> T["Each turn: POST /api/chat"]
  T -- "model error" --> TPL["Approved template or clear error<br/>(never the mock in disguise)"]
  T -- "network error" --> RETRY["'Not sent' + Send again<br/>(text kept)"]
```

Layout on a phone, top to bottom:
- the blue McKinley band;
- the demo row (Demo sign-in select and About this demo), which scrolls away;
- the conversation;
- the composer, pinned at every height and lifted above the keyboard (`visualViewport` on iOS,
  `interactive-widget=resizes-content` on Android). It holds the suggestions, the message box with Send, then
  Talk to a person, Start over and Call 911.

Details: [../design/BRAND_SYSTEM.md](../design/BRAND_SYSTEM.md), [../design/MOBILE_UX_AUDIT.md](../design/MOBILE_UX_AUDIT.md).
