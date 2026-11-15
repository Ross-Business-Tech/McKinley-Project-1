# Archive: the pre-MVP design (before the 2026-11 MVP reset)

These documents describe the code **before** the MVP reset: the ordered planner (`actions.plan_turn`), the decision
gate (rules / LLM / Jev), the structured understanding layer, the workflow state machine, quick-fix draft tips, and
the evaluations run on that pipeline. They are kept unchanged as a record; file names, settings and numbers in them
do not describe the current code. The current design is [../../architecture/overview.md](../../architecture/overview.md).

| Document | What it described |
| --- | --- |
| [architecture/CONVERSATION_ORCHESTRATION.md](architecture/CONVERSATION_ORCHESTRATION.md) | The planner's order of checks and orchestration |
| [architecture/CONVERSATION_STATE.md](architecture/CONVERSATION_STATE.md) | Conversation state, card lifecycle, tour states |
| [architecture/WORKFLOW_STATE_MACHINE.md](architecture/WORKFLOW_STATE_MACHINE.md) | The explicit workflow state machine |
| [architecture/decision-gate.md](architecture/decision-gate.md) | Intent / urgency / human-required decision gate |
| [diagrams/chat-turn-sequence.md](diagrams/chat-turn-sequence.md) | The 11-step chat turn |
| [diagrams/conversation-routing.md](diagrams/conversation-routing.md) | Planner routing and handoff |
| [workflows/QUICKFIX_DRAFT_KB.md](workflows/QUICKFIX_DRAFT_KB.md) | Draft quick-fix repair tips (removed) |
| [evaluation/PROTOTYPE_REVIEW_REMEDIATION.md](evaluation/PROTOTYPE_REVIEW_REMEDIATION.md) | Sprint 10 independent review and remediation |
| [evaluation/GEMINI_GATEWAY_ACCEPTANCE.md](evaluation/GEMINI_GATEWAY_ACCEPTANCE.md) | Gemini through the U-M gateway acceptance (not accepted) |
