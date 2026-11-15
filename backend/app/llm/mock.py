"""Deterministic MOCK provider for development, tests and the offline demo. NOT a language model.

It answers the assistant contract (app/assistant.py) with a crude keyword stand-in so the deterministic parts of the
product (safety, privacy, consent, task state, persistence) can be exercised offline. It is not the product's
understanding: conversation quality is only ever evaluated with a live model. Every result is flagged is_mock=True.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.base import GenerationConfig, LLMResult, ModelOutput, Target

_REPAIR = re.compile(r"leak|drip|clog|broken|not working|isn'?t working|won'?t|stopped|no hot water|noise|rattl|"
                     r"backing up|cracked|mold|pest|roach|mice|ac\b|a/c|heat|toilet|faucet|sink|dishwasher|loud|"
                     r"rattles?|fan\b|light|outlet|door|window|fridge|oven|stove|dryer|washer|"
                     r"fuga|gotea|no funciona|roto", re.I)
_ROOM = {"kitchen": "Kitchen", "bathroom": "Bathroom", "bedroom": "Bedroom", "living room": "Living room",
         "laundry": "Laundry area", "hallway": "Hallway", "cocina": "Cocina", "baño": "Baño"}
_ENTER = re.compile(r"come in|let yourselves in|can enter|may enter|go in|ok to enter|pueden entrar", re.I)
_CONTACT_FIRST = re.compile(r"contact me first|call (?:me )?first|text (?:me )?first|i'?ll be home|llamen primero",
                            re.I)
_PERSON = re.compile(r"\b(?:manager|a person|real person|human|someone|staff|talk to|speak to|speak with|"
                     r"una persona|gerente)\b", re.I)
_RESUME = re.compile(r"\b(?:back to|resume|continue|finish|pick up|return to|where were we|go on with|"
                     r"after all|volvamos|seguir con)\b", re.I)
_CANCEL = re.compile(r"\b(?:cancel|never ?mind|don'?t send|do not send|forget (?:it|that|about it)|scratch that)\b",
                     re.I)
_SUSPEND = re.compile(r"\b(?:hold (?:on|off|that)|later|not now|pause)\b", re.I)
_TOUR = re.compile(r"\b(?:tour|visit|see (?:the|an?) (?:apartment|unit|place))\b", re.I)
_RENEW = re.compile(r"\b(?:renew\w*|lease|rent|contrato)\b", re.I)
_COMMUNITY = {"heron lake": "Heron Lake Apartments", "birchwood": "Birchwood Commons",
              "sandpiper": "Sandpiper Pointe", "fernhill": "Fernhill Apartments"}
_UNIT = re.compile(r"\b(?:unit|apt\.?|apartment|#)\s*([A-Za-z]?\d{1,4}[A-Za-z]?)\b|^\W*([A-Za-z]?\d{1,4}[A-Za-z]?)\W*$",
                   re.I)
_DAYS = re.compile(r"\b(?:mon|tues?|wednes|thurs?|fri|satur|sun)\w*day\b|\btomorrow\b|\bweekend\b", re.I)
_TIME = re.compile(r"\b(morning|afternoon|evening)\b", re.I)
ASK = {"issue": "What's going on?", "location": "Which room is it in?",
       "entry": "If maintenance comes while you're out, may they enter, or should they contact you first?",
       "area": "Which community would you like to see?", "days": "Which days work for you?",
       "time": "Morning, afternoon or evening?", "message": "What would you like the office to know?",
       "community": "Which McKinley community do you live in?", "unit": "And what's your unit number?"}
REQUIRED = {"maintenance_request": ["issue", "location", "entry"], "tour_request": ["area", "days", "time"],
            "staff_handoff": ["message"]}
WHAT = {"maintenance_request": "repair request", "tour_request": "tour request", "staff_handoff": "note"}


def _active(system: str) -> tuple[str | None, list[str], bool]:
    m = re.search(r"^ACTIVE: (\w+)(?P<guest> \(guest repair note\))?.*?(?:\[missing: (?P<miss>[^\]]*)\])?$", system,
                  re.M)
    if not m or m.group(1) == "none":
        return None, [], False
    return m.group(1), [x.strip() for x in (m.group("miss") or "").split(",") if x.strip()], bool(m.group("guest"))


def assistant_reply(system: str, msg: str) -> dict[str, Any]:
    low = msg.lower()
    kind, miss, guest = _active(system)
    waiting = re.findall(r"^WAITING: (\w+)", system, re.M)
    who = (re.search(r"## Who you are talking to\n(.+)", system) or re.search("(.*)", "")).group(1)
    visitor = "NOT signed in" in who or "prospective renter" in who
    fields = {f: "" for f in ["area", "beds", "community", "days", "entry", "issue", "location", "message", "move_in",
                              "time", "topic", "unit"]}
    op, task_kind, team, others = "none", "none", "none", []
    mine = bool(re.search(r"\b(?:status|my (?:open )?(?:requests?|work orders?|repairs?|tickets?)|"
                          r"what'?s open|history)\b", low)) and not re.search(r"\b(?:his|her|their|neighbou?r)", low)
    room = next((v for k, v in _ROOM.items() if k in low), "")
    if room:
        fields["location"] = room
    if _ENTER.search(msg):
        fields["entry"] = "Yes, maintenance may enter if I'm not home"
    elif _CONTACT_FIRST.search(msg):
        fields["entry"] = "Contact me first"
    if c := next((v for k, v in _COMMUNITY.items() if k in low), None):
        fields["community"] = fields["area"] = c
    if (u := _UNIT.search(msg)) and (u.group(1) or (u.group(2) and kind and "unit" in miss)):
        fields["unit"] = (u.group(1) or u.group(2)).upper()
    if d := _DAYS.search(msg):
        fields["days"] = d.group(0).capitalize()
    if t := _TIME.search(msg):
        fields["time"] = t.group(1).capitalize()
    if _CANCEL.search(msg) and kind:
        op = "cancel"
    elif _RESUME.search(msg) and (waiting or kind):
        op, task_kind = "resume", (waiting or [kind])[0]
    elif _SUSPEND.search(msg) and kind and not _REPAIR.search(msg):
        op = "suspend"
    elif _PERSON.search(msg):
        op, task_kind, team = "start", "staff_handoff", "management"
        fields["message"], fields["topic"] = msg, "Asked for a team member"
    elif _TOUR.search(msg) and kind != "tour_request":
        op, task_kind = "start", "tour_request"
    elif _REPAIR.search(msg) and kind not in ("maintenance_request",) and not guest:
        op, task_kind = "start", "maintenance_request"
        repair_part = re.split(r"\band (?:i |also |can |could )", msg, maxsplit=1, flags=re.I)[0]
        fields["issue"] = repair_part.strip(" ,.")[:200]
        if _RENEW.search(msg) and repair_part != msg:
            others = [msg[len(repair_part):].strip(" ,.")]
    elif kind and any(fields[f] for f in ("location", "entry", "community", "unit", "days", "time", "area")):
        op = "update"
    # the reply describes the state the backend is about to show (the mock is not a language model)
    after_kind = task_kind if op in ("start", "resume") else None if op in ("cancel", "suspend") else kind
    if op == "start" and task_kind == "maintenance_request" and visitor:
        need = [f for f in ("community", "unit") if not fields[f]]
        reply = "Sorry you're dealing with that. Since this chat isn't signed in, I'll put it together as a note " \
                "for the maintenance team. " + (ASK[need[0]] if need else "Your note is ready below.")
    elif op == "start":
        need = [f for f in REQUIRED[task_kind] if not fields[f]]
        lead = {"maintenance_request": "Sorry you're dealing with that.", "tour_request": "Happy to help you plan a "
                "visit.", "staff_handoff": "Of course. I've prepared a note for the office with what you've told me."
                }[task_kind]
        reply = f"{lead} " + (ASK[need[0]] if need else f"Your {WHAT[task_kind]} is ready below. Press Send when "
                                                         "it looks right.")
        if others:
            reply += " I'll also keep your question about the lease for a note to the leasing team."
    elif op == "update":
        left = [f for f in miss if not fields.get(f)]
        reply = "Thanks. " + (ASK[left[0]] if left else f"Your {WHAT[kind or 'staff_handoff']} is ready below. "
                                                          "Press Send when it looks right.")
    elif op == "resume":
        reply = f"Sure, here's your {WHAT[after_kind or 'staff_handoff']} again. It isn't sent yet."
    elif op == "cancel":
        reply = "Okay, I haven't sent it. Say \"go back to it\" if you change your mind."
    elif op == "suspend":
        reply = "No problem, I've set it aside. It isn't sent; we can come back to it anytime."
    elif "?" in msg or re.search(r"^\W*(?:what|when|where|how|do|does|can|is|are)\b", low):
        reply = "I don't have approved details about that, so I won't guess. The office can answer it." + (
            f" Your {WHAT[kind]} is still below." if kind else "")
    else:
        reply = "Thanks for letting me know. How can I help?" if not kind else \
            (f"{ASK[miss[0]]}" if miss else f"Your {WHAT[kind]} is ready below. Press Send when it looks right.")
    if mine and op == "none":
        reply = "Here's what's on your record." if "- none on record" not in system else \
            "I don't see any requests on your record here."
    return {"reply": reply, "task": {"op": op, "kind": task_kind, "fields": fields}, "other_needs": others,
            "show_my_requests": mine and op == "none",
            "handoff": {"team": team, "reason": "Asked for a person" if team != "none" else ""}, "language": "en"}


class MockProvider:
    name = "mock"

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        turn = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        if schema_name == "mckinley_assistant":
            content = json.dumps(assistant_reply(system, turn))
        else:  # e.g. the optional semantic safety classifier: the mock offers no opinion (rules decide)
            content = json.dumps({"reply": "mock"})
        reply = json.loads(content).get("reply", "")
        return LLMResult(output=ModelOutput(reply=reply or "mock"), provider=self.name, requested_model=target.model,
                         model=target.model, stop_reason="mock", input_tokens=len(system.split()) + len(turn.split()),
                         output_tokens=len(content.split()), latency_ms=5, parse_mode="json", is_mock=True,
                         estimated_cost_usd=0.0, extra={"content": content})
