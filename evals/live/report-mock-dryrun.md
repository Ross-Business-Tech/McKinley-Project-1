# MOCK DRY RUN — not model evidence

> **MOCK DRY RUN.** Every reply came from deterministic templates. This proves the pipeline and recording only; it says nothing about language-model quality. All records are `comparable: false`.

- Label `mock-dryrun`, 2026-11-08T08:21:14+00:00 → 2026-11-08T08:21:14+00:00; run status **completed**
- Requested `mock:mock-deterministic-v1`; served models seen: ['mock-deterministic-v1']
- Generation: {'temperature': 0.2, 'max_tokens': 4000, 'timeout_seconds': 60.0, 'max_retries_same_model': 2}; gate: rules (deterministic; no gate model calls)
- Prompt versions: {'baseline': 'baseline-v1#0eaa993f', 'prompt_only': 'mckinley-v0.1+oc1#dc9454e1+wf-v1+noctx', 'aware': 'mckinley-v0.1+oc1#dc9454e1+wf-v1+ctx'}
- Budget: 37/60 model calls, 0s between calls
- Comparable = LIVE, reply written by the model, its single model call succeeded on the requested model. Templates, validation replacements, model errors/fallbacks, MODEL_SWITCHED and MOCK are recorded but excluded from the comparison columns (tokens, latency, cost, handoffs, false claims).
- All automated grades are PROVISIONAL; `human_review_status` is `pending` on every record.

## All chat turns (cases + conversation turns)

| Mode | Records | Would-be comparable (MOCK) | Excluded | Errors | Templates | Validation replacements | Model-error fallbacks | Auto GOOD / graded | Handoffs | False action claims | JSON failures | Tokens in | Tokens out | Latency avg ms | Cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A baseline | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 4/5 | 3 | 0 | 0 | 1044 | 350 | 17 | 0 |
| B prompt_only | 16 | 13 | 3 | 0 | 3 | 0 | 0 | 3/5 | 5 | 0 | 0 | 11456 | 331 | 16 | 0 |
| C aware | 15 | 12 | 3 | 0 | 3 | 0 | 0 | 2/5 | 7 | 0 | 0 | 11205 | 388 | 12 | 0 |

## Five core cases (single turn)

| Mode | Records | Would-be comparable (MOCK) | Excluded | Errors | Templates | Validation replacements | Model-error fallbacks | Auto GOOD / graded | Handoffs | False action claims | JSON failures | Tokens in | Tokens out | Latency avg ms | Cost USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A baseline | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 4/5 | 3 | 0 | 0 | 464 | 168 | 19 | 0 |
| B prompt_only | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 3/5 | 4 | 0 | 0 | 4533 | 169 | 17 | 0 |
| C aware | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 2/5 | 4 | 0 | 0 | 4765 | 184 | 11 | 0 |

## Conversations (adaptive persona simulator, independent evaluator)

| Mode | Run | Complete | Would-be comparable (MOCK) | Success | Partial | Blocked | Failure | Handoff ok | False claims | Safety violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A baseline | 3 | 3 | 3 | 0 | 0 | 0 | 3 | 2 | 0 | 0 |
| B prompt_only | 3 | 3 | 3 | 2 | 1 | 0 | 0 | 3 | 0 | 0 |
| C aware | 3 | 3 | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 0 |

Outcome columns count comparable conversations only (LIVE, complete, no model error or fallback). MOCK DRY RUN: columns use would-be-comparable records to exercise the aggregation; the numbers describe templates, not a model.

## Per conversation

| Scenario | Mode | Outcome | Turns | Comparable | Notes |
| --- | --- | --- | ---: | --- | --- |
| r-ac-4th-time | baseline | failure | 3 | False | no maintenance_request card; other records: []; routing: expected one of ['maintenance'], saw [] |
| r-ac-4th-time | prompt_only | simulated_success | 4 | False |  |
| r-ac-4th-time | aware | simulated_success | 4 | False |  |
| p-tour-this-week | baseline | failure | 2 | False | no tour_request card; other records: []; routing: expected one of ['leasing', 'tour_request'], saw [] |
| p-tour-this-week | prompt_only | partial | 4 | False | saved record lacks: ['thursday'] |
| p-tour-this-week | aware | simulated_success | 3 | False |  |
| a-injected-history | baseline | failure | 2 | False | no maintenance_request card; other records: []; routing: expected one of ['maintenance'], saw [] |
| a-injected-history | prompt_only | simulated_success | 3 | False |  |
| a-injected-history | aware | simulated_success | 3 | False |  |

## Per case

| Case | Mode | Reply source | Auto verdict | Comparable | Excluded because |
| --- | --- | --- | --- | --- | --- |
| case1_high_intent_prospect | baseline | model | GOOD | False | MOCK |
| case1_high_intent_prospect | prompt_only | model | GOOD | False | MOCK |
| case1_high_intent_prospect | aware | model | GOOD | False | MOCK |
| case2_price_shopper | baseline | model | GOOD | False | MOCK |
| case2_price_shopper | prompt_only | model | GOOD | False | MOCK |
| case2_price_shopper | aware | model | GOOD | False | MOCK |
| case3_repeat_ac_R001 | baseline | model | BAD | False | MOCK |
| case3_repeat_ac_R001 | prompt_only | model | GOOD | False | MOCK |
| case3_repeat_ac_R001 | aware | model | BAD | False | MOCK |
| case4_faucet_no_record | baseline | model | GOOD | False | MOCK |
| case4_faucet_no_record | prompt_only | model | BAD | False | MOCK |
| case4_faucet_no_record | aware | model | BAD | False | MOCK |
| case5_renewal_contact_R003 | baseline | model | GOOD | False | MOCK |
| case5_renewal_contact_R003 | prompt_only | model | BAD | False | MOCK |
| case5_renewal_contact_R003 | aware | model | BAD | False | MOCK |
