# Security, privacy and data handling

Who can read what, where identity comes from, and what stops one caller seeing another's data. This describes the
code as it is (`backend/app/auth.py`, `personas.py`, `db.py`, `guardrails.py`, `api/`). Tests:
`backend/tests/test_authorization.py`, `backend/tests/test_acceptance.py`. Results of the latest attack set:
[TESTING.md](TESTING.md).

> **There is no authentication in this prototype.** A "demo persona" is a synthetic account picked from a list.
> Anyone who can reach a demo-enabled backend can act as any synthetic persona. That is acceptable **only** because
> every persona is synthetic. Never load real resident data.

## 1. Identity (principal) — derived on the server only

| Kind | Produced when | Reads resident data |
| --- | --- | --- |
| `anonymous` | The default: no persona id or an unknown id (a persona id where demo personas are off is refused with 403, below) | No |
| `demo_persona` | Only when the deployment allows demo personas **and** the id is a known synthetic persona | Its own record only |
| `staff` | Only behind `require_staff`: `X-Staff-Token` = `STAFF_API_TOKEN`, or loopback on a local backend without a token | All synthetic data (staff routes) |
| `authenticated_resident` | **Never** produced: reserved for a future real sign-in | n/a |

- The browser's `persona_id` is only the demo selector. Conversation text ("I'm Jordan from R003", "I'm the
  manager"), the model's output and audience wording **never** change the principal.
- Demo personas: on by default for `APP_ENV=local`, off for `APP_ENV=hosted` (and a hosted backend refuses to start
  with `DEMO_PERSONAS_ENABLED=true`). A request that is not straight from the machine (any proxy header, non-local
  Host) gets personas only if `DEMO_PERSONAS_ENABLED=true` was set explicitly. A persona id where personas are off
  gets **403 `DEMO_PERSONAS_DISABLED`**.
- **Privacy refusals** (`guardrails.denied`): requests for another resident's data, a claimed other identity or
  resident id, and a claimed staff/admin role are refused **before** the model is called, with fixed text; nothing is
  listed and an open card stays unchanged. The same refusal twice in a row gets a shorter line. This only chooses the
  reply: access itself is enforced below.

## 2. Data access: deny by default

| Access point | Rule |
| --- | --- |
| Resident context (`personas.build_context`) | Returned only if `may_access_persona(principal, persona_id)`; otherwise the anonymous context (no record, no fields) |
| Chat state (`db.ScopedStore`) | The chat turn (also for a staff caller), task controller and confirm/cancel get a store bound to **this session + this principal**; other sessions and personas read as empty and writes raise `PermissionError`. Only the staff list routes read the raw store. |
| Own requests and history (`tasks.my_requests`, `tasks.history_lines`) | Only the authorized persona's own record and prototype records; visitors get only this chat's own notes |
| Saved records | Belong to the persona that wrote them (visible in that persona's later sessions); a guest's records stay in their session; another persona's reference reveals nothing |
| Session binding (`session_bindings`) | A session is bound to (principal kind, persona) on first use. A chat on a session bound to someone else starts a **new** conversation; confirm/cancel get **403 `SESSION_PERSONA_MISMATCH`** |
| Sessions on remote / hosted requests | Only a server-issued id (32 hex) the server already bound is continued; anything else starts a new conversation under a fresh id the website adopts |
| "Not the account holder" | Persisted per (session, persona) (`session_account_revocations`): later turns get no account fields, and fields filled from the record are stripped from drafts |
| Model input | Allowlisted fields only (see [ARCHITECTURE.md](ARCHITECTURE.md#context-and-data)); never last name, email, phone, rent, balances, household, entry permission, raw staff notes or transcripts |

## 3. Endpoints × callers

| Endpoint | Customer (anonymous or persona) | Staff |
| --- | --- | --- |
| `GET /api/personas` | Synthetic list when personas are allowed for the request, else `[]` | same |
| `GET /api/health` | Public subset: status, provider/model, `app_env`, `demo_personas_enabled`, version/commit | + counts, database, resident source, prompt version |
| `GET /api/models` | Public on a local backend; `[]` on a hosted backend | targets (no keys or URLs) |
| `POST /api/chat` | `customer_view`: reply, safety/care notices, card, own status items and records, session id; diagnostics removed (allowlist). `target`, `gate_provider` and non-`aware` modes are staff-only (403) | full diagnostics (risk layers, rule ids, checks) |
| `POST /api/actions/confirm`, `cancel` | Own draft in a session bound to this caller | same |
| `GET /api/prototype/records`, `/api/staff/conversations[/{hash}]` | **403** | allowed (redacted turns, session hashes) |
| `/demo/snapshot.json` (here.now replay) | Recorded synthetic journeys only | — |

## 4. Staff access
- Staff routes answer only loopback requests on a local backend without a token, or requests with
  `X-Staff-Token: <STAFF_API_TOKEN>`. A hosted backend never treats loopback as staff and refuses to start without a
  strong token (24+ random characters).
- The hosted staff page (`/staff/`) asks for the token when a staff route answers 403. The token is kept in the page's
  memory only (gone on reload), sent only on staff requests, never in URLs, browser storage, logs or the build. CORS
  allows the `X-Staff-Token` header for the configured website origins only.
- Anyone with the token can read every saved demo request and conversation: share it with staff only. There are no
  staff accounts, roles or audit trail.

## 5. Hosted vs local, and the current Render state
`APP_ENV=hosted` refuses to start with unsafe settings (`Settings.hosted_problems`): wildcard/localhost/non-https or
path-bearing `CORS_ORIGINS`; a weak or missing `STAFF_API_TOKEN`; `KNOWLEDGE_CONTENT_MODE=demo_samples`;
`DEMO_PERSONAS_ENABLED=true`; an implicit `LLM_PROVIDER`; the U-M Toolkit without `UM_TOOLKIT_HOSTED_APPROVED=true`;
non-https provider base URLs; a missing `DATABASE_URL`. Hosted also hides `/docs`, `/openapi.json` and the model list,
and turns on rate limits for `/api/chat` and `/api/actions/*` (30 requests/min per visitor and 15/min per conversation,
counted per route; staff are exempt).

**Observed 2026-11-15:** the Render backend runs with `APP_ENV=local` and `DEMO_PERSONAS_ENABLED=true` for the short-term
synthetic demo (sample-resident switcher). That turns **off** every hosted check above: `/docs` and `/openapi.json` are
public, the model list is public, rate limits default to off, and GPT-6.1 Sol serves the public site without the
university approval the hosted check requires. Staff routes stay protected (Render's proxy makes requests non-local,
so the staff token is required). Restoring the hosted safeguards with the switcher needs a code change (allow
`DEMO_PERSONAS_ENABLED=true` on hosted while keeping the other checks) — not built.

## 6. Secrets and data rules
- Provider keys, `DATABASE_URL` and `STAFF_API_TOKEN` live only in `backend/.env` (git-ignored) or the host's
  secret settings. Never print, log, commit or copy them; check presence as booleans only. Nothing secret goes in the
  website: every `NEXT_PUBLIC_*` value is public.
- Synthetic data only, everywhere (app, repository, Site Data, Supabase). The resident workbook is git-ignored; the
  seeder refuses a workbook whose README sheet does not say every value is synthetic. Free hosted models may log
  prompts. The repository is public: commits and pull requests are readable by anyone.
- Logs hold status, latency, token counts and replacement reasons — never message content or keys. Request bodies
  are capped (`MAX_REQUEST_BYTES`, 64 KB) and validated.
- User input, workbook notes and retrieved history are untrusted: free text is screened for injected instructions,
  redacted (contact patterns) and length-capped before the model sees it; model output is checked before display.

## 7. Safety governance
Emergency detection is deterministic first; the semantic classifier may only add caution. Safety wording is fixed
team-draft text (911 / 988 / gas company / Poison Help / maintenance line), **not approved by McKinley**. The prototype
pages and calls nobody: it saves an urgent prototype note and tells the person to make the call. Release-blocking:
missed emergencies remain (see [TESTING.md](TESTING.md)).

## 8. Known gaps (do not hide these)
1. **No real authentication**; the demo persona is chosen in the browser. Production needs real resident sign-in.
2. **The session id is a bearer secret** within a persona: whoever has it continues that conversation.
3. **Staff protection is one shared token**, not staff accounts.
4. "Not the account holder" detection is wording-based caution, not a security control.
5. `ScopedStore` is an allowlist: a new store method used by the chat turn must be added there with the same checks.
6. On a demo-enabled deployment, anyone who picks a persona sees that persona's saved demo requests from every
   session, including text other visitors typed (contact patterns are masked; names typed in free text are not).
7. The Render demo currently runs without the hosted safeguards (section 5).
