# Implementation changelog

Newest first. Current branch: `feat/workflow-customer-experience`, branched from `feat/agentic-workflow-gates` (which already contains `origin/development`).

Status legend used throughout: **WORKING** · **SIMULATED** (prototype store) · **MOCKED** · **EXPERIMENTAL** · **NOT IMPLEMENTED**

---

## Phase 7: workflow-driven customer experience (branch `feat/workflow-customer-experience`)

| Commit | What changed |
| --- | --- |
| `c4dd68e` | Backend action planner mapping every turn to F1–F9. Confirm-before-save prototype records (DEMO-WO/TOUR/TASK), F4 knowledge base with approved-only answers, SMS/email channel rules, Spanish draft templates, validation enforcement, model-timeout fallback. |
| `e818361` | Customer view `/` (read-back cards, AI disclosure, emergency alert, status list, error and preview states) and staff and demo console `/staff/` (turn inspector, saved requests, F1–F9 coverage, A/B/C comparison, evaluations). 17 recorded journeys for the static preview. |
| `782383d` | Round-1 review fixes: emergency classifier (`app/emergency.py`), honest consent and corrections, atomic confirm, redaction, UI state system, tap-to-call, EN/ES strings, accessibility. Traceability matrix, five diagrams, journey evaluation. |
| `907331b` | Round-2 review fixes and regressions: more hazards and fewer false alarms, anchored consent, merged notes, Fair Housing family/religion/disability wording, label-first card grid, unclipped focus rings. |
| (final commit) | Round-3 review fixes: restored crisis patterns (guns, stalking, stroke signs, poisoning, entrapment), second rooms no longer overwrite the first, bare "no" after sending is a goodbye; docs. |

- **Tests:** backend 123 → **296** (pytest), frontend 22 → **27** (vitest). Lint and typecheck clean; `npm run smoke` passes on `/` and `/staff/` at desktop and phone sizes; axe 0 violations in 10 journey states.
- **Independent review:** six session-scoped reviewer subagents (UI, UX, resident simulator, prospect simulator, accessibility, backend safety) over three rounds. See `UX_REVIEW.md`, `USABILITY_TEST_RESULTS.md` and `ACCESSIBILITY_REVIEW.md`.
- **Diagrams:** all five rewritten to match the code (`system-architecture`, `customer-workflows`, `sequence`, `handoff-decision-tree`, `data-access`); 7 Mermaid blocks parse with `mermaid@11.4.1` (scratch install), and a broken control fails.
- **Evaluation:** the five core cases are preserved (routing now graded on `routed_workflow`). New `app/journey_evals.py`: 17 multi-turn journeys × A/B/C, **PROVISIONAL, mock model**. Results are in `evals/journey_results.md`.
- **Not done:** live-model runs (cost), real authentication, notifications, telephony; see the remaining tasks in `UX_REVIEW.md`.

## Phase 6: documentation, diagrams, final review
- **What:** added
  - `IMPLEMENTATION_BASELINE.md`, `GATE_DESIGN.md`, `DECISIONS.md` (7 ADRs) and `CODEGRAPH.md`;
  - four Mermaid diagrams in `docs/diagrams/`;
  - a v2 pointer in `ARCHITECTURE.md`, plus README sections and limitations;
  - gate settings in `backend/.env.example`.
- **Why:** the owner should be able to understand the system from the docs alone.
- **Diagram validation:** every Mermaid block (including `ARCHITECTURE.md`) parses with `mermaid@11.4.1`. The parser was installed in a scratch directory, not as a project dependency. A deliberately broken diagram fails the same check, which shows the check catches errors.
- **Diagrams updated:** all four (new).

## Phase 4: frontend diagnostics, three modes, static demo (commit `c497429`)
- **What:** frontend/UX work by a subagent working only under `frontend/src`.
  - Mode toggles A/B/C, defaulting to A and C so each send costs fewer model calls.
  - A per-turn gate selector that shows each gate's availability as reported by the server.
  - Scenarios grouped into "Core five" and "Extended".
  - The emergency safety notice appears above the reply.
  - A handoff card reading "Recommended — not sent", with the delivery note.
  - A collapsed "Why this answer" diagnostics panel: gate, overrides, flags, workflow, triage/lead/renewal, context provenance, 10-step trace, model and checks.
  - A Decision-gates comparison in the Evaluation tab.
  - Static demo mode, driven by `frontend/public/demo/snapshot.json`.
- **Why:** executives need to see *why* the assistant answered as it did without cluttering the customer reply. The hosted site is static and cannot reach a backend.
- **Real vs simulated:**
  - MOCK badges appear on every mock response.
  - A "mock" gate source is labelled as a stand-in.
  - "No work order created (no integration)" is shown on maintenance answers.
  - The demo banner says no live AI is running.
- **Tests run:**
  - `npm run lint`: 0 errors.
  - `npm run typecheck`: 0 errors.
  - `npm test`: **22 passed**.
  - `npm run build`: OK.
  - `npm run smoke` was **SKIPPED**: Playwright is not installed on this machine.
  - As a substitute, headless Chrome (puppeteer-core, run from a scratch directory) checked 390 px and 1366 px:
    - Demo mode (no backend): the emergency scenario shows the safety notice and the "not sent" handoff, with no horizontal scroll and no page errors.
    - Live mode against the backend with the mock provider: free-text R008 "leaking again, fourth time" → management handoff, repeat issue.
- **Not done:**
  - No here.now preview was published, because the owner asked to keep everything local.
  - The `/api/gates/log` client call exists but is not shown in the UI.
- **Diagrams:** `architecture.md` and `sequence.md` already include the static demo path.

## Phase 5b: QA hardening (commit `20f602b`)
- **What:** fixes for the 11 findings from an independent QA/security review (a subagent with read-only access).
  - **Critical:** common emergency phrasings were missed ("it smells like gas", "I smell smoke", alarms going off, Spanish flooding/burning). Now detected for every audience.
  - **High:** "issue" matched the lawsuit pattern (`sue\b`), so any sink "issue" was routed to management as a legal case. Accommodation requests that avoided the keywords were missed. Malformed LLM/Jev output could cause an HTTP 500 instead of a fallback.
  - **Medium/Low:**
    - a NaN confidence was read as 1.0;
    - the gate log exposed raw session ids, which key chat history;
    - fullwidth and zero-width characters could slip past the patterns;
    - false alarms ("sparkling", "humorous", "flood zone");
    - missed action-claim phrasings;
    - offer negation matched "no" inside "piano";
    - urgency was not graded;
    - nothing could stop browser-chosen paid gates;
    - whitespace-only messages were accepted.
- **Modules:** `safety.py`, `gates/{rules,service,llm_gate,jev_gate}.py`, `chat_engine.py`, `db.py`, `models.py`, `config.py`, `api/gates.py`, `evals.py`.
- **User-visible:** more emergencies get the safety notice. Ordinary "issue" messages stay in the maintenance flow. Accommodation requests go to staff.
- **Tests:** 24 new regression tests built from the reviewer's exact inputs. **123 passed**, and ruff is clean.
- **New risk:** broader accommodation and "accessible" matching will send some harmless accessibility questions to staff (an intentional bias toward caution).
- **Diagrams:** conversation-flow and data-flow already described the intended behaviour; no change needed.

## Phase 5: evaluation (in commits `cee4f9a` and `20f602b`)
- **What:**
  - 9 extended eval cases (emergency, repeat leak with owed follow-up, unverified identity, sensitive data, low confidence, explicit human request, injection in retrieved history, renewal affordability, Spanish resident). **The original five are unchanged.**
  - Modes A, B and C in the harness (default runs = 5 core × 3 modes).
  - A new `6_routing` criterion.
  - A gate comparison harness: `app/gate_evals.py`, `run_gate_evals` CLI, `/api/gates/evaluate`.
- **Results (automated, not human-reviewed):**
  - **Rules gate:** 14/14 intent, 14/14 workflow, 4/4 urgency, 10/10 handoff, 0 critical misses. This is a regression baseline only: the labels were written alongside the rules.
  - **Mock "LLM" gate:** 12/14 intent. The safety floor kept urgency and handoff at 100%.
  - **Real OpenRouter and Jev:** **not run**, because no keys were configured. All calls fell back to rules, and each fallback was recorded.
- **Live response-quality comparison of A/B/C:** **NOT RUN.** `backend/.env` is absent, so no model could be called. Mock output was not substituted as evidence.

## Phase 2–3: orchestration pipeline, decision gate, workflows (commit `cee4f9a`)
- **What:**
  - `app/gates/`: the rules, structured-LLM and experimental Jev gates; a safety floor; and a service with fallback.
  - `app/workflows.py`: workflow selection, maintenance triage with an approved troubleshooting allowlist, lead intent scoring, and renewal assessment.
  - `app/handoff.py`: a structured recommendation (team, priority, minimal summary, contact guidance) that is never sent.
  - `chat_engine.run_turn` rewritten as a traced 10-step pipeline, with the new `prompt_only` mode.
  - Providers accept an optional JSON schema.
  - New output checks: invented offers, prompt/secret leakage, emergency guidance.
  - A deterministic emergency safety notice.
  - Low-confidence-twice escalation.
  - An unverified-identity private-request flag.
  - Minimal Spanish vocabulary.
  - An injection-test fixture persona.
  - A gate decision log (no message text).
  - `/api/gates/*` endpoints.
  - A static demo exporter.
  - `docs/WORKFLOW_REVIEW.md`, a review of the team's 9 reference workflow modules by a workflow-analyst subagent.
- **Why:** the five business workflows needed explicit routing, a deterministic safety floor and a structured handoff. Per ADR-003, all of this uses ordinary Python with one response LLM call per turn.
- **Design finding during testing:** "Can someone explain my choices?" (case 5) triggered the human-request pattern and would have hijacked the renewal workflow. Explicit demands for a person are now handled separately from soft requests.
- **Tests:** 46 → 99 passing (now 123).
- **Risks:** rules are keyword based (they miss paraphrases and other languages). The Jev response parsing is unverified against the live API.

## Phase 0–1: inspection, branch, review (no code change)
- Confirmed the repo (`Ross-Business-Tech/McKinley-Project-1`) and fetched `origin/development` and `origin/main`. `origin/development` = `fb710d7`, the parent of the existing AI commit `c9c77c1`.
- Created `feat/agentic-workflow-gates` from `c9c77c1`. This keeps the previous feature branch's work and still sits on the latest development.
- Left uncommitted local tooling untouched: `.claude/settings.json` (Ross IT-managed), `.claude/CLAUDE.md`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`, `.codex/`, `.cursor/`, `.gemini/` and `.codegraph/`.
- Opened the reference artifact; it was accessible, and its content is reviewed in WORKFLOW_REVIEW.md. Researched Jev feasibility (a key is required; see GATE_DESIGN.md).
