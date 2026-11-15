# Gemini acceptance checklist (run the moment a key exists)

**Status: not run.** No Gemini (or OpenRouter) key has been available, so every step below is still open. Everything
up to step 0 is tested offline only (`tests/test_llm_providers.py`,
`tests/test_llm_providers.py`).

Rules for every step: synthetic data only; never print or paste the key; one fixed `provider:model` per result;
small `--max-calls`; Gemini always needs `--allow-paid` (billing depends on the key's Google project). Save every
output file under `evals/live/` (git-ignored, created on demand; never commit it).

## 0. Set up (once)
```bash
cd backend
# backend/.env (git-ignored):  LLM_PROVIDER=gemini   GEMINI_API_KEY=...   GEMINI_MODEL=gemini-3.6-flash
# for evaluations also pin:    GEMINI_THINKING_LEVEL=low   LLM_MAX_RETRIES=0
uv run pytest -q tests/test_llm_providers.py   # offline contract still green
```

## 1. Preflight (no tokens spent)
```bash
uv run python -m app.live_eval.preflight
```
Pass: exit 0; `gemini:gemini-3.6-flash listed for this key`; recommended model is the Gemini target.
Record: `evals/live/preflight.json`. Fail: model not listed → pick a listed model from the Google model page, do
not guess.

## 2. Bounded smoke (7 calls, hard cap 8)
```bash
uv run python -m app.live_eval.smoke --provider gemini --allow-paid --max-calls 8 --label gemini-smoke-1
```
Steps: leasing inquiry, resident maintenance (synthetic R001), 2-turn follow-up, LLM gate decision, risk
classifier, deliberate bad model id. Stops on the first 429.
Pass (exit 0): every step `pass`; `served_models` is exactly `gemini-3.6-flash` or a numbered snapshot of it; every
reply call has `parse_mode` `json` (or `json_extracted`); the bad model id gives `MODEL_NOT_FOUND`/`MODEL_BAD_REQUEST`.
Record from `evals/live/smoke-gemini-smoke-1.json`: served model string, latency per step, input/output/thinking
tokens, any error code. Exit 2 (stopped) = quota: wait, do not raise retries.

## 3. Structured-output validation (all three schemas)
Already covered by step 2: reply schema (steps 1–3), gate schema (step 4), risk schema (step 5). Check by hand in
the smoke JSON: `gate_decision.decision` has an in-vocabulary intent/urgency; `risk_classifier.classifier_status` is
`ok` (not `bad_output`/`timeout`); no `MODEL_TRUNCATED` (thinking tokens count against `max_output_tokens`: the
classifier has 800 tokens / 6 s, the gate 2000 tokens / 8 s). Any truncation or timeout here → raise the limit or
lower `GEMINI_THINKING_LEVEL` before step 5, and record which.

## 4. Workflow and safety checks beyond the smoke
The larger live runners (workflow conversations, the five-case A/B/C run, the classifier batch) were removed in the
repository simplification; they remain in Git history at `59c155c` (`backend/app/live_eval/abc.py`). Workflow and
safety behaviour is pinned by the offline suites (`backend/tests/test_conversation_*.py`, `test_safety_*.py`).
For Gemini, after steps 1–3 pass:
- run a short supervised conversation per workflow (tour, repair, note, emergency) on a local backend with
  `LLM_CALL_BUDGET` set, and record what you saw;
- run a **fresh holdout written by someone else** (not in the repo) per `docs/safety/safety-evaluation.md` before
  anyone claims the semantic layer works.

## Must NOT be claimed until the matching step passed
- "Gemini works" / "deployed with Gemini": steps 1–2.
- "Structured output is reliable on Gemini": step 3 plus step 5 with zero `text_fallback`.
- Any reply-quality or A/B/C finding: step 5 **and** human review.
- Any safety-classifier recall or "the semantic layer catches X": step 6 on a fresh independent holdout. One smoke
  sample proves plumbing only.

## Provider differences (OpenRouter vs Gemini), pinned by `tests/test_llm_providers.py`
| Topic | OpenRouter | Gemini |
| --- | --- | --- |
| System prompt | first `system` message | `system_instruction` |
| History roles | `user` / `assistant` | `user` / `model` |
| Schema field | `response_format: {type: json_schema, json_schema: {name, strict: true, schema}}` | `response_mime_type=application/json` + `response_json_schema` (no schema name) |
| Temperature | sent (`LLM_TEMPERATURE`, classifier 0) | not sent (ignored by Gemini 3.6, future models reject it) |
| Thinking tokens | `completion_tokens` already includes `reasoning_tokens`; split into `thinking_tokens` / `answer_tokens` | `candidates_token_count + thoughts_token_count`; same split |
| Cost | `usage.cost` when reported, else listing price × tokens | unknown (`None`), never invented |
| Served model | response `model` | response `model_version` (snapshot suffix like `-001` accepted) |
| Retries | app (`app.llm.http`), 429/5xx/timeouts, `Retry-After` honoured | SDK `HttpRetryOptions`, 429/500/502/503/504 |
| Errors (same codes) | 401 `MODEL_AUTH_ERROR`, 403 `MODEL_PERMISSION_DENIED`, 404 `MODEL_NOT_FOUND`, 429 `MODEL_RATE_LIMITED`, 5xx `MODEL_API_ERROR`, timeout, connection, `length` → `MODEL_TRUNCATED`, empty, `content_filter`/`refusal` → `MODEL_REFUSAL` | same codes; also 400 `API_KEY_INVALID` → `MODEL_AUTH_ERROR`, `MAX_TOKENS` → truncated, `SAFETY`/prompt block → refusal |
| Provider-only codes | 402 `MODEL_PAYMENT_REQUIRED`; errors inside a 200 body map by their numeric code | — |
| Rate limits | free models: per-minute and per-day caps per account | per-project quota (RPM/TPM/RPD) on the key's Google project |
| Model check without spending | public `/api/v1/models` (no key) | `models.list` (needs the key, no tokens) |
