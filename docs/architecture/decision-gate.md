# Decision gate design

Status: rules gate **WORKING** (default). LLM gate **WORKING** through the provider abstraction, but exercised only with the mock provider in this repo, because no OpenRouter key was configured during development. Jev gate **EXPERIMENTAL**: the adapter is built from public docs and tested only against mocked HTTP.

Code: `backend/app/gates/` · tests: `backend/tests/test_gates.py` · diagrams: [conversation routing](../diagrams/conversation-routing.md), [chat turn sequence](../diagrams/chat-turn-sequence.md)

## Interface

```python
DecisionGateService.classify(message: str, ctx: GateContext, provider: str | None = None) -> GateDecision
```

`GateContext` holds only **application-established** facts:
- `audience`, from the demo persona;
- `identity_verified` and `record_found`;
- `topics`;
- `context_flags`, the names of derived record flags such as `repeat_issue_flag`;
- `prior_low_confidence`, from the session gate log.

`GateDecision` (in `backend/app/models.py`) has these fields:

| Field | Meaning |
|---|---|
| `audience` | prospect / resident / unknown. **Always the trusted audience**: a gate can never set it. |
| `intent` | leasing / maintenance / renewal / general |
| `urgency` | low / medium / high / emergency |
| `requires_human` | bool, forced true by any always-human flag |
| `handoff_reason` | staff-facing text built from flag reasons, plus the external gate's reason if one ran |
| `confidence`, `confidence_calibrated` | rules: a heuristic (0.35–0.95), `calibrated=false`. LLM: self-reported, `false`. Jev: vendor "probability concentration", `false` |
| `risk_flags` | policy indicators (list below) |
| `decision_source` | rules / llm / jev / mock |
| `requested_provider`, `fallback_used`, `fallback_reason` | what was asked for and what actually decided |
| `overrides` | each change the safety floor made to an external decision |
| `rationale`, `latency_ms`, `gate_usage` | trace, timing, and tokens/cost of the extra LLM call |

Selection: `DECISION_GATE_PROVIDER=rules|llm|jev` (default `rules`). `DECISION_GATE_LLM_TARGET=provider:model` (defaults to the chat target), `DECISION_GATE_TIMEOUT_SECONDS=8`, `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`, `JEV_MODEL`. The UI can override the provider per turn (`gate_provider` in `/api/chat`) for experiments.

## Providers

**A. Rules** (`rules.py`). Deterministic regexes on top of the existing policy patterns in `safety.py`, plus topic detection from `context.py`. It costs nothing, runs offline in under 1 ms, and is auditable. It always runs, even when another provider is selected, because it supplies the safety floor.

**B. Structured LLM** (`llm_gate.py`). One extra call through the existing `LLMGateway`, using a gate-specific JSON schema (providers gained an optional `schema` argument). The call has a short timeout and **no retries**, so it fails fast to rules. Output is validated strictly: an intent or urgency outside the vocabulary is rejected, not guessed, and unknown flags are dropped.

**C. Jev** (`jev_gate.py`). `POST {TYPESAFE_BASE_URL}/v1/systemone` with `{model, state, questions}`, using `choice` questions for intent and urgency and a `noul` question for needs_human. The contract was checked against the official docs (https://docs.typesafe.ai/api, OpenAPI at https://api.typesafe.ai/openapi.json) in Sprint 5.1. Answers come back as choice `{choice, confidence, probabilities}` and noul `{noul: 0..1}`, plus `usage` (input $0.042 per 1M tokens; output free). Anything else raises `JEV_UNEXPECTED_RESPONSE`, which falls back to rules. Two synthetic live calls succeeded in 80–150 ms, and the rules floor stayed authoritative (a gas smell remained an emergency). Without `TYPESAFE_API_KEY` it reports `JEV_NOT_CONFIGURED` and falls back. The `typesafe-sdk` package is deliberately not a dependency.

## Safety floor (`policy.py`): what no external gate can change

1. **Identity:** the audience is reset to the trusted audience. A model guess is recorded as an override and then ignored.
2. **Emergencies are deterministic:** if the rules see a hazard (gas, fire, smoke, sparks, flooding, CO; English plus basic Spanish), urgency is forced to `emergency` and intent to `maintenance`, for **any** audience, including unverified people and prospects.
3. **No downgrades:** urgency is never below the rules urgency. Risk flags are unioned, never removed.
4. **Always-human flags** (`ALWAYS_HUMAN_FLAGS` in `base.py`) force `requires_human`. These cover emergencies, explicit or soft human requests, sensitive data, fair housing/accommodation/legal, financial/lease, vouchers, unverified private requests, repeat issues or owed follow-ups in the record, and repeated low confidence.
5. **Low confidence is not "safe":** below 0.5 the decision is flagged `low_confidence` and the conversation goes to the general workflow, which asks one clarifying question. Two low-confidence turns in a row in one session add `repeated_low_confidence`, and that requires a human.
6. **No privileged actions:** gates only classify. Workflows and handoffs are computed by code, and nothing performs a side effect. `HandoffRecommendation.completed` is typed as `Literal[False]`.
7. **Fair Housing:** accommodation, disability, service-animal, discrimination, legal and voucher topics always route to staff. They are never declined by the assistant and never decided by a model.

## Risk flags

`emergency_hazard`, `human_requested`, `explicit_human_request`, `sensitive_data_request`, `fair_housing_or_legal`, `financial_or_lease`, `voucher_eligibility`, `repeat_language`, `unverified_private_request`, `message_injection_attempt` (informational), `complaint_or_frustration`, `context_repeat_issue`, `context_open_commitment`, `repeat_with_history`, `no_matched_record` (informational), `low_confidence`, `repeated_low_confidence`.

## Recorded outputs

Every non-baseline chat turn writes routing metadata to the SQLite `gate_decisions` table: intent, urgency, flags, source, fallback, workflow and latency. The **message text is never logged**. `GET /api/gates/log` returns recent entries. `POST /api/gates/evaluate {providers}` and `uv run python -m app.run_gate_evals --providers rules,llm,jev --out ../evals/gate_results.json` compare providers on the 14 labelled scenarios.

## Comparison results (2026-11-05, automated, not human-reviewed)

| Provider | Intent | Workflow | Urgency | Handoff | Critical misses | Notes |
|---|---|---|---|---|---|---|
| rules | 14/14 | 14/14 | 4/4 | 10/10 | 0 | **Circular:** the labels were written alongside the rules, so this is a regression baseline, not independent accuracy evidence. |
| llm (mock stand-in) | 12/14 | 13/14 | 4/4 | 10/10 | 0 | The mock keyword "LLM" misclassified 2 intents and under-called urgency, and the **safety floor restored urgency and handoff**. This shows the plumbing, not model quality. |
| llm (OpenRouter) | n/a | n/a | n/a | n/a | n/a | **Not run:** no `OPENROUTER_API_KEY` in this environment. All 14 calls fell back to rules with `NEEDS_API_KEY`. |
| jev | n/a | n/a | n/a | n/a | n/a | **Not run:** no `TYPESAFE_API_KEY`. All 14 calls fell back with `JEV_NOT_CONFIGURED`. |

Raw output: `evals/gate_results.json`.

## Recommendation

Keep **rules as the default and the permanent safety floor**. An LLM or Jev gate is worth enabling only where rules are weak:
- languages other than English and basic Spanish;
- paraphrased intents;
- messages that contain two requests.

Even then, it should only add to the floor, never replace it. Jev's typed choice/score/yes-no questions map cleanly onto this interface, and its vendor-reported latency (70–500 ms) is lower than a free LLM's. However, it needs a paid key, it is early access, and its data-processing terms must be reviewed before any non-synthetic message is sent (the schema is now documented and matched; see above). Evaluate it only after someone gets a key and runs `run_gate_evals --providers rules,jev` on a larger, independently labelled scenario set.

## Known limitations

- Rules are keyword based. They miss paraphrases ("it's like a sauna in here" is not detected as HVAC) and they can over-trigger: "fire" matches, though "fireplace" does not, because the pattern uses word boundaries.
- Language coverage is English plus a minimal Spanish vocabulary. Messages in other languages default to `general`, low confidence and a clarifying question. Emergencies in those languages are only caught if the LLM or Jev gate is enabled.
- Confidence values are not calibrated for any provider.
- A message with two needs is routed on the more safety-critical one (maintenance > renewal > leasing). It is not split.
- The 14 labelled scenarios are small and were written by the developers.
