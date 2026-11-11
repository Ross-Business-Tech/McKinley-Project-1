"""Adaptive simulated user for the customer-journey suite (see ``journeys`` for the policy rules).

The simulator only decides what the persona does next from the STRUCTURE of each response (card kind/stage/missing,
records, safety notice, handoff, status items, whether a question was asked). It never matches assistant wording
and it does not grade anything: grading is ``journey_evaluator``'s job.

A ``BudgetTransport`` wraps any transport and stops before a call once ``max_calls`` replies came from a model
(``reply_source == "model"``); the run is then marked truncated rather than silently shortened.
"""

import re
from typing import Any

from app.usability.journeys import Journey
from app.usability.simulator import Transport, Turn, _button_turn, _chat_turn

# Missing-detail labels shown on the card (EN + ES, see app/actions.LABEL) -> persona answer slot.
_SLOTS = [
    ("issue", re.compile(r"what'?s wrong|problema|issue", re.I)),
    ("entry", re.compile(r"entry|enter|entrar|acceso|permiso", re.I)),
    ("location", re.compile(r"^where|location|room|ubicaci|lugar|d[oó]nde", re.I)),
    ("area", re.compile(r"community|city|area|comunidad|ciudad", re.I)),
    ("time", re.compile(r"time of day|^time|hora", re.I)),
    ("days", re.compile(r"\bdays?\b|d[ií]as?", re.I)),
]


class BudgetExhausted(Exception):
    pass


class BudgetTransport:
    """Counts model-written replies and refuses to send once ``max_calls`` is reached (live runs only)."""

    def __init__(self, inner: Transport, max_calls: int):
        self.inner, self.max_calls, self.calls = inner, max_calls, 0

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if path == "/api/chat" and self.calls >= self.max_calls:
            raise BudgetExhausted(f"model-call budget of {self.max_calls} reached")
        status, d = self.inner.post(path, body)
        if path == "/api/chat" and d.get("reply_source") == "model":
            self.calls += 1
        return status, d


def slot_for(label: str) -> str | None:
    for slot, rx in _SLOTS:
        if rx.search(label):
            return slot
    return None


def observe(turns: list[Turn]) -> dict[str, Any]:
    """Structural view of the conversation so far (what a person sees on screen, minus the wording)."""
    last = turns[-1] if turns else None
    action = (last.action if last else None) or {}
    missing = action.get("missing") or []
    records = [r for t in turns for r in t.records]
    return {
        "turns": len(turns), "last_kind": last.kind if last else None,
        "card_kind": action.get("kind"), "card_stage": action.get("stage"),
        "missing_slot": slot_for(missing[0]) if missing else None,
        "record_kinds": [r.get("kind") for r in records],
        "question": bool(last and "?" in (last.reply or "")),
        "handoff": bool(last and (last.recommended_handoff or action.get("kind") == "staff_handoff")),
        "notice": bool(last and last.safety_notice),
        "status": bool(last and (last.status_items or last.status_refs)),
    }


def _atom(cond: str, o: dict[str, Any]) -> bool:
    if cond.startswith("!"):
        return not _atom(cond[1:], o)
    name, _, arg = cond.partition(":")
    if name.startswith("turn>="):
        return o["turns"] >= int(name[6:])
    match name:
        case "any":
            return True
        case "start":
            return o["turns"] == 0
        case "card_collecting":
            return o["card_stage"] == "collecting"
        case "card_ready":
            return o["card_stage"] == "ready"
        case "card_none":
            return o["card_kind"] is None
        case "card":
            return o["card_kind"] == arg
        case "missing":
            return o["card_stage"] == "collecting" and o["missing_slot"] == arg
        case "submitted":
            return bool(o["record_kinds"]) if not arg else arg in o["record_kinds"]
        case "declined":
            return o["last_kind"] == "cancel"
        case "question" | "handoff" | "notice" | "status":
            return o[name]
    raise ValueError(f"unknown journey condition {cond!r}")


def holds(expr: str, o: dict[str, Any]) -> bool:
    """``a&b|c`` = (a and b) or c; ``!x`` negates one atom."""
    return any(all(_atom(a.strip(), o) for a in part.split("&")) for part in expr.split("|"))


def run_journey(t: Transport, j: Journey, run_tag: str) -> dict[str, Any]:
    pid = j.persona.identity
    sid = f"jr-{run_tag}-{j.id}"[:64]
    pol = j.policy
    turns: list[Turn] = []
    decisions: list[str] = []  # why the persona did what it did, per turn (for debugging the policy)
    hazard_turns: list[int] = []
    used: set[int] = set()
    answered: dict[str, int] = {}
    cards_seen = 0
    acted_ready_at = -1
    truncated = None

    def say(text: str, kind: str, why: str) -> None:
        turns.append(_chat_turn(t, sid, pid, text, kind, j.channel))
        decisions.append(why)

    try:
        while len(turns) < pol.max_turns:
            o = observe(turns)
            last = turns[-1] if turns else None
            # 1) a ready read-back card: the persona's card move (once per appearance of a ready card)
            if o["card_stage"] == "ready" and acted_ready_at != len(turns) - 1 and last and last.kind != "cancel":
                move = pol.on_card[min(cards_seen, len(pol.on_card) - 1)]
                cards_seen += 1
                acted_ready_at = len(turns) - 1
                if move in ("send", "decline"):
                    turns.append(_button_turn(t, sid, pid, last.action or {}, confirm=move == "send"))
                    decisions.append(f"card ready -> pressed {move}")
                    continue
            # 2) reactive beats, 3) answer the card's first missing detail, 4) agenda beats
            beat_i = next((i for i, b in enumerate(pol.beats) if i not in used and b.when != "any"
                           and holds(b.when, o)), None)
            if beat_i is None and o["card_stage"] == "collecting" and o["missing_slot"]:
                slot = o["missing_slot"]
                text = pol.answers.get(slot)
                if text is None and answered.get("unknown", 0) == 0:
                    text, slot = pol.answers.get("unknown"), "unknown"
                if text and answered.get(slot, 0) < 2:  # a person repeats an answer once, then gives up
                    answered[slot] = answered.get(slot, 0) + 1
                    say(text, "answer", f"answered missing '{slot}'")
                    continue
            if beat_i is None:
                beat_i = next((i for i, b in enumerate(pol.beats) if i not in used and b.when == "any"), None)
            if beat_i is None:
                break
            used.add(beat_i)
            b = pol.beats[beat_i]
            say(b.say, "say", f"beat {beat_i} ({b.when})")
            if b.hazard:
                hazard_turns.append(len(turns) - 1)
            if b.ends:
                break
    except BudgetExhausted as e:
        truncated = str(e)
    return {"journey": j.id, "persona": j.persona.id, "identity": pid, "session_id": sid,
            "turns": [x.__dict__ for x in turns], "decisions": decisions, "hazard_turns": hazard_turns,
            "truncated": truncated}
