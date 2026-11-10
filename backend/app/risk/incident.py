"""Layer 5 (sprint 6): persistent incident state for active emergencies.

When a turn raises a full alert, an incident is opened for the session (kind, started_at, last_seen_turn,
status=active). While it is active, every later turn is classified before the normal flow sees it:

  resolved  explicit resolution: responders arrived AND handled it ("the fire department is here and it's out",
            "paramedics took him", "police arrested him"), or "all clear" from responders. A negated or future
            version ("the ambulance isn't here yet", "they're on the way") is not a resolution.
  ack       a short acknowledgement or a status line ("ok", "calling now", "I called 911", "we're outside").
            "I'm fine" / "I'm safe" is an ack only when the person themselves was the one in danger; for a
            third-party emergency (someone else unwell, poisoned, trapped) it is treated as a follow-up.
  topic     a clearly different request (rent, tour, pool hours, a repair) with no danger, person or
            continuation words.
  follow    anything else: "he's still not waking up", "what now", "she won't leave", "my kid is here too",
            "there's no smoke now" (a negation does not clear the incident), "what if it starts again".

Effects on the safety decision (applied after the policy, so they can only ADD caution):
  follow -> the full alert for the incident's kind again (rule R10): the approved notice is shown FIRST and the
            planner's emergency step runs (no new note for the same kind, never a repair form).
  ack / topic -> a "quiet" turn: if the policy would show nothing, the calm line is kept (rule R10q: 988 after
            self-harm, else 911). QUIET_TURNS_TO_RESOLVE quiet turns in a row resolve the incident.
  resolved -> the incident closes; the turn is decided by the policy alone, and later turns work normally.

Storage: one JSON row per change in the existing gate_decisions table under the mode key INCIDENT_MODE (no schema
change, works on SQLite and Postgres, keeps RLS). The row holds kind, status, turn numbers and timestamps only, never
message text. Only the planner's emergency steps and this module read it.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel

from app.db import now_iso
from app.emergency import possible_risk, scan
from app.risk.models import RiskAssessment, RiskDecision

INCIDENT_MODE = "safety_incident"
QUIET_TURNS_TO_RESOLVE = 3
THIRD_PARTY_KINDS = {"medical", "poison", "trapped"}
Turn = Literal["resolved", "ack", "topic", "follow"]


class Incident(BaseModel):
    kind: str
    status: Literal["active", "resolved"] = "active"
    started_at: str
    opened_turn: int
    last_seen_turn: int
    quiet: int = 0
    third_party: bool = False
    resolved_reason: str | None = None
    resolved_at: str | None = None
    kinds: list[str] = []  # every alert kind raised during this incident, in order (no text)


# ---- message classes -------------------------------------------------------------------------------------------
_RESPONDER = (r"\b(?:fire ?(?:department|dept|fighters?|men|truck)|firefighters?|paramedics?|ambulance|emts?|medics?|"
              r"police|cops?|officers?|sheriff|security|911|the gas company|gas company|utility|maintenance|"
              r"the (?:tech|plumber|electrician)|responders?|bomberos|polic[ií]a|param[eé]dicos|ambulancia)\b")
_HANDLED = (r"\b(?:(?:is|are|'s|'re|got) here|arrived|showed up|came|took (?:him|her|them|it)|has (?:him|her|them)|"
            r"got (?:him|her|them|it)|is with (?:him|her|them|us|me)|are with (?:him|her|them|us|me)|"
            r"put it out|put out|it'?s out|is out|are out|shut (?:it|the \w+) off|turned (?:it|the \w+) off|"
            r"fixed|handled|arrested|took (?:him|her|them) away|left with|cleared|all clear|said it'?s safe|"
            r"said (?:we|it) (?:can|is)|lleg(?:ó|aron)|se (?:lo|la|los) llevaron|lo apagaron|ya est[aá]n aqu[ií])\b")
_RESOLVED_ALONE = re.compile(
    r"\ball clear\b|\b(?:fire|it|the fire)(?:'s| is| was) (?:out|put out|completely out)\b.*\b(?:fire ?(?:department|"
    r"fighters?)|they|911)\b|\b(?:he|she|they)(?:'s| is| are|'re) (?:at|in) the hospital\b|"
    r"\b(?:on (?:the|their) way to|took (?:him|her|them) to) the hospital\b|"
    r"\b(?:police|cops) (?:arrested|took) (?:him|her|them)\b|"
    r"\bya pas[oó] todo\b|\bya se fue (?:con la|la) polic[ií]a\b", re.I)
_NOT_YET = re.compile(r"\b(?:not|isn'?t|aren'?t|haven'?t|hasn'?t|didn'?t|no one|nobody|still waiting|on (?:the|their) "
                      r"way|coming|will be|yet|todav[ií]a no|no (?:han|ha) llegado)\b", re.I)
_ACK = re.compile(
    r"^\W*(?:ok(?:ay)?|k|kk|alright|all right|got it|understood|will do|thanks?|thank you|ty|thx|calling(?: (?:them|"
    r"911|now))?(?: now)?|i(?:'m| am) calling(?: 911| them)?(?: now)?|(?:i|we) (?:already )?called(?: 911| them| the"
    r" \w+)?(?: already)?|(?:i|we)(?:'re| are| am|'m) (?:outside|out|out of the (?:building|apartment|unit)|downstairs|"
    r"in the (?:lobby|parking lot|car))(?: now)?|(?:we|i)(?:'re| are| am|'m) (?:all )?(?:safe|fine|ok(?:ay)?|good)"
    r"(?: now)?|on it|doing it|ya (?:llam[eé]|sal[ií]|salimos)|gracias|entendido|vale|listo|estamos (?:afuera|bien)"
    r"|estoy (?:afuera|bien))(?:[\s,.!]+(?:ok(?:ay)?|thanks?|thank you|gracias|now|already|ya))*\W*$", re.I)
_SELF_FINE = re.compile(r"\b(?:i'?m|i am|we'?re|we are|estoy|estamos)\s+(?:all\s+)?(?:fine|ok(?:ay)?|good|safe|bien)\b",
                        re.I)
_PRIVACY_OR_STATUS = re.compile(
    r"\bwho (?:can|will) (?:see|read)\b|\b(?:is|was) (?:it|this|my note) (?:saved|sent|private)\b|\bdid (?:you|it) "
    r"(?:send|save)\b|\bprivacy\b|\bprivate\b|\bqui[eé]n (?:puede|va a) (?:ver|leer)\b", re.I)
_TOPIC = re.compile(
    r"\b(?:rent|pay(?:ment)?|balance|lease|renew\w*|tour|pool|gym|fitness|parking|package|amenit\w*|hours|open|"
    r"application|apply|pet policy|wifi|internet|move[- ]?in|move[- ]?out|deposit|floor ?plans?|availability|"
    r"faucet|sink|toilet|dishwasher|fridge|refrigerator|washer|dryer|garbage disposal|light bulb|door ?knob|"
    r"cabinet|blinds|thermostat|ac\b|a/c|air condition\w*|renta|alquiler|piscina|contrato)\b", re.I)
# Words that tie a message to the emergency (a person, the hazard, "still"): a message with these is never a topic
# change, even if it also mentions rent or a repair.
_CONTINUE_CUE = re.compile(
    r"\b(?:still|again|worse|getting worse|spreading|help|he|she|they|him|her|them|his|kid|kids|baby|child|son|"
    r"daughter|mom|dad|grand\w+|"
    r"wife|husband|partner|roommate|neighbou?r|dog|cat|smoke|fire|gas|smell\w*|spark\w*|alarm|breath\w*|wake|"
    r"bleed\w*|blood|hurt\w*|sick|dizzy|unconscious|todav[ií]a|sigue|ayuda)\b", re.I)


_WHAT_NOW = re.compile(
    r"\bwhat (?:now|next|do (?:i|we) do|should (?:i|we) do|can (?:i|we) do|else)\b|\bnow what\b|\bwhat do i do\b|"
    r"\bis (?:help|someone|anyone|anybody) coming\b|\b(?:is|are) (?:they|you|someone) (?:coming|sending)\b|"
    r"\bhow long\b|\bshould (?:i|we) (?:go|leave|stay|wait|call|open|move|touch)\b|\bcan (?:i|we) go back\b|"
    r"\b(?:qu[eé] hago|y ahora|qu[eé] (?:debo|puedo) hacer|viene alguien)\b", re.I)


def classify(message: str, inc: Incident) -> Turn:
    text = message.strip()
    low = text.lower()
    if (re.search(_RESPONDER, low, re.I) and re.search(_HANDLED, low, re.I) and not _NOT_YET.search(low)) or (
            _RESOLVED_ALONE.search(low) and not _NOT_YET.search(low)):
        return "resolved"
    if _PRIVACY_OR_STATUS.search(low):
        return "ack"  # the planner answers privacy / status questions after an alert; the calm line stays
    if _ACK.match(low):
        if inc.third_party and _SELF_FINE.search(low):
            return "follow"  # "I'm fine" is about the speaker, not the person who is in danger
        return "ack"
    if _WHAT_NOW.search(low) or _CONTINUE_CUE.search(low) or (inc.third_party and _SELF_FINE.search(low)):
        return "follow"
    if possible_risk(text) or scan(text)[0]:
        return "follow"  # danger words, or the hazard named again (even negated / past / hypothetical)
    return "topic" if _TOPIC.search(low) else "ack"


# ---- storage ---------------------------------------------------------------------------------------------------
def load(store: Any, session_id: str, persona_key: str) -> Incident | None:
    if store is None:
        return None
    try:
        row = store.last_gate(session_id, INCIDENT_MODE, persona_key)
    except Exception:  # a storage failure must never break the safety step
        return None
    try:
        return Incident.model_validate(row) if row else None
    except Exception:
        return None


def active(store: Any, session_id: str, persona_key: str) -> Incident | None:
    inc = load(store, session_id, persona_key)
    return inc if inc and inc.status == "active" else None


def _save(store: Any, session_id: str, persona_key: str, inc: Incident) -> None:
    if store is None:
        return
    try:
        store.log_gate(session_id, INCIDENT_MODE, persona_key, inc.model_dump())
    except Exception:
        pass  # the turn still shows the right safety text; only continuity across turns is lost


_OTHER_PERSON = re.compile(
    r"\b(?:my|our|the|a|his|her) (?:\w+ )?(?:grand\w+|mom|mum|mother|dad|father|husband|wife|partner|roommate|"
    r"neighbou?r|kid|kids|son|daughter|baby|child|toddler|infant|friend|boyfriend|girlfriend|brother|sister|cousin|"
    r"man|woman|guy|lady|boy|girl|dog|cat|pet)\b|\b(?:he|she|they|him|her|them|someone|somebody)\b|"
    r"\bmi (?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|abuel[oa]|vecin[oa]|beb[eé]|amig[oa])\b", re.I)


def _call(decision: RiskDecision, inc: Incident, rule: str, conflict: str) -> RiskDecision:
    return decision.model_copy(update={"rule": rule, "incident": inc.kind, "conflict": conflict,
                                       "sources": list(dict.fromkeys([*decision.sources, "incident"]))})


def step(store: Any, session_id: str, persona_key: str, message: str, risk: RiskAssessment,
         turn: int) -> RiskAssessment:
    """Apply the incident state machine to this turn's assessment and persist the new state. Never lowers the
    policy's decision: it only re-issues the alert (R10) or keeps a calm line (R10q)."""
    d = risk.decision
    inc = load(store, session_id, persona_key)
    now = now_iso()
    if d.response == "full_alert" and d.kind:
        if inc and inc.status == "active":
            inc.kind, inc.last_seen_turn, inc.quiet = d.kind, turn, 0
            inc.kinds = [*inc.kinds, d.kind][-10:]
            inc.third_party = inc.third_party or (d.kind in THIRD_PARTY_KINDS and bool(_OTHER_PERSON.search(message)))
        else:
            inc = Incident(kind=d.kind, started_at=now, opened_turn=turn, last_seen_turn=turn, kinds=[d.kind],
                           third_party=d.kind in THIRD_PARTY_KINDS and bool(_OTHER_PERSON.search(message)))
        _save(store, session_id, persona_key, inc)
        return risk.model_copy(update={"decision": d.model_copy(update={"incident": inc.kind})})
    if not inc or inc.status != "active":
        return risk
    if inc.kind == "self_harm":
        # Self-harm keeps its reviewed flow: R9 shows the 988 line on every later turn (even after "I'm fine, stop")
        # and the planner (J-1) answers "what do I do" / privacy questions with the approved notice. Nothing here
        # may change it; the incident only records that the turn happened.
        inc.last_seen_turn = turn
        _save(store, session_id, persona_key, inc)
        return risk.model_copy(update={"decision": d.model_copy(update={"incident": inc.kind})})
    kind = classify(message, inc)
    inc.last_seen_turn = turn
    if kind == "resolved":
        inc.status, inc.resolved_reason, inc.resolved_at = "resolved", "explicit", now
        _save(store, session_id, persona_key, inc)
        return risk
    if kind == "follow":
        inc.quiet = 0
        _save(store, session_id, persona_key, inc)
        nd = d.model_copy(update={"response": "full_alert", "kind": inc.kind, "needs_human": True,
                                  "escalation_priority": "urgent", "care": None,
                                  "also_988": d.also_988 or (inc.kind == "poison" and "self_harm" in inc.kinds)})
        nd = _call(nd, inc, "R10", f"follow-up during an active {inc.kind} incident: approved notice repeated"
                   + (f" (policy alone: {d.rule})" if d.rule else ""))
        return risk.model_copy(update={"decision": nd})
    inc.quiet += 1
    if inc.quiet >= QUIET_TURNS_TO_RESOLVE:
        inc.status, inc.resolved_reason, inc.resolved_at = "resolved", f"{inc.quiet} quiet turns", now
    _save(store, session_id, persona_key, inc)
    if d.response == "none":
        care = "distress" if inc.kind == "self_harm" or "self_harm" in inc.kinds else "danger"
        nd = d.model_copy(update={"response": "care_line", "care": care})
        return risk.model_copy(update={"decision": _call(nd, inc, "R10q",
                                                         f"quiet turn during an active {inc.kind} incident: calm "
                                                         "line kept")})
    return risk.model_copy(update={"decision": d.model_copy(update={"incident": inc.kind})})


def summary(inc: Incident | None) -> dict[str, Any] | None:
    return inc.model_dump() if inc else None
