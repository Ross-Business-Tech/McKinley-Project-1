# Conversation flow: gate → workflow → handoff

Mirrors `select_workflow` (`backend/app/workflows.py`), `classify_rules` (`backend/app/gates/rules.py`) and
`build_handoff` (`backend/app/handoff.py`). The order of the checks matters: the first matching branch wins.

```mermaid
flowchart TD
  M["Message + trusted persona"] --> MODE{"Mode?"}
  MODE -->|"A baseline"| BASE["Generic prompt only<br/>no gate, no workflow<br/>handoff = model's own opinion"]
  MODE -->|"B prompt_only / C aware"| GATE["Decision gate<br/>(rules always run; LLM/Jev optional + safety floor)"]

  GATE --> E{"urgency = emergency?<br/>(gas, fire, smoke, sparks, flooding, CO;<br/>any audience, EN + basic ES)"}
  E -->|yes| EMER["Maintenance workflow, EMERGENCY triage<br/>safety notice: leave, call 911 / emergency line<br/>no troubleshooting<br/>handoff → emergency_maintenance, URGENT"]
  E -->|no| HF{"Handoff-workflow flag?<br/>explicit human request · fair housing / accommodation / legal<br/>sensitive data · unverified private request<br/>low confidence twice"}
  HF -->|yes| HW["Human handoff workflow<br/>explain why staff are needed<br/>never claim it happened"]
  HF -->|no| L{"intent = leasing<br/>and not a resident?"}
  L -->|yes| LEAD["Leasing workflow<br/>lead intent high / low / unclear<br/>one next question · no prices or availability"]
  LEAD --> HI{"high intent?"}
  HI -->|yes| LH["handoff → leasing (leasing_follow_up)"]
  HI -->|no| NOH1["no handoff unless the model asks"]
  L -->|no| MT{"intent = maintenance?"}
  MT -->|yes| TRI["Maintenance triage"]
  TRI --> RP{"repeat issue in record<br/>or recurring + history?"}
  RP -->|yes| REP["repeat: no troubleshooting<br/>handoff → maintenance, HIGH<br/>(management if a follow-up is also owed)"]
  RP -->|no| ROU["routine: approved steps only<br/>(unclear category → none)<br/>no work order created"]
  MT -->|no| RN{"intent = renewal<br/>and resident?"}
  RN -->|yes| REN["Renewal workflow<br/>compassionate, no offers or discounts<br/>open commitments, contact preference<br/>handoff → leasing when money / lease / human"]
  RN -->|no| RES{"resident?"}
  RES -->|yes| RS["Resident support workflow<br/>preferred language and channel, no re-asking"]
  RES -->|no| GEN["General inquiry<br/>one clarifying question<br/>(low confidence is flagged, never 'safe')"]

  EMER & HW & LH & REP & REN --> HOFF["HandoffRecommendation<br/>status = recommended_not_sent<br/>completed = false"]
```

Notes:
- A *soft* request ("can someone explain my choices?") sets `human_requested`, so a handoff is still recommended, but the conversation stays in the more specific workflow (for example renewal). Only an *explicit* request ("real person", "not a bot") switches to the human handoff workflow.
- Any always-human flag forces `requires_human` (see `ALWAYS_HUMAN_FLAGS` in `backend/app/gates/base.py`). If the response model recommends a handoff on its own, that also produces a recommendation.
