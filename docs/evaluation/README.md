# Evaluation summary

Exactly one recorded run compared real language models end to end (2026-11-01, sprint-1 pipeline); a few later
bounded live checks are noted below. Everything else used the deterministic **mock** model or fixed templates, so
it measures the product pipeline (routing, questions, actions, safety rules, honesty), **not** language-model
quality. "Saved" means saved to the prototype store, not to Yardi or any McKinley system.

## How to check the app today
| What | How (from `backend/` unless noted) | Model |
| --- | --- | --- |
| Deterministic regressions: conversation, workflows, safety, authorization, API/persistence, providers, gate | `uv run pytest` (domain modules in `backend/tests/`) | mock / offline |
| Focused safety verification | `uv run pytest tests/test_safety_detection.py tests/test_safety_pipeline.py tests/test_risk_policy_table.py`, then a **fresh holdout written by someone else** ([safety-evaluation.md](../safety/safety-evaluation.md)) | rules (+ classifier if live) |
| Manual provider check (no spend) | `uv run python -m app.live_eval.preflight` | none |
| Manual provider smoke (≤ 8 calls) | `uv run python -m app.live_eval.smoke --provider <p> [--allow-paid] --max-calls 8` | **live** |
| Frontend | from `frontend/`: `npm run lint && npm run typecheck && npm test && npm run build`; from the root: `npm run smoke` | mock |

Live-check output goes to `evals/` at the repository root, which is git-ignored and created on demand; nothing there
is committed.

## Recorded results (newest first; full reports are in Git history at `59c155c`)
| Result | Model | Where |
| --- | --- | --- |
| Sprint 10 review remediation: independent holdout 61 conversations + 38 injection singles — false alerts 4 → 2, real alerts 22/24 (unchanged), benign injection flags 11/22 → 0/22; customer simulator 326 → 339/420 | MOCK | [PROTOTYPE_REVIEW_REMEDIATION.md](PROTOTYPE_REVIEW_REMEDIATION.md) |
| Gemini through the U-M gateway: not accepted for the deployed site yet | **live** | [GEMINI_GATEWAY_ACCEPTANCE.md](GEMINI_GATEWAY_ACCEPTANCE.md) |
| Sprint 9 matched journeys: words per reply 41.9 → 30.0 (MOCK), 48.8 → 31.9 (LIVE) | mock + live (nemotron) | `SPRINT9_WARM_VOICE.md` (history) |
| Sprint 8 red-team suite (288 frozen cases): full alert 67/86, no guidance 8 → 6, unsafe tips 2 → 0 of 40 | rules only | `SPRINT8_EMERGENCY_UX_MAINTENANCE.md` (history) |
| **Sprint 7 safety holdout** (216 danger turns, 79 look-alikes): 88.1% full alert, 90.7% any guidance; **20 turns with no guidance (release-blocking)** | rules only | `SPRINT7_GENERALIZATION.md` §4 (history) |
| Sprint 7 live smoke: 21 OpenRouter calls through the pipeline, 0 errors | **live** | [sprint7-live-smoke-metadata.json](../archive/evaluation/sprint7-live-smoke-metadata.json) |
| **Sprint 6 safety holdout** (109 danger, 42 look-alikes, 41 security): 76% full alert, 85% any guidance, 41/41 attacks blocked; **16 release-blocking misses** | rules only | `SPRINT6_RESULTS.md` §4 (history) |
| **Sprint 3 safety holdout** (150 fresh items): 64.5% full alert, 78.5% any guidance; **release-blocking misses** | rules only | [safety-evaluation.md](../safety/safety-evaluation.md) |
| Five-case A/B/C (the one real comparison): Nemotron 10 replies, Gemma 10 rate-limit errors; human verdicts empty | **live (historical)** | [five-case live run](../archive/evaluation/five-case-live-run-2026-11-01.md); cases in [five_cases.md](../workflows/five_cases.md) |

Holdout sets are never committed (they are held by their independent authors). Other reviews:
[accessibility-review.md](accessibility-review.md).

## Rules for anything new
Label mock vs live per record; a template or fallback reply is never "live"; keep holdout sets out of the repository
and out of development; never tune on a set and then report it as held out; don't commit generated output.
