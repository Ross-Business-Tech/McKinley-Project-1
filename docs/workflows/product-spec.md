# Product Requirement Document — MVP 1

## Decision context
McKinley owns/manages about 14,000 apartments in ~52 properties and currently uses Yardi's 24/7 AI. Joshua reports ~50–60% human handoff at many properties, but this is not a satisfaction measure. He wants a more context-sensitive assistant without a large maintenance team. His criterion: **Is it actually better for the customer?**

## Goal
Demonstrate whether a contextualized LLM assistant improves *resident/prospect response appropriateness*, especially empathy, informed next steps, and appropriate escalation, vs. the same model used generically. The LLM provider is not yet chosen; the prototype compares models across providers (OpenRouter, Ollama; others pluggable). Avoid claiming production ROI from 5 synthetic cases.

## MVP P0 user stories
1. As a McKinley reviewer, I can choose a synthetic prospect/resident and view a limited, sanitized context summary.
2. I can type a message and get a response in two side-by-side modes: baseline and McKinley-aware.
3. A prospect receives professional, helpful, time-sensitive sales support, without fictitious price/availability claims.
4. A resident gets high-empathy service based on *relevant* maintenance/contact history, not generic apologies.
5. Escalation reason is surfaced for safety, repeats, unresolved tickets, policy uncertainties, human requests, and property-office follow-up.
6. I can run five scripted test cases and mark each answer Good/Bad with evidence and reviewer notes.
7. I can view a simple outcomes dashboard: good count, failure categories, appropriate human escalation, latency, token usage and estimated API spend if available.

## Out of scope
Phone/SMS/email integrations; Yardi writebacks; Databricks live data; work orders created in Yardi; promises of dispatch; staff notifications; auth for real residents; automatic prompt self-editing; live unit pricing or leasing offers; autonomous actions.

## Critical business constraints
- Residents are often cost-conscious workforce renters. Speak clearly and respectfully; never stereotype.
- Every property accepts housing vouchers, per Joshua, but eligibility and case-specific details should be verified by human staff.
- McKinley terminology: **beds**, not **bedrooms**; **floor plans**, not **unit types**.
- Sales tone = professional, proactive, sensible urgency; resident retention/service = patient, high empathy, listening and questions.
- Multilingual support should be possible; respond in the user's language when confident and offer a human otherwise.
- Financial, accommodation, discrimination, legal, and lease disputes should not receive improvised guarantees or determinations.
- Fair housing: do not steer or discriminate based on protected characteristics; language rules alone do not guarantee compliance.

## Five-case demo
See `docs/workflows/five_cases.md`: high-intent prospect, generic prospect, repeated AC repair, first-time leaky faucet, renewal / preferred communication. Ensure at least one human-handoff case and one unknown-data case.

## Acceptance checklist
- [ ] Full stack runs with documented commands.
- [ ] XLSX import validates columns and handles missing values.
- [ ] No raw email, phone, sensitive notes, full-history transcript or financial data in AI context by default.
- [ ] Baseline/aware outputs are clearly labeled; no fake/mock responses shown as real model executions.
- [ ] Five model executions recorded with timestamps, provider + model identifier, configurable temperature, prompt version, latency, tokens (when reported) and Good/Bad judgments; multiple models comparable side by side without silent model switching.
- [ ] If key is absent, UI indicates setup required, not silently simulated responses.
- [ ] No side-effect actions; escalation is a **recommendation**, not a completed handoff.
- [ ] Tests cover terminology, context relevance, safety, data leakage, model errors, and response schema.
