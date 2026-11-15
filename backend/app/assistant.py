"""The conversational turn: one language-model call that understands the message in context and answers it.

The model gets only what this person is authorized to see (their minimized resident context, their own task state,
approved property facts) and returns a natural reply plus at most ONE proposed task operation. The proposal is
validated here and applied by `app.tasks`; the model can never save a request, change identity, or reach another
resident's data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm import LLMError, LLMGateway, LLMResult, Target
from app.models import SafeContext
from app.tasks import FIELDS, Lang

TASK_FIELDS = sorted({f for fs in FIELDS.values() for f in fs} - {"history", "earlier"})
SCHEMA_NAME = "mckinley_assistant"
SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["reply", "task", "other_needs", "show_my_requests", "include_history", "handoff", "language"],
    "properties": {
        "reply": {"type": "string"},
        "task": {"type": "object", "additionalProperties": False, "required": ["op", "kind", "fields"],
                 "properties": {
                     "op": {"type": "string", "enum": ["none", "start", "update", "suspend", "resume", "cancel"]},
                     "kind": {"type": "string",
                              "enum": ["none", "maintenance_request", "tour_request", "staff_handoff"]},
                     "fields": {"type": "object", "additionalProperties": False, "required": TASK_FIELDS,
                                "properties": {f: {"type": "string"} for f in TASK_FIELDS}}}},
        # remediation P2: each further need says what it is, so a second repair waits as a repair, not as a note
        "other_needs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "text"],
            "properties": {"kind": {"type": "string", "enum": ["maintenance_request", "tour_request", "staff_handoff"]},
                           "text": {"type": "string"}}}},
        "show_my_requests": {"type": "boolean"},
        "include_history": {"type": "string", "enum": ["none", "related", "all"]},
        "handoff": {"type": "object", "additionalProperties": False, "required": ["team", "reason"],
                    "properties": {"team": {"type": "string",
                                            "enum": ["none", "maintenance", "leasing", "accounting", "management"]},
                                   "reason": {"type": "string"}}},
        "language": {"type": "string", "enum": ["en", "es"]},
    },
}


class Proposal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reply: str = Field(min_length=1, max_length=1500)
    op: str = "none"
    kind: str = "none"
    fields: dict[str, str] = Field(default_factory=dict)
    other_needs: list[str] = Field(default_factory=list)
    other_kinds: list[str] = Field(default_factory=list)  # same order as other_needs
    show_my_requests: bool = False
    include_history: str = "none"
    team: str = "none"
    reason: str = ""
    language: str = "en"


@dataclass
class Turn:
    proposal: Proposal | None
    result: LLMResult | None
    error: str | None = None
    exc: LLMError | None = None
    notes: list[str] = field(default_factory=list)


RULES = """You are McKinley's automated assistant for residents and people looking for an apartment. You are not a
person. Be warm, brief (1-3 sentences) and natural. Answer what the person actually asked.

Facts you may use are below. Never invent policies, prices, availability, dates, names or reference numbers. If you
don't have an answer, say so plainly and offer a note for the office.

This is a PROTOTYPE. Nothing you do reaches McKinley staff, Yardi or anyone else. Never say a request, note or
message was sent, filed, scheduled or that someone will call, visit or follow up. A card is saved (in this demo only)
when the person presses Send on it; you cannot save anything yourself. The card on screen already says it is a demo:
don't repeat that in your reply unless they ask whether something was sent or who will see it.
If their context shows an open related request or a repeat-issue flag, acknowledge it briefly and kindly (for example
that it has happened before and a request is still open) - their own history only.

Tasks (one card is on screen at a time; the backend keeps the others waiting, unchanged):
- maintenance_request: a repair for a signed-in resident. Fields: issue, location (room), entry (may maintenance
  enter if they're out, or contact first). Ask for one missing field at a time.
- tour_request: fields area (community or city), days, time.
- staff_handoff: a note for the office (a person asked for, a question only staff can answer, a complaint, a
  billing or lease question). Fields: topic, message. For a visitor who is NOT signed in, a repair is a
  maintenance_request (the backend turns it into a note for the office that needs community and unit); never ask a
  visitor for name, phone or email.
- A question you can't answer (a lease, renewal or billing question): answer what you can and OFFER a note; start a
  staff_handoff only when they accept or ask for a person.
Choose task.op:
- start: a new need that needs a card. update: the person gave or corrected details for the ACTIVE card.
- resume: they want to go back to a waiting or cancelled card (name its kind). suspend: they want to set the active
  card aside for now. cancel: they don't want the active card. none: anything else (questions, small talk) - the
  active card stays exactly as it is.
- If the task state says a card is back after an emergency, tell them gently, once. Never say YOU checked or
  confirmed that a place is safe: only repeat who told them (for example "since the gas company says it's fixed").
- Put only values the person actually said in task.fields; use "" for the rest.
- If the message asks for two different things, handle the first and put each other need in other_needs with its
  kind: maintenance_request for another repair, tour_request for a tour, staff_handoff for anything else.
- handoff.team: the team that should see it when a person is needed, else "none".
- show_my_requests: true when they ask about the status or history of THEIR OWN requests (the list below is theirs;
  nothing else exists for you). Never describe anyone else's requests.
- include_history (for a note): "related" when they want their earlier requests about THIS problem on it, "all" only
  when they explicitly ask for their whole repair history, else "none". The backend adds those lines from their
  record; don't copy history into task.fields.message, and in your reply mention only requests about this problem
  unless they asked for everything.
Respond in the person's language (language: en or es). Return only the JSON object."""


def system_prompt(ctx: SafeContext, verified: bool, task_state: str, facts: str, resumed: str | None,
                  own: str = "") -> str:
    who = (f"Signed-in synthetic resident (demo sign-in, not real authentication): {ctx.persona_id}"
           if verified else "A visitor who is NOT signed in: no account details are available to you or to them"
           if ctx.audience != "prospect" else "A prospective renter (no account)")
    context = "\n".join(f"- {f.name}: {f.value}" for f in ctx.fields) or "- (none)"
    extra = f"\nNote: {resumed}" if resumed else ""
    return (f"{RULES}\n\n## Who you are talking to\n{who}\n\n## Their authorized context (theirs only)\n{context}\n\n"
            f"## Their own requests\n{own or '- none on record'}\n\n"
            f"## Approved property information\n{facts}\n\n## Task state\n{task_state}{extra}")


def _needs(raw: Any) -> list[tuple[str, str]]:
    """(text, kind) for each further need; a plain string (older output) is a note for the office."""
    out = []
    for x in raw or []:
        text, kind = (str(x.get("text") or ""), str(x.get("kind") or "staff_handoff")) if isinstance(x, dict) else (
            str(x), "staff_handoff")
        if text.strip():
            known = kind in ("maintenance_request", "tour_request")
            out.append((text.strip()[:200], kind if known else "staff_handoff"))
    return out[:3]


def ask(gateway: LLMGateway, target: Target, system: str, history: list[dict[str, str]], msg: str) -> Turn:
    """The single model call of an ordinary turn. Any failure returns Turn(proposal=None) and the caller answers
    with a fixed message; the task state is never changed by a failed call."""
    try:
        result = gateway.complete(system, [*history[-10:], {"role": "user", "content": msg}], target,
                                  schema=SCHEMA, schema_name=SCHEMA_NAME)
    except LLMError as e:
        return Turn(None, None, e.code, e)
    raw = str(result.extra.get("content") or "")
    try:
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        task, hand = data.get("task") or {}, data.get("handoff") or {}
        p = Proposal(reply=str(data.get("reply") or "").strip(), op=str(task.get("op") or "none"),
                     kind=str(task.get("kind") or "none"),
                     fields={k: str(v) for k, v in (task.get("fields") or {}).items() if v},
                     other_needs=[n for n, _ in _needs(data.get("other_needs"))],
                     other_kinds=[k for _, k in _needs(data.get("other_needs"))],
                     show_my_requests=bool(data.get("show_my_requests")),
                     include_history=str(data.get("include_history") or "none"),
                     team=str(hand.get("team") or "none"), reason=str(hand.get("reason") or "")[:200],
                     language=str(data.get("language") or "en"))
    except (ValueError, ValidationError):
        return Turn(None, result, "BAD_OUTPUT")
    return Turn(p, result)


# Spanish marker words (the previous detector's list): two or more, or ¿ ¡ ñ, means the message is Spanish.
_ES_WORDS = re.compile(
    r"\b(hola|gracias|por favor|necesito|tengo|mi|mis|está|esta|no funciona|ayuda|cocina|baño|bano|puerta|"
    r"reportar|reparaci[oó]n|solicitudes|una|oficina|ver|env[ií]elo|"
    r"agua|luz|renta|contrato|cuándo|cuando|quiero|hablar|persona|apartamento|horno|fuga|gotea|olor|"
    r"mantenimiento|solicitud|estado|sí|usted|español|espanol|el|la|los|las|refrigerador|enfría|enfria|"
    r"funciona|lavaplatos|ba[ñn]era|ducha|calefacci[oó]n|aire|luz|puede|pueden|entrar|hay|muy|también|"
    # Sprint 7: prospects' Spanish ("busco un apartamento de 1 recámara", "me gustaría visitar ... el sábado")
    r"busco|buscando|interesa|rec[aá]maras?|departamento|gustar[ií]a|visitar|visita|recorrido|barato|rentar|"
    r"cu[aá]nto|cuesta|precio|mascotas|dep[oó]sito|d[oó]nde|ubicados|s[aá]bado|domingo|lunes|martes|mi[eé]rcoles|"
    r"jueves|viernes|tarde|noche|un|una|de|del|con|para|que|es|agendar|disponibles?|lugar|pr[oó]ximo|mes|ba[ñn]os)\b",
    re.IGNORECASE)


def language(msg: str, previous: str | None, preferred: str | None) -> Lang:
    """Spanish when the message reads as Spanish; a short or unclear message keeps the conversation's language."""
    hits = len(_ES_WORDS.findall(msg))
    if hits >= 2 or re.search(r"[¿¡ñ]", msg):
        return "es"
    if re.search(r"\b(?:the|my|is|are|and|please|what|can|it|i|you|with|need|this)\b", msg, re.I):
        return "en"
    if previous in ("en", "es"):
        return previous  # type: ignore[return-value]
    return "es" if (preferred or "").lower().startswith("span") or hits else "en"
