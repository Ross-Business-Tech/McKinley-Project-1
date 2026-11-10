"""Layer 1: deterministic risk detection (wraps app.emergency) on the message and the recent conversation.

Sprint 7: the compositional frame (app/risk/frame.py) is combined with the phrase rules. It may only ADD caution:
  - a frame alert (critical state, a person with two signs, heat / cold body signs, a child at a height or in water,
    an ingestion, veiled self-harm) turns a miss into an alert;
  - a live sign inside a conditional or a question ("if my dad can't breathe what do I do") turns a "hypothetical"
    rule match into a report;
  - a possible sign gives the calm care line and marks it as a person-in-danger line (`concern`);
  - the only thing it can lower is a rule match that the frame reads as a media / drill / policy-question / device
    look-alike with NO live state or sign in the message, and never for self-harm or personal safety.
"""

import re

from app.emergency import intent_to_self_harm, person_concern, possible_risk, scan
from app.risk.frame import RiskFrame, analyse
from app.risk.models import DeterministicRisk

WINDOW_TURNS = 3  # earlier user messages combined with this one
# "It's happening now" after a hypothetical/past mention turns that mention into a report.
_HAPPENING_NOW = re.compile(r"\b(?:it'?s|it is|this is|that'?s) (?:happening|going on) (?:now|right now)\b|"
                            r"\b(?:yes|yeah|yep)\W+(?:\w+\W+){0,2}(?:right )?now\b|\bhappening now\b|"
                            r"est[aá] pasando (?:ahora)?|s[ií],? ahora", re.I)
_NEVER_LOWERED = {"self_harm", "personal_safety"}
_OTHER_ACTOR = re.compile(r"\b(?:he|she|they|him|them|someone|somebody|stranger|intruder|my (?:ex|partner|husband|wife|"
                          r"boyfriend|girlfriend|roommate|neighbou?r)|a (?:man|guy|woman)|threat\w*|alguien|[eé]l|ella"
                          r")\b",
                          re.I)
_IT = re.compile(r"\b(?:it|that|this)('s| is|s)?\b(?! (?:is )?(?:ok|okay|fine|all|me|you|happening|going on))", re.I)
_OBJECT = re.compile(r"\b(ceiling|roof|wall|floor|stairs|staircase|balcony|deck|railing|outlet|socket|panel|breaker|"
                     r"stove|oven|dryer|heater|furnace|water heater|pipe|toilet|elevator|door|window|techo|pared|piso|"
                     r"escalera|balc[oó]n|enchufe|estufa|tuber[ií]a)\b", re.I)
_LOOKALIKE_FRAMING = {"media": "quoted", "drill": "hypothetical", "policy": "hypothetical", "device": "hypothetical",
                      "past": "past", "joking": "joking", "signs": "hypothetical"}


def detect(message: str, recent: list[str] | None = None) -> DeterministicRisk:
    """`recent` = earlier user messages in this conversation (oldest first, current message excluded)."""
    kind, framing = scan(message)
    out = DeterministicRisk(care=possible_risk(message), concern=person_concern(message))  # type: ignore[arg-type]
    prev = [m for m in (recent or []) if m][-WINDOW_TURNS:]
    fr = analyse(message, prev)
    out.frame = fr.__dict__.copy()  # type: ignore[assignment]
    if kind and framing == "report":
        out.kind, out.framing = kind, "report"
    elif kind:
        out.mentioned_kind, out.framing = kind, framing  # type: ignore[assignment]
    if not out.kind and prev:
        # Danger that only becomes clear across turns ("the kid got under the sink" ... "now he's throwing up").
        before, _ = scan(" . ".join(prev))
        joined_kind, joined_framing = scan(" . ".join([*prev, message]))
        if joined_kind and joined_framing == "report" and joined_kind != before:
            out.kind, out.framing, out.via_window = joined_kind, "report", True
    if not out.kind and prev and _HAPPENING_NOW.search(message):
        for m in reversed(prev):
            k, _f = scan(m)
            if k:
                out.kind, out.framing, out.via_window = k, "report", True
                break
    if not out.kind and prev and _IT.search(message):
        # "the ceiling has a stain" ... "now it's sagging": read "it" as the hazard object named in the last turns
        obj = None
        for m in reversed(prev):
            found = _OBJECT.findall(m)
            if found:
                obj = found[-1]
                break
        if obj:
            resolved = _IT.sub(lambda m: f"the {obj} is" if m.group(1) else f"the {obj}", message)
            k, fr_ = scan(resolved)
            fr2 = analyse(resolved, prev)
            if k and fr_ == "report":
                out.kind, out.framing, out.via_window = k, "report", True
            elif fr2.alert and fr2.category and fr2.category != "medical":
                fr = fr2
    _combine(out, fr, message)
    if out.kind == "poison" and (intent_to_self_harm(message) or any(intent_to_self_harm(m) for m in prev)):
        out.self_harm_intent = True
    return out


def _combine(out: DeterministicRisk, fr: RiskFrame, message: str) -> None:
    """Frame + phrase rules, conservatively (see the module docstring)."""
    # media / past / joking frame the whole message; a device, drill or policy question only when no body state at all
    # is described ("our CO detector is screaming and my daughter threw up" is a report)
    live_sign = (fr.alert and fr.look_alike != "joking") or (
        bool(fr.states) and fr.look_alike in ("device", "drill", "policy"))
    if out.kind and fr.look_alike and out.kind not in _NEVER_LOWERED and not live_sign and not out.via_window:
        out.mentioned_kind, out.kind = out.kind, None
        out.framing = _LOOKALIKE_FRAMING[fr.look_alike]  # type: ignore[assignment]
        return
    if out.kind == "personal_safety" and fr.alert and fr.category == "self_harm" and not _OTHER_ACTOR.search(
            message):
        out.kind = "self_harm"  # "i don't see a way out and i have my dad's gun": the speaker's own means
        return
    if out.kind:
        return
    if fr.alert and fr.category:
        if out.mentioned_kind and out.mentioned_kind != fr.category and out.framing in ("hypothetical", "past"):
            # a live sign the rules framed as a question: keep the rules' more specific kind
            out.kind = out.mentioned_kind if fr.live_conditional else fr.category
        else:
            out.kind = fr.category
        out.framing, out.mentioned_kind = "report", None
        out.frame_rule = True
        return
    if fr.possible and fr.category:
        if fr.category == "self_harm":
            out.care = "distress"
        elif out.care not in ("distress", "unwell"):
            out.care = fr.care_hint or "danger"  # type: ignore[assignment]
        out.concern = True
        if fr.ongoing in ("hypothetical", "past") and not out.mentioned_kind:
            out.mentioned_kind, out.framing = fr.category, fr.ongoing  # type: ignore[assignment]
