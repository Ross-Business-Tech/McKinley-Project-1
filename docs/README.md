# Documentation

Start here: [`../README.md`](../README.md) (what it is, status, setup) → [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md)
(current state and next steps) → [`development/CLAUDE_PROJECT_GUIDE.md`](development/CLAUDE_PROJECT_GUIDE.md) (how
to work here). The project is a **prototype, not production ready**.

## Architecture
- [architecture/overview.md](architecture/overview.md) — components, endpoints, providers, context, safety, security
- [architecture/decisions.md](architecture/decisions.md) — ADR-001…011 (modes, gate, pipeline, static demo, safety, store)
- [architecture/decision-gate.md](architecture/decision-gate.md) — intent / urgency / human-required gate
- [architecture/build-vs-buy.md](architecture/build-vs-buy.md)

## Workflows
- [workflows/traceability.md](workflows/traceability.md) — **authoritative** F1–F9 / instruction / data status
- [workflows/product-spec.md](workflows/product-spec.md) — product intent and user stories
- [workflows/source-review.md](workflows/source-review.md) — the original workflow analysis (historical; findings are cited by code)

## Safety
- [safety/safety-evaluation.md](safety/safety-evaluation.md) — **authoritative** safety architecture, policy rules R1–R9e,
  independent holdout results, every remaining safety-critical failure for human review

## Evaluation
- [evaluation/README.md](evaluation/README.md) — every suite: latest result, live vs mock, command, data
- [evaluation/live-llm.md](evaluation/live-llm.md) — live A/B/C runner (blocked without a key)
- [evaluation/ux-review.md](evaluation/ux-review.md), [evaluation/usability-results.md](evaluation/usability-results.md),
  [evaluation/accessibility-review.md](evaluation/accessibility-review.md) — reviews (newest sprint first)

## Diagrams (Mermaid, validated against the code)
- [diagrams/system-architecture.md](diagrams/system-architecture.md)
- [diagrams/chat-turn-sequence.md](diagrams/chat-turn-sequence.md) — one chat turn and the confirm button
- [diagrams/safety-architecture.md](diagrams/safety-architecture.md) — layers and policy rule order
- [diagrams/conversation-routing.md](diagrams/conversation-routing.md) — planner order of checks and handoff routing
- [diagrams/data-access.md](diagrams/data-access.md) — who can see what

## Development
- [development/CLAUDE_PROJECT_GUIDE.md](development/CLAUDE_PROJECT_GUIDE.md) — conventions, tests, Definition of Done
- [development/engineering-rules.md](development/engineering-rules.md) — rules imported by `backend/` and `frontend/` CLAUDE.md
- [development/CLAUDE_MD_PROPOSED_PATCH.md](development/CLAUDE_MD_PROPOSED_PATCH.md) — proposed addition to the Ross IT root `CLAUDE.md` (not applied)
- [development/deploy-vercel-render-supabase.md](development/deploy-vercel-render-supabase.md) — put the typeable version online (Vercel + Render + Supabase)
- [development/codegraph.md](development/codegraph.md) — optional local code index

## Archive
- [archive/README.md](archive/README.md) — sprint reports, changelog, baseline (historical; numbers as of their date)

Team reference material (`docs/references/`) is kept locally and is not part of the public repository.
