# System architecture

Reflects the simplified MVP (`mvp-reset`). Two front-ends share one static build; the Python API is the only place with resident data, model keys or business rules.

```mermaid
flowchart LR
  subgraph Browser["Browser (static Next.js export)"]
    CV["Customer view /<br/>CustomerApp + ActionCard"]
    SC["Staff queue /staff/<br/>Saved requests, Live conversations"]
    SNAP[("demo/snapshot.json<br/>recorded journeys + saved requests")]
  end

  subgraph API["FastAPI backend (backend/app)"]
    CHAT["POST /api/chat"]
    ACT["POST /api/actions/confirm | cancel"]
    REC["GET /api/prototype/records<br/>GET /api/staff/conversations"]
    GUARD["staff_guard: loopback-only<br/>or X-Staff-Token"]
    ENG["chat_engine.run_turn<br/>A identity, B safety, C conversation, D tasks"]
    AUTH["A. auth.py + db.ScopedStore<br/>server-side principal"]
    RISK["B. risk/ + emergency.py<br/>rules -> semantic classifier -> policy<br/>-> approved text, incident state"]
    ASSIST["C. assistant.py<br/>ONE structured model call"]
    GR["guardrails.py<br/>privacy, explicit send,<br/>unsupported claims"]
    TASKS["D. tasks.py<br/>active card + waiting list;<br/>save only via confirm"]
    TOOLS["E. context.py + personas.py<br/>+ knowledge_base.json<br/>own history, approved facts"]
    LIVE["live_eval/ (dev only)<br/>preflight + budgeted smoke"]
    LLM["LLMGateway<br/>Gemini | OpenRouter | U-M Toolkit |<br/>Ollama | Anthropic | Mock"]
  end

  subgraph Data["Data (synthetic)"]
    XLSX[("Resident workbook<br/>(XLSX, not committed)")]
    DB[("SQLite (local) or Postgres / Supabase (DATABASE_URL)<br/>chat_turns, action_drafts (task state),<br/>gate_decisions (incident rows), prototype_records,<br/>synthetic residents")]
  end

  CV -- "live mode" --> CHAT
  CV -- "Send / don't send" --> ACT
  CV -. "no backend: replay" .-> SNAP
  SC --> GUARD
  GUARD --> REC
  SC -. "no backend" .-> SNAP
  CHAT --> ENG
  ACT --> TASKS
  ENG --> AUTH
  ENG --> RISK
  RISK -. "optional semantic layer<br/>(never lowers a rules alert)" .-> LLM
  ENG --> GR
  ENG --> ASSIST
  ASSIST --> LLM
  ENG --> TASKS
  ENG --> TOOLS
  LIVE -. "fixed provider:model" .-> LLM
  TOOLS --> XLSX
  TOOLS --> DB
  TASKS --> DB
  REC --> DB
```

Notes

- **here.now hosts only `dist/`.** On the preview link there is no backend, so both views fall back to `demo/snapshot.json`, which `uv run python -m app.export_demo` records by running the real pipeline on the MOCK model over the recorded multi-turn journeys.
- **Providers never receive workbook rows.** The one conversation call gets the system prompt (rules, the minimized SAFE_CONTEXT block, the person's own requests, approved property facts, the task state) and the last few messages.
- **Safety runs first** (`risk/`, see `safety-architecture.md`): an emergency answers with fixed approved text and pauses the open task, with no conversation model call. The
  semantic classifier receives only the customer's last message and up to three earlier customer messages (never
  resident records). Without a provider key it does not run and the rules alone decide.
- **Prototype store ≠ Yardi.** `prototype_records` stands in for work orders (D-11), CRM tour requests (D-10) and the staff queue (D-14). Nothing leaves the prototype database.

## Deployment (live public demo since 2026-11-11; option B)

```mermaid
flowchart LR
  P["Phone / browser"] --> W["Render static site mckinley-frontend<br/>static export of frontend/ (out/)<br/>NEXT_PUBLIC_API_BASE_URL only"]
  P -.->|"option A"| V["Vercel<br/>same static export"]
  W -->|"HTTPS, CORS: exact website origin"| R["Render web service mckinley-backend<br/>FastAPI + uvicorn, APP_ENV=hosted<br/>alembic upgrade head on start"]
  V -.-> R
  R -->|"DATABASE_URL (Session pooler, TLS), backend only"| S[("Supabase Postgres (dev project)<br/>RLS on every table, no policies<br/>synthetic residents via seed")]
  R -->|"OPENROUTER_API_KEY, backend only"| O["OpenRouter<br/>free model, replies"]
  R -.->|"GEMINI_API_KEY (option)"| G["Gemini Developer API"]
  H["here.now (team preview)<br/>static replay, no backend"] -.-> P
```

Secrets (`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`, `STAFF_API_TOKEN`) live only in Render's settings.
The browser never talks to Supabase or the model provider. Status and checklist: [../DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md).


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
