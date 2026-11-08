# Live LLM evaluation (sprint 3)

**Status: BLOCKED. No live-model conversation was run in this sprint.** No `OPENROUTER_API_KEY` or
`ANTHROPIC_API_KEY` exists in the shell or in `backend/.env` (checked as booleans only; no key was printed), and
Ollama is not installed. Nothing below is language-model quality evidence. Nothing silently fell back to mock:
the live runner refuses to start without a key and writes `evals/live/status.json` saying so.

| Item | State |
| --- | --- |
| Live-model conversations run | **0** |
| Mock conversations (pipeline only) | 48 persona-suite scenarios (in-process), 49 adaptive simulator conversations (baseline build), ≥12 regression conversations (frozen sprint-3 build), 37 mock dry-run calls in the A/B/C runner |
| Semantic safety classifier on a live model | **Not run** (see `docs/SAFETY_EVALUATION.md` §5 for an offline, clearly labelled stand-in experiment) |

## 1. Configuration verified without spending (`evals/live/preflight.json`)

`uv run python -m app.live_eval.preflight` reads OpenRouter's **public** model list (no key needed) and reports key
presence as booleans.

| Configured target | Listed | Free | Structured outputs | Context | Note |
| --- | --- | --- | --- | --- | --- |
| `openrouter:nvidia/nemotron-3.5-super-vl:free` (default) | yes | yes | yes | 1M | **recommended fixed model** for the controlled comparison |
| `openrouter:google/gemma-4-31b-it:free` | yes | yes | no (`response_format` only) | 262k | expect more JSON-contract failures |
| `openrouter:dots-studio/dots-3-note-preview:free` | yes | yes | yes | 512k | listed as expiring 2026-12-31 |
| `ollama:llama3.2` | – | – | – | – | Ollama not reachable |

Generation settings shared by every mode: temperature 0.2, max_tokens 4000, timeout 60 s, 2 same-model retries
(429 / 5xx / timeout), strict model check (`MODEL_SWITCHED` discards a result served by another model).

## 2. Controlled A/B/C runner (`backend/app/live_eval/`, implemented and tested, not run live)

- **A** generic baseline prompt, **B** McKinley prompt without resident context, **C** McKinley prompt + authorized
  SAFE_CONTEXT. One fixed `provider:model`, identical generation settings, rules gate (no extra model calls), a
  temporary database per run.
- Per model call it records: requested and **served** model ID, prompt version, full response, context fields
  supplied, tokens in/out, latency, estimated cost, workflow decision (route, card kind/stage, records), handoff,
  every safety field on the response including the sprint-3 `risk` object, `reply_source`, output checks, the
  automated grade and `human_review_status: "pending"`.
- A record is `comparable: false` (kept, but excluded from A/B/C comparisons) when the reply came from a template,
  a validation replacement or a model-error fallback, when the provider served another model, or when it is MOCK.
- Free-tier limits: global `--max-calls` budget (default 60), `--sleep` between calls (default 3 s), a clean stop
  with partial results on a persistent 429; an item only starts if the budget covers all its modes.
- The semantic safety classifier is pinned **off** in A/B/C runs (it would add a call per turn and change the
  budget); `--with-safety-classifier` runs it on the same fixed model.
- Tests: `backend/tests/test_live_eval.py` (13, offline with fake transports): blocked without a key and no mock
  fallback, persistent 429 stops cleanly, timeout recorded as an error, MODEL_SWITCHED excluded, mock dry run labelled
  and non-comparable, budget respected, preflight parsing and network failure.

The MOCK dry run (`evals/live/report-mock-dryrun.md`) proves the recording and aggregation only.

## 3. What a teammate runs once a key exists

```
cd backend
# add OPENROUTER_API_KEY=... to backend/.env (never commit it)
uv run python -m app.live_eval.preflight
uv run python -m app.live_eval.abc --target recommended --label live-v1
uv run python -m app.live_eval.abc --target recommended --label live-v1-safety --with-safety-classifier --cases none
```

Then: have a person review the `pending` records, and run a **fresh** independent safety holdout with
`SAFETY_CLASSIFIER=auto` before claiming anything about the semantic layer. Free hosted models may log prompts;
send only synthetic data.

## 4. Implemented and tested vs not

| | Status |
| --- | --- |
| Provider abstraction, strict model check, bounded same-model retries | Implemented and tested (earlier sprints) |
| Preflight against the public model list | Implemented, run (network, no key) |
| A/B/C runner, budget, comparability rules | Implemented and tested offline; mock dry run only |
| Semantic safety classifier through the gateway | Implemented and tested with fake providers; **not live-verified** |
| Live A/B/C results, token/cost/latency on a real model | **Blocked** (no key) |
| Human review of live outputs | Not started (nothing to review) |
