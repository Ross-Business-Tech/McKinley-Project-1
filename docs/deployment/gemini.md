# Gemini provider

**Status: implemented and tested offline only.** No Gemini key was available, so no request has been sent to
Google; nothing here is evidence of Gemini's reply quality or of the model ID working on your key.

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
GEMINI_MODEL=gemini-3.6-flash
LLM_MODEL=                 # empty = use GEMINI_MODEL
```

**Model choice.** `gemini-3.6-flash` is listed as a stable model in Google's model documentation (checked
2026-11-10). Alternatives on the same page: `gemini-3.8-flash` (newest Flash, labelled "new"), `gemini-3.5-flash-lite`
(cheaper). `gemini-2.5-flash` / `-pro` are deprecated and re-route on 1 December 2026 — do not use them. Confirm the
model exists for your key **without generating anything**: `uv run python -m app.live_eval.preflight`.

## Open questions to settle with a key
- Which thinking levels `gemini-3.6-flash` accepts (Google's pages disagree); pin one with `GEMINI_THINKING_LEVEL` for
  evaluations, and check that the safety classifier (800 tokens, 6 s) and gate (2000 tokens, 8 s) don't time out or
  truncate with thinking on — otherwise the semantic layer is mostly `degraded`.
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
`tests/test_provider_contract.py` runs one parametrised suite against both adapters (OpenRouter over
`httpx.MockTransport`, Gemini over a fake `google-genai` client, the Mock where meaningful): system prompt delivery,
history order and roles, each app schema passed as structured output (`app.llm.contracts`: reply, gate, risk), the
same text parsing to the same `ModelOutput`, normalised usage (thinking counted in output tokens), served model and
`MODEL_SWITCHED`, identical error codes / retryable flags / HTTP statuses, and the real callers (`LLMGate`,
`SemanticRiskClassifier`, `run_turn`) on each adapter. Genuine differences are asserted explicitly, not skipped:
temperature (OpenRouter only), schema name (OpenRouter only), cost (OpenRouter only; Gemini `None`), who retries
(app vs SDK), provider-only errors (402 and errors inside a 200 body on OpenRouter; `API_KEY_INVALID` and prompt
blocks on Gemini). The differences table is in the [acceptance checklist](../development/GEMINI_ACCEPTANCE_CHECKLIST.md).
All of this is offline evidence about the adapters, not about Gemini's behaviour on a real key.
