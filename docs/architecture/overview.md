# Architecture overview

Current code on `feat/workflow-customer-experience`. Diagrams: [system architecture](../diagrams/system-architecture.md),
[chat turn sequence](../diagrams/chat-turn-sequence.md), [safety architecture](../diagrams/safety-architecture.md),
[conversation routing](../diagrams/conversation-routing.md), [data access](../diagrams/data-access.md). Decisions:
[decisions.md](decisions.md). Status and limitations: [../../README.md](../../README.md#status).

The system is a **prototype on synthetic data**. Nothing here connects to Yardi, a CRM, a pager, SMS/email or a
work-order system; "submitted" means saved to the labelled prototype store in SQLite.

## Components

| Part | Where | What it does |
| --- | --- | --- |
| Customer chat | `frontend/src/components/customer/` (`/`) | One conversation, read-back cards (confirm before save), status list, safety notices and care lines |
| Staff / demo console | `frontend/src/components/staff/`, `frontend/src/components/mckinley/` (`/staff/`) | Saved requests, Live conversations, Conversation inspector, Workflow coverage, Usability, Model comparison (A/B/C), Evaluation |
| Static replay | `frontend/public/demo/snapshot.json` (built by `backend/app/export_demo.py`) | Lets the here.now build work without a backend: recorded journeys, MOCK model |
| API | `backend/app/main.py`, `backend/app/api/` | FastAPI routes; one error envelope `{"error": {code, message, retryable}}` |
| Chat pipeline | `backend/app/chat_engine.py` (`run_turn`) | 11 traced steps: 1 receive · 2 identity · **2b safety** · 3 privacy · 4 context · 5 gate · 6 workflow + plan · 7 generate · 8 validate · 9 handoff · 10 persist |
| Safety | `backend/app/risk/` + `emergency.py` | Rules → optional semantic classifier → policy R1–R9e → approved text → escalation; runs before routing and generation ([safety](../safety/safety-evaluation.md)) |
| Decision gate | `backend/app/gates/` | Intent / urgency / human-required; rules always, optional LLM or Jev gate may only add risk ([decision-gate.md](decision-gate.md)) |
| Planner | `backend/app/actions.py` (`plan_turn`, `confirm`) | F2–F9 behaviour: questions, read-back cards, notes, status; ordered checks (the order is the spec) |
| Detectors and text | `intake.py`, `templates.py`, `content/knowledge_base.json`, `workflows.py`, `handoff.py` | Message detectors, approved/draft wording, FAQ content, workflow selection, handoff recommendations |
| Context | `context.py`, `personas.py` | Workbook adapter, allowlisted SAFE_CONTEXT, demo identity; "not the account holder" rule |
| Providers | `backend/app/llm/` | Gemini (intended for deployments), OpenRouter, Ollama, Anthropic (optional), Mock behind one gateway |
| Persistence | `db.py`, `migrations/` (Alembic), `seed_synthetic.py` | SQLite locally or Postgres/Supabase (`DATABASE_URL`); chat turns, gate log (no message text), drafts, prototype records, eval runs, synthetic residents/communities/interactions; RLS on in Postgres |
| Deployment | `render.yaml`, `frontend/vercel.json` | Render backend (`APP_ENV=hosted` refuses unsafe settings), Vercel static site; [DEPLOYMENT_READINESS](../DEPLOYMENT_READINESS.md) |
| Evaluation | `evals.py`, `gate_evals.py`, `journey_evals.py`, `usability/`, `live_eval/` | Five cases, gate scenarios, journeys, persona suite, live A/B/C runner ([evaluation](../evaluation/README.md)) |

## Endpoints

Customer (open; identity is the demo `persona_id`, not authentication): `POST /api/chat`,
`POST /api/actions/confirm`, `POST /api/actions/cancel`, `GET /api/personas`, `GET /api/health`, `GET /api/models`,
`GET /api/gates/config`.

Staff / demo (loopback only, or `X-Staff-Token` when `STAFF_API_TOKEN` is set; any proxy-forwarding header or a
non-local `Host` is refused): `GET /api/prototype/records`, `GET /api/staff/conversations[/{session_hash}]`,
`POST /api/context/preview`, `/api/evals/*` (cases, run, runs, results, summary), `/api/gates/*` (scenarios, evaluate,
log). Note: `POST /api/chat` returns staff diagnostics (`risk`, `gate`, `pipeline`, `source_context_fields`) to every
caller, including the customer browser; decide before any deployment whether to strip them for non-staff callers.
The browser never sends `X-Staff-Token`, so with a token set the console's staff tabs only work from tools
that send the header.

## LLM provider abstraction
- **Contract:** `LLMProvider.complete(system, messages, target, cfg) -> LLMResult`. Providers receive only a system prompt and chat messages. They have no access to the workbook, personas or policy code. This keeps synthetic resident data handling separate from vendor adapters.
- **Targets:** a `Target` is an explicit `provider:model` pair. Chat uses `LLM_PROVIDER`/`LLM_MODEL` unless the UI picks another target from `EVAL_TARGETS`. The server rejects arbitrary targets from the browser.
- **No silent switching:** the OpenRouter request names a single model (no `models` fallback list, no auto-router). Retries on 429/5xx/timeouts reuse the same model with bounded backoff that honors `Retry-After`. The gateway compares the served model ID with the requested one (allowing `:free`/`:latest` and dated-snapshot suffixes). On mismatch it raises `MODEL_SWITCHED` and the result is discarded rather than recorded under the wrong model.
- **Structured output:** every provider is asked for the same JSON schema (OpenRouter `response_format: json_schema`, Ollama `format`, Anthropic `output_config.format`). Free and local models often ignore it, so parsing is lenient: plain JSON, then JSON extracted from prose or code fences, then `text_fallback`, where the raw text becomes the reply with no model handoff signal. The parse mode is recorded and shown, and `text_fallback` fails the `structured_output` check.
- **Generation settings** (`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`) are identical for baseline and aware modes. Anthropic's current models reject temperature, so it records `temperature: null` and uses `ANTHROPIC_EFFORT`.
- **Mock provider:** rule-based templates, deterministic latency/tokens, `is_mock=true`, labelled MOCK in the UI and in exports. It exists to exercise the harness and UI, and is never evidence of model quality.
- **Adding a provider** (Gemini, Groq, etc.): implement `complete()` in `app/llm/<name>.py`, register a factory in `app/llm/__init__.py:FACTORIES`, add a key to `Settings.api_key_for` and any readiness logic to `provider_ready`. Groq and many others are OpenAI-compatible and can reuse the OpenRouter adapter's shape.

## Context adapter
- Workbook tabs: README; Residents (20 rows, 31 fields); Interactions (101 rows, 10 fields). Required sheets/columns are validated, missing values are normalized to empty, and orphan interactions are ignored with a warning.
- Join on `resident_id`; normalize strings/dates; keep provenance (`Residents.preferred_contact`, `Interactions[I003]`).
- Send only what is minimally necessary: first name, community, tenure band, preferred language/channel, plus topic-gated fields: renewal status for renewal topics, open requests/entry window for maintenance topics, and the contact-timing clause of `notes_for_staff` for contact, renewal or maintenance topics. Related history is summarized from category/subject/status/follow-up columns only. Derived flags: `repeat_issue_flag` (2+ related maintenance contacts) and `open_commitment_flag`.
- Never forwarded: last name, email, phone, `unit_type`, rent, balance, late payments, autopay, household, pets, vehicles, lead source, entry permission, raw `notes_for_staff`, `full_text`.
- Free-text values pass an instruction-injection screen and are redacted and length-capped. Dropped items are listed in the Context Preview.
- Prospects: no prospect dataset was supplied, so prospects are clearly labelled fictional fixtures with no live inventory or pricing.

## Safety
Before any routing or generation, `risk.pipeline.assess` combines the deterministic rules (`risk/detect.py`, which
wraps `emergency.scan`: keywords, meaning-level concepts, framing, negation, a 3-turn window) with an optional
semantic classifier (`risk/classifier.py`, structured output through the gateway; runs only when a key exists and the
target is not the mock). `risk/policy.decide` applies rules R1–R9e: the semantic layer never removes a rules alert (the one thing it may remove is the broad 911 care line, R7, at confidence >= 0.8); failure
marks the turn `degraded`, never "safe". `risk/responses.select` picks fixed team-draft text (911 / 988 / Poison Help /
maintenance line). A full alert forces the gate to `emergency` and the planner saves one urgent prototype note per
hazard (nobody is paged). Other layers still apply: input redaction and tag stripping, pre-model policy gates
(`safety.pre_model_gates`), output checks with template replacement on critical failures, and handoff merge.
**Fresh-holdout result: 64.5% full alert, release-blocking misses** — see [safety-evaluation.md](../safety/safety-evaluation.md).

## Evaluation
See [evaluation/README.md](../evaluation/README.md) for every suite, its latest result, whether it is live or mock,
and the command. Only one historical run used a real model (2026-11-01); everything since is mock, and the live A/B/C
runner is blocked until a key is configured.

## Architectural decisions (MVP)
- **Provider-agnostic gateway over a vendor SDK:** OpenRouter and Ollama use plain HTTP via `httpx`. The Anthropic SDK is an optional extra, so nothing requires a paid key.
- **Direct browser → FastAPI over CORS** instead of a Next.js proxy, so long eval runs avoid dev-proxy timeouts. Only the public base URL is exposed to the browser.
- **Deterministic safety alongside prompting:** regex gates and checks are simple, testable and visible in the UI. They supplement model judgment and do not by themselves guarantee fair-housing compliance.
- **SQLite + JSON export:** enough for demo sessions and eval history, with no infrastructure.

## Security and governance
Server-side keys only (`backend/.env`, gitignored); request validation (`extra="forbid"`, length limits); restricted CORS; model output treated as untrusted text; logs contain status/latency/token counts only, never message content or keys; no external writes. Free hosted models may log prompts, so only synthetic or de-identified data is allowed. Production would additionally require authentication, RBAC, audit logs, retention controls, encryption, rate limits, vendor/legal review (including provider data-use terms) and documented data access contracts.

## Future integration, NOT MVP
Yardi Voyager / RentCafe -> authorized Databricks replica (about a 10-minute delay, per the sprint brief) -> least-privilege data gateway -> context engine -> channels (web, phone, email, SMS). Live lookups and write actions need separate permissions and robust reconciliation. For maintenance emergencies, route to actual emergency channels, not unsupported self-service instructions.
