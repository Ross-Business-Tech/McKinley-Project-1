# Documentation

Start here: [`../README.md`](../README.md) (what it is, status, setup) → [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md)
(current state and next steps) → [`development/CLAUDE_PROJECT_GUIDE.md`](development/CLAUDE_PROJECT_GUIDE.md) (how
to work here). The project is a **prototype, not production ready**.

## Deployment (Render + Supabase, Gemini later; prepared, not deployed)
- [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md) — status, missing access, checklist, blockers
- [INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md) — can a phone open a public link and chat? (not yet)
- [design/BRAND_SYSTEM.md](design/BRAND_SYSTEM.md) — McKinley colours, type, components, contrast
- [design/MOBILE_UX_AUDIT.md](design/MOBILE_UX_AUDIT.md) — viewport matrix, findings, fixes, open issues
- [design/TASTE_SKILL_REVIEW.md](design/TASTE_SKILL_REVIEW.md) — which design skills were used and how
- [IMPLEMENTATION_CHANGELOG.md](IMPLEMENTATION_CHANGELOG.md) — what changed in each sprint and what was tested
- [evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md](evaluation/SPRINT5_1_CUSTOMER_JOURNEYS.md) — Sprint 5.1: live OpenRouter journeys, simulators, judges, fixes, remaining failures
- [evaluation/SPRINT5_LIVE_CONVERSATION.md](evaluation/SPRINT5_LIVE_CONVERSATION.md) — Sprint 5: what is verified with OpenRouter (nothing yet), with Mock, Gemini-ready
- [architecture/CONVERSATION_STATE.md](architecture/CONVERSATION_STATE.md) — conversation state, card lifecycle, tour states
- [development/GEMINI_ACCEPTANCE_CHECKLIST.md](development/GEMINI_ACCEPTANCE_CHECKLIST.md) — what to run the moment a Gemini key exists
- [deployment/gemini.md](deployment/gemini.md) · [deployment/supabase.md](deployment/supabase.md) (migrations, seed) ·
  [deployment/render.md](deployment/render.md) · [security/SUPABASE_AUTH.md](security/SUPABASE_AUTH.md) (sign-in)

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
- [development/deploy-render-supabase.md](development/deploy-render-supabase.md) — put the typeable, signed-in version online (Render + Supabase)
- [development/codegraph.md](development/codegraph.md) — optional local code index

## Archive
- [archive/README.md](archive/README.md) — sprint reports, changelog, baseline (historical; numbers as of their date)

Team reference material (`docs/references/`) is kept locally and is not part of the public repository.
