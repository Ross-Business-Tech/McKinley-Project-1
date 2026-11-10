# Authorization boundaries (Sprint 6)

Who can read which data, where identity comes from, and what stops one caller seeing another's data. This
describes the code as it is (`backend/app/auth.py`, `personas.py`, `db.py`, `chat_engine.py` step 2,
`api/*.py`). Tests: `backend/tests/test_sprint6_auth.py`.

> **There is no authentication in this prototype.** A "demo persona" is a synthetic account picked from a list.
> Anyone who can reach a demo-enabled backend can act as any synthetic persona. That is acceptable only because
> every persona is synthetic. On a hosted backend (`APP_ENV=hosted`) demo personas are off and cannot be turned
> on, so every customer request is anonymous and no resident data can be reached.

## 1. Principal model (`app/auth.py`)

| Kind | Produced when | Can read resident data |
|---|---|---|
| `anonymous` | The default. No persona id; an unknown persona id; offline tooling with demo personas off. | No |
| `demo_persona` | Only on a deployment that allows demo personas (`Settings.demo_personas_allowed`), and only for a **known** demo persona id (fictional prospect, unmatched resident, the injection fixture, or a workbook/database resident). | Only that exact persona's synthetic record (`can_read_resident_data` is true for resident personas only) |
| `authenticated_resident` | **Never.** The type exists for a future real sign-in; no code path creates it. | n/a |
| `staff` | Only behind `require_staff` (loopback without a token, or `X-Staff-Token` = `STAFF_API_TOKEN`), plus offline staff tooling (`auth.TOOLING`: eval runs, gate evals, journey evals, the demo exporter, tests). Never for `/api/chat` or `/api/actions/*`. | Any synthetic persona |

Rules:

- The principal is derived **server-side only** (`derive_principal`). The browser's `persona_id` is just the demo
  selector value; it is used only after the checks above.
- Conversation text ("I'm her roommate", "I'm resident R001", "borrowing a login"), the model and audience
  classification (prospect/resident wording, LLM gate) **never** change the principal.
- `demo_personas_allowed`: `DEMO_PERSONAS_ENABLED` unset means on for `APP_ENV=local` and off for `APP_ENV=hosted`.
  It is always false when hosted, and `hosted_problems()` refuses to start a hosted backend with
  `DEMO_PERSONAS_ENABLED=true`. A local deployment can switch personas off with `DEMO_PERSONAS_ENABLED=false`.
- API requests are strict: a `persona_id` on a deployment without demo personas gets **403
  `DEMO_PERSONAS_DISABLED`**, so the caller knows it was not used. Offline tooling (`strict=False`) quietly drops it.

## 2. Enforcement at the data-access layer (deny by default)

| Access point | Check |
|---|---|
| `personas.build_context(persona_id, msg, wb, *, principal)` | `principal` is required. It returns the persona's context only if `may_access_persona(principal, persona_id)`. Otherwise it returns the anonymous context (no record, no fields). Database-loaded residents (Supabase) are `Workbook` rows too, so the same check applies. |
| `chat_engine.run_turn` step 2 | Derives the principal (or takes the one the API derived). It rebinds `persona_id` / `hist_key` to the **authorized** persona only, so the later steps (`resident_for`, `plan_turn`, status lookups, history, persistence) never see an unauthorized persona id. It replaces `deps.store` with a `ScopedStore`. |
| `db.ScopedStore(store, session_id, persona_key)` | The only store the chat turn, the planner and confirm/cancel get. Reads for any other session or persona return nothing. Writes for them raise `PermissionError`. `records()` returns only records written **in this session by this persona**, whatever filter the caller passes (so `status_items(store, …, persona_id)` cannot list another session's or persona's records). It has no staff-wide listings (`conversations`, `conversation`, `gate_log`, eval runs): accessing them raises `AttributeError`. |
| `actions.resident_for` / `status_items` (planner, owned by the conversation engineer) | Receive only the authorized persona id and the scoped store (above). Synthetic history items come from `resident_for(persona_id)`, which `chat_engine` calls only when the context is a verified resident record. |
| Session binding (`session_bindings` table, `Store.bind_session`) | A session id is bound to (principal kind, persona key) on first use (atomic insert-if-absent). |
| `/api/chat` with a session bound to someone else | **Starts a new conversation** under a fresh server-issued `session_id`, returned in the response (the website adopts it). No history, drafts or records of the first session are visible. It is never a 403, so an emergency message is always answered. |
| `/api/actions/confirm`, `/api/actions/cancel` | Derive the principal and require the session binding to match. Otherwise **403 `SESSION_PERSONA_MISMATCH`**. Then they work only on the scoped store, and the draft is keyed by (session, persona) and kind. A wrong kind gets `NO_PENDING_ACTION`. Repair requests still need a verified resident context (`NOT_AUTHORIZED`). |
| Account-holder rule (`personas.apply_account_holder_rule`) | Wording-based **caution only**, kept from earlier sprints and extended to "borrowing / using someone's login or account". If it fires, the rest of the session uses no account data. It is **not** the security boundary: the principal and the scoped store are. |

## 3. Audit: every path that exposes data

| Path | Identity comes from | Returns | Guard |
|---|---|---|---|
| `GET /api/personas` | none | Synthetic persona labels (id, first name, community) | Empty list when demo personas are off (hosted) |
| `GET /api/health` | none | Counts, provider, `app_env`, `demo_personas_enabled` (no records, no secrets) | Public by design |
| `GET /api/models` | none | Configured `provider:model` targets (no keys or URLs) | Public by design |
| `POST /api/chat` → step 2 `build_context` | Server-derived principal (client `persona_id` is the demo selector only) | Allowlisted context fields, as `source_context_fields` and in the model prompt | `may_access_persona`. Hosted: 403 for any persona id. |
| `POST /api/chat` → history (`history`, `user_messages`, `last_gate`) | `session_id` (a client-generated random UUID, the bearer) + principal key | Earlier turns, given to the model and the planner | `ScopedStore` + session binding |
| `POST /api/chat` → status lookups (`status_items`, typed `DEMO-WO-…` reference, "the one for the sink", hurry/frustration) | Principal → scoped store + `resident_for` | References, short subjects, statuses, opened dates of this persona's own items | Records: this session + persona only. History items: own synthetic record only, verified resident context only. |
| `POST /api/chat` → drafts / action cards | session + principal key | Draft fields the person typed | `ScopedStore` |
| `POST /api/chat` → `identity_note`, renewal, contact preference, entry window | Context fields above | Own persona's allowlisted fields only | `build_context` |
| `POST /api/actions/confirm` / `cancel` | Server-derived principal + session binding | The saved record (own draft) | 403 on mismatch, scoped store |
| `POST /api/context/preview` | Staff guard | Any persona's minimized context | `require_staff`; `staff` principal |
| `GET /api/prototype/records`, `/api/staff/conversations[/{hash}]` | Staff guard | All prototype records, redacted turns, session hashes | `require_staff` (hosted: token required) |
| `/api/evals/*`, `/api/gates/*` | Staff guard | Eval results, gate log (persona ids, no text) | `require_staff` |
| Static snapshot `/demo/snapshot.json` (here.now preview) | Built offline by `app.export_demo` with `TOOLING` | Recorded responses for synthetic personas | Synthetic data only, by design |

## 4. Hosted vs local

| | `APP_ENV=local` (default) | `APP_ENV=hosted` |
|---|---|---|
| Demo personas | On (switch off with `DEMO_PERSONAS_ENABLED=false`) | Off. `DEMO_PERSONAS_ENABLED=true` refuses to start. |
| `/api/personas` | Synthetic list | `[]` |
| Website | Demo sign-in picker | Picker hidden; "Guest: general questions and notes to the office" (wording NEEDS McKINLEY REVIEW) |
| Customer capabilities | Per persona: status, repair requests, renewal and contact facts | Public information only: general questions, tour requests, office notes without account data. No status, no repair requests (they need a verified resident), no account fields. |
| Staff routes | Loopback, or the token if one is set | Token required (`hosted_problems` requires a strong `STAFF_API_TOKEN`) |

## 5. What is and is not protected

Protected:

- A request with another persona id, or none, cannot read a persona's context, synthetic history, records, drafts
  or conversation history. In hosted mode nobody can.
- Reusing a session id as another persona or as a guest shows nothing of the first conversation. Confirm and cancel
  are refused.
- Records of session X are never listed in session Y, even for the same persona.
- Typing another persona's reference (`DEMO-WO-…`, `I008`) reveals nothing about it.
- Conversation text cannot raise the principal.

Not protected (known gaps):

1. **No real authentication.** In a demo-enabled (local) deployment, anyone can choose any synthetic persona. This
   is by design for the demo and must never hold real data. A real deployment needs real resident sign-in that
   produces `authenticated_resident`. It is not built.
2. **The session id is a bearer secret.** Whoever has a session id *and* uses the same persona continues that
   conversation (the model sees its history). Session ids are random UUIDs generated in the browser and stored in
   `sessionStorage`. They are not signed or server-issued, except after a mismatch.
3. **Staff protection is a shared token or loopback,** not staff accounts (existing deployment blocker).
4. **Eval runs on a hosted backend** (`/api/evals/run`, staff only) call `run_turn` without a principal, so their
   personas are dropped there (anonymous). Passing `principal=auth.TOOLING` from `app/evals.py` would restore
   persona evals behind the staff guard if that is wanted.
5. The staff console's persona picker also uses `/api/personas`, so it is empty on a hosted backend.
6. The account-holder caution is wording-based and will miss phrasings. That is acceptable only because it is not
   the security mechanism.
7. `ScopedStore` uses an allowlist. A new store method used by the chat turn (for example persistent incident or
   workflow state) must be added to `ScopedStore` with the same session + persona check, or it raises
   `AttributeError`.
