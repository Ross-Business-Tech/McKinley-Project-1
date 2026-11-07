"""Adaptive simulated user. Talks to the REAL HTTP API (or an in-process client with the same interface).

Each turn the simulator looks at the actual response:
- a read-back card that is ready -> presses Send or Don't send (per the scenario), like tapping the button;
- the assistant is collecting a missing detail the persona knows -> answers it in the persona's own words
  (unless the persona ignores questions);
- otherwise -> says the next thing the persona wanted to say.
So the conversation follows what the assistant actually did, not a fixed replay.
"""

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.usability.personas import PERSONAS
from app.usability.scenarios import Scenario

MAX_USER_TURNS = 8

# Which persona fact answers which missing-detail label (labels are shown to the customer in EN or ES).
_SLOT_OF_LABEL = [
    ("entry", re.compile(r"entry|enter|entrar|acceso", re.I)),
    ("location", re.compile(r"where|location|room|ubicaci|lugar", re.I)),
    ("area", re.compile(r"community|city|area|comunidad|ciudad", re.I)),
    ("time", re.compile(r"time|hora", re.I)),
    ("days", re.compile(r"\bday|d[ií]a", re.I)),
]


class Transport(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...


class HttpTransport:
    """Real HTTP calls to a running backend (the same endpoints the browser uses)."""

    def __init__(self, base_url: str, timeout: float = 120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - local/base URL from CLI
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, {"error": str(e)}


@dataclass
class Turn:
    user: str  # what the person typed, or "[pressed: <button>]"
    kind: str  # "say" | "answer" | "confirm" | "cancel"
    status: int
    latency_ms: int
    reply: str = ""
    safety_notice: str | None = None
    emergency_kind: str | None = None
    routed_workflow: str | None = None
    workflow: str | None = None
    recommended_handoff: bool | None = None
    handoff_team: str | None = None
    action: dict[str, Any] | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    status_items: int = 0
    suggested_replies: list[str] = field(default_factory=list)
    model: str | None = None
    is_mock: bool | None = None
    reply_source: str | None = None
    error: str | None = None


def _slot_for(label: str) -> str | None:
    for slot, rx in _SLOT_OF_LABEL:
        if rx.search(label):
            return slot
    return None


def _chat_turn(t: Transport, sid: str, pid: str | None, message: str, kind: str, channel: str = "web_chat") -> Turn:
    t0 = time.perf_counter()
    status, d = t.post("/api/chat", {"message": message, "persona_id": pid, "mode": "aware", "session_id": sid,
                                     "channel": channel})
    ms = int((time.perf_counter() - t0) * 1000)
    if status != 200:
        return Turn(message, kind, status, ms, error=d.get("message") or d.get("detail") or str(d))
    handoff = d.get("handoff") or {}
    return Turn(
        user=message, kind=kind, status=status, latency_ms=ms, reply=d.get("reply", ""),
        safety_notice=d.get("safety_notice"), emergency_kind=d.get("emergency_kind"),
        routed_workflow=(d.get("routed_workflow") or {}).get("id"), workflow=(d.get("workflow") or {}).get("id"),
        recommended_handoff=d.get("recommended_handoff"), handoff_team=handoff.get("team"), action=d.get("action"),
        records=d.get("records_created") or [], status_items=len(d.get("status_items") or []),
        suggested_replies=d.get("suggested_replies") or [], model=d.get("model"), is_mock=d.get("is_mock"),
        reply_source=d.get("reply_source"),
    )


def _button_turn(t: Transport, sid: str, pid: str | None, action: dict[str, Any], confirm: bool) -> Turn:
    label = action.get("confirm_label") or "Send" if confirm else "Don't send"
    t0 = time.perf_counter()
    status, d = t.post("/api/actions/" + ("confirm" if confirm else "cancel"),
                       {"session_id": sid, "persona_id": pid, "kind": action["kind"]})
    ms = int((time.perf_counter() - t0) * 1000)
    rec = d.get("record")
    return Turn(user=f"[pressed: {label}]", kind="confirm" if confirm else "cancel", status=status, latency_ms=ms,
                reply=d.get("message", ""), action=d.get("action"), records=[rec] if rec else [],
                error=None if status == 200 and d.get("ok", True) else (d.get("error_code") or d.get("message")))


def run_scenario(t: Transport, sc: Scenario, run_tag: str) -> dict[str, Any]:
    persona = PERSONAS[sc.persona]
    pid = persona.identity
    sid = f"ux-{run_tag}-{sc.id}"
    moves = list(sc.moves)
    turns: list[Turn] = []
    answered: set[str] = set()
    acted_on_card = False
    while len(turns) < MAX_USER_TURNS:
        last = turns[-1] if turns else None
        action = last.action if last else None
        stage = action.get("stage") if action else None
        if stage == "ready" and not acted_on_card and sc.on_card != "ignore" and last and last.kind != "cancel":
            acted_on_card = True
            turns.append(_button_turn(t, sid, pid, action, confirm=sc.on_card == "send"))  # type: ignore[arg-type]
            continue
        if stage == "collecting" and persona.answers_questions and action and action.get("missing"):
            slot = _slot_for(action["missing"][0])
            if slot and slot in persona.facts and slot not in answered and not _next_move_answers(moves, slot):
                answered.add(slot)
                turns.append(_chat_turn(t, sid, pid, persona.facts[slot], "answer", sc.channel))
                continue
        if not moves:
            break
        if stage in ("submitted",) or (last and last.kind == "confirm"):
            acted_on_card = False  # a new card later in the conversation can be acted on again
        turns.append(_chat_turn(t, sid, pid, moves.pop(0), "say", sc.channel))
    return {"scenario": sc.id, "persona": sc.persona, "identity": pid, "session_id": sid,
            "turns": [t.__dict__ for t in turns]}


_ANSWERS = {
    "entry": re.compile(r"\b(enter|come in|contact me|text (?:me )?first|entrar)\b", re.I),
    "location": re.compile(r"\b(kitchen|bath ?room|bedroom|living room|hallway|cocina|baño)\b", re.I),
    "days": re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)\w*|weekend\b", re.I),
    "time": re.compile(r"\b(morning|afternoon|evening|\d{1,2} ?(?:am|pm))\b", re.I),
}


def _next_move_answers(moves: list[str], slot: str) -> bool:
    """The persona was about to say this anyway (keeps their own wording instead of a canned fact)."""
    rx = _ANSWERS.get(slot)
    return bool(moves and rx and rx.search(moves[0]))
