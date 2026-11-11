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
from app.emergency import asks_emergency_line, possible_risk, scan
from app.risk.frame import analyse as frame_of
from app.risk.models import RiskAssessment, RiskDecision

INCIDENT_MODE = "safety_incident"
QUIET_TURNS_TO_RESOLVE = 3
THIRD_PARTY_KINDS = {"medical", "poison", "trapped"}
Turn = Literal["resolved", "ack", "topic", "follow", "retracted", "controlled"]
RETRACT_WINDOW = 1  # a retraction closes an incident opened in this turn or the one before it
# Sprint 7 fix round: a property-hazard false alarm WITH a harmless cause ("false alarm, it was a candle") may close the
# incident a little later too (the hazard words it uses are already checked by is_retraction).
RETRACT_WINDOW_HAZARD = 3
# Kinds whose "it's under control now" closes the incident (the hazard is the building, and the resident stopped it).
# Fire, smoke and CO stay open until responders clear them (the approved notice: don't go back in until they say so).
CONTROLLABLE_KINDS = {"flood", "gas", "electrical", "structural"}


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
    safe: bool = False  # sprint 7: the resident said they are outside / safe (property hazards only)


# ---- message classes -------------------------------------------------------------------------------------------
_RESPONDER = (r"\b(?:fire ?(?:department|dept|fighters?|men|truck)|firefighters?|paramedics?|ambulance|emts?|medics?|"
              r"police|cops?|officers?|sheriff|security|911|the gas company|gas company|utility|maintenance|"
              r"the (?:tech|plumber|electrician)|responders?|bomberos|polic[ií]a|param[eé]dicos|ambulancia)\b")
_HANDLED = (r"\b(?:(?:is|are|'s|'re|got) here|arrived|showed up|came|took (?:him|her|them|it)|has (?:him|her|them)|"
            r"got (?:him|her|them|it)|is with (?:him|her|them|us|me)|are with (?:him|her|them|us|me)|"
            r"put it out|put out|it'?s out|is out|are out|shut (?:it|the \w+) off|turned (?:it|the \w+) off|"
            r"fixed|handled|arrested|took (?:him|her|them) away|left with|cleared|all clear|said it'?s safe|"
            r"said (?:its|it|everythings|everything|we|all)(?:'s| is| are|'re)? (?:fine|ok(?:ay)?|safe|good|clear)"
            r"(?: now)?|"
            r"said (?:we|it) (?:can|is)|"
            r"dijeron que (?:ya )?(?:est[aá] bien|todo (?:est[aá] )?bien|no hay peligro|es seguro)|lleg(?:ó|aron)|"
            r"se (?:lo|la|los) llevaron|lo apagaron|ya est[aá]n aqu[ií])\b")
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
    r"\b(?:still|again|worse|getting worse|spreading|help(?!\s+(?:me\s+)?(?:with|to|me (?:with|find|book|schedule|"
    r"understand|figure|set)|you|finding|booking))|he|she|they|him|her|them|his|kid|kids|baby|child|son|"
    r"daughter|mom|dad|grand\w+|"
    r"wife|husband|partner|roommate|neighbou?r|dog|cat|smoke|fire|gas|smell\w*|spark\w*|alarm|breath\w*|wake|"
    r"bleed\w*|blood|hurt\w*|sick|dizzy|unconscious|todav[ií]a|sigue|ayuda|"
    # sprint 7: the hazard getting closer / bigger, and Spanish continuation words
    r"closer|close to|bigger|higher|rising|spread\w*|outlets?|wires?|panel|ceiling|reaching|creciendo|subiendo|"
    r"m[aá]s cerca|enchufes?|peor|[eé]l|ella|est[aá]|sigue\w*|adentro|inside|in there)\b", re.I)


_WHAT_NOW = re.compile(
    r"\bwhat (?:now|next|do (?:i|we) do|should (?:i|we) do|can (?:i|we) do|else)\b|\bnow what\b|\bwhat do i do\b|"
    r"\bis (?:help|someone|anyone|anybody) coming\b|\b(?:is|are) (?:they|you|someone) (?:coming|sending)\b|"
    r"\bhow long\b|\bshould (?:i|we) (?:go|leave|stay|wait|call|open|move|touch)\b|\bcan (?:i|we) go back\b|"
    r"\b(?:qu[eé] hago|y ahora|qu[eé] (?:debo|puedo) hacer|viene alguien)\b", re.I)


# ---- fix round: retraction, hazard controlled, safety questions -----------------------------------------------
# An explicit "it was a misunderstanding" ("false alarm", "nobody is hurt", "I meant my texts"). Only closes an
# incident opened in this turn or the previous one, and never when the rest of the message still describes danger.
_RETRACT = re.compile(
    r"\bfalse alarm\b|\b(?:no ?one|nobody|no one)(?:'s| is| was| got| has been)? (?:\w+ )?(?:hurt|injured|in danger|"
    r"unconscious|sick|unresponsive|passed out)\b|\b(?:there'?s|there is|it'?s|this is|it is|that'?s)? ?(?:no|not an?) "
    r"emergency\b|\bnot an emergency\b|\bi (?:only |just )?(?:meant|was talking about|was referring to|was (?:just )?"
    r"(?:venting|complaining|kidding|joking))\b|\bthat'?s not what i meant\b|\bi didn'?t mean\b|\byou (?:mis"
    r"understood|got it wrong|read that wrong)\b|\bmisunderst\w*|\bnever ?mind\b|\beveryone(?:'s| is) (?:fine|ok"
    r"(?:ay)?|"
    r"safe)\b|\b(?:he|she|they)(?:'s| is| are|'re) (?:totally |completely )?(?:fine|ok(?:ay)?)\b(?=.*\b(?:meant|"
    r"misunderst\w*|false alarm|nobody|no one|no emergency)\b)|\bfalsa alarma\b|\bnadie (?:est[aá] )?herido\b|"
    r"\bno es (?:una )?emergencia\b|\bme refer[ií]a\b", re.I)
_RETRACT_DANGER = re.compile(r"\b(?:no wait|wait,? no|thick\w*|spread\w*|grow\w*|still|again|but (?:he|she|they|"
                             r"it|now)|now (?:he|she|they|it)|worse|can'?t "
                             r"breathe|not breathing|bleeding|won'?t wake|"
                             # Sprint 6 final (verifier P0-B): a body state or a hazard that is still there
                             r"on the floor|gr[ae]y|sweat\w*|pale|turning blue|collaps\w*|fell|unconscious|"
                             r"not responding|unresponsive|pain|seizur\w*|vomit\w*|stronger|getting (?:worse|bigger|"
                             r"stronger)|keeps? (?:going|beeping|sparking|crackling)|crackl\w*|yet|sigue\w*|"
                             r"todav[ií]a|peor)\b", re.I)
# Only these phrases retract an alert. "Nobody is hurt", "not an emergency" and "everyone's fine" alone never do:
# a gas leak or a sparking panel has no victim yet and is still dangerous.
_RETRACT_EXPLICIT = re.compile(
    r"\bfalse alarm\b|\bi (?:only |just )?(?:meant|was talking about|was referring to|was (?:just )?(?:venting|"
    r"complaining|kidding|joking))\b|\bthat'?s not what i meant\b|\bi didn'?t mean\b|\byou (?:misunderstood|got it "
    r"wrong|read that wrong)\b|\bmisunderst\w*|\bjust kidding\b|\bfalsa alarma\b|\bme refer[ií]a\b", re.I)
# For a hazard incident (no person named), the message must not name the hazard again ("false alarm, but it still
# smells", "falsa alarma, pero sigue oliendo").
_HAZARD_CUE = re.compile(r"\b(?:smell\w*|odou?r|gas|smok\w*|spark\w*|alarm(?:'s| is)? (?:going|beep\w*|sound\w*)|"
                         r"beep\w*|water|flood\w*|fire|flames?|burn\w*|heat|hot|outlet|panel|breaker|ceiling|crack\w*|"
                         r"huele|oliendo|olor|humo|agua|fuego)\b", re.I)
# Hazard words a genuine false alarm uses harmlessly: negated ("no sparks", "not smoke", "there is no fire"), a harmless
# source ("burnt toast", "steam from the shower"), or a device named ("the fire extinguisher is expired"). Removed
# before the hazard-cue check, so "false alarm, it was burnt toast" retracts while "false alarm, but it still smells"
# does not ("still" is a danger word above).
_HARMLESS_HAZARD = re.compile(
    r"\b(?:no|not|never|isn'?t|wasn'?t|there(?:'s| is| was) no|nothing (?:is |was )?)\s+"
    r"(?:any\s+|a\s+|actual\s+|real\s+)?"
    r"(?:smok\w*|spark\w*|fire|flames?|gas(?: leak)?|leak\w*|water|flood\w*|burn\w*|smell\w*|odou?r)\b|"
    r"\b(?:burn(?:t|ed|ing)?|charred)\s+(?:toast|popcorn|food|bacon|rice|pan|pizza|dinner|eggs?|cookies)\b|"
    r"\b(?:toast|popcorn|cooking|candle|incense|steam\w*|shower|vapou?r|fog machine|reflection|sunlight|glare)\b|"
    r"\b(?:fire|smoke|co|carbon monoxide) (?:extinguisher|detector|alarm|door|drill)s?\b|"
    r"\b(?:the )?smell\w*\s+(?:was|is|came|comes)\s+(?:just\s+)?(?:from\s+)?(?:the\s+|my\s+|a\s+)?(?:trash|"
    r"garbage|bin|food|cooking|fridge|candle|perfume|paint|dog|compost|drain)\b|"
    r"\bno (?:hay|había) (?:humo|fuego|gas|olor)\b|\bera (?:vapor|la tostada|comida)\b", re.I)
HAZARD_KINDS = {"gas", "co", "electrical", "fire_smoke", "flood", "structural", "extreme_temp"}
REOPEN_WINDOW = 3  # turns after a retraction in which a body state or the hazard reopens the incident
# The resident stopped the hazard ("water stopped, I shut the valve", "the smell is gone, gas is off at the stove").
_CONTROLLED = re.compile(
    r"\b(?:water|leak|leaking|flow|it|the pipe|dripping|spraying|sparking|sparks|smell|odou?r|hissing)(?:'s| is| has| "
    r"have)?(?: finally| now| completely)? (?:stopped|gone|off|done|under control|dried up|died down)\b|"
    r"\b(?:i|we|he|she|they|my \w+)(?: just| finally| already)? (?:shut|turned|switched|closed|flipped|cut)(?: off| "
    r"down)? (?:the |it |off the |that )?(?:main |water |gas |shut-?off |shutoff )?(?:valve|water|main|gas|breaker|"
    r"power|stove|burner|knob|supply|it)(?: off| down)?\b|"
    r"\b(?:gas|water|power|breaker|valve|stove|burner)(?:'s| is| are)? (?:now |all |completely )?(?:off|shut|closed)\b|"
    r"\bunder control\b|\bya (?:par[oó]|se fue el olor|cerr[eé] la (?:llave|v[aá]lvula))\b", re.I)
_CONTROLLED_NOT = re.compile(r"\b(?:not|n'?t|never|still|again|can'?t|cannot|won'?t|wont|isn'?t|hasn'?t|haven'?t|"
                             r"didn'?t|trying|try|how (?:do|can) i)\b|\?", re.I)
# During an active incident ANY question about what to do, where to go, going back in or the responders is a
# follow-up (approved notice again, never a repair form).
_ASKS = re.compile(r"\?|^\s*(?:is|are|can|could|should|do|does|did|what|where|when|how|who|will|would|may|must|"
                   r"am i|ok to|okay to|safe to|puedo|debo|qu[eé]|d[oó]nde|cu[aá]ndo|c[oó]mo)\b", re.I)
_SAFETY_TOPIC = re.compile(
    r"\b(?:go(?:ing)? back|back in(?:side)?|get back in|go in(?:side)?|re-?enter|return|stay (?:inside|in here|here|"
    r"put|in the)|sleep (?:here|in)|safe|fine to|ok(?:ay)? to|alright to|all right to|"
    r"balcony|floor|stair\w*|window\w*|roof|hallway|lobby|exit|elevator|lift|outside|bathroom|closet|"
    r"turn (?:it |the \w+ )?(?:off|on)|shut (?:it |the \w+ )?(?:off|down)|breaker|valve|main|unplug|fan|towels?|"
    r"mop|bucket|leave|evacuat\w*|wait|carry|grab|pets?|dog|cat|car|move (?:him|her|them)|cpr|aspirin|narcan|"
    r"lay (?:him|her|them)|on (?:his|her|their) side|water|smoke|fumes|air|door|"
    r"dispatch\w*|operator|911|paramedic\w*|ambulance|emts?|firefighter\w*|fire ?(?:department|fighters?|truck)|"
    r"police|cops|gas company|utility|tell (?:them|the|911)|say to|what (?:do|should) i (?:tell|say)|gate code|"
    r"address|buzz (?:them|in)|let (?:them|the \w+) in|meet (?:them|the)|how long|when will|hospital|"
    r"volver|entrar|salir|bomberos|ambulancia|operador)\b", re.I)
_CONTINUE_PERSON = re.compile(r"\b(?:hurt\w*|bleed\w*|sick|dizzy|head\w*|breath\w*|burn(?:ed|t)|shock\w*|kid|baby|"
                              r"child|someone|somebody|worse|but)\b", re.I)
_LOCATION = re.compile(r"^\W*(?:i'?m|im|i am|we'?re|we are|he'?s|she'?s|they'?re|my \w+ is|estoy|estamos)\s+(?:\w+\s+)?"
                       r"(?:on|in|at|by|near|stuck|trapped|still|upstairs|downstairs|en)\b", re.I)


# Sprint 7 fix round (UX judge): "I'm outside now" / "we got out" during a property-hazard incident acknowledges the
# approved notice; it is an ack (calm line, no second alert or note), unless the turn still describes danger.
_SAFE_UPDATE = re.compile(
    r"\b(?:i|we)(?:'?m|'?re| am| are| got| made it| just got)? (?:all )?(?:out(?:side)?|out of (?:the )?(?:building|"
    r"apartment|unit|house)|downstairs|in the (?:lobby|parking lot|street|car)|across the street|safe)\b|"
    r"\b(?:we|i) (?:left|evacuated|got out)\b|\b(?:ya )?(?:salimos|sal[ií]|estamos afuera|estoy afuera|estamos bien)\b",
    re.I)
_STILL_DANGER = re.compile(r"\b(?:go(?:ing)? back|back in(?:side)?|re-?enter|get (?:my|the|our)|volver|regresar|entrar|"
                           r"still (?:in|inside|in there)|inside|in there|trapped|stuck|can'?t get|"
                           r"smell\w* (?:it )?"
                           r"(?:out here|outside)|worse|dizz\w*|sick|headache|hurt|bleed\w*|breath\w*|my (?:\w+ )?(?:i"
                           r"s|are)"
                           r" (?:still )?(?:in|inside)|sigue adentro|todav[ií]a (?:est[aá]|adentro))\b", re.I)


def is_retraction(message: str, kind: str | None = None) -> bool:
    """'false alarm', 'I meant my texts', 'you misunderstood' with nothing in the rest of the message still describing
    danger. 'Nobody is hurt' / 'not an emergency' alone are not retractions (Sprint 6 final, verifier P0-B)."""
    text = message.strip()
    if not _RETRACT_EXPLICIT.search(text) or _RETRACT_DANGER.search(text):
        return False
    if kind in HAZARD_KINDS and _HAZARD_CUE.search(_HARMLESS_HAZARD.sub(" ", _RETRACT_EXPLICIT.sub(" ", text))):
        return False
    rest = _RETRACT.sub(" ", text)
    return not scan(rest)[0]


_CLAUSE_BREAK = re.compile(r"[,.;!]|\b(?:but|pero|and then|y luego)\b")


def _clause_at(text: str, pos: int) -> str:
    """The clause of `text` around position `pos` (up to the next break; the question mark stays in it)."""
    start = max((m.end() for m in _CLAUSE_BREAK.finditer(text, 0, pos)), default=0)
    end_m = _CLAUSE_BREAK.search(text, pos)
    return text[start:end_m.start() if end_m else len(text)]


def classify(message: str, inc: Incident) -> Turn:
    text = message.strip()
    low = text.lower()
    if is_retraction(text, inc.kind):
        return "retracted"
    ctl = _CONTROLLED.search(low)
    if inc.kind in CONTROLLABLE_KINDS and ctl and not _CONTROLLED_NOT.search(_clause_at(low, ctl.start())):
        # final round: only the clause that reports the control is checked ("ok the water is shut off now, what next?"
        # is controlled; "is the water off?" and "should i shut it off?" are not)
        rest = _CONTROLLED.sub(" ", text)
        if not scan(rest)[0] and possible_risk(rest) not in ("unwell", "distress") and not (
                _CONTINUE_PERSON.search(rest)):
            return "controlled"
    if asks_emergency_line(text):
        return "follow"  # "I don't have the emergency number": answered honestly by the planner's emergency step
    if (re.search(_RESPONDER, low, re.I) and re.search(_HANDLED, low, re.I) and not _NOT_YET.search(low)) or (
            _RESOLVED_ALONE.search(low) and not _NOT_YET.search(low)):
        return "resolved"
    if inc.kind in HAZARD_KINDS and _SAFE_UPDATE.search(low) and not _STILL_DANGER.search(low):
        return "ack"  # an ack; step() also records that the resident is out / safe
    if _PRIVACY_OR_STATUS.search(low):
        return "ack"  # the planner answers privacy / status questions after an alert; the calm line stays
    if _ACK.match(low):
        if inc.third_party and _SELF_FINE.search(low):
            return "follow"  # "I'm fine" is about the speaker, not the person who is in danger
        return "ack"
    if _WHAT_NOW.search(low) or _CONTINUE_CUE.search(low) or (inc.third_party and _SELF_FINE.search(low)):
        return "follow"
    if (_ASKS.search(low) and _SAFETY_TOPIC.search(low)) or _LOCATION.search(low):
        return "follow"  # a question about safety actions, location, re-entry or responders; "I'm on the balcony"
    if possible_risk(text) or scan(text)[0]:
        return "follow"  # danger words, or the hazard named again (even negated / past / hypothetical)
    fr = frame_of(text)
    if fr.states or fr.hazards or fr.urgency != "none" or (any(r != "self" for r in fr.who) and not _TOPIC.search(low)):
        return "follow"  # sprint 7: any body state, hazard or person in the frame ties the turn to the incident
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
    r"man|woman|guy|lady|boy|girl|dog|cat|pet|aunt|uncle|nephew|niece|co-?worker|colleague|boss|guest|visitor|"
    r"patient|cousin|fianc[eé]e?)\b|\b(?:he|she|they|him|her|them|someone|somebody)\b|"
    r"\bmi (?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|abuel[oa]|vecin[oa]|beb[eé]|amig[oa]|t[ií][oa]|sobrin[oa]|"
    r"prim[oa]|herman[oa]|nieto|nieta|suegr[oa]|novi[oa]|pareja)\b", re.I)


def _call(decision: RiskDecision, inc: Incident, rule: str, conflict: str) -> RiskDecision:
    return decision.model_copy(update={"rule": rule, "incident": inc.kind, "conflict": conflict, "person_danger": True,
                                       "sources": list(dict.fromkeys([*decision.sources, "incident"]))})


# ---- fix round (P0-1): pending conditional ----------------------------------------------------------------------
# After safety information for a question (R5 / R5c: "if my dad can't breathe, what should I do?") the reply asks
# whether it is happening now. For PENDING_TURNS turns a "yes", a short "he is / she isn't" answer, or any description
# of a sign becomes the full alert of that kind (rule R5f, an incident is opened, the planner writes the urgent note).
# "No, just asking" clears it. Stored as its own row (mode PENDING_MODE): kind and turn only, never text.
PENDING_MODE = "safety_pending"
PENDING_TURNS = 2
# A bare "yes" / "sí" / "it is happening" counts only on the turn RIGHT AFTER the safety reply (final round: a later
# "yes" usually answers another question, e.g. "can we enter?").
_AFFIRM_BARE = re.compile(
    r"^\W*(?:yes|yeah|yea|yep|yup|ya|uh-?huh|it is|its happening|it'?s happening|it is happening|"
    r"happening (?:right )?now|right now|correct|exactly|that'?s right|i think so|please help|help|s[ií]|asi es|"
    r"así es|claro|est[aá] pasando|ahora mismo|ayuda|por favor)\b", re.I)
# "he is / she isn't / my dad can't ...": only with a PERSON subject ("my AC is broken" is not an answer)
_PERSON_SUBJ = (r"(?:he|she|they|him|her|el|él|ella|ellos|(?:my|our|mi|nuestr[oa]) (?:\w+ )?(?:grand\w+|mom|mum|mother|"
                r"dad|father|husband|wife|partner|son|daughter|kid|child|baby|toddler|boy|girl|brother|sister|"
                r"uncle|aunt|cousin|nephew|niece|friend|roommate|neighbou?r|boyfriend|girlfriend|fianc\w*|"
                r"coworker|esposo|esposa|hij[oa]|mam[aá]|pap[aá]|abuel[oa]|beb[eé]|niñ[oa]|herman[oa]|t[ií][oa]|"
                r"amig[oa]|vecin[oa]|novi[oa]|pareja))")
_AFFIRM_PERSON = re.compile(
    rf"^\W*(?:yes,?\s*|yeah,?\s*|s[ií],?\s*)?{_PERSON_SUBJ}(?:'s|'re)?\s*(?:is|are|was|isn'?t|is not|aren'?t|can'?t|"
    rf"cannot|won'?t|doesn'?t|didn'?t|has|hasn'?t|still|not|no|est[aá]|sigue|s)\b", re.I)
_DENY = re.compile(
    r"^\W*(?:no|nope|nah|not (?:right )?now|not happening|nothing like that|just (?:asking|curious|wondering|in case)|"
    r"only asking|hypothetical\w*|asking for (?:a friend|the future)|solo (?:pregunt\w*|por si acaso)|por si acaso|"
    r"nada de eso|no est[aá] pasando)\b|\b(?:fine|ok|okay|safe|alright|all right|doing good|bien|tranquil[oa])\b",
    re.I)
# a turn about something else closes the marker: a repair, a tour, the office, rent, an answer about entry or times
_OTHER_TOPIC = re.compile(
    r"\b(?:repair|fix|broken|broke|clogged|leak\w*|drip\w*|ac|a/c|heat(?:er|ing)?|fan|sink|toilet|dishwasher|washer|"
    r"dryer|fridge|oven|stove|light|bulb|door|lock|window|outlet|tour|schedule|visit|office|hours|rent|lease|"
    r"pay\w*|parking|package|pool|gym|amenit\w*|enter|entry|come in|permission|key|maintenance|work order|"
    r"apartment|unit|move|pet|noise|appointment|tomorrow|morning|afternoon|anytime|any time|reparar|arreglar|roto|"
    r"tapad[oa]|gotea|visita|oficina|horario|renta|pago|estacionamiento|entrar|llave|mantenimiento|cita|mañana)\b",
    re.I)
_NEUTRAL = re.compile(r"^\W*(?:ok(?:ay)?|k|thanks?|thank you|hmm+|wait|one sec(?:ond)?|hold on|gracias|espera|"
                      r"un momento)\W*$", re.I)


def _pending(store: Any, session_id: str, persona_key: str) -> dict[str, Any] | None:
    if store is None:
        return None
    try:
        row = store.last_gate(session_id, PENDING_MODE, persona_key)
    except Exception:
        return None
    return row if row and row.get("kind") else None


def _set_pending(store: Any, session_id: str, persona_key: str, data: dict[str, Any]) -> None:
    if store is None:
        return
    try:
        store.log_gate(session_id, PENDING_MODE, persona_key, data)
    except Exception:
        pass  # only the follow-up escalation is lost; this turn's safety text is unaffected


def confirms_pending(message: str, risk: RiskAssessment, next_turn: bool = True) -> bool:
    """A sign described, a "he is / she isn't" answer about a person, or (only on the very next turn) a bare "yes"."""
    det = risk.deterministic
    fr = det.frame or {}
    people = [w for w in fr.get("who") or [] if w not in ("pet",)]
    sign = bool(det.kind or det.care in ("distress", "unwell") or (fr.get("states") and people)
                or scan(message)[0] or possible_risk(message) in ("distress", "unwell"))
    if sign:
        return True
    text = message.strip()
    if _DENY.search(text):
        return False
    if _AFFIRM_PERSON.search(text):
        return True
    return next_turn and bool(_AFFIRM_BARE.search(text)) and not _OTHER_TOPIC.search(text)


def pending_open(store: Any, session_id: str, persona_key: str, turn: int) -> bool:
    """For the planner: a safety question ("is anything like that happening right now?") is waiting for an answer."""
    pend = _pending(store, session_id, persona_key)
    return bool(pend and pend.get("open") and turn - int(pend.get("turn", 0)) <= PENDING_TURNS)


def step(store: Any, session_id: str, persona_key: str, message: str, risk: RiskAssessment,
         turn: int) -> RiskAssessment:
    """Apply the incident state machine to this turn's assessment and persist the new state. Never lowers the
    policy's decision: it only re-issues the alert (R10 / R5f) or keeps a calm line (R10q)."""
    risk = _apply_pending(store, session_id, persona_key, message, risk, turn)
    return _step(store, session_id, persona_key, message, risk, turn)


def _apply_pending(store: Any, session_id: str, persona_key: str, message: str, risk: RiskAssessment,
                   turn: int) -> RiskAssessment:
    d = risk.decision
    pend = _pending(store, session_id, persona_key)
    if pend and pend.get("open") and turn - int(pend.get("turn", 0)) <= PENDING_TURNS:
        gap = turn - int(pend.get("turn", 0))
        if d.response == "full_alert":
            _set_pending(store, session_id, persona_key, {**pend, "open": False, "closed": "alert"})
        elif confirms_pending(message, risk, next_turn=gap == 1):
            from app.risk.category import refine
            kind, reason = refine(pend["kind"], message)
            nd = d.model_copy(update={
                "response": "full_alert", "kind": kind, "detected_kind": pend["kind"], "notice_reason": reason,
                "care": None, "needs_human": True, "escalation_priority": "urgent", "rule": "R5f",
                "person_danger": True, "conditional_danger": False,
                "sources": list(dict.fromkeys([*d.sources, "pending_conditional"])),
                "conflict": f"confirmed after safety information for a {pend['kind']} question: full alert"})
            _set_pending(store, session_id, persona_key, {**pend, "open": False, "closed": "confirmed"})
            return risk.model_copy(update={"decision": nd})
        elif not _NEUTRAL.search(message):
            # a denial, or a turn about anything else (a repair, a tour, the office, an answer to another question)
            # closes it; only "ok" / "wait" / "thanks" keep it open for the second turn
            _set_pending(store, session_id, persona_key, {**pend, "open": False, "closed": "other turn"})
    if d.response == "safety_info" and d.kind and risk.deterministic.framing == "hypothetical":
        _set_pending(store, session_id, persona_key, {"kind": d.kind, "turn": turn, "open": True,
                                                     "rule": d.rule})
    return risk


def _step(store: Any, session_id: str, persona_key: str, message: str, risk: RiskAssessment,
          turn: int) -> RiskAssessment:
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
    if inc and inc.status == "resolved" and inc.resolved_reason == "retracted" and turn - inc.last_seen_turn <= \
            REOPEN_WINDOW and (_RETRACT_DANGER.search(message) or scan(message)[0] or possible_risk(message)
                               or (inc.kind in HAZARD_KINDS and _HAZARD_CUE.search(message))):
        # "you misunderstood, he's fine" then "he's grey and sweating": the retracted incident comes back
        inc.status, inc.resolved_reason, inc.resolved_at, inc.quiet, inc.last_seen_turn = "active", None, None, 0, turn
        _save(store, session_id, persona_key, inc)
        nd = d.model_copy(update={"response": "full_alert", "kind": inc.kind, "needs_human": True,
                                  "escalation_priority": "urgent", "care": None,
                                  "also_988": d.also_988 or (inc.kind == "poison" and "self_harm" in inc.kinds)})
        return risk.model_copy(update={"decision": _call(nd, inc, "R10", f"danger after a retracted {inc.kind} "
                                                                          "alert: incident reopened")})
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
    window = RETRACT_WINDOW_HAZARD if inc.kind in HAZARD_KINDS else RETRACT_WINDOW
    if kind == "retracted" and (turn - inc.opened_turn > window or inc.kind == "personal_safety"
                                or "self_harm" in inc.kinds):
        kind = "ack"  # an old incident, or a possible threat (a "never mind" may be coerced): a quiet turn only
    inc.last_seen_turn = turn
    if kind == "retracted":
        inc.status, inc.resolved_reason, inc.resolved_at = "resolved", "retracted", now
        _save(store, session_id, persona_key, inc)
        if d.rule == "R9" and not d.kind:  # the remembered line came only from the alert being retracted
            nd = d.model_copy(update={"response": "none", "care": None, "rule": "R8", "conflict":
                                      f"{inc.kind} alert retracted by the resident (false alarm); remembered line "
                                      "dropped"})
            return risk.model_copy(update={"decision": nd})
        return risk
    if kind == "controlled":
        inc.status, inc.resolved_reason, inc.resolved_at = "resolved", "controlled", now
        _save(store, session_id, persona_key, inc)
        if d.response == "none":  # the calm line stays on the turn the hazard is reported under control
            nd = d.model_copy(update={"response": "care_line", "care": "danger"})
            return risk.model_copy(update={"decision": _call(nd, inc, "R10q", f"{inc.kind} reported under control: "
                                                                               "incident closed, calm line kept")})
        return risk
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
    if (kind == "ack" and inc.kind in HAZARD_KINDS and _SAFE_UPDATE.search(message)
            and not _STILL_DANGER.search(message)):
        inc.safe = True
    if kind == "topic" and inc.safe and inc.kind in HAZARD_KINDS:
        # the resident is out / safe and has moved on to an unrelated request: the incident is over for this chat
        inc.status, inc.resolved_reason, inc.resolved_at = "resolved", "safe and moved on", now
        _save(store, session_id, persona_key, inc)
        return risk.model_copy(update={"decision": d.model_copy(update={"incident": None})})
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


def closed(store: Any, session_id: str, persona_key: str) -> Incident | None:
    """The last incident of this conversation, if it is resolved (the planner then stops treating short messages as
    emergency follow-ups)."""
    inc = load(store, session_id, persona_key)
    return inc if inc and inc.status == "resolved" else None


def prior_hazards(store: Any, session_id: str, persona_key: str, message: str, turn: int,
                  hazards: list[str]) -> list[str]:
    """Earlier alert kinds the policy should remember (R9 / R9e). An alert the resident retracted ("false alarm,
    nobody is hurt"), this turn or earlier, is not remembered. Self-harm is never dropped."""
    inc = load(store, session_id, persona_key)
    if not inc or inc.kind == "self_harm" or "self_harm" in inc.kinds:
        return hazards
    retracted = inc.status == "resolved" and (inc.resolved_reason == "retracted" or (
        inc.kind != "personal_safety" and "personal_safety" not in inc.kinds))
    if inc.status == "active" and inc.kind not in ("personal_safety",) and classify(message, inc) == "resolved":
        retracted = True  # "the paramedics took him to the hospital": this turn closes it
    window = RETRACT_WINDOW_HAZARD if inc.kind in HAZARD_KINDS else RETRACT_WINDOW
    retracting = (inc.status == "active" and inc.kind != "personal_safety" and turn - inc.opened_turn <= window
                  and is_retraction(message, inc.kind))
    if not (retracted or retracting):
        return hazards
    gone = set(inc.kinds) | {inc.kind}
    return [h for h in hazards if h not in gone]


def summary(inc: Incident | None) -> dict[str, Any] | None:
    return inc.model_dump() if inc else None
