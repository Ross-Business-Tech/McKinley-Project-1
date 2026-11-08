# Journey evaluation (mock:mock-deterministic-v1, MOCK) — PROVISIONAL

PROVISIONAL automated grading. With the MOCK target this measures the backend pipeline (routing, actions, safety net), not language-model quality. Empathy/tone needs human review.

| Metric | A baseline | B prompt only | C with context |
| --- | --- | --- | --- |
| journeys | 17 | 17 | 17 |
| task_completed | 2/17 | 17/17 | 17/17 |
| routing_correct | 0/17 | 17/17 | 17/17 |
| handoff_correct | 5/12 | 12/12 | 12/12 |
| context_reused | 0/1 | 0/1 | 1/1 |
| language_correct | 1/1 | 1/1 | 1/1 |
| false_action_claims | 0 | 0 | 0 |
| critical_check_failures | 0 | 0 | 0 |
| avg_user_turns | 1.59 | 1.65 | 1.65 |
| total_latency_ms | 411 | 369 | 334 |
| total_cost_usd | 0.0 | 0.0 | 0.0 |
| errors | 0 | 0 | 0 |

| Journey | Mode | Completed | Routing | Handoff | Context reused | False claims | Turns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| res-repeat-ac | baseline | False | False | False | None | 0 | 2 |
| res-repeat-ac | prompt_only | True | True | True | None | 0 | 3 |
| res-repeat-ac | aware | True | True | True | None | 0 | 3 |
| res-renewal | baseline | False | False | True | None | 0 | 1 |
| res-renewal | prompt_only | True | True | True | None | 0 | 1 |
| res-renewal | aware | True | True | True | None | 0 | 1 |
| res-human | baseline | False | False | True | None | 0 | 1 |
| res-human | prompt_only | True | True | True | None | 0 | 1 |
| res-human | aware | True | True | True | None | 0 | 1 |
| res-gas | baseline | False | False | True | None | 0 | 1 |
| res-gas | prompt_only | True | True | True | None | 0 | 1 |
| res-gas | aware | True | True | True | None | 0 | 1 |
| res-text-pref | baseline | False | False | False | False | 0 | 3 |
| res-text-pref | prompt_only | True | True | True | False | 0 | 3 |
| res-text-pref | aware | True | True | True | True | 0 | 3 |
| res-spanish | baseline | False | False | True | None | 0 | 2 |
| res-spanish | prompt_only | True | True | True | None | 0 | 2 |
| res-spanish | aware | True | True | True | None | 0 | 2 |
| res-status | baseline | False | False | False | None | 0 | 1 |
| res-status | prompt_only | True | True | True | None | 0 | 1 |
| res-status | aware | True | True | True | None | 0 | 1 |
| unverified-status | baseline | False | False | False | None | 0 | 1 |
| unverified-status | prompt_only | True | True | True | None | 0 | 1 |
| unverified-status | aware | True | True | True | None | 0 | 1 |
| pro-tour-week | baseline | False | False | True | None | 0 | 2 |
| pro-tour-week | prompt_only | True | True | True | None | 0 | 2 |
| pro-tour-week | aware | True | True | True | None | 0 | 2 |
| pro-price | baseline | True | False | None | None | 0 | 2 |
| pro-price | prompt_only | True | True | None | None | 0 | 2 |
| pro-price | aware | True | True | None | None | 0 | 2 |
| pro-new-to-area | baseline | False | False | None | None | 0 | 1 |
| pro-new-to-area | prompt_only | True | True | None | None | 0 | 1 |
| pro-new-to-area | aware | True | True | None | None | 0 | 1 |
| pro-floor-plans | baseline | True | False | None | None | 0 | 1 |
| pro-floor-plans | prompt_only | True | True | None | None | 0 | 1 |
| pro-floor-plans | aware | True | True | None | None | 0 | 1 |
| pro-incomplete | baseline | False | False | None | None | 0 | 4 |
| pro-incomplete | prompt_only | True | True | None | None | 0 | 4 |
| pro-incomplete | aware | True | True | None | None | 0 | 4 |
| pro-steering | baseline | False | False | False | None | 0 | 1 |
| pro-steering | prompt_only | True | True | True | None | 0 | 1 |
| pro-steering | aware | True | True | True | None | 0 | 1 |
| pro-change-tour | baseline | False | False | None | None | 0 | 2 |
| pro-change-tour | prompt_only | True | True | None | None | 0 | 2 |
| pro-change-tour | aware | True | True | None | None | 0 | 2 |
| pro-human | baseline | False | False | False | None | 0 | 1 |
| pro-human | prompt_only | True | True | True | None | 0 | 1 |
| pro-human | aware | True | True | True | None | 0 | 1 |
| vendor | baseline | False | False | False | None | 0 | 1 |
| vendor | prompt_only | True | True | True | None | 0 | 1 |
| vendor | aware | True | True | True | None | 0 | 1 |
