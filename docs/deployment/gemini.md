# Gemini provider

**Status (2026-11-11): Gemini is the default chat provider in code (`LLM_PROVIDER` default `gemini`) and has been
tested live through an OpenAI-compatible university gateway (the U-M GPT Toolkit), on synthetic data only. The
deployed Render backend still runs OpenRouter; switch it only after the acceptance criteria below pass.** Google's
own Gemini Developer API path (no `GEMINI_BASE_URL`) is unchanged and still tested offline only.
Results: [evaluation/GEMINI_GATEWAY_ACCEPTANCE.md](../evaluation/GEMINI_GATEWAY_ACCEPTANCE.md).

## What it is
`backend/app/llm/gemini_provider.py` uses Google's official `google-genai` SDK (3.0.0, Gemini Developer API — a key
from Google AI Studio). It plugs into the same gateway as OpenRouter, Ollama, Anthropic and the Mock, so the chat
pipeline, the decision gate (`DECISION_GATE_PROVIDER=llm`) and the semantic safety classifier can all use it.

| Feature | How |
| --- | --- |
| System prompt + history | `system_instruction` + user/model turns; resident context arrives only as the allowlisted SAFE_CONTEXT block |
| Structured output | `response_mime_type="application/json"` + `response_json_schema` (reply schema, gate schema, safety schema) |
| Limits | `LLM_MAX_TOKENS` → `max_output_tokens` (thinking tokens count against it); `LLM_TIMEOUT_SECONDS` → request timeout |
| Temperature | **not sent** to Gemini: Google's "What's new in Gemini 3.6" says temperature/top_p/top_k are ignored and future models return 400; recorded as `null` |
| Thinking | `GEMINI_THINKING_LEVEL` = minimal / low / medium / high pins the level (empty = model default, recorded as such) so a server default change can't alter an evaluation |
| Retries | SDK retries 429/500/502/503/504 on the **same** model (`LLM_MAX_RETRIES`) |
| No silent switching | served `model_version` is compared with the requested model; a different model raises `MODEL_SWITCHED` |
| Errors | 401 and 400 `API_KEY_INVALID` → `MODEL_AUTH_ERROR`, 403 → `MODEL_PERMISSION_DENIED` (same as OpenRouter), not found (404), rate limit (429), bad request, server, timeout, connection, truncated, blocked/refused, empty → the gateway's standard codes |
| Usage | prompt tokens; output = visible answer + thinking (billed), both also recorded separately; cost left unknown (no invented prices) |
| Network errors | the SDK uses `httpx2`; timeouts and connection errors from either httpx family map to `MODEL_TIMEOUT` / `MODEL_CONNECTION_ERROR`; anything else to `MODEL_API_ERROR` (never a raw 500) |

## Configure
```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=            # backend only (backend/.env locally, Render secret when hosted); never in the website
GEMINI_BASE_URL=           # empty = Google's API via google-genai; set = an OpenAI-compatible gateway (see below)
GEMINI_MODEL=gemini-3.6-flash
GEMINI_THINKING_LEVEL=low  # measured: see "Thinking" below
LLM_MODEL=                 # empty = use GEMINI_MODEL
```

## Through an OpenAI-compatible gateway (`GEMINI_BASE_URL`)
Some organisations put Gemini behind their own gateway (for example the U-M GPT Toolkit, which ITS provides; its
address and key come from ITS or the instructor and are **not** committed here). With `GEMINI_BASE_URL` set, the
adapter (`_complete_gateway` in `app/llm/gemini_provider.py`) does not use the Google SDK. The contract below was
checked with real calls on 2026-11-11, not assumed:

| Feature | Gateway behaviour (verified) |
| --- | --- |
| Endpoint | `POST {GEMINI_BASE_URL}/chat/completions`, `Authorization: Bearer <GEMINI_API_KEY>`; `GET /models` lists 48 models incl. `gemini-3.6-flash` |
| Messages | OpenAI roles; the system prompt is the first `system` message |
| Structured output | `response_format: {type: json_schema, json_schema: {name, strict: true, schema}}` is honoured (all 165 live reply calls parsed as JSON) |
| Thinking | `reasoning_effort` is forwarded to Gemini's `thinking_level` (an invalid value returns Google's `thinking_level` 400). `minimal` / `low` work. `reasoning_effort: none`, `thinking: {type: disabled}` and Google's native `thinking_config` are accepted but **ignored** (300-400 thinking tokens) |
| Usage | `completion_tokens` includes `completion_tokens_details.reasoning_tokens` (OpenAI convention) |
| Served model | `model` echoes `gemini-3.6-flash`, so the `MODEL_SWITCHED` check works |
| Errors | wrong key → 401 (`Portkey Error: Invalid API Key`) → `MODEL_AUTH_ERROR`; unknown model → 404 → `MODEL_NOT_FOUND`; truncation → `finish_reason: length` → `MODEL_TRUNCATED`; occasional 503 / slow responses are retried on the same model |
| Privacy | the gateway address never appears in errors, `/api/health` or logs; a hosted backend refuses a non-`https` `GEMINI_BASE_URL` |

`python -m app.live_eval.preflight` lists the gateway's models (no tokens) when `GEMINI_BASE_URL` is set.

**Thinking (measured on the real app prompts, 2026-11-11).** The model default spends ~750 hidden thinking tokens per
reply (median 4.9 s). `low`: 0-380 thinking tokens, reply median 1.3-2.8 s, natural wording. `minimal`: never thinks,
fastest, but sometimes robotic ("Preferred days: Friday.", a duplicated sentence). The safety classifier gave the same
results at all three levels on a small synthetic set. **Use `GEMINI_THINKING_LEVEL=low`.**

**Data use.** The gateway was provisioned for this course by Ross IT / ITS. This project has **not** verified that it
is approved for real resident data: send synthetic data only, as everywhere else in this repository.

## Switching the Render backend from OpenRouter to Gemini (do this only after acceptance passes)
The live service (`mckinley-backend`, branch `development`, auto-deploy on commit) takes its settings from the Render
**Dashboard → Environment**, not from `render.yaml`. Since 2026-11-11 a hosted backend **refuses to start** unless
`LLM_PROVIDER` is set explicitly, so a release can never switch provider silently (a refused start leaves the
previous deploy serving).
1. Before merging the Gemini code into `development`: confirm the Dashboard has `LLM_PROVIDER=openrouter` (it is the
   documented live value). If it is missing, add it first, or the next deploy will refuse to start.
2. When acceptance passes, in the Dashboard add `GEMINI_API_KEY` (secret), `GEMINI_BASE_URL` (secret, the gateway
   address ending in `/v1`), `GEMINI_MODEL=gemini-3.6-flash`, `GEMINI_THINKING_LEVEL=low`.
3. Change `LLM_PROVIDER` to `gemini` and **delete** `LLM_MODEL` (or set it to `gemini-3.6-flash`): with
   `LLM_MODEL=nvidia/nemotron-…` the app refuses `LLM_PROVIDER=gemini` on purpose. Keep `OPENROUTER_API_KEY` so
   rolling back is one variable change.
4. Save and deploy. Check `GET /api/health`: `provider: gemini`, `model: gemini-3.6-flash`, `provider_ready: true`.
5. Send 3-5 synthetic messages on the public site (a tour, a repair as a guest, "talk to a person") and read the
   replies. Roll back by setting `LLM_PROVIDER=openrouter` and `LLM_MODEL=nvidia/nemotron-3.5-super-vl:free`.
Cost: each chat turn makes up to two Gemini calls (reply + safety classifier, ~2,000 + ~700 input tokens); the
gateway key has a monthly budget set by ITS, and a public site spends it on every visitor.

**Model choice.** `gemini-3.6-flash` is listed as a stable model in Google's model documentation (checked
2026-11-10). Alternatives on the same page: `gemini-3.8-flash` (newest Flash, labelled "new"), `gemini-3.5-flash-lite`
(cheaper). `gemini-2.5-flash` / `-pro` are deprecated and re-route on 1 December 2026 — do not use them. Confirm the
model exists for your key **without generating anything**: `uv run python -m app.live_eval.preflight`.

## Open questions (Google's direct API path)
- Through the gateway, `minimal` and `low` work and `low` is pinned (above). On the gateway the safety classifier
  timed out 4 times and got one 503 in 251 calls at `low` (6 s cap; the rules still applied); on Google's direct API this is still unmeasured.
- The served `modelVersion` format (the gateway accepts `gemini-3.6-flash` and numbered snapshots like `-001`).
- SDK retries (429/5xx) happen inside one call: latency includes them and quota is per project. For live
  evaluations consider `LLM_MAX_RETRIES=0` and let the runner stop on the first 429.
- **Data use:** on the free tier Google may use content to improve products and humans may review it ("do not
  submit sensitive, confidential, or personal information"). Synthetic data is fine, but a public hosted demo sends
  whatever visitors type: use a billed key for public hosting, or say so on the site. Free tier is not offered in
  the EEA, Switzerland or the UK.
- The semantic safety classifier's `confidence` is model-written and is never used to remove guidance: since Sprint
  7 the classifier can only add caution (the old R7 exception is gone). In the first live run, review how often it
  disagrees with the rules (logged as a conflict) and how often it times out.
- Billing: the live A/B/C runner refuses Gemini without `--allow-paid`.

## First live test (after the key is set)
Full step-by-step list with pass/fail criteria: [`GEMINI_ACCEPTANCE_CHECKLIST.md`](../development/GEMINI_ACCEPTANCE_CHECKLIST.md).
```bash
cd backend
uv run python -m app.live_eval.preflight                     # model listed for this key? (no tokens spent)
uv run python -m app.live_eval.smoke --provider gemini --allow-paid --max-calls 8   # 7 bounded calls, real app path
uv run python -m app.live_eval.abc --target gemini:gemini-3.6-flash --allow-paid --max-calls 30 --label gemini-v1
uv run python -m app.live_eval.abc --target gemini:gemini-3.6-flash --allow-paid --with-safety-classifier \
  --cases none --max-calls 30 --label gemini-safety-v1
```
Then a person reviews the `pending` records (`evals/live/`), and a **fresh** independent safety holdout is run with
`SAFETY_CLASSIFIER=auto` before anyone claims the semantic layer works (see `docs/safety/safety-evaluation.md`).

## Provider contract (OpenRouter and Gemini behave the same to the app)
`tests/test_provider_contract.py` runs one parametrised suite against three adapters (OpenRouter over
`httpx.MockTransport`, Gemini over a fake `google-genai` client, Gemini through the gateway over
`httpx.MockTransport`, the Mock where meaningful); `tests/test_gemini_gateway.py` pins the gateway request shape: system prompt delivery,
history order and roles, each app schema passed as structured output (`app.llm.contracts`: reply, gate, risk), the
same text parsing to the same `ModelOutput`, normalised usage (thinking counted in output tokens), served model and
`MODEL_SWITCHED`, identical error codes / retryable flags / HTTP statuses, and the real callers (`LLMGate`,
`SemanticRiskClassifier`, `run_turn`) on each adapter. Genuine differences are asserted explicitly, not skipped:
temperature (OpenRouter only), schema name (OpenRouter only), cost (OpenRouter only; Gemini `None`), who retries
(app vs SDK), provider-only errors (402 and errors inside a 200 body on OpenRouter; `API_KEY_INVALID` and prompt
blocks on Gemini). The differences table is in the [acceptance checklist](../development/GEMINI_ACCEPTANCE_CHECKLIST.md).
All of this is offline evidence about the adapters, not about Gemini's behaviour on a real key.
