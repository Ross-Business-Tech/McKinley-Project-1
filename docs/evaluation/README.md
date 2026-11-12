# Evaluation: what exists, what it shows, how to run it

**Read this first.** Exactly one run used a real language model (2026-11-01, sprint-1 pipeline). Every other result
below used the deterministic **mock** model or fixed backend templates, so it measures the product pipeline
(routing, questions, actions, safety rules, honesty), **not** language-model quality. "Simulated success" means a
record was saved to the prototype store, not to Yardi.

| Suite | Latest result | Model | Data | Command (from `backend/`) |
| --- | --- | --- | --- | --- |
| Sprint 10 review remediation ([report](PROTOTYPE_REVIEW_REMEDIATION.md)): independent safety holdout 61 conv. + 38 injection | false alerts 4 → 2, real alerts 22/24 (unchanged), benign injection flags 11/22 → 0/22; simulator 326 → 339/420; journeys 32 PASS / 3 WARN both | MOCK | holdout not committed | `uv run python -m app.usability.run --suite journeys --in-process` |
| Sprint 8 red-team suite (independent, frozen: 288 cases incl. 55 quick-fix traps) | full alert 67/86 (unchanged), no guidance 8 → 6, unsafe tips 2 → 0 of 40 | rules only | not committed; IDs in [SPRINT8_EMERGENCY_UX_MAINTENANCE.md](SPRINT8_EMERGENCY_UX_MAINTENANCE.md) | — |
| Sprint 9 matched journeys (7, MOCK; 5 LIVE on the first sprint commit) | words per reply 41.9 → 30.0 (MOCK), 48.8 → 31.9 (LIVE); demo-limit sentences per journey 4.6 → 2.0 (MOCK), 2.8 → 1.0 (LIVE) | mock + openrouter:nvidia/nemotron-3.5-super-vl:free | scratch transcripts, summary in [SPRINT9_WARM_VOICE.md](SPRINT9_WARM_VOICE.md) | — |
| **Sprint 7 safety holdout** (independent, frozen before implementation: 216 danger turns, 79 look-alikes, 47 ES/mixed) | 88.1% full alert, 90.7% any guidance, 10/79 look-alike full alerts; **20 turns with no guidance** (release-blocking) | rules only | not committed; results and miss IDs in [SPRINT7_GENERALIZATION.md](SPRINT7_GENERALIZATION.md) §4 | — |
| Sprint 7 live smoke | 21 OpenRouter calls through the pipeline, 0 errors | **live** (`nvidia/nemotron-3.5-super-vl:free`) | `evals/live/sprint7-live.json` (metadata only) | — |
| **Sprint 6 safety holdout** (independent, frozen before implementation: 109 danger, 42 look-alikes, 41 security) | 76% full alert, 85% any guidance, 14% look-alike full alerts, 41/41 attacks blocked at the data layer; **16 release-blocking misses** | rules only (live semantic layer rate-limited) | not committed; results and miss IDs in [SPRINT6_RESULTS.md](SPRINT6_RESULTS.md) §4 | — |
| Customer journeys, adaptive (Sprint 5.1 / 6) | 29 PASS / 6 WARN / 0 FAIL of 35 | mock | `evals/usability/journeys-s6-after.{json,md}` | `uv run python -m app.usability.run --suite journeys --label <name>` |
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
