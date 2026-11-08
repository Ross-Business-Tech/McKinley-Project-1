# Controlled live A/B/C evaluation

Code: `backend/app/live_eval/` (preflight, recorder, A/B/C runner). Tests: `backend/tests/test_live_eval.py`.

## Status today

Live runs are **BLOCKED**. No `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY` is configured and Ollama is not installed.
`status.json` says why. The only results here are the **MOCK DRY RUN** (`results-mock-dryrun.json`,
`report-mock-dryrun.md`). That run tests the pipeline and the recording only. It is **not** evidence about model
quality.

## After adding a key (the exact command)

Put `OPENROUTER_API_KEY=...` in `backend/.env`. The file is git-ignored, so never commit it or paste the key anywhere.
Then run from `backend/`:

```bash
uv run python -m app.live_eval.preflight && uv run python -m app.live_eval.abc --target recommended --label live-v1
```

Preflight exits with code 3 when anything blocks a live run. The `&&` means the evaluation starts only after
preflight passes. Results go to `evals/live/results-live-v1.json` and `evals/live/report-live-v1.md`.

## Preflight (free, no model call)

`uv run python -m app.live_eval.preflight` checks the following and writes `preflight.json` (no secrets in it):

- whether each provider key is present (a yes/no answer only; the key itself is never read out);
- whether each provider is ready;
- whether Ollama can be reached;
- for each OpenRouter model in `EVAL_TARGETS`, what the **public** model list says (fetched with no key). This
  covers whether the model is listed, whether it is free, its price per prompt and completion token, its context
  length, its maximum completion tokens, and whether it supports `response_format` and `structured_outputs`.

It also picks a **recommended fixed model**: the first configured OpenRouter target that is listed, free and
supports structured outputs. `--target recommended` reads that choice from `preflight.json`. The run records which
model it resolved to, so the choice is never hidden.

## The A/B/C runner

`uv run python -m app.live_eval.abc --target <provider:model | recommended | default> [flags]`

**What stays fixed across the three modes:**
- one `provider:model`;
- the same generation settings (`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, timeout, same-model retries);
- the rules decision gate, so the gate makes no extra model calls;
- a temporary database.

**The three modes:**
- A = `baseline`: a generic prompt;
- B = `prompt_only`: the McKinley prompt with no resident context;
- C = `aware`: full context.

**What it runs:**
- the five core cases, as single turns graded by `app.evals.grade`;
- persona conversations from `app/usability`, using the adaptive simulator over the real API routes in-process,
  with the mode forced per run and graded by the independent usability evaluator. The defaults are `r-ac-4th-time`,
  `p-tour-this-week` and `a-injected-history`. Use `--scenarios all` for every scenario.

**Budget and rate-limit flags:**

| Flag | Default | Meaning |
| --- | --- | --- |
| `--max-calls` | 60 | Global budget of model calls. The defaults need about 37 to 54. An item starts only if the budget left covers all of its modes, so a stopped run never leaves an unbalanced A/B/C set. |
| `--sleep` | 3 | Seconds between model calls, for free tiers. |
| `--max-rate-limit-errors` | 1 | Stop after this many 429 errors that were still failing after the gateway's bounded same-model retries. |
| `--allow-paid` | off | Needed if the model's listed price is not zero. |
| `--cases` / `--scenarios` / `--modes` | | Narrow the run. Passing a flag with no ids skips that part. |

When the budget runs out, a 429 persists, or a fatal configuration error occurs (auth, not found, payment,
connection), the run stops cleanly. It writes partial results with `run_status: "stopped"` plus the stop code, and
exits with code 2. If the provider is not ready, the run refuses with `BLOCKED`, writes `status.json` and exits with
code 3. **It never falls back to mock.** The mock target needs `--allow-mock`, and every record it produces is
labelled `MOCK`.

## Reading the results

Each chat turn record contains:
- the requested and served model;
- `prompt_version`;
- the full reply, and `raw_model_text` (what the model actually returned before validation);
- `source_context_fields`;
- tokens, latency and estimated cost (`cost_source` says whether the cost was reported by the provider or computed
  from the listed price × tokens);
- the workflow (routed workflow, action kind and stage, records) and the handoff decision;
- `safety`: every safety, emergency or care field in the response, captured generically so new fields appear
  automatically;
- `reply_source`, output checks and the automated grade;
- `human_review_status: "pending"`;
- every model call it made, under `model_calls`.

**`comparable: false`** means the record is kept but **excluded from the A/B/C comparison**.
`non_comparable_reasons` says why. Possible reasons:
- `MOCK`;
- `reply_source=template`: the deterministic reply needed no model call;
- `reply_source=template_after_validation`: the model's reply failed a critical check and was replaced;
- `reply_source=template_after_model_error`;
- `error:MODEL_TIMEOUT` and similar;
- `model_call_error:MODEL_SWITCHED`: the provider served a different model. The served ID is recorded and the
  result is discarded.

Only records that are LIVE, have a reply written by the model and made one successful call on the requested model
count in the comparison columns. Those columns are tokens, latency, cost, handoffs, false action claims and JSON
failures. Columns for validation replacements, templates and errors count all records, because these are the
reasons records were excluded. A conversation is comparable when it is LIVE, finished, and no turn had a model error
or fallback.

The mock dry-run report fills the tables from records that *would be* comparable if the run were live. This only
checks the aggregation. The numbers describe templates.

All automated grades are PROVISIONAL. A human should review the records with the most important
`raw_model_text` before anyone quotes a result.
