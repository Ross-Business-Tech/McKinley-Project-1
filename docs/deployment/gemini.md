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
| Limits | `LLM_MAX_TOKENS` → `max_output_tokens`; `LLM_TIMEOUT_SECONDS` → request timeout; `LLM_TEMPERATURE` shared with every mode |
| Retries | SDK retries 429/500/502/503/504 on the **same** model (`LLM_MAX_RETRIES`) |
| No silent switching | served `model_version` is compared with the requested model; a different model raises `MODEL_SWITCHED` |
| Errors | auth (401/403), not found (404), rate limit (429), bad request, server, timeout, connection, truncated, blocked/refused, empty → the gateway's standard codes |
| Usage | prompt / output / thinking tokens recorded; cost left unknown (no invented prices) |

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
- Google's Gemini 3 pages give no temperature guidance; the project uses 0.2 for every mode. Re-check the current
  docs and keep one value for all A/B/C modes.
- Thinking is on by default for Gemini 3.x Flash; check whether thinking tokens consume `max_output_tokens` (4000)
  and the latency/cost impact.
- Free-tier limits and data use: free tiers may use prompts to improve products. Synthetic data only.
- Billing: the live A/B/C runner refuses Gemini without `--allow-paid`.

## First live test (after the key is set)
```bash
cd backend
uv run python -m app.live_eval.preflight                     # model listed for this key? (no tokens spent)
uv run python -m app.live_eval.abc --target gemini:gemini-3.6-flash --allow-paid --max-calls 30 --label gemini-v1
uv run python -m app.live_eval.abc --target gemini:gemini-3.6-flash --allow-paid --with-safety-classifier \
  --cases none --max-calls 30 --label gemini-safety-v1
```
Then a person reviews the `pending` records (`evals/live/`), and a **fresh** independent safety holdout is run with
`SAFETY_CLASSIFIER=auto` before anyone claims the semantic layer works (see `docs/safety/safety-evaluation.md`).
