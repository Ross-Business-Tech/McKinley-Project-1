# Architecture overview

The simplified MVP (the `mvp-reset` integration). Diagrams: [system architecture](../diagrams/system-architecture.md),
[chat turn sequence](../diagrams/chat-turn-sequence.md), [safety architecture](../diagrams/safety-architecture.md),
[data access](../diagrams/data-access.md). Decisions: [decisions.md](decisions.md). Status and limitations:
[../../README.md](../../README.md#status). The earlier planner / decision-gate / quick-fix design is archived in
[../archive/pre-mvp/](../archive/pre-mvp/README.md).

The system is a **prototype on synthetic data**. Nothing here connects to Yardi, a CRM, a pager, SMS/email or a
work-order system; "saved" means saved to the labelled prototype store (SQLite locally, Postgres/Supabase hosted).

## One chat turn: five parts

`backend/app/chat_engine.py` (`run_turn`) calls five owners, always in this order:

| Part | Where | What it does |
| --- | --- | --- |
| **A. Identity** | `app/auth.py`, `app/db.py` (`ScopedStore`) | Derives the principal server-side (anonymous, or a demo persona the deployment allows). Message text and the model never change it. Every read and write goes through a store scoped to this session and this principal. |
| **B. Safety** | `app/risk/`, `app/emergency.py` | Runs on **every** message before anything else: deterministic rules → optional semantic classifier → policy → fixed approved text. An emergency gets the approved instructions, one urgent prototype note per incident, and pauses any open task; **no model call** on that turn. An incident ends only on a grounded responder resolution ("the gas company fixed it") or explicit retraction, never on vague reassurance. |
| **C. Conversation** | `app/assistant.py`, `app/guardrails.py` | Privacy refusals (another resident's data, impersonation, claimed admin roles) and explicit typed sends are decided first, deterministically. Otherwise **one** structured model call (schema `mckinley_assistant`) returns a natural reply plus at most one proposed task operation. |
| **D. Tasks** | `app/tasks.py` | The only owner of task state: one **active** card plus a **waiting** list. Operations `start`, `update`, `suspend`, `resume`, `cancel` are validated here; `complete` (save) happens **only** through `confirm` (the Send button or an explicit "send it"), never from a model proposal. Saving twice returns the same record. |
| **E. Tools and guardrails** | `app/tasks.py` (`my_requests`, `history_lines`), `app/personas.py`, `app/context.py`, `content/knowledge_base.json` | Authorized resident context, the person's own requests and history, approved property facts. The model's reply is checked before it is shown (`guardrails.unsupported_claims` + `safety.output_checks`): a claim that something was saved, an identity change, an unknown reference, or history that is not on record is replaced by the backend's own plain sentence. |

Handoff notes (`staff_handoff`) carry what the person said, the waiting task they came from (`earlier`) and, for a
signed-in demo resident, a **history** line built from their own record (related requests by default; the whole
history only when they ask). The model never writes that history.

## Other components

| Part | Where | What it does |
| --- | --- | --- |
| Customer chat | `frontend/src/components/customer/` (`/`) | One conversation, read-back cards (Send before save), status list, safety notices and care lines, demo sign-in picker when the backend allows demo personas |
| Staff queue | `frontend/src/components/staff/` (`/staff/`) | Saved prototype requests and live conversations |
| Static replay | `frontend/public/demo/snapshot.json` (`backend/app/export_demo.py`) | Lets the here.now build work without a backend: recorded journeys on the MOCK model |
| API | `backend/app/main.py`, `backend/app/api/` | FastAPI routes; one error envelope `{"error": {code, message, retryable}}` |
| Providers | `backend/app/llm/` | Gemini, OpenRouter, U-M GPT Toolkit (`um_toolkit`), Ollama, Anthropic (optional), Mock behind one gateway |
| Persistence | `db.py`, `migrations/` (Alembic), `seed_synthetic.py` | Chat turns, task state (one draft row per session), incident rows, prototype records, synthetic residents/communities/interactions; RLS on in Postgres |
| Deployment | `render.yaml`, `frontend/vercel.json` | Render backend (`APP_ENV=hosted` refuses unsafe settings at startup), static website; [DEPLOYMENT_READINESS](../DEPLOYMENT_READINESS.md) |
| Dev tools (never imported by the app) | `live_eval/` (preflight, smoke), `export_demo.py` | Manual budgeted provider checks; the static demo snapshot |

## Endpoints

Customer (identity is the demo `persona_id` when allowed, never authentication): `POST /api/chat`,
`POST /api/actions/confirm`, `POST /api/actions/cancel`, `GET /api/personas`, `GET /api/health`, `GET /api/models`.

Staff (loopback only without a token; `X-Staff-Token` = `STAFF_API_TOKEN` otherwise; a hosted backend always needs
the token): `GET /api/prototype/records`, `GET /api/staff/conversations[/{session_hash}]`.

## LLM provider abstraction
- **Contract:** `LLMProvider.complete(system, messages, target, cfg, schema) -> LLMResult`. Providers receive only a
  system prompt and chat messages; they never see the workbook, personas or policy code.
- **Targets:** an explicit `provider:model` pair from `LLM_PROVIDER` / `LLM_MODEL`. The browser cannot choose one
  (target, gate and mode overrides are staff-only).
- **No silent switching:** one model per request, same-model retries with bounded backoff, `MODEL_SWITCHED` when the
  served model differs from the requested one.
- **Structured output:** the conversation call and the safety classifier each pass a JSON schema. A failed or
  unparseable call never changes task state: the person gets a fixed "say it another way" line.
- **Mock provider:** a keyword stand-in for offline tests and the replay (`is_mock=true`, labelled MOCK). It is
  never evidence of conversation quality; that is only ever measured live.

## Context adapter
- Workbook tabs: README, Residents, Interactions; joined on `resident_id`, normalized, provenance kept.
- Only minimal, allowlisted fields reach the model: first name, community, tenure band, preferred language/channel,
  and topic-gated items (renewal status, open requests, related history summarized from category/subject/status).
- Never forwarded: last name, email, phone, rent, balances, household, pets, vehicles, entry permission, raw staff
  notes, full transcripts. Free text is screened for injected instructions, redacted and length-capped.

## Security and governance
Server-side keys only (`backend/.env`, git-ignored); request validation; restricted CORS; model output treated as
untrusted text; logs hold status, latency and replacement reasons, never message content or keys; no external
writes. Free hosted models may log prompts, so only synthetic data is allowed. Production would additionally need
real authentication, RBAC, audit logs, retention controls and vendor/legal review.

## Future integration, NOT MVP
Yardi Voyager / RentCafe → authorized Databricks replica → least-privilege data gateway → context engine → channels.
Live lookups and write actions need separate permissions and reconciliation; emergencies must route to real
emergency channels.
