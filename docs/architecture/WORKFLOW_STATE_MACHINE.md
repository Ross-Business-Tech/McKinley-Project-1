# Workflow state machine (Sprint 6, as implemented)

Code: `backend/app/workflow_state.py` (states, events, `TRANSITIONS`, `derive`, `apply`, `duplicate_of`), wired into
`backend/app/actions.py` (`plan_turn` step 1c-understand and step 2; `confirm`). Tests:
`backend/tests/test_sprint6_conversation_model.py` (state machine) and `test_sprint6_conversation.py` (API replays).

## Principles
- **The state is derived, never stored twice.** `derive(draft, records)` reads the open draft (its kind, missing
  fields, `declined`, `vague_issue`, `parked`, `queued`) and the records saved in the session. It can't drift from
  the card on screen.
- **`apply(snapshot, understanding)` is pure.** It looks the event up in the explicit `TRANSITIONS` table and returns
  the next state plus *effects*: proposals such as `update_field`, `park_draft`, `open_handoff`, `ask_next`,
  `prompt_send`, `save`. `plan_turn` executes them. Nothing in `workflow_state.py` writes to the store.
- **Illegal transitions are rejected** with a reason and no effects, for example `save` while collecting, restore
  with nothing declined, or cancel with nothing open.
- **Only an explicit confirmation proposes `save`.** That means the Send button (`/api/actions/confirm`) or a typed
  "send it", "submit it" or "envíelo" (`Understanding.explicit_send`, rules only). A bare "yes", "ok" or "sí"
  proposes `prompt_send` ("Tap Send…"). A model can never produce a save, because model CONFIRM acts are dropped in
  the merge.
- **Saving is idempotent.** `confirm()` takes the draft atomically first, so concurrent Sends still write at most
  one record. It then checks `duplicate_of`, which compares the kind and the person's field values with records
  already saved in this session for this person. If they match, it shows that record (`error_code="ALREADY_SAVED"`,
  "…already has these details, so I didn't save it twice") and writes nothing.
- **Safety is not decided here.** A possible emergency adds `pass_to_safety` on top of the message's own event. The
  safety steps run before all of this: `chat_engine` 2b, and `plan_turn` 1 and 1b, which belong to the safety
  engineer. `EMERGENCY` is the event those steps cause (an urgent note recorded); `event_for` never returns it.

## States
| State | Derived from | Shown to the person |
| --- | --- | --- |
| `idle` | no open draft, nothing saved | the menu or the answer |
| `collecting` | open draft with a missing required field | the card plus one question |
| `awaiting_clarification` | repair card whose problem is vague ("it's broken") | "What is it that isn't working?" |
| `ready` | nothing missing | card plus "Tap Send" |
| `pending_staff_review` | a non-urgent record saved, no open draft | the reference and "nobody is notified" |
| `declined` | draft marked `declined` (restorable once) | "Okay, I haven't sent it" |
| `escalation_recommended` | an open note for the office (a parked card may ride inside it) | the note card |
| `escalation_recorded` | an urgent note saved by the safety step | the fixed safety text |

A **parked** card is not a separate state. It is the repair or tour card stored inside an open note
(`draft["parked"]`). It comes back when the note is sent (`confirm`) or skipped (`decline` plus `restore`).
**Queued** problems (`draft["queued"]`) are the other problems from a two-issue message. The card's note names them,
and after Send they become the next card.

## Transitions

```mermaid
stateDiagram-v2
  [*] --> idle
  idle --> collecting: new_request / second_issue (start_draft, queue_issue)
  collecting --> collecting: provide_info / correct (update_field, ask_next)
  collecting --> awaiting_clarification: problem too vague
  awaiting_clarification --> collecting: provide_info
  collecting --> ready: last missing field given
  ready --> ready: correct (update_field) / confirm_bare (prompt_send)
  ready --> pending_staff_review: confirm_explicit or Send button (save, idempotent)
  collecting --> declined: cancel (decline)
  ready --> declined: cancel (decline)
  declined --> collecting: resume (restore), fields missing
  declined --> ready: resume (restore), complete
  collecting --> escalation_recommended: request_human (park_draft, open_handoff)
  ready --> escalation_recommended: request_human (park_draft, open_handoff)
  idle --> escalation_recommended: request_human (open_handoff)
  escalation_recommended --> pending_staff_review: confirm_explicit (save, parked card returns)
  escalation_recommended --> declined: cancel (decline, parked card returns)
  pending_staff_review --> collecting: new_request
  collecting --> collecting: ask / check_status / frustration / switch_topic (keep_card)
  idle --> escalation_recorded: emergency (safety step, not this module)
  collecting --> escalation_recorded: emergency (safety step)
  note right of pending_staff_review
    Prototype store only. Nobody is notified.
  end note
```

Events come from `event_for(understanding)`, checked most consequential first: `confirm_explicit` (button or typed
send) → `request_human` → `resume` → `switch_topic` → `cancel` → `correct` → `check_status` → `confirm_bare` →
`frustration` (with the assistant) → `provide_info` → `ask` → `second_issue` → `small_talk` → `new_request`.
So "yes, but it's the kitchen, not the bathroom" is a correction, never consent. "Forget it, what are the pool
hours?" is `switch_topic`: the question is answered and the card stays, unsent, with a line saying how to cancel.

## Where plan_turn uses it (documented position)
- **Top (declined card):** `apply(derive(declined), u0)` → `restore`. This is how paraphrased restores ("I hit
  Don't send by accident") bring back the same card.
- **Step 1c-understand:** `tr = apply(derive(live, mine), u)`, plus the switch-topic branch.
- **Step 2 (consent):** `tr2.event in (confirm_explicit, confirm_bare)`. `prompt_send` gives "Tap Send"; `save`
  calls `confirm()`. This replaced `is_affirmative(msg) or is_explicit_send(msg)`.
- **`confirm()`:** `duplicate_of` after the atomic `take_draft`.
- The `transition` summary (from, event, to, effects: names only) goes on `TurnPlan.transition` and into the
  pipeline trace (`6a_understanding`).

## Not yet driven by the table
`plan_turn`'s later steps (5 to 13) still decide most routing themselves, though they now read the understanding
(`wants_person`, `status_q`, `chat_frustrated`, `act`). The table is authoritative for consent, cancel, restore,
switch-topic and the duplicate check. Moving the remaining branches over is future work, one tested branch at a time.
