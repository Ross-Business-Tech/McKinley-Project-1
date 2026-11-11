"""Typed workflow state machine for the open card (Sprint 6).

The state is DERIVED from what the store really holds (the open draft, its flags, the saved records), never kept in a
second place, so it can't drift from the card the person sees. `apply(snapshot, understanding)` looks the event up in
an explicit transition table and returns the new state plus EFFECTS: proposals that `actions.plan_turn` executes
(update a field, park a draft, open a note, ask the next question, save). Nothing here writes to the store.

Rules the table enforces (see docs/architecture/WORKFLOW_STATE_MACHINE.md):
- `save` is proposed only from READY on an explicit confirmation (the Send button, or a typed "send it" /
  "submit it" / "envíelo"). A bare "yes" on a ready card proposes `prompt_send`; on any other state it is rejected.
- A model can't produce a save: `Understanding.explicit_send` is rules-only and CONFIRM from a model is dropped.
- Saving is idempotent: `duplicate_of` finds an identical record already saved in the session, and the planner
  shows that record instead of writing a second one.
- An illegal transition (save while collecting, restore with nothing declined, cancel with nothing open) is
  rejected with a reason and no effects.
- A possible emergency is never handled here: `pass_to_safety` is added to whatever else the message does, and the
  safety steps (chat_engine 2b, plan_turn 1/1b, owned by the safety engineer) run before any of this anyway. The
  EMERGENCY event is what those steps cause (an urgent note recorded); `event_for` never returns it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.understanding import DialogueAct, Understanding

REQUIRED: dict[str, list[str]] = {"maintenance_request": ["issue", "location", "entry"],
                                  "tour_request": ["area", "days", "time"], "staff_handoff": []}


class WState(StrEnum):
    IDLE = "idle"  # no open card
    COLLECTING = "collecting"  # a card with a missing required field
    AWAITING_CLARIFICATION = "awaiting_clarification"  # the problem itself is unclear ("it's broken": what is?)
    READY = "ready"  # nothing missing; waiting for Send
    PENDING_STAFF_REVIEW = "pending_staff_review"  # saved (submitted / requested); no open card
    DECLINED = "declined"  # the person chose not to send; restorable once
    ESCALATION_RECOMMENDED = "escalation_recommended"  # a note for the office is open, not sent
    ESCALATION_RECORDED = "escalation_recorded"  # an urgent note was saved by the safety step


class Event(StrEnum):
    PROVIDE_INFO = "provide_info"
    CORRECT = "correct"
    ASK = "ask"
    CONFIRM_EXPLICIT = "confirm_explicit"  # Send button or a typed "send it"
    CONFIRM_BARE = "confirm_bare"  # "yes", "ok", "sure": never saves
    CANCEL = "cancel"
    SWITCH_TOPIC = "switch_topic"  # "forget it, what are the pool hours?": answer, keep the card set aside
    RESUME = "resume"
    REQUEST_HUMAN = "request_human"
    CHECK_STATUS = "check_status"
    FRUSTRATION = "frustration"
    NEW_REQUEST = "new_request"
    SECOND_ISSUE = "second_issue"  # two problems in one message
    SMALL_TALK = "small_talk"
    EMERGENCY = "emergency"
    HOLD = "hold"  # "don't send it yet": the card stays, unsent (never a cancel)
    DROP_ISSUE = "drop_issue"  # "never mind the smoke detector, only the faucet": that problem only
    SPLIT_ISSUE = "split_issue"  # "those are 2 different things": one request per problem


@dataclass(frozen=True)
class Effect:
    kind: str  # update_field | drop_issue | split_issue |
    #           ask_next | answer_question | prompt_send | save | decline | restore | park_draft |
    #           open_handoff | queue_issue | show_status | acknowledge | start_draft | pass_to_safety | keep_card
    field: str | None = None
    value: str | None = None


@dataclass
class Snapshot:
    state: WState
    kind: str | None = None  # the open (or declined) card's kind
    pending: str | None = None  # its next missing field
    parked_kind: str | None = None  # a card parked inside an open note
    queued: list[str] = field(default_factory=list)  # further problems waiting their turn
    sent: int = 0  # records saved in this session (non-urgent)


@dataclass
class Transition:
    before: WState
    event: Event
    after: WState
    effects: list[Effect]
    allowed: bool = True
    reason: str = ""

    def has(self, kind: str) -> bool:
        return any(e.kind == kind for e in self.effects)

    def summary(self) -> dict[str, Any]:
        return {"from": self.before.value, "event": self.event.value, "to": self.after.value,
                "effects": [e.kind for e in self.effects], "allowed": self.allowed}


S, E = WState, Event
_OPEN = (S.COLLECTING, S.AWAITING_CLARIFICATION, S.READY, S.ESCALATION_RECOMMENDED)
# (state, event) -> next state. Anything not listed is illegal (rejected, no effects). "same" = stays where it is.
TRANSITIONS: dict[tuple[WState, Event], WState | str] = {
    **{(s, E.PROVIDE_INFO): "recompute" for s in _OPEN},
    **{(s, E.CORRECT): "recompute" for s in _OPEN},
    **{(s, E.ASK): "same" for s in WState},
    **{(s, E.CHECK_STATUS): "same" for s in WState},
    **{(s, E.SMALL_TALK): "same" for s in WState},
    **{(s, E.FRUSTRATION): "same" for s in WState},
    **{(s, E.EMERGENCY): S.ESCALATION_RECORDED for s in WState},
    **{(s, E.CANCEL): S.DECLINED for s in _OPEN},
    **{(s, E.SWITCH_TOPIC): "same" for s in _OPEN},
    (S.IDLE, E.SWITCH_TOPIC): S.IDLE,
    **{(s, E.HOLD): "same" for s in _OPEN},
    **{(s, E.DROP_ISSUE): "recompute" for s in (S.COLLECTING, S.AWAITING_CLARIFICATION, S.READY)},
    **{(s, E.SPLIT_ISSUE): "recompute" for s in (S.COLLECTING, S.AWAITING_CLARIFICATION, S.READY)},
    (S.DECLINED, E.RESUME): "recompute",
    **{(s, E.REQUEST_HUMAN): S.ESCALATION_RECOMMENDED for s in WState if s != S.ESCALATION_RECORDED},
    (S.ESCALATION_RECORDED, E.REQUEST_HUMAN): S.ESCALATION_RECORDED,  # the urgent note already went to staff
    (S.READY, E.CONFIRM_EXPLICIT): S.PENDING_STAFF_REVIEW,
    (S.ESCALATION_RECOMMENDED, E.CONFIRM_EXPLICIT): S.PENDING_STAFF_REVIEW,  # a note with nothing missing
    (S.READY, E.CONFIRM_BARE): S.READY,
    (S.ESCALATION_RECOMMENDED, E.CONFIRM_BARE): S.ESCALATION_RECOMMENDED,
    **{(s, E.NEW_REQUEST): S.COLLECTING for s in (S.IDLE, S.PENDING_STAFF_REVIEW, S.DECLINED,
                                                  S.ESCALATION_RECORDED)},
    **{(s, E.NEW_REQUEST): "recompute" for s in _OPEN},  # more detail for the open card
    **{(s, E.SECOND_ISSUE): S.COLLECTING for s in (S.IDLE, S.PENDING_STAFF_REVIEW, S.DECLINED,
                                                   S.ESCALATION_RECORDED)},
}


def _missing(kind: str, draft: dict[str, Any]) -> list[str]:
    fields = draft.get("fields", {})
    out = [k for k in REQUIRED.get(kind, []) if not (fields.get(k) or {}).get("value")]
    if kind == "maintenance_request" and draft.get("vague_issue") and "issue" not in out:
        out.insert(0, "issue")
    return out


def derive(draft: dict[str, Any] | None, records: list[dict[str, Any]] | None = None) -> Snapshot:
    """The state as the store holds it right now."""
    recs = records or []
    sent = [r for r in recs if r.get("status") != "urgent_queued"]
    urgent = [r for r in recs if r.get("status") == "urgent_queued"]
    if not draft:
        st = S.ESCALATION_RECORDED if urgent and (not sent or urgent[0] is recs[0]) else \
            S.PENDING_STAFF_REVIEW if sent else S.IDLE
        return Snapshot(st, sent=len(sent))
    kind = draft.get("kind")
    queued = [q for q in (draft.get("queued") or []) if q]
    if draft.get("declined"):
        return Snapshot(S.DECLINED, kind=kind, queued=queued, sent=len(sent))
    missing = _missing(kind or "", draft)
    if kind == "staff_handoff":
        return Snapshot(S.ESCALATION_RECOMMENDED, kind=kind, parked_kind=(draft.get("parked") or {}).get("kind"),
                        sent=len(sent))
    if missing and missing[0] == "issue" and draft.get("vague_issue"):
        st = S.AWAITING_CLARIFICATION
    else:
        st = S.COLLECTING if missing else S.READY
    return Snapshot(st, kind=kind, pending=missing[0] if missing else None, queued=queued, sent=len(sent))


def event_for(u: Understanding, *, send_button: bool = False, open_card: bool = False) -> Event:
    """The single event a message causes, most consequential first (the same order as the understanding layer)."""
    if send_button or u.explicit_send:
        return E.CONFIRM_EXPLICIT
    if u.requests_human:
        return E.REQUEST_HUMAN
    if u.has(DialogueAct.RESUME_TASK):
        return E.RESUME
    if u.has(DialogueAct.SWITCH_TOPIC):
        return E.SWITCH_TOPIC
    if u.hold:
        return E.HOLD
    if u.drop_issue:
        return E.DROP_ISSUE
    if u.split_request:
        return E.SPLIT_ISSUE
    if u.has(DialogueAct.CANCEL):
        return E.CANCEL
    if u.corrections:
        return E.CORRECT
    if u.has(DialogueAct.CHECK_STATUS):
        return E.CHECK_STATUS
    if u.has(DialogueAct.CONFIRM):
        return E.CONFIRM_BARE
    if u.has(DialogueAct.EXPRESS_FRUSTRATION) and u.frustration_target == "assistant":
        return E.FRUSTRATION
    if u.has(DialogueAct.PROVIDE_INFORMATION):
        return E.PROVIDE_INFO
    if u.has(DialogueAct.ASK_QUESTION):
        return E.ASK
    if len(u.entities.issues) >= 2 and not open_card:
        return E.SECOND_ISSUE
    if u.has(DialogueAct.SMALL_TALK):
        return E.SMALL_TALK
    return E.NEW_REQUEST if not open_card else E.PROVIDE_INFO


def apply(snap: Snapshot, u: Understanding, *, send_button: bool = False) -> Transition:
    """Look the event up in TRANSITIONS and propose effects. Pure: no store access, no side effects."""
    ev = event_for(u, send_button=send_button, open_card=snap.state in _OPEN)
    nxt = TRANSITIONS.get((snap.state, ev))
    if nxt is None:
        reason = {E.CONFIRM_EXPLICIT: "nothing ready to send" if snap.state != S.COLLECTING else
                  "the card still has a missing field", E.CONFIRM_BARE: "a bare yes never saves",
                  E.RESUME: "nothing was declined", E.CANCEL: "nothing is open"}.get(ev, "not allowed here")
        effects = [Effect("ask_next", snap.pending)] if ev in (E.CONFIRM_EXPLICIT, E.CONFIRM_BARE) and \
            snap.state == S.COLLECTING else []
        if u.report_possible_emergency:
            effects.insert(0, Effect("pass_to_safety"))
        return Transition(snap.state, ev, snap.state, effects, allowed=False, reason=reason)
    # a possible emergency never changes the flow here: it is flagged for the safety layer, on top of the event
    effects: list[Effect] = [Effect("pass_to_safety")] if u.report_possible_emergency else []
    after: WState
    if ev is E.EMERGENCY:
        effects.append(Effect("pass_to_safety"))
    elif ev is E.CONFIRM_EXPLICIT:
        effects.append(Effect("save", snap.kind))
    elif ev is E.CONFIRM_BARE:
        effects.append(Effect("prompt_send", snap.kind))
    elif ev is E.REQUEST_HUMAN:
        if snap.state in (S.COLLECTING, S.AWAITING_CLARIFICATION, S.READY):
            effects.append(Effect("park_draft", snap.kind))  # the card rides inside the note, restorable
        effects.append(Effect("open_handoff"))
    elif ev is E.CANCEL:
        effects.append(Effect("decline", snap.kind))
        if snap.state == S.ESCALATION_RECOMMENDED and snap.parked_kind:
            effects.append(Effect("restore", snap.parked_kind))  # skipping a note brings back the card it parked
    elif ev is E.SWITCH_TOPIC:
        effects += [Effect("answer_question", u.question_topic), Effect("keep_card", snap.kind)]
    elif ev is E.RESUME:
        effects.append(Effect("restore", snap.kind))
    elif ev is E.HOLD:
        effects.append(Effect("keep_card", snap.kind))
    elif ev is E.DROP_ISSUE:
        effects += [Effect("drop_issue", value=u.drop_issue), Effect("ask_next")]
    elif ev is E.SPLIT_ISSUE:
        effects += [Effect("split_issue", value=u.split_target), Effect("ask_next")]
    elif ev is E.CORRECT:
        effects += [Effect("update_field", c.field, c.value) for c in u.corrections]
        effects.append(Effect("ask_next"))
    elif ev is E.PROVIDE_INFO:
        effects.append(Effect("ask_next"))
    elif ev is E.ASK:
        effects.append(Effect("answer_question", u.question_topic))
        if snap.state in _OPEN:
            effects.append(Effect("keep_card", snap.kind))
    elif ev is E.CHECK_STATUS:
        effects.append(Effect("show_status"))
        if snap.state in _OPEN:
            effects.append(Effect("keep_card", snap.kind))
    elif ev is E.FRUSTRATION:
        effects.append(Effect("acknowledge"))
        if snap.state in _OPEN:
            effects.append(Effect("keep_card", snap.kind))
    elif ev is E.SECOND_ISSUE:
        effects.append(Effect("start_draft"))
        effects += [Effect("queue_issue", value=i) for i in u.entities.issues[1:3]]
    elif ev is E.NEW_REQUEST:
        effects.append(Effect("start_draft" if snap.state not in _OPEN else "ask_next"))
    if nxt == "same":
        after = snap.state
    elif nxt == "recompute":  # depends on the fields after the update: the planner re-derives it from the store
        after = S.COLLECTING if snap.state in (S.DECLINED, S.IDLE) else snap.state
    else:
        after = nxt  # type: ignore[assignment]
    return Transition(snap.state, ev, after, effects, reason="ok")


def fingerprint(kind: str, fields: dict[str, Any] | list[dict[str, Any]]) -> str:
    """What makes two saved cards the same request: kind + the person's field values (sources ignored)."""
    if isinstance(fields, list):
        vals = {f.get("key"): f.get("value") for f in fields}
    else:
        vals = {k: (v or {}).get("value") for k, v in fields.items()}
    keep = {k: str(v).strip().lower() for k, v in vals.items() if v and k in (
        "issue", "location", "entry", "area", "days", "time", "topic", "message", "move_in")}
    return json.dumps([kind, sorted(keep.items())])


def duplicate_of(records: list[dict[str, Any]], kind: str, draft: dict[str, Any],
                 persona_id: str | None) -> dict[str, Any] | None:
    """A record already saved in this session with the same content (idempotent save: show it, don't write again)."""
    fp = fingerprint(kind, draft.get("fields", {}))
    for r in records:
        if r.get("kind") == kind and (r.get("persona_id") or None) == (persona_id or None) and \
                r.get("status") != "urgent_queued" and fingerprint(kind, r.get("fields") or []) == fp:
            return r
    return None


def _fvals(fields: Any) -> dict[str, str]:
    if isinstance(fields, dict):
        return {k: str((v or {}).get("value") or "") for k, v in fields.items()}
    return {f.get("key"): str(f.get("value") or "") for f in fields or [] if f.get("key")}


_STEM_STOP = {"the", "my", "is", "has", "have", "a", "an", "and", "it", "its", "in", "on", "of", "to", "with", "there",
              "bathroom", "kitchen", "bedroom", "room", "again", "still", "very", "really", "some", "this", "that"}
_SYMPTOM_STEMS = {"crack", "broke", "leak", "drip", "stuck", "loose", "dirty", "stain", "brok", "damag", "missi",
                  "worki", "not"}


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-zà-ÿ]{3,}", (text or "").lower()) if w not in _STEM_STOP}


def near_duplicate_of(records: list[dict[str, Any]], kind: str, draft: dict[str, Any],
                      persona_id: str | None) -> dict[str, Any] | None:
    """Sprint 7: a repair about the SAME thing in the SAME place as one already saved in this session, worded
    differently ("kitchen sink leaking" then "the sink under the kitchen cabinet drips"). Not saved again unless the
    person says it is a different problem (`draft["dup_ok"]`). Other kinds: only the exact fingerprint counts."""
    if kind != "maintenance_request" or draft.get("dup_ok"):
        return None
    from app.utterance import room_in, things

    mine = _fvals(draft.get("fields", {}))
    parts = {"cabinet", "floor", "pipe", "wall"}  # around a fixture: the same repair
    objs = things(mine.get("issue", "")) - parts or things(mine.get("issue", ""))
    room = room_in(mine.get("location", "") or mine.get("issue", ""))
    words = _stems(mine.get("issue", ""))
    if not objs and len(words) < 1:
        return None
    for r in records:
        if r.get("kind") != kind or (r.get("persona_id") or None) != (persona_id or None) or \
                r.get("status") == "urgent_queued":
            continue
        theirs = _fvals(r.get("fields") or [])
        r_room = room_in(theirs.get("location", "") or theirs.get("issue", ""))
        r_objs = things(theirs.get("issue", "")) - parts or things(theirs.get("issue", ""))
        same_place = room is None or r_room is None or r_room == room
        if objs and r_objs == objs and same_place:
            return r
        if not objs and not r_objs and same_place and words and (words & _stems(theirs.get("issue", ""))) >= {
                w for w in words if w not in _SYMPTOM_STEMS} and words - _SYMPTOM_STEMS:
            return r  # "the mirror is cracked" / "the mirror has a crack": the same unnamed fixture, same place
    return None


__all__ = ["WState", "Event", "Effect", "Snapshot", "Transition", "TRANSITIONS", "derive", "event_for", "apply",
           "fingerprint", "duplicate_of", "near_duplicate_of"]
