# Safety architecture (sprint 3, updated sprint 6)

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
    DET["scan(): keyword KINDS + concept CONCEPTS<br/>+ sprint 6 concept slots (risk/concepts.py)<br/>framing: report / hypothetical / past / joking<br/>narrow negation, idioms, contractions<br/>+ conversation window, 'it's happening now'<br/>+ person-in-danger 'concern' flag"]
  end
  MSG --> SEM
  subgraph L2["Layer 2: risk/classifier.py (semantic, optional)"]
    SEM["SemanticRiskClassifier<br/>LLMGateway, structured output,<br/>strict Pydantic contract (self-contradiction rejected),<br/>timeout capped at 10 s, no retry"]
    ST{"provider ready<br/>and not mock?"}
    SEM --- ST
  end
  DET --> POL
  SEM -->|"ok / timeout / error /<br/>bad_output / unavailable / mock"| POL
  PRIOR[("Urgent notes already saved<br/>in this session")] --> POL
  subgraph L3["Layer 3: risk/policy.py (explicit rules R1-R9, R9e)"]
    POL["decide(): semantic only adds caution;<br/>never removes a rules alert or care line (Sprint 7);<br/>failure = degraded, never 'safe'"]
  end
  POL --> CAT["risk/category.py: approved notice that fits<br/>(hot car / child shut in -> medical, device smoke -><br/>electrical, fuel source + symptoms -> co)"]
  CAT --> INC
  INCDB[("Incident row (gate_decisions,<br/>mode safety_incident; no text)")] <--> INC
  INC["risk/incident.py (chat_engine 2b'):<br/>open on full alert; follow-up -> R10 alert again;<br/>quiet -> R10q calm line; resolution rules"]
  INC --> RESP["risk/responses.py<br/>approved text per category<br/>911 / 988 / Poison Help / maintenance line"]
  INC --> ESC["risk/escalation.py<br/>handoff recommendation (not sent)"]
  INC --> GATE["Decision gate: urgency raised to<br/>emergency when policy says full alert"]
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
  G -->|yes| CL7["care line: 911<br/>(988 if self-harm was alerted earlier);<br/>semantic none = conflict logged, line kept"]
  G -->|no| I{"R9: person-danger alert<br/>earlier in this session?"}
  I -->|yes| CL9["keep calm line:<br/>988 if self-harm, else 911"]
  I -->|no| NONE8["R8: no safety text"]
  FA1 --> X{"after the policy: active incident?<br/>(risk/incident.py)"}
  NONE8 --> X
  X -->|"follow-up, not self-harm"| R10["R10: full alert again (incident kind)"]
  X -->|"quiet turn, policy showed nothing"| R10Q["R10q: calm line kept"]
  X -->|"no incident / resolved"| KEEP["policy result unchanged"]
```

The normal-versus-emergency sequence is part of [chat-turn-sequence.md](chat-turn-sequence.md) (step 2b).

Sprint 6 live check (6 calls, `openrouter:nvidia/nemotron-3.5-super-vl:free`): 3 valid structured answers, 3
timeouts at 6 s (recorded as degraded; the rules alone decided). The semantic layer is therefore **not reliable
enough to carry recall** on this model. See [SAFETY_STATE_AND_EVALUATION.md](../safety/SAFETY_STATE_AND_EVALUATION.md).
The incident state machine diagram is in the same document.
