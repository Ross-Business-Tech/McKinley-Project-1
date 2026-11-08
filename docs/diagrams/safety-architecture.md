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
  subgraph L3["Layer 3: risk/policy.py (explicit rules R1-R9)"]
    POL["decide(): semantic may only ADD caution;<br/>failure = degraded, never 'safe'"]
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
  F -->|no| G{"R7: broad danger vocabulary?"}
  G -->|yes| H{"semantic ran ok, says none,<br/>confidence >= 0.8, and no<br/>person-danger alert earlier?"}
  H -->|yes| NONE7["no safety text (recorded)"]
  H -->|no| CL7["911 care line"]
  G -->|no| I{"R9: person-danger alert<br/>earlier in this session?"}
  I -->|yes| CL9["keep calm line:<br/>988 if self-harm, else 911"]
  I -->|no| NONE8["R8: no safety text"]
```

## 3. Normal versus emergency path

```mermaid
sequenceDiagram
  participant C as Customer
  participant E as chat_engine
  participant R as risk (L1-L3)
  participant G as gate + planner
  participant M as Response model
  C->>E: message
  E->>R: assess(message, earlier turns, prior hazards)
  alt full alert
    R-->>E: decision R1/R2 (kind)
    E->>G: urgency forced to emergency
    G-->>E: fixed safety text + urgent PROTOTYPE note (no model call)
    E-->>C: safety_notice + heading + call buttons (nothing is dispatched)
  else care line / safety info
    R-->>E: decision R3-R7/R9
    E->>G: normal routing (distress: no forms)
    G->>M: only if the plan needs wording
    E-->>C: calm care_note above the reply
  else none
    R-->>E: R8
    E->>G: normal routing
    G->>M: model rewrites the backend draft (validated afterwards)
    E-->>C: reply
  end
```

The semantic classifier is **not live-verified**: in this environment no provider key exists, so every turn is
recorded as `semantic.status = mock | unavailable` and `decision.degraded = true`, and safety rests on layer 1 + the
policy alone. See `docs/SAFETY_EVALUATION.md`.
