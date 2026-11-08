# evals/: committed evaluation data

Index, meaning and commands: [`docs/evaluation/README.md`](../docs/evaluation/README.md).

| Path | Kind | Current? |
| --- | --- | --- |
| `five_cases.md` | the five reference cases (spec, not outputs) | current |
| `actual_results.json`, `actual_results_review.md` | the **only real-model outputs** (2026-11-01, sprint-1 pipeline) | historical, keep |
| `gate_results.json` | gate scenarios, rules/mock | reproduces on current code |
| `journey_results.json`, `.md` | 17 customer journeys, mock | reproduces on current code |
| `usability/results-sprint3.json`, `report-sprint3.md` | persona suite, mock | current |
| `usability/results-baseline.json` | persona suite before sprint 2 (`d3d64d6`), mock | historical |
| `usability/results-{after,verify-h,final-h}.json` | sprint-2 checkpoints, mock | historical |
| `live/status.json`, `preflight.json` | live A/B/C status (BLOCKED) and model availability | current |
| `live/results-mock-dryrun.json`, `report-mock-dryrun.md`, `status-mock-dryrun.json` | MOCK dry run of the live runner (plumbing only) | current |

Usability `execution` labels were recomputed on 2026-11-08 from the stored per-turn data (templates had been
miscounted as live); no conversation or score changed.
