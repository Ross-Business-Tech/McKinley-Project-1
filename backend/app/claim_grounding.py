"""Ground what a model reply says about requests and McKinley staff in the turn's real backend state.

The response model may write warm, natural wording, but it does not decide what happened. The backend does:
`TurnPlan.action` (the card on screen and its stage), `TurnPlan.records` (prototype rows written THIS turn) and each
record's `system`. Every record today has `system == "prototype"`: it is saved in the demo store and reaches no one.
So any sentence in which McKinley staff receive, review, follow up, call, visit, schedule or confirm something, in
which Send delivers the request to a team, or in which the assistant says it notified, sent, escalated or booked
something, asserts a side effect that the state does not contain. Such clauses are removed, and when the card is
ready the one next-step sentence comes from the card's real stage. A real integration would mark its records with
another `system`; only then could a claim about that party be supported (`delivered_parties`).

What stays: answers, empathy, questions, referrals of knowledge ("the leasing team has current prices"), negated or
explicitly hypothetical statements ("no one will call", "in the real service ..."), the entry-permission question
("if maintenance comes while you're out, may they enter?"), and statements backed by state (a card exists -> "I've
started your request"; a record was written -> "it's saved"; the draft carries the repeat flag -> "I've marked this
as a repeat issue"). The output validator (`app.safety.output_checks`) still runs afterwards as the backstop.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# ---- parties at McKinley (never the person themselves) ----------------------------------------------------------
_PARTY = (r"(?:mckinley(?:\s+(?:staff|team))?|(?:our|the|a|your)\s+(?:\w+\s+){0,2}(?:team|staff|crew|office|agents?|"
          r"specialists?|managers?|management|representatives?|technicians?|techs?|people|person)|staff(?:\s+members?)?|"
          r"team\s+members?|teammates?|(?:a|one)\s+member\s+of\s+(?:our|the)\s+\w+(?:\s+\w+)?|"
          r"maintenance(?!\s+(?:request|issue|problem|history|needs|ticket))|leasing(?:\s+\w+)?|"
          r"(?:community|property|office)\s+manager|managers?|someone|somebody|a\s+person|"
          r"el\s+(?:equipo|personal|gerente)|la\s+oficina|alguien)")
_ACT = (r"(?:follow(?:s|ing|ed)?\s+up|reach(?:es|ing)?\s+out|get(?:s|ting)?\s+(?:back|in\s+touch)|contact(?:s|ing)?|"
        r"call(?:s|ing)?|phone|text|e-?mail|review(?:s|ing)?|look(?:s|ing)?\s+(?:at|into|over)|check(?:s|ing)?\s+"
        r"(?:on|in|into|it|this)|visit(?:s|ing)?|come(?:s)?\s+(?:by|out|over)|stop(?:s)?\s+by|schedul\w+|book\w*|"
        r"confirm\w*|finali[sz]\w+|arrang\w+|coordinat\w+|assign\w*|dispatch\w*|fix(?:es|ing)?|address(?:es|ing)?|"
        r"handl\w+|take\s+care|process\w*|prioriti[sz]\w+|receiv\w+|get(?:s)?\s+(?:it|this|your|the)|see(?:s)?\s+"
        r"(?:it|this|your)|assist\w*|help\s+you|work\s+with\s+you|repl(?:y|ies)|respond\w*|let\s+you\s+know|"
        r"notif\w+|update\s+you|share|give\s+you|send\s+you|provide|meet|show\s+you|walk\s+you|"
        r"se\s+comunicar\w*|llamar\w*|contactar\w*|revisar\w*|recibir\w*|programar\w*|confirmar\w*|visitar\w*|"
        r"atender\w*|ayudar\w*|la\s+reciba|lo\s+reciba)")
# Modality decides what a staff sentence asserts. will/should/going to = a promise of action; can/could = a claim only
# for contact-type actions ("the team can follow up"), otherwise a capability referral ("can walk you through it");
# would = hypothetical (not a claim).
_FUTURE = r"(?:will|'ll|’ll|shall|is\s+going\s+to|are\s+going\s+to|should|may|might|is\s+about\s+to)"
_CAN = r"(?:can|could)"
_CONTACT = (r"(?:follow(?:s|ing)?\s+up|reach(?:es|ing)?\s+out|get(?:s|ting)?\s+(?:back|in\s+touch)|contact\w*|"
            r"call\w*|phone|text|e-?mail|review\s+(?:it|this|your|the)|visit\w*|come\s+(?:by|out|over)|stop\s+by|"
            r"schedul\w+|book\w*|confirm\w*|receiv\w+|get\s+(?:it|this|your)|see\s+(?:it|this|your)|"
            r"let\s+you\s+know|notif\w+|update\s+you|send\s+you|reply|respond\w*)")
_DONE_PASSIVE = r"(?:received|notified|reviewed|scheduled|confirmed|assigned|alerted|informed|dispatched|told)"

_STAFF_ACTION = re.compile(
    rf"\b{_PARTY}\s+(?:\w+\s+){{0,2}}{_FUTURE}\s+(?:\w+\s+){{0,2}}{_ACT}\b"
    rf"|\b{_PARTY}\s+(?:\w+\s+){{0,2}}{_CAN}\s+(?:\w+\s+){{0,1}}{_CONTACT}\b"
    rf"|\b{_PARTY}\s+(?:\w+\s+){{0,1}}(?:has|have|had|was|were|is|are)\s+(?:been\s+|now\s+|already\s+)?{_DONE_PASSIVE}\b",
    re.I)
_PURPOSE = re.compile(rf"\b(?:so(?:\s+that)?|para\s+que)\s+{_PARTY}\s+(?:\w+\s+){{0,3}}{_ACT}\b"
                      rf"|\bfor\s+{_PARTY}\s+to\s+(?:\w+\s+){{0,2}}{_ACT}\b"
                      rf"|\bso(?:\s+that)?\s+they\s+(?:can|could|will|'ll|’ll)\s+(?:\w+\s+){{0,1}}{_CONTACT}\b", re.I)
_DELIVERY = re.compile(rf"\b(?:send|submit|pass|forward|route|escalat\w+|hand(?:\s+(?:it|this))?\s+(?:over|off)|"
                       rf"get\s+(?:it|this))\w*\s+(?:\w+\s+){{0,4}}(?:to|over\s+to|along\s+to|with)\s+{_PARTY}"
                       rf"|\bsave\s+it\s+for\s+{_PARTY}", re.I)
# Offers of the note/request action the backend really has ("I can send a note to the office", "want me to pass your
# question to the leasing team?"): the card's own demo line states what Send does.
_OFFER_LEAD = re.compile(r"\b(?:I\s+(?:can|could|'ll|’ll|will|am\s+happy\s+to|'d\s+be\s+happy\s+to|"
                         r"would\s+be\s+happy\s+to)|want\s+me\s+to|would\s+you\s+like\s+me\s+to|shall\s+I|"
                         r"should\s+I|puedo|le\s+paso)\b", re.I)
# The person's own request being described ("You also asked for the office to contact you", "your note asking for a
# call"), not a promise.
_THEIR_ASK = re.compile(r"\b(?:you\s+(?:also\s+)?(?:asked|requested|wanted|want)|asking|requested|pidió|pide)\b", re.I)
_BUTTON = re.compile(r"^(?:please\s+|just\s+|then\s+|when\s+you'?re\s+ready,?\s+)?(?:press|tap|click)?\s*"
                     r"[\"“']?\s*send\b|[\"“][^\"”]*\bsend\b[^\"”]*[\"”]", re.I)
_BOOKED = re.compile(r"\b(?:you'?re|you\s+are|it'?s|it\s+is|that'?s|(?:the\s+|your\s+)?(?:tour|visit|appointment|"
                     r"time|request|booking)\s+(?:is|has\s+been))\s+(?:all\s+|now\s+)?(?:booked|confirmed|scheduled|"
                     r"reserved|locked\s+in|set\s+up|on\s+(?:the|their)\s+calendar)\b", re.I)
_DONE = re.compile(r"\b(?:I(?:'ve|’ve|\s+have|'m|’m|\s+am)?|we(?:'ve|\s+have)?|he|hemos)\s+"
                   r"(?:just\s+|already\s+|now\s+)?"
                   r"(flagged|marked|marking|escalat\w+|notifi\w+|alert\w+|informed|told|sent|sending|submitted|"
                   r"submitting|forward\w+|passed|passing|booked|booking|scheduled|scheduling|reserved|confirmed|"
                   r"locked|logged|filed|placed|prioriti[sz]\w+|assigned|routed|shared|enviado|notificado|"
                   r"programado|reservado|confirmado|avisado)\b", re.I)
_MARKED_ES = re.compile(r"\b(?:la|lo)\s+marqu[ée]\b", re.I)
# Contact implied without a staff subject: "a time you prefer for a call", "best number to be reached at".
_CALL_PREF = re.compile(r"\b(?:prefer\w*|best|good|convenient|works?)\b[^.?!]{0,40}\bfor\s+a\s+"
                        r"(?:call|callback|call\s+back)\b|\bto\s+be\s+(?:called|contacted|reached)\b|"
                        r"\bcall\s+you\s+back\b", re.I)
# Spanish word order: "para que la reciba el equipo", "el equipo se comunicará / lo revisará".
_ES_PURPOSE = re.compile(r"\bpara\s+que\s+(?:la|lo|le|se)\s+\w+\s+(?:el|la)\s+(?:equipo|personal|gerente|oficina)\b",
                         re.I)
_ES_FUTURE = re.compile(r"\b(?:el\s+equipo|el\s+personal|el\s+gerente|la\s+oficina|alguien|mantenimiento)\b[^.?!]{0,30}"
                        r"\b(?:se\s+|le\s+|lo\s+|la\s+)?\w+(?:ará|erá|irá|arán|erán|irán)\b", re.I)
# The planner's own repeat label ("... a repeat issue for the community manager to review"): a label on the request,
# allowed only while the draft really carries the repeat flag.
_REPEAT_LABEL = re.compile(r"\bfor\s+(?:the\s+|a\s+)?(?:community\s+)?(?:manager|team)"
                           r"(?:\s+to\s+review|\s+review|'s\s+review)\b|"
                           r"\bpara\s+que\s+la\s+revise\s+(?:el|un)\s+gerente(?:\s+de\s+la\s+comunidad)?\b|"
                           r"\bpara\s+revisi[oó]n\s+del\s+gerente(?:\s+de\s+la\s+comunidad)?\b", re.I)

_NEGATED = re.compile(r"\b(?:no\s+one|nobody|nadie|not|never|won'?t|wont|isn'?t|hasn'?t|haven'?t|wasn'?t|can'?t|"
                      r"cannot|no|ni)\b|n't\b", re.I)
_NOT_NEGATION = re.compile(r"\b(?:don'?t\s+worry|no\s+problem|no\s+worries|not\s+sure|no\s+rush)\b", re.I)
_HYPOTHETICAL = re.compile(r"\bin\s+(?:the|a)\s+real\s+(?:service|system)\b|\ben\s+el\s+servicio\s+real\b", re.I)
# "If maintenance comes while you're out, may they enter, or should they contact you first?" (the planner's own
# entry-permission question) and other conditionals about a visit the person is being asked about.
_ENTRY_QUESTION = re.compile(r"\b(?:if|when|si|cuando)\b[^.?!]{0,60}\b(?:come|comes|visit|visits|need|needs|stop|"
                             r"vengan?|visiten?)\b|\b(?:may|can|should)\s+they\s+(?:enter|come\s+in|contact\s+you\s+"
                             r"first)|\bpermission\b|\bpermiso\b", re.I)
# Knowledge referrals: who HAS the answer, not who will act ("the leasing team has current prices / can answer that /
# is best placed to share rates").
_REFERRAL = re.compile(rf"\b{_PARTY}\s+(?:\w+\s+){{0,2}}(?:has|have|knows?|keeps?|can\s+answer|could\s+answer|"
                       rf"can\s+(?:give\s+you|share|provide|offer)\s+(?:\w+\s+){{0,2}}(?:information|details|answers|"
                       rf"rates|prices|options)|can\s+(?:tell\s+you|explain|walk\s+you\s+through|help\s+with)|"
                       rf"(?:is|are|will\s+be)\s+(?:the\s+)?best\s+(?:placed|equipped|positioned|position)|"
                       rf"(?:is|are)\s+(?:in\s+)?the\s+best\s+position)\b", re.I)

_STATE_LINE = {
    "en": "When it looks right, press Send to save it.",
    "es": "Cuando esté bien, presione Enviar para guardarla.",
}


@dataclass(frozen=True)
class TurnState:
    """The authoritative facts for one turn, taken from the plan (never from model text)."""

    card_kind: str | None = None
    card_stage: str | None = None  # collecting | ready | submitted | blocked
    records_written: tuple[str, ...] = ()  # ids written THIS turn
    delivered_parties: frozenset[str] = frozenset()  # parties a real integration delivered to (none: prototype only)
    repeat_marked: bool = False
    priority_marked: bool = False  # the draft/record really carries high or urgent priority
    lang: str = "en"

    @classmethod
    def from_plan(cls, plan: Any, lang: str = "en") -> "TurnState":
        if plan is None:
            return cls(lang=lang)
        a = getattr(plan, "action", None)
        records = list(getattr(plan, "records", None) or [])
        if a is not None and getattr(a, "record", None) is not None and a.record not in records:
            records.append(a.record)
        delivered = frozenset(str(getattr(r, "team", "") or "") for r in records
                              if getattr(r, "system", "prototype") != "prototype")
        values = " ".join(str(getattr(f, "value", "") or "") for f in (getattr(a, "fields", None) or []))
        facts = " ".join(getattr(plan, "facts", None) or [])
        repeat = bool(re.search(r"\brepeat\b|repetid", f"{values} {facts}", re.I))
        priority = any(str(getattr(r, "priority", "") or "") in ("high", "urgent")
                       or getattr(r, "status", "") == "urgent_queued" for r in records) or bool(
            re.search(r"\burgent\b|\bhigh\s+priority\b|\burgente\b", values, re.I))
        return cls(card_kind=a.kind if a else None, card_stage=a.stage if a else None,
                   records_written=tuple(str(getattr(r, "id", "")) for r in records), delivered_parties=delivered,
                   repeat_marked=repeat, priority_marked=priority, lang=lang)


@dataclass
class GroundingResult:
    reply: str
    removed: list[tuple[str, str]] = field(default_factory=list)  # (kind, clause)
    status_line_added: bool = False
    needs_template: bool = False  # the cleaned reply lost what the turn needed (fall back to the planner's draft)

    @property
    def changed(self) -> bool:
        return bool(self.removed) or self.status_line_added


_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CLAUSE = re.compile(r"\s*[—–;]\s*|\s+-\s+")


def _clauses(reply: str) -> list[str]:
    out: list[str] = []
    for s in _SENTENCE.split(reply.strip()):
        parts = [p for p in _CLAUSE.split(s) if p.strip()]
        out.extend(parts or [s])
    return [c.strip() for c in out if c.strip()]


def _honest(clause: str) -> bool:
    stripped = _NOT_NEGATION.sub("", clause)
    return bool(_NEGATED.search(stripped)) or bool(_HYPOTHETICAL.search(clause))


def unsupported_claim(clause: str, state: TurnState) -> str | None:
    """The kind of side effect this clause asserts that the state does not contain, or None."""
    if _honest(clause):
        return None
    labelled = state.repeat_marked or state.priority_marked
    if labelled:
        clause = _REPEAT_LABEL.sub("", clause)  # the request's real flag ("for the manager to review"), not a promise
    m = _DONE.search(clause)
    if m:
        verb = m.group(1).lower()
        if not (verb in ("flagged", "marked", "marking") and labelled):
            return "assistant_action"
    if _MARKED_ES.search(clause) and not labelled:
        return "assistant_action"
    if state.delivered_parties:
        return None  # a real integration delivered this turn's record (none exists in the prototype)
    if _CALL_PREF.search(clause) and not _THEIR_ASK.search(clause):
        return "staff_action"
    if _ES_PURPOSE.search(clause) or _ES_FUTURE.search(clause):
        return "staff_action"
    if _BOOKED.search(clause):
        return "booking"
    d = _DELIVERY.search(clause)
    b = _BUTTON.search(clause)
    on_button = bool(b and b.start() <= d.start() < b.end()) if d else False  # "Send it to the office" = the button
    if d and not (on_button or _OFFER_LEAD.search(clause[:d.start()])):
        return "delivery"
    p = _PURPOSE.search(clause)
    if p and not _ENTRY_QUESTION.search(clause) and not _THEIR_ASK.search(clause[:p.start()]):
        return "staff_action"
    if _STAFF_ACTION.search(clause) and not (_ENTRY_QUESTION.search(clause) or _REFERRAL.search(clause)):
        return "staff_action"
    return None


def _join(clauses: list[str]) -> str:
    out: list[str] = []
    for c in clauses:
        c = c.strip()
        if not c:
            continue
        if out and not re.search(r"[.!?]$", out[-1]):
            out[-1] += "."
        out.append(c[0].upper() + c[1:] if c[0].islower() else c)
    text = " ".join(out)
    return text if not text or re.search(r"[.!?]$", text) else text + "."


def ground_reply(reply: str, state: TurnState) -> GroundingResult:
    """Remove clauses that assert side effects the backend state does not contain; add the state's next step."""
    clauses = _clauses(reply)
    kept: list[str] = []
    removed: list[tuple[str, str]] = []
    for c in clauses:
        kind = unsupported_claim(c, state)
        if kind:
            removed.append((kind, c))
        else:
            kept.append(c)
    res = GroundingResult(reply=reply, removed=removed)
    if not removed:
        return res
    asked_before = "?" in reply
    text = _join(kept)
    if state.card_stage == "ready" and not re.search(r"\b(?:send|enviar|envíe|envie)\b", text, re.I):
        line = _STATE_LINE.get(state.lang, _STATE_LINE["en"])
        # the next step goes before a closing question, so the reply still ends with what it asks
        tail = [kept.pop()] if kept and kept[-1].rstrip().endswith("?") else []
        text = _join([*kept, line, *tail])
        res.status_line_added = True
    res.reply = text
    if not text.strip() or (state.card_stage == "collecting" and asked_before and "?" not in text):
        res.needs_template = True
    return res


def check_detail(res: GroundingResult) -> str:
    if not res.removed:
        return "No claims about staff or completed actions beyond the backend state"
    kinds = ", ".join(sorted({k for k, _ in res.removed}))
    return (f"Removed {len(res.removed)} unsupported clause(s) ({kinds}): nothing reaches McKinley staff in this demo"
            + ("; next step taken from the card's state" if res.status_line_added else ""))
