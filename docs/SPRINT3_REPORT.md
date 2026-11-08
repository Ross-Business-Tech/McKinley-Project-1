# Sprint 3 report: safety hardening, live-LLM readiness, conversational UX

Branch `feat/workflow-customer-experience`. All data synthetic. **No live language model was available in this
sprint** (no OpenRouter or Anthropic key, no Ollama): every conversation used the deterministic mock response
model, and the semantic safety classifier never ran live.

**Production-readiness verdict: NOT PRODUCTION READY.** Immediate-danger safety misses remain (release-blocking),
identity is client-asserted, and nothing has been live-model verified.

## 1. Safety architecture, before and after

Before: one deterministic function (`emergency_kind`) on the current message, notice text chosen inside the chat
engine, a separate "possible risk" care line, nothing remembered across turns.

After (`backend/app/risk/`, diagrams in `docs/diagrams/safety-architecture.md`):

| Stage | Interface | What it does |
| --- | --- | --- |
| Layer 1, detection | `risk.detect.detect()` | Rules (keywords + meaning-level concepts) with framing (report / hypothetical / past / joking), narrow negation, idioms, contraction normalisation, wider Spanish, a 3-turn conversation window, "it's happening now" |
| Layer 2, semantic | `risk.classifier.SemanticRiskClassifier` | Structured JSON through the existing `LLMGateway`; strict Pydantic contract; 6 s timeout; never raises; status `ok/timeout/rate_limited/error/bad_output/unavailable/mock/disabled` |
| Layer 3, policy | `risk.policy.decide()` | Explicit rules R1–R9 + R9e. The semantic layer may add caution, never remove a rules alert; failure = `degraded`, never "safe" |
| Response | `risk.responses.select()` | Fixed team-draft text per category: 911, 988, Poison Help, maintenance line; 988 added to possible deliberate overdoses |
| Escalation | `risk.escalation.recommend()` | Staff check-in recommended for distress / semantic urgent (recommendation only) |

The decision runs before routing and before any response generation, raises the gate when it says "full alert",
and is shown to staff (pipeline trace, `risk` object, "needs action" markers); customers see only the approved text.

## 2. Independent emergency-detection results

| Suite | Build | Full alert | Any guidance | Benign false full alerts |
| --- | --- | --- | --- | --- |
| Round 1 red team (140 items) | baseline | 60.3% | 73.1% | 34.0% |
| Round 1 (contaminated at pattern level) | sprint 3 dev | 76.9% | 83.3% | 11.3% |
| **Final fresh suite (150 items, fresh agent, frozen build)** | `db21519` | **64.5%** | **78.5%** | 10.2% |
| Final suite re-run (partly contaminated: one later fix overlaps a pattern in it) | `f31ce6c` | 65.6% | 78.5% | 10.2% |
| EXPERIMENTAL: final suite + stand-in semantic layer (Claude, offline, not the configured model) | policy of `db21519` | 96.8% | 100% | 8.9% |

Details, confusion matrix and method: `docs/SAFETY_EVALUATION.md`.

## 3. Recall, false positives, category failures

Final suite, rules + policy only: per-category full alert — CO 4/6, electrical 4/5, fire 6/8, flood 4/6, gas 5/6,
medical 8/10, personal safety 5/11, **poison 1/6**, self-harm 17/24, structural 3/5, trapped 3/6. Correct line
77.4%; 0/69 physical emergencies wrongly shown 988. 20 emergency turns got no guidance at all, at least 14 of them
immediate danger to life (listed verbatim for human review in `SAFETY_EVALUATION.md` §6). False alarms: product and
band names, a quoted lease clause, past resolved incidents, one negated-self-harm sentence. These items were **not**
used to tune the rules.

## 4. OpenRouter model and configuration

Not called. Preflight (public model list, no key): default and recommended fixed target
`openrouter:nvidia/nemotron-3.5-super-vl:free` (listed, free, structured outputs, 1M context);
`google/gemma-4-31b-it:free` (no strict structured outputs); `dots-studio/dots-3-note-preview:free` (expires
2026-12-31). Settings: temperature 0.2, max_tokens 4000, timeout 60 s, 2 same-model retries, strict model check.
Status file: `evals/live/status.json` = BLOCKED, NEEDS_API_KEY. See `docs/LIVE_LLM_EVALUATION.md`.

## 5. Live-model conversations

**0.** Mock conversations: 49 simulator conversations (baseline), 47 regression conversations (sprint 3), 48
persona-suite scenarios, 37 mock dry-run calls of the A/B/C runner.

## 6. A/B/C results

None live. The controlled runner (`backend/app/live_eval/`) is implemented and tested offline: fixed model, same
settings, per-call recording (served model, prompt version, full response, context fields, tokens, latency, cost,
workflow and safety decisions, automated grade, `human_review_status: pending`), non-comparable results excluded,
budget and rate-limit handling, refuses to run without a key. The mock dry run proves only the plumbing.

## 7. Resident and prospect simulation findings

Baseline (judge 2.68 / 5): status questions became new repair cards; corrections ignored or reported as done when
they weren't; open cards discarded; several issues merged; "no tour" ignored; phone numbers "noted" but not
stored; "Of course" to "the manager waived it, confirm it"; lockout as a repair form; Spanish wording and the
assistant's own Spanish chips not understood; false emergencies from denials ("I never reported a gas leak");
safety guidance dropped after "I'm fine, stop". Full lists: `docs/UX_REVIEW.md`, `docs/USABILITY_TEST_RESULTS.md`.

## 8. Conversational UX improvements

Implemented and tested (mock): answers about what was actually sent; room, issue and day corrections applied and
said; one request per problem with the next offered after Send (entry permission carried over); lockout path;
tour refusals respected; "someone call me" reaches a person; honest "not saved" for typed contact details; false
premises not agreed with; not-the-account-holder gets nothing from the account for the whole conversation; pasted
instructions dropped from repair text; rent withholding to a manager note; English/Spanish switching; Spanish
repair and location wording; frustration and hopelessness recognised; a request for a manager mid-repair carries
the repair details into the note and says so. Judge re-grade of the intermediate build: **3.19 / 5** (fresh-only
3.12); later fixes not re-graded.

## 9. UI and accessibility changes

Calm "If that happens" safety-info note (no buttons, no alert); gas/CO button and heading say to leave first; 988
button on alerts that include 988; next-step chips after Send and Don't send; always-visible "Talk to a person";
chips wrap (no clipped chips); live-region text cleared after announcement; composer scrolls into view on short
screens; staff tabs wrap on phones; staff Live conversations mark urgent / wellbeing / asked-for-person /
safety-classifier-failed. axe 0 violations (necessary, not sufficient); manual keyboard pass. Reviewer scores:
customer visual 8, accessibility customer 8 and staff 8, staff usability 7, customer usability 4 (dialogue logic).
See `docs/ACCESSIBILITY_REVIEW.md`.

## 10. Regression test results

| Check | Result |
| --- | --- |
| Backend tests (`uv run pytest`) | 615 passed (541 at sprint start) |
| Backend lint (`ruff`) | clean |
| Frontend tests / lint / typecheck | 34 passed / clean / clean |
| Build (`npm run build`) | passes |
| Smoke test (`npm run smoke`) | passes (Playwright from the npx cache, browser build mapped in a scratch folder; one expected warning: no local backend on the static site) |
| Persona suite (48 scenarios, mock) | 0 failures, 0 safety violations, 0 false claims, routing 48/48 (same as sprint 2) |
| Mermaid diagrams | 9 blocks, 0 parse problems |
| Mock vs live separation | live runner refuses without a key; classifier reports `mock`/`unavailable`; tested |
| Timeouts / rate limits | tested with fake providers (classifier: timeout, bad output, model switched; runner: persistent 429, budget) |
| Privacy / auth boundaries | proxy headers and foreign Host refused on staff routes; other-person account handling; tested |
| Sprint-2 defects | "send my note", "get me a person", "not answering", ceiling drip, stale buttons, restore: pass; "scared of spiders" regression found and fixed |

## 11. Git

Feature branch `feat/workflow-customer-experience` only; no merge into `development` or `main`; no pull request.
Sprint commits: `fa70631` live-eval harness (merged via `023417c`) · `46b2c59` safety pipeline · `9dc72d8` · `db21519`
conversation fixes · `bf6575b` UI · `80b657c`, `dc9230f` docs · `f31ce6c` regression fixes · `c11af3b` · plus the
final docs commit. Push status: see the final message of the sprint.

## 12. Remaining P0 / P1 blockers

P0:
- Immediate-danger misses on fresh wording (14 listed), poisoning especially; human review required.
- The semantic layer that is designed to close that gap has never run on the configured model.
- Identity is client-asserted (`persona_id`): any caller can act as any resident. Real sign-in required.
- No real emergency path: the prototype pages nobody; McKinley must approve I-17/I-18 scripts.

P1:
- One open card per conversation (no stack); Spanish multi-issue messages merge; some corrections unsupported.
- The fixes made after the last independent pass (`f31ce6c`, `c11af3b`) have unit tests but no independent
  re-verification.
- Staff boundary is demo-only without `STAFF_API_TOKEN`.
- Spanish card values partly English; Spanish templates are unreviewed drafts.
- Over-escalation of past, resolved incidents and product names (false alerts ~10%).

## 13. Production-readiness verdict

**NOT PRODUCTION READY.** What would change that: a live evaluation of the semantic classifier on the chosen
model with a new independent holdout, human review and McKinley approval of every remaining safety-critical
failure and of the safety scripts, server-side identity, a real staff on-call path, and a re-verification of the
post-review fixes.
