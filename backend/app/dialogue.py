"""Typed dialogue acts for one customer message (Sprint 5.1).

Root cause this addresses: while a card was open, almost any message was absorbed into the draft. Questions, meta
talk, contact wording and topic switches were appended to "What's wrong"; the pending question was asked again; the
person's own question was ignored; or a duplicate draft started.

`classify_turn` runs BEFORE any draft mutation in `actions.plan_turn` (step "1c-acts") and says what the message
does. One message may carry several acts ("morning. also is the dog ok?" = ANSWER + QUESTION; "KITCHEN. I already
told you" = ANSWER + META).

Rules the planner enforces with it:
- Only ANSWER, CORRECTION and NEW_DETAIL may change card fields. A QUESTION is never written into a field.
- A QUESTION gets an honest in-context answer, and the open card stays (re-shown unchanged).
- ANSWER + META: the answer is saved first, then one apology.
- CANCEL is understood inside a sentence ("actually nevermind, don't send it"). A bare "no" to the entry question
  is an ANSWER ("contact me first"), never a CANCEL.
- RESTORE ("I pressed the wrong button", "undo", "send it after all") brings back the SAME declined card.
- NEW_ISSUE while a card is open never destroys that card (it is kept, or parked and restorable).

The classifier only combines existing detectors from app/intake.py; it does not duplicate them.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.intake import (
    asks_for_person,
    asks_to_restore,
    bare_area_answer,
    cancels_in_sentence,
    city_in,
    community_in,
    contact_change,
    extract_area_correction,
    extract_clock_preference,
    extract_days,
    extract_entry,
    extract_issue_restate,
    extract_issue_swap,
    extract_location,
    extract_location_change,
    extract_time_of_day,
    flexible_answer,
    is_bare_no,
    is_decline,
    is_issue_description,
    is_lost_or_frustrated_with_chat,
    is_meta_complaint,
    is_staff_request,
    match_faq,
    policy_topic,
    question_kind,
)


class Act(StrEnum):
    ANSWER = "answer"  # answers the pending question (value parsed)
    CORRECTION = "correction"  # replaces a field ("change what's wrong to: X", "it's the bathroom not the kitchen")
    NEW_DETAIL = "new_detail"  # adds to the problem description
    QUESTION = "question"  # about something else (status, who sees it, cost, renewal, parking, a number, priority)
    CANCEL = "cancel"  # do not send the open card (also inside a sentence)
    RESTORE = "restore"  # bring a declined card back
    META = "meta"  # about the assistant itself ("I already told you", "why do you keep asking")
    NEW_ISSUE = "new_issue"  # a different need (a person, another request) while a card is open
    SMALL_TALK = "small_talk"


@dataclass(frozen=True)
class TurnAct:
    acts: frozenset[Act]
    slot: str | None = None  # ANSWER: which pending slot
    value: str | None = None  # ANSWER: the parsed value (canonical English; the planner translates)
    question: str | None = None  # QUESTION: kind (see intake._QUESTION_KINDS, plus "policy" / "faq")
    correction: tuple[str, str] | None = None  # CORRECTION: (field, new value)
    extra: dict[str, str] = field(default_factory=dict)  # answers to other slots found in the same message

    def has(self, act: Act) -> bool:
        return act in self.acts


_ENTRY_YES = "Yes, maintenance may enter if I'm not home"
_ENTRY_NO = "Contact me first; only enter when I'm home"
_LEAD_YES = re.compile(r"^\W*(?:yes|yeah|yep|yup|sure|s[ií])\b(?![^.?!]*\b(?:but|don'?t|not)\b)", re.I)
_SAME_AS_BEFORE = re.compile(r"\bsame as (?:before|last time|the other one)\b", re.I)
_SMALL = re.compile(r"^\W*(?:hi|hello|hey|thanks|thank you|thx|ty|ok thanks|gracias|hola)\W*$", re.I)
_QUESTIONISH = re.compile(r"\?|^\W*(?:what|when|where|how|who|can|is|are|do|does|did|will|whats|wheres)\b", re.I)


def _entry_answer(msg: str) -> str | None:
    """Entry permission in the person's words, including bare yes/no and 'whatever works' (W-12, A-2, B-2)."""
    if e := extract_entry(msg):
        return e
    if is_bare_no(msg) or re.fullmatch(r"\W*(?:no|nope|nah)\W+(?:thanks|thank you|i'?d rather not)\W*", msg, re.I):
        return _ENTRY_NO  # "no" to "may they enter?" means contact me first, never "cancel the request"
    if re.search(r"\bwhatever works\b|\bany ?time\b|\bdoesn'?t matter\b|\bno preference\b", msg, re.I) and not \
            re.search(r"\b(?:don'?t|not|but)\b", msg, re.I):
        return _ENTRY_YES
    if _LEAD_YES.search(msg):
        return _ENTRY_YES  # "yes for both", "yes same as before"
    return None


def _tour_answer(slot: str, msg: str) -> str | None:
    if slot == "area":
        return community_in(msg) or city_in(msg) or extract_area_correction(msg) or bare_area_answer(msg)
    if slot == "days":
        return extract_days(msg) or ("flexible" if flexible_answer(msg, "days") else None)
    if slot == "time":
        clock = extract_clock_preference(msg)
        return (f"{clock[0]} ({clock[1]})" if clock else extract_time_of_day(msg)) or (
            "flexible" if flexible_answer(msg, "time") else None)
    return None


def classify_turn(msg: str, draft: dict[str, Any] | None, pending: str | None) -> TurnAct:
    """What `msg` does relative to the open card `draft` (None when there is none) whose next missing slot is
    `pending` (None when the card is ready or there is no card)."""
    acts: set[Act] = set()
    kind = (draft or {}).get("kind")
    declined = bool(draft and draft.get("declined"))
    slot = value = None
    correction: tuple[str, str] | None = None
    extra: dict[str, str] = {}

    if declined and asks_to_restore(msg):
        acts.add(Act.RESTORE)

    # ANSWER to the pending question. Checked before CANCEL, so "no" to the entry question is an answer (W-7).
    if draft and not declined and pending:
        if kind == "maintenance_request" and pending == "entry":
            value = _entry_answer(msg)
        elif kind == "maintenance_request" and pending == "location":
            value = extract_location(re.sub(r"\bnot (?:the |my |in the )?\w+", " ", msg, flags=re.I))
        elif kind == "tour_request":
            value = _tour_answer(pending, msg)
            for other in ("days", "time", "area"):
                if other != pending and (v := _tour_answer(other, msg)) and v != "flexible":
                    extra[other] = v
        if value:
            acts.add(Act.ANSWER)
            slot = pending
        if _SAME_AS_BEFORE.search(msg) and pending == "entry" and not value:
            acts.add(Act.ANSWER)
            slot, value = "entry", "same_as_before"

    if draft and not declined and not (slot == "entry" and value == _ENTRY_NO and len(msg.split()) <= 3):
        if cancels_in_sentence(msg) or is_decline(msg):
            acts.add(Act.CANCEL)

    if kind == "maintenance_request" and not declined:
        if (swap := extract_issue_swap(msg) or extract_issue_restate(msg)) and draft and \
                draft.get("fields", {}).get("issue"):
            correction = ("issue", swap)
        elif (loc := extract_location_change(msg, (draft or {}).get("fields", {}).get("location", {}).get("value"))):
            correction = ("location", loc)
        if correction:
            acts.add(Act.CORRECTION)
    if draft and not declined and (ch := contact_change(msg)):
        acts.add(Act.CORRECTION)
        correction = correction or ("contact", ch)

    if is_meta_complaint(msg) or (is_lost_or_frustrated_with_chat(msg) and slot):
        acts.add(Act.META)

    q = question_kind(msg)
    if not q and _QUESTIONISH.search(msg) and (pt := policy_topic(msg)):
        q = "policy" if pt else None
    if not q and _QUESTIONISH.search(msg) and match_faq(msg):
        q = "faq"
    if q:
        acts.add(Act.QUESTION)

    if is_staff_request(msg) or asks_for_person(msg):
        acts.add(Act.NEW_ISSUE)
    if is_issue_description(msg) and not q:
        acts.add(Act.NEW_DETAIL)
    if _SMALL.match(msg):
        acts.add(Act.SMALL_TALK)
    return TurnAct(acts=frozenset(acts), slot=slot, value=value, question=q, correction=correction, extra=extra)


__all__ = ["Act", "TurnAct", "classify_turn"]
