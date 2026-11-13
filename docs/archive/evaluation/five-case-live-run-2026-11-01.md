# Five-case evaluation — real OpenRouter run (2026-11-01)

Raw outputs: `docs/archive/evaluation/five-case-live-run-2026-11-01.json` (run #2). Everything below refers to **actual model outputs**, not the reference examples in `five_cases.md` and not Mock output.

## Setup (identical for both modes)
| Setting | Value |
|---|---|
| Provider / model | `openrouter` / `nvidia/nemotron-3.5-super-vl:free`. The served model ID matched the request on all 10 calls; no switching. |
| Temperature / max tokens | 0.2 / 4000 |
| Prompts | baseline `baseline-v1#0eaa993f`; aware `mckinley-v0.1+oc1#dc9454e1` (+ SAFE_CONTEXT) |
| Runs | 1 sample per case × mode (10 calls), sequential |
| Comparison model | `google/gemma-4-31b-it:free`: all 10 calls returned **429 (upstream provider rate limit)** after same-model retries. Recorded as errors; not substituted. |

## Verdicts
"Provisional" = automated checks (after the grader fix described below). "AI review" = rubric judgment by Claude Code reading each reply. **Neither is a human verdict.** McKinley reviewers should confirm or override them in the dashboard (Good/Bad + notes), which writes `human_verdict`.

| Case | Mode | Provisional | AI review | Rationale |
|---|---|---|---|---|
| 1 High-intent prospect | baseline | BAD | **BAD** | Says "2-bedroom"; "I'll connect you with our leasing team… and set up the tour" claims an action the prototype can't take. Sales tone and next-step question are good. |
| 1 | aware | GOOD | **GOOD** | "two-bed floor plans", no invented availability or times, clear next step. Minor: offers to "pass your request along" (no such integration) and assumes an "Ann Arbor leasing team". |
| 2 Price shopper | baseline | BAD | **BAD** | "1-bedroom"; deflects to the website with no follow-up question. No invented prices (good). |
| 2 | aware | GOOD | **GOOD** | "1-bed floor plan", explicitly no live pricing, asks which Florida community. Minor: "connect you with them" offer. |
| 3 Repeat AC (R001) | baseline | BAD | **BAD** | Empathetic, but "I'll escalate this to our maintenance team so a technician can inspect" is a **false action claim** (critical). No history, as expected for baseline. |
| 3 | aware | GOOD | **GOOD** | Uses first name, acknowledges the repeated history, states it can't open a request, recommends staff follow-up, honours text/morning preference. Gap: doesn't mention emergency maintenance if the heat becomes unsafe. |
| 4 Faucet drip, no record | baseline | BAD | **BAD (borderline)** | Safe ("don't fix it yourself") but curt: no acknowledgement, no low-risk interim steps. Fails tone. |
| 4 | aware | GOOD | **GOOD** | Matches the reference: close the handle, towel/container, don't disassemble, contact maintenance, one follow-up question. Doesn't pretend to know history. |
| 5 Renewal + contact (R003) | baseline | BAD | **BAD** | "I've noted your preference… we'll reach out by email or text" fabricates a staff commitment (critical). Generic option list. Stray trailing "reply" token in the output. |
| 5 | aware | GOOD | **GOOD** | Empathetic, no pricing claims, references the pending 9-month option (from verified context), reflects "text first, no calls before 10 AM", recommends the leasing office. |

**Score:** McKinley-aware 5/5 GOOD, generic baseline 0/5 GOOD (same model, same settings). Both modes recommended a handoff in 4 of 5 cases. Aware handoffs carried specific reasons (repeat issue, open commitment, financial/lease, leasing follow-up).

## Cost / latency (free tier, $0 billed)
| Mode | Avg latency | Input tokens (5 calls) | Output tokens (5 calls, incl. hidden reasoning) |
|---|---|---|---|
| baseline | 4.7 s | 814 | 3,262 |
| aware | 9.7 s | 5,742 | 6,411 |

The aware prompt plus context uses about 7× the input tokens and roughly doubles latency. Case 5 aware took 20 s.

## Grader fix during this run
The first automated pass marked case 3 and case 5 baseline as GOOD because the false-action check missed "I'll escalate", "we'll reach out" and curly apostrophes (`I’ve`). The check was widened (with regression tests from these exact phrasings), and stored replies were **re-graded without new model calls**: `uv run python -m app.run_evals --regrade 2`.

## Limitations
- 5 synthetic cases × 1 sample: a functional demonstration, not statistical evidence. Temperature 0.2 is not deterministic, so re-runs can differ.
- Automated tone and personalization checks are keyword heuristics; human review is required.
- Only one model produced outputs. The Gemma comparison was blocked by upstream rate limits. `dots-studio/dots-3-note-preview:free` answered a JSON probe correctly and is the recommended second comparison target.
- Free OpenRouter endpoints may log prompts. Only synthetic data was sent.
- Not covered live: multilingual (R012 Spanish), emergencies (gas/flood), injection attempts and explicit human requests. These are covered by deterministic tests only.
