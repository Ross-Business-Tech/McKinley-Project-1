# Evaluation: what exists, what it shows, how to run it

**Read this first.** Exactly one run used a real language model (2026-11-01, sprint-1 pipeline). Every other result
below used the deterministic **mock** model or fixed backend templates, so it measures the product pipeline
(routing, questions, actions, safety rules, honesty), **not** language-model quality. "Simulated success" means a
record was saved to the prototype store, not to Yardi.

| Suite | Latest result | Model | Data | Command (from `backend/`) |
| --- | --- | --- | --- | --- |
| **Safety holdout** (independent, fresh 150 items) | 64.5% full alert, 78.5% any guidance, 10% benign false alerts; **release-blocking misses** | rules only (semantic layer not live) | not committed (held by the independent evaluator); method and verbatim failures in [safety-evaluation.md](../safety/safety-evaluation.md) | — |
| Five-case eval (A/B/C) | historical real run: Nemotron 10 replies, Gemma 10 rate-limit errors (2026-11-01, sprint-1 pipeline, human verdicts empty) | **live (historical)** | `evals/actual_results.json`, review `evals/actual_results_review.md`; cases `evals/five_cases.md` | `uv run python -m app.run_evals [--targets …] [--cases …]` (5 cases × 3 modes) |
| Gate scenarios | rules gate 14/14 (reproduced on current code) | rules / mock | `evals/gate_results.json` | `uv run python -m app.run_gate_evals --providers rules --out ../evals/gate_results.json` |
| Customer journeys | C: 17/17 tasks, routing and handoff correct | mock | `evals/journey_results.{json,md}` | `uv run python -m app.journey_evals --target mock:mock-deterministic-v1` |
| Persona usability suite (48 scenarios, 25 personas) | 15 success, 22 simulated, 7 blocked, 4 partial, 0 failure, 0 safety violations | mock | `evals/usability/results-sprint3.json` (current), `results-baseline.json` (before sprint 2); `after`, `verify-h`, `final-h` are sprint-2 checkpoints | `uv run python -m app.usability.run --in-process --label <name>` |
| Adaptive simulators + UX judge (sprint 3) | conversational UX 2.68 → 3.19 / 5 | mock | transcripts not committed; summary in [ux-review.md](ux-review.md) | — |
| Live A/B/C runner | **BLOCKED** (`NEEDS_API_KEY`); mock dry run only | — / mock | `evals/live/status.json`, `results-mock-dryrun.json` | see [live-llm.md](live-llm.md) |

Reviews: [ux-review.md](ux-review.md) · [usability-results.md](usability-results.md) ·
[accessibility-review.md](accessibility-review.md). Historical sprint reports: [../archive/](../archive/README.md).

Rules for anything new: label mock vs live at the record level; a template or fallback reply is never "live"
(`usability/evaluator.turn_source`); keep holdout sets out of the repository and out of development; never tune on
a set and then report it as held-out.
