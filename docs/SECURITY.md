# Security, privacy and data handling

Who can read what, where identity comes from, and which guards are implemented, as the code stands. Main code:
`backend/app/auth.py`, `personas.py`, `db.py`, `guardrails.py`, `api/`. Tests: `backend/tests/test_authorization.py`,
`test_acceptance.py`.

> **There is no authentication in this prototype.** A "demo persona" is a synthetic account picked from a list:
> anyone who can reach a demo-enabled backend can act as any synthetic persona. That is acceptable **only** because
> every persona is synthetic. Never load real resident data.

## 1. Identity (implemented)

| Principal | Produced when | Resident data |
| --- | --- | --- |
| `anonymous` | No persona id, or an unknown one | None |
| `demo_persona` | The deployment allows demo personas **and** the id is a known synthetic persona | Its own record only |
| `staff` | `X-Staff-Token` = `STAFF_API_TOKEN`, or a loopback request on a local backend without a token | All synthetic data, on staff routes only |
| `authenticated_resident` | **Never**: reserved for a future real sign-in | — |

- **Where identity comes from:** the browser's `persona_id` is only the demo selector. Conversation text ("I'm R003",
  "I'm the manager"), model output and audience wording never change the principal.
- **When demo personas are on:**
  - on by default for `APP_ENV=local`, always off for `APP_ENV=hosted`;
  - a request that isn't straight from the machine gets them only with `DEMO_PERSONAS_ENABLED=true`;
  - otherwise a persona id gets 403 `DEMO_PERSONAS_DISABLED`.

## 2. Data access: deny by default (implemented)

| Access point | Rule |
| --- | --- |
| Resident context (`personas.build_context`) | Only if `auth.may_access_persona`; otherwise the anonymous context |
| Chat state (`db.ScopedStore`) | Bound to this session and principal. Other sessions and personas read as empty; writes raise `PermissionError`. Only staff list routes read the raw store. |
| Own requests and history | The authorized persona's own record and prototype records only; a visitor gets only this chat's own notes |
| Saved records | Belong to the persona that wrote them; another persona's reference reveals nothing |
| Session binding | A session is bound to (principal kind, persona) on first use. Someone else's session starts a new conversation; confirm and cancel get 403 `SESSION_PERSONA_MISMATCH`. Remote requests continue only a server-issued id. |
| "Not the account holder" | Persisted per session and persona; later turns get no account fields |
| Model input | Allowlisted fields only ([ARCHITECTURE.md](ARCHITECTURE.md#identity-and-scoped-data)); free text is redacted, screened and length-capped |

## 3. Guards on what is said and saved (implemented)

| Guard | What it does | Limits |
| --- | --- | --- |
| Privacy refusal (`guardrails.denied`) | Requests for another resident's data, a claimed other identity or a claimed staff role are refused **before** the model, with fixed text | Only chooses the reply; access itself is enforced by section 2 |
| Consent (`guardrails.explicit_send`, `tasks.confirm`) | Only the Send button or a whole-message "send it" saves; a question ("send it?") never does. One record per card; Send never saves a card that isn't on screen. | — |
| Reply checks (`guardrails.unsupported_claims`, `safety.output_checks`) | Claims that something was saved or sent, identity changes, unknown references, invented prices or times, contact details and secrets are replaced by backend text | Pattern based |
| Legal / fair-housing boundary (`guardrails.legal_conclusion_kind`, `legal_referral`) | A reply that states a legal determination (what the law or a landlord must, may or can't do, eligibility, a claimed right) or describes a community by who lives there is **always** replaced by a referral. A note on such a question goes to leasing (prospects) or management (residents). | **Pattern matching in EN and ES: it reduces, but cannot guarantee against, unsupported legal claims** (known miss: a Spanish paraphrase, see [TESTING.md](TESTING.md)). The referral wording is **provisional** (`pending_approval`), not approved by McKinley or legal. |
| Safety | Emergencies are assessed before the model, with fixed wording ([ARCHITECTURE.md](ARCHITECTURE.md#safety-assessment-safety-pipeline)) | Team-draft wording, **not McKinley-approved**; nobody is paged or dispatched |

Nothing reaches McKinley staff or responders. A note for the office notifies nobody. An emergency saves an urgent
prototype note and tells the person to make the call themselves. A tour request is never a booking.

## 4. Endpoints × callers

| Endpoint | Customer (anonymous or persona) | Staff |
| --- | --- | --- |
| `GET /api/personas` | The synthetic list when personas are allowed, else `[]` | same |
| `GET /api/health` | Public subset (status, provider/model, `app_env`, version/commit) | plus counts, database, prompt version |
| `GET /api/models` | Public on a local backend; `[]` on a hosted one | targets (no keys or URLs) |
| `POST /api/chat` | Customer view; diagnostics removed. `target`, `gate_provider` and non-`aware` modes are staff-only (403). | Full diagnostics |
| `POST /api/actions/confirm`, `cancel` | Own draft, in a session bound to this caller | same |
| `GET /api/prototype/records`, `/api/staff/conversations[/{hash}]` | **403** | Allowed (redacted turns, session hashes) |

## 5. Staff access
- **Who gets staff routes:** a request with `X-Staff-Token: <STAFF_API_TOKEN>`, or a loopback request on a local
  backend without a token. A hosted backend never treats loopback as staff and requires a strong token.
- **How the staff page holds the token:** it asks for the token when a staff route answers 403 and keeps it in page
  memory only, never in storage, URLs, logs or the build.
- **One shared token:** anyone with it reads every saved demo request and conversation. There are no staff accounts,
  roles or audit trail.

## 6. Hosted protections
- **Startup refusal:** `APP_ENV=hosted` refuses to start with unsafe settings (`Settings.hosted_problems`, listed in
  [DEPLOYMENT.md](DEPLOYMENT.md#3-backend-settings)).
- **What hosted hides and limits:** `/docs`, `/openapi.json` and the model list are hidden, and rate limits are on.
- **The Render demo currently runs `APP_ENV=local`**, so none of this is active there
  ([DEPLOYMENT.md](DEPLOYMENT.md#2-environments)). The U-M Toolkit approval check doesn't run either.

## 7. Secrets and data rules
- **Where secrets live:** provider keys, `DATABASE_URL` and `STAFF_API_TOKEN` only in `backend/.env` (git-ignored)
  or the host's secret settings. Check them as booleans; never print or commit them. Every `NEXT_PUBLIC_*` value is
  public.
- **Synthetic data only, everywhere:** the seeder refuses a workbook that isn't marked synthetic. Free hosted models
  may log prompts, and the repository is public.
- **Logs:** they hold status, latency, token counts and controlled reason codes, never message content or keys.
  Request bodies are capped (64 KB) and validated.
- **Prompt injection:** messages are treated as data. There is no dedicated detector (gap 8 below).

## 8. Known gaps (do not hide these)
1. **No real authentication**; the demo persona is chosen in the browser.
2. **The session id is a bearer secret** within a persona.
3. **Staff protection is one shared token**, not accounts.
4. "Not the account holder" detection is wording-based caution, not a security control.
5. `ScopedStore` is an allowlist: a new store method used by the chat turn must be added there with the same checks.
6. **Shared persona records:** on a demo-enabled deployment, anyone who picks a persona sees that persona's saved demo
   requests from every session (contact patterns masked; names typed in free text are not).
7. **The Render demo runs without the hosted protections** (section 6).
8. **No prompt-injection detector.** The defence is structural: the model only proposes, the backend decides identity,
   access, saving and the shown text, and no secret or other resident's data is in any prompt.

**Production prerequisites (not built):**
- real resident sign-in;
- staff accounts with roles and an audit log;
- real integrations, with an authorized data gateway;
- retention controls;
- McKinley-approved safety and fair-housing wording;
- legal, security and vendor review.
