# Safety architecture (sprint 3)

Reflects `backend/app/risk/` and its use in `backend/app/chat_engine.py` on `feat/workflow-customer-experience`.
Safety is decided **before** routing and before any response generation, and no later step (the response model,
the customer's instructions or retrieved records) can lower it. The safety text is fixed team-draft wording
(I-17/I-18, not McKinley-approved); no model writes it.

## 1. Layers and their separate interfaces

```mermaid
flowchart TB
  MSG["Incoming message<br/>(cleaned: tags stripped, PII redacted)"] --> DET
  HIST[("Earlier user turns<br/>(this session, last 3)")] --> DET
  HIST --> SEM
  subgraph L1["Layer 1: risk/detect.py (deterministic)"]
    DET["scan(): keyword KINDS + concept CONCEPTS<br/>framing: report / hypothetical / past / joking<br/>narrow negation, idioms, contractions<br/>+ conversation window, 'it's happening now'"]
  end
  MSG --> SEM
  subgraph L2["Layer 2: risk/classifier.py (semantic, optional)"]
    SEM["SemanticRiskClassifier<br/>LLMGateway, structured output,<br/>strict Pydantic contract, 6 s timeout, no retry"]
    ST{"provider ready<br/>and not mock?"}
    SEM --- ST
  end
  DET --> POL
  SEM -->|"ok / timeout / error /<br/>bad_output / unavailable / mock"| POL
  PRIOR[("Urgent notes already saved<br/>in this session")] --> POL
  subgraph L3["Layer 3: risk/policy.py (explicit rules R1-R9, R9e)"]
    POL["decide(): semantic never removes a rules alert<br/>(may drop only the broad 911 line, R7);<br/>failure = degraded, never 'safe'"]
  end
  POL --> RESP["risk/responses.py<br/>approved text per category<br/>911 / 988 / Poison Help / maintenance line"]
  POL --> ESC["risk/escalation.py<br/>handoff recommendation (not sent)"]
  POL --> GATE["Decision gate: urgency raised to<br/>emergency when policy says full alert"]
  GATE --> PLAN["actions.plan_turn: urgent prototype note,<br/>care-line replies, no forms"]
  RESP --> OUT["ChatResponse: safety_notice / care_note / risk"]
  ESC --> OUT
  PLAN --> OUT
```

## 2. Conflict resolution (policy rules, first match wins)

Authoritative rule table with conditions: [safety-evaluation.md §2](../safety/safety-evaluation.md).

```mermaid
flowchart TD
  A{"R1: deterministic emergency<br/>(message or window)?"} -->|yes| FA1["FULL ALERT, rules' category.<br/>Semantic 'none' is recorded as a conflict,<br/>never applied. Semantic self-harm adds 988."]
  A -->|no| B{"R2: semantic emergency,<br/>or urgent + immediate danger?"}
  B -->|yes| FA2["FULL ALERT, semantic category"]
  B -->|no| C{"R3: self-harm words<br/>with a laughing marker?"}
  C -->|yes| CL3["988 care line (never silent)"]
  C -->|no| D{"R4: semantic urgent/uncertain<br/>with a category?"}
  D -->|yes| CL4["category care line;<br/>staff check-in for self-harm / urgent"]
  D -->|no| E{"R5: hazard framed as<br/>hypothetical or past?"}
  E -->|yes| INFO["calm safety info:<br/>same steps, no alarm, no note"]
  E -->|no| F{"R6: distress / unwell words?"}
  F -->|yes| CL6["988 line (distress, staff check-in)<br/>or 911-if-worse; semantic cannot remove"]
  F -->|no| E9{"R9e: danger words AND an earlier<br/>threat/medical/poison/trapped alert?"}
  E9 -->|yes| FA9["FULL ALERT again (same kind)"]
  E9 -->|no| G{"R7: broad danger vocabulary?"}
  G -->|yes| H{"semantic ran ok, says none,<br/>confidence >= 0.8, and no<br/>person-danger alert earlier?"}
  H -->|yes| NONE7["R7-suppressed: no safety text (recorded)"]
  H -->|no| CL7["care line: 911<br/>(988 if self-harm was alerted earlier)"]
  G -->|no| I{"R9: person-danger alert<br/>earlier in this session?"}
  I -->|yes| CL9["keep calm line:<br/>988 if self-harm, else 911"]
  I -->|no| NONE8["R8: no safety text"]
```

The normal-versus-emergency sequence is part of [chat-turn-sequence.md](chat-turn-sequence.md) (step 2b).

The semantic classifier is **not live-verified**: in this environment no provider key exists, so every turn is
recorded as `semantic.status = mock | unavailable` and `decision.degraded = true`, and safety rests on layer 1 + the
policy alone. See `docs/safety/safety-evaluation.md`.
