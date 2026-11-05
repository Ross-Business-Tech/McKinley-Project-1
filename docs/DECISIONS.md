# Architecture Decision Records

Short records of the major decisions. Each one gives its status, context, the decision, and its consequences. Newest first.

---

## ADR-007: Static demo snapshot for the hosted site
**Status:** Accepted (2026-11-05)

**Context:** here.now hosts static files only. The browser-hosted app cannot reach the local FastAPI backend, so the published preview used to show only a connection error.

**Decision:** `uv run python -m app.export_demo` writes `frontend/public/demo/snapshot.json`. It holds 14 scenarios × 3 modes, pre-computed with the **MOCK** provider and the rules gate. The UI loads it only when the backend is unreachable, labels every response as pre-computed MOCK output, and disables free-text chat.

**Consequences:**
- Executives can click through the gate, workflow and handoff behaviour on a phone.
- No live AI runs on the hosted site.
- The snapshot holds minimized synthetic SAFE_CONTEXT values (first names, community, history subjects). That is the same class of data already committed in `evals/actual_results.json`, and never raw workbook rows.
- The snapshot must be regenerated after any change to the backend or workflows.

---

## ADR-006: Local-only backend; no hosted AI
**Status:** Accepted

**Context:** here.now has no server runtime. A here.now proxy route could hold an OpenRouter key, but it would only proxy a single model call. The gate, context adapter and safety checks are Python and must run server-side, and putting the workbook in the browser would expose it.

**Decision:** Live AI stays local: run `npm run backend:dev`, then the frontend with `NEXT_PUBLIC_API_BASE_URL`. A secure hosted backend (with auth, rate limits and secret management) is future work for Ross IT or McKinley.

**Consequences:** The demo needs a laptop running the backend to show live model output. The hosted site runs in static demo mode.

---

## ADR-005: Keep the Next.js static export; do not move to Vite
**Status:** Accepted

**Context:** The project instructions call Vite the default, but this prototype already ships a Next.js 16 app that exports static files to `dist/` (`frontend/scripts/export-static.mjs`). That export works with the protected here.now scripts and the smoke test.

**Decision:** Keep Next.js with `output: "export"`, and use no server features.

**Consequences:** There is no framework migration risk. The rule stays the same: anything that needs a server belongs in FastAPI, not in Next.js API routes.

---

## ADR-004: Optional third-party dependencies only
**Status:** Accepted

**Decision:**
- Jev uses plain `httpx`, with no `typesafe-sdk`.
- Anthropic remains an optional extra.
- Mermaid diagrams are plain Markdown. They were validated with a throwaway parser in a scratch directory, not a project dependency.
- CodeGraph is a developer tool. Its index is git-ignored, and it is not a runtime component.

**Consequences:** `uv sync` and `npm ci` stay small, and nothing requires a paid key to run the tests or the demo.

---

## ADR-003: Single-agent deterministic pipeline, not a multi-agent runtime
**Status:** Accepted

**Context:** Five business workflows could each get their own LLM "agent", and frameworks such as LangChain, LangGraph and CrewAI exist for that.

**Decision:** Use one response-generation LLM call per turn, wrapped in an ordinary-Python 10-step pipeline (`chat_engine.run_turn`). Workflows differ only in the trusted instructions and the backend-computed facts appended to the system prompt. No agent framework is used.

**Why:**
- Each workflow is a short, linear policy (classify → retrieve → instruct → check). There are no tool calls with side effects to coordinate, and no long-horizon planning.
- Ordinary functions give a typed, testable trace (`pipeline` in every response) and deterministic safety behaviour.
- One call keeps latency and free-tier usage low. Per-workflow agents would double or triple the calls and would add places where an injected instruction could steer behaviour.
- A framework would add mainly abstraction and a dependency surface. Its real benefits (durable state, tool routing, checkpointing) only matter once real integrations exist: Yardi reads, work-order writes, a staff queue.

**Revisit when:** the system must call real tools with side effects that need retries, approvals and audit (work orders, tour booking). Even then, a small state machine plus explicit authorization is likely enough.

---

## ADR-002: Rules gate as default and permanent safety floor; LLM and Jev optional
**Status:** Accepted. Details in [GATE_DESIGN.md](GATE_DESIGN.md).

**Decision:** `DECISION_GATE_PROVIDER=rules` by default. LLM and Jev gates are opt-in and can only *add* risk. Emergencies, identity, privacy and Fair Housing never depend on model confidence. Any external failure falls back to rules, and the fallback is recorded.

**Why:**
- Safety behaviour must be deterministic and auditable.
- The rules gate is free and instant.
- No live model or Jev key was available to justify a model-first gate.
- Jev requires a paid key and has an undocumented response schema.

---

## ADR-001: Three comparison modes (A/B/C)
**Status:** Accepted

**Decision:**
- **A. `baseline`:** generic prompt, with no McKinley layers.
- **B. `prompt_only`:** McKinley prompt + gate + workflow instructions, with no resident fields.
- **C. `aware`:** B plus authorized resident context.

The gate in B sees no record flags, so the difference between B and C isolates the value of resident context. The UI defaults to comparing A and C to limit model calls. The eval harness runs all three by default.
