# Architecture (as implemented)

Last verified against code on 2026-11-05 (branch `feat/agentic-workflow-gates`). Solid boxes are working code.
Dashed boxes are optional or experimental and only active when configured. Nothing here writes to an external system.

```mermaid
flowchart TB
  subgraph Browser["Browser (static Next.js export, hosted on here.now)"]
    UI["Chat comparison: modes A / B / C"]
    DIAG["Diagnostics panel: gate, workflow, context, pipeline trace"]
    EVUI["Eval dashboard: five-case + decision-gate comparison"]
    DEMO["Static demo mode<br/>/demo/snapshot.json (MOCK, pre-computed)"]
  end

  subgraph API["FastAPI backend (local only; not hosted)"]
    ROUTES["/api/chat · /api/context/preview · /api/personas<br/>/api/evals/* · /api/gates/*"]
    ENGINE["chat_engine.run_turn<br/>10-step deterministic pipeline"]
    subgraph GATES["app/gates: DecisionGateService"]
      RULES["rules.py<br/>deterministic (default)"]
      FLOOR["policy.py<br/>safety floor"]
      LLMG["llm_gate.py<br/>structured-output LLM gate"]
      JEV["jev_gate.py<br/>EXPERIMENTAL, needs TYPESAFE_API_KEY"]
    end
    WF["workflows.py<br/>select_workflow, triage, lead, renewal"]
    HO["handoff.py<br/>HandoffRecommendation (never sent)"]
    CTX["context.py + personas.py<br/>allowlisted SAFE_CONTEXT"]
    SAFE["safety.py<br/>redaction, policy patterns, output checks"]
    GW["llm/ LLMGateway<br/>no silent model switching"]
    EVALS["evals.py · gate_evals.py · export_demo.py"]
  end

  subgraph Data["Local data (git-ignored)"]
    XLSX[("Synthetic workbook XLSX<br/>20 residents, 101 interactions")]
    FIX[("In-code fixtures:<br/>2 fictional prospects, unmatched resident,<br/>injection-test resident")]
    DB[("SQLite: chat turns, gate log,<br/>eval runs/results")]
  end

  subgraph Providers["LLM providers (one target per call)"]
    OR["OpenRouter (default, free models)"]
    OL["Ollama (local)"]
    MK["Mock (deterministic, NOT a model)"]
    AN["Anthropic (optional extra)"]
    TS["TypeSafe Jev API"]
  end

  UI -->|NEXT_PUBLIC_API_BASE_URL| ROUTES
  EVUI --> ROUTES
  UI -. backend unreachable .-> DEMO
  ROUTES --> ENGINE
  ROUTES --> EVALS
  ENGINE --> CTX
  ENGINE --> SAFE
  ENGINE --> GATES
  ENGINE --> WF
  ENGINE --> HO
  ENGINE --> GW
  ENGINE --> DB
  RULES --> FLOOR
  LLMG --> FLOOR
  JEV --> FLOOR
  LLMG --> GW
  JEV -.-> TS
  CTX --> XLSX
  CTX --> FIX
  GW --> OR
  GW --> OL
  GW --> MK
  GW -.-> AN
  EVALS --> ENGINE
  EVALS -->|writes| DEMO

  classDef optional stroke-dasharray: 5 5;
  class JEV,AN,TS,LLMG optional;
```

| Component | File(s) | Status |
|---|---|---|
| Rules gate + safety floor | `backend/app/gates/rules.py`, `policy.py` | WORKING (default) |
| Structured LLM gate | `backend/app/gates/llm_gate.py` | WORKING via mock; untested against a live model in this repo (no key) |
| Jev gate | `backend/app/gates/jev_gate.py` | EXPERIMENTAL: built from public docs and tested with mocked HTTP only |
| Workflows / handoff | `backend/app/workflows.py`, `handoff.py` | WORKING (recommendation only) |
| Static demo mode | `frontend/public/demo/snapshot.json`, `frontend/src` | MOCKED (labelled) |
| Response generation | `backend/app/llm/*` | WORKING with OpenRouter/Ollama/Mock; Anthropic optional |
