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
from app.risk.frame import RiskFrame, analyse, normalize, unknown_ingestion, without_lookalike
from app.risk.models import DeterministicRisk
from app.risk.neutralize import spans

WINDOW_TURNS = 3  # earlier user messages combined with this one
# "It's happening now" after a hypothetical/past mention turns that mention into a report.
_HAPPENING_NOW = re.compile(r"\b(?:it'?s|it is|this is|that'?s) (?:happening|going on) (?:now|right now)\b|"
                            r"\b(?:yes|yeah|yep)\W+(?:\w+\W+){0,2}(?:right )?now\b|\bhappening now\b|"
                            r"est[aá] pasando (?:ahora)?|s[ií],? ahora", re.I)
_SAME_MSG_NOW = re.compile(r"\b(?:mine|ours|my (?:\w+ )?(?:one|unit|stove|apartment|place))\s+(?:just |"
                           r"actually |is |did "
                           r"|does )?(?:did|does|is|has|happened|happening|right now|now)\b|\b(?:and|because|cause|cuz|"
                           r"but) (?:it|that|this) (?:just |is |'s )?(?:happened|happening|did|is happening)\b|"
                           r"\bit'?s happening (?:now|right now)\b|\b(?:a m[ií]|el m[ií]o|la m[ií]a) (?:me )?(?:acaba "
                           r"de|"
                           r"est[aá]) pas(?:ar|ando)\b|\bme (?:acaba de|est[aá]) pasando\b", re.I)
_HABITUAL = re.compile(r"\b(?:sometimes|usually|every time|always|a veces|siempre|de vez en cuando)\b", re.I)
_NEVER_LOWERED = {"self_harm", "personal_safety", "poison"}
_OTHER_ACTOR = re.compile(r"\b(?:he|she|they|him|them|someone|somebody|stranger|intruder|my (?:ex|partner|husband|wife|"
                          r"boyfriend|girlfriend|roommate|neighbou?r)|a (?:man|guy|woman)|threat\w*|alguien|[eé]l|ella"
                          r")\b",
                          re.I)
_IT = re.compile(r"\b(?:it|that|this)('s| is|s)?\b(?! (?:is )?(?:ok|okay|fine|all|me|you|happening|going on))", re.I)
_OBJECT = re.compile(r"\b(ceiling|roof|wall|floor|stairs|staircase|balcony|deck|railing|outlet|socket|panel|breaker|"
                     r"stove|oven|dryer|heater|furnace|water heater|pipe|toilet|elevator|door|window|techo|pared|piso|"
                     r"escalera|balc[oó]n|enchufe|estufa|tuber[ií]a)\b", re.I)
_LOOKALIKE_FRAMING = {"media": "quoted", "drill": "hypothetical", "policy": "hypothetical", "device": "hypothetical",
                      "past": "past", "signs": "hypothetical"}


def _rank(d: DeterministicRisk) -> int:
    return 3 if d.kind else 2 if d.care else 1 if d.mentioned_kind else 0


_NEVER_LOWERED_BY_SPANS = {"self_harm", "personal_safety"}
# fix round (P1-1): a separate present-tense symptom of a person next to the question keeps it live ("is it bad if my
# daughter swallowed bleach? she's coughing")
_SYMPTOM_REST = re.compile(
    r"\b(?:he|she|they|it|my \w+|mi \w+|est[aá]|esta|i'?m|i am|estoy)\b(?:\W+\w+){0,4}?\W+(?:cough\w*|vomit\w*|"
    r"throwing "
    r"up|threw up|drows\w*|sleepy|dizzy|choking|gasping|wheez\w*|crying|screaming|bleeding|shaking|pale|limp|"
    r"confused|drooling|tosiendo|tose|vomit\w*|mare\w*|dormid[oa]|llorando|sangrando|temblando|ahog\w*)\b", re.I)
_LIVE_REST = re.compile(r"\b(?:now|right now|still|currently|again|just did|just happened|is happening|just now|"
                        r"(?:he|she|they|it|we|i) (?:did|has|have|is|was)\b(?:\W+\w+){0,2}?\W+(?:ago|now|minutes?|"
                        r"mins?)|(?:a few|an?|about|\d+|ten|five|twenty|thirty) (?:min\w*|seconds|hours?) ago|"
                        r"hace (?:un|una|unos|unas|\d+|poco|rato)\b|reci[eé]n|acaba de|"
                        r"happening|ahora|ahorita|todav[ií]a|sigue|otra vez|me est[aá] pasando|est[aá] pasando)\b",
                        re.I)


def detect(message: str, recent: list[str] | None = None) -> DeterministicRisk:
    """`recent` = earlier user messages in this conversation (oldest first, current message excluded).

    Sprint 8: the rules run on the message and on what is left after removing benign spans (app/risk/neutralize.py:
    titles, fiction, training, device subjects, idioms, ordinary activities, conditional clauses, past-and-recovered
    clauses). The result is lowered only when the remainder is lower, never for self-harm / personal safety / a
    window alert / a possible deliberate poisoning; a conditional or recovered span lowers only to nothing-left."""
    full = _detect(message, recent)
    sp = spans(message)
    if not sp.reasons and sp.hypothetical is None and sp.recovered is None and not sp.controlled:
        return full
    routine = "routine dose" in sp.reasons and not intent_to_self_harm(sp.benign) and not (
        _SELF_QUANTITY.search(message))  # "i took 2 tylenol for my headache": the dose alone set the 988 hint
    if full.kind in _NEVER_LOWERED_BY_SPANS or full.via_window or (full.self_harm_intent and not routine) or (
            full.care == "distress"):
        return full
    cur = full
    if sp.reasons:
        lite = _detect(sp.benign, recent)
        # a routine dose lowers only to nothing-left ("...and now i'm throwing up blood" keeps the alert)
        if _rank(lite) < _rank(cur) and not ("routine dose" in sp.reasons and _rank(lite) > 0):
            cur = lite.model_copy(update={"frame": {**(lite.frame or {}), "neutralized": list(sp.reasons)}})
    if sp.hypothetical is not None:
        lite = _detect(sp.hypothetical, recent)
        live_rest = bool(_LIVE_REST.search(sp.hypothetical) or _SAME_MSG_NOW.search(sp.hypothetical)
                         or _HAPPENING_NOW.search(sp.hypothetical) or _SYMPTOM_REST.search(sp.hypothetical))
        if _rank(lite) == 0 and not live_rest:  # "what do you do if an outlet sparks? mine is right now" stays live
            kind, clause_alert = cur.kind or cur.mentioned_kind, False
            for clause in sp.clauses:
                c = _detect(clause, None)
                fr = c.frame or {}
                clause_alert = clause_alert or bool(c.kind)
                kind = kind or c.kind or c.mentioned_kind or (fr.get("category") if fr.get("urgency") != "none"
                                                              else None)
            if kind and kind not in _NEVER_LOWERED_BY_SPANS:
                # R5c when the condition, said as a statement, would be an alert about a specific person
                cur = DeterministicRisk(mentioned_kind=kind, framing="hypothetical", frame={
                    **(full.frame or {}), "neutralized": [*sp.reasons, "conditional"]},
                    conditional_danger=bool(sp.conditional_specific and clause_alert))
    if sp.recovered is not None and _rank(cur) > 0:
        lite = _detect(sp.recovered, recent) if sp.recovered.strip(" ,") else DeterministicRisk()
        if _rank(lite) == 0 and (cur.kind or cur.care or cur.mentioned_kind) and \
                (cur.kind or cur.mentioned_kind) not in _NEVER_LOWERED_BY_SPANS:
            cur = DeterministicRisk(framing="past", frame={**(full.frame or {}),
                                                            "neutralized": [*sp.reasons, "past and recovered"]})
    if sp.controlled and cur.kind in _CONTROLLABLE and not full.via_window:
        fr = full.frame or {}
        if not (fr.get("states") and any(w not in ("self", "pet") for w in fr.get("who") or [])):
            # "small grease fire, I put it out, everyone is fine": the approved steps as calm info, no incident
            # (R5, not R5p: "If that happens: get out..." fits a fire that is already out better than "Get out now")
            cur = DeterministicRisk(mentioned_kind=cur.kind, framing="past", frame={
                **(full.frame or {}), "neutralized": [*sp.reasons, "controlled in this message"]})
    return cur


# gas and carbon monoxide stay alerts even when the source is off: the air is still unsafe until checked
_CONTROLLABLE = {"fire_smoke", "flood", "electrical"}
_CO_SYMPTOM = (r"head ?aches?|head (?:hurts|is pounding)|dizz\w*|light-?headed|nause\w*|throwing up|vomit\w*|"
               r"(?:so |really |very )?(?:sleepy|drowsy|groggy)|feel(?:s|ing)? (?:sick|weird|awful|faint)|sick|"
               r"confus\w*|dolor de cabeza|mare\w*|n[aá]usea\w*|v[oó]mit\w*|somnolient\w*")
_CO_HOUSEHOLD = re.compile(rf"\b(?:everyone|everybody|all of us|we all|the whole (?:family|house|household)|both of us|"
                           rf"all the (?:kids|family)|my whole family|todos|toda la familia|los dos|ambos)\b(?:\W+\w+)"
                           rf"{{0,6}}?\W+(?:{_CO_SYMPTOM})\b", re.I)
_CO_OTHER_CAUSE = re.compile(r"\b(?:flu|cold|covid|virus|bug|hangover|hungover|party|drinking|drunk|allerg\w*|food "
                             r"poisoning|ate|dinner|restaurant|gripe|resfriado|resaca|fiesta|comida)\b", re.I)
_ALARM_NOW = re.compile(r"\b(?:alarm|detector|sensor|alarma)\b(?:\W+\w+){0,5}?\W+(?:is |keeps |kept |won'?t stop |"
                        r"started |just )?(?:going off|went off|goes off|beeping|sounding|blaring|screeching|"
                        r"screaming|wailing|flashing red|alarming|sonando|son[oó]|pitando|chillando)\b|\b(?:keeps|won"
                        r"'?t "
                        r"stop) (?:going off|beeping|sounding)\b", re.I)
_FUEL_NEAR = re.compile(r"\b(?:furnace|water heater|boiler|heater|generator|stove|oven|fireplace|garage|dryer|"
                        r"caldera|calentador|calefactor|generador|estufa|horno|chimenea)\b", re.I)
_LOW_BATTERY = re.compile(r"\b(?:car|clock|phone|wake-?up|snooze|morning|kitchen timer|timer|oven timer|reloj|"
                          r"celular)\s+alarms?\b|\balarm clock\b|\bmy alarm\b|\balarma del (?:carro|coche|reloj|"
                          r"celular)\b|\bdespertador\b|\b(?:low battery|battery|batteries|chirp\w* (?:every|once)|eve"
                          r"ry (?:\d+|few|30) (?:seconds|"
                          r"minutes)|test(?:ing)?|drill|pila|bater[ií]a|smoke detector|detector de humo|burnt toast|"
                          r"cooking|shower steam|steam)\b", re.I)
_SELF_CUT = re.compile(r"\b(?:i|i'?ve|i just|i have)\s+(?:\w+\s+)?(?:cut|sliced|slashed|stabbed|carved|burned|burnt)\s+"
                       r"(?:myself|my (?:own )?(?:arm|arms|wrist|wrists|leg|legs|thigh|thighs|skin|stomach))\b|"
                       r"\bme (?:cort[eé]|lastim[eé]|quem[eé]|raj[eé])\b(?! (?:con el cuchillo )?(?:cocinando|sin que"
                       r"rer|"
                       r"por accidente))", re.I)
_ACCIDENT = re.compile(r"\b(?:cooking|chopping|cutting (?:onions|vegetables|bread|the)|knife slipped|slipped|by accid"
                       r"ent|"
                       r"accident\w*|shaving|opening|broken glass|glass broke|on the (?:can|glass|fence|counter)|while|"
                       r"sin querer|por accidente|cocinando|picando|rasur\w*|accidente)\b", re.I)
_BARE_HELP = re.compile(r"^\W*(?:please\W+)?(?:help|help me|help us|help please|i need help|we need help|someone "
                        r"help(?: me| us)?|sos|ayuda|ay[uú]dame|ay[uú]denme|ayuda por favor|socorro|auxilio)\W*"
                        r"(?:please|plz|por favor|now|ya|ahora)?\W*$", re.I)
_SHOCK_INJURY = re.compile(r"\b(?:numb\w*|tingl\w*|burn(?:ed|t|ing|s)?|hurts?|pain\w*|dizz\w*|chest|heart|racing|can'"
                           r"?t "
                           r"(?:feel|move)|weak|entumid\w*|hormigue\w*|quemad\w*|duele|dolor|mare\w*|pecho)\b", re.I)
_MINOR_SHOCK = re.compile(
    r"\b(?:a )?(?:little|small|tiny|mild|slight|quick) (?:electric(?:al)? )?(?:shock|jolt|zap)\b|"
    r"\b(?:got|get|getting|felt|feel) (?:a |an )?(?:little |small |tiny |mild |slight |quick )?(?:shock|shocked|zap|"
    r"zapped|jolt)\b|\b(?:shocked|zapped) me\b|\bme (?:dio|da|dieron) (?:un |una )?(?:peque[nñ]o |pequeña |leve )?"
    r"(?:toque|choque|descarga|calambre)\b|\bme (?:dio|da) corriente\b", re.I)
_SELF_QUANTITY = re.compile(
    r"\b(?:i|i'?ve|i just|me)\b(?:\W+\w+){0,3}?\W+(?:swallowed|took|taken|ate|drank|downed|tom[eé]|me tom[eé]|"
    r"tragu[eé])\b(?:\W+\w+){0,2}?\W+(?:a |an |the |my )?(?:whole|entire|full|all (?:of )?(?:my|the)|handful|"
    r"bunch of|todas (?:mis|las)|toda la|un frasco entero|un pu[nñ]ado|[1-9]\d|\d{3})\b", re.I)


def _detect(message: str, recent: list[str] | None = None) -> DeterministicRisk:
    kind, framing = scan(message)
    if kind == "self_harm" and framing == "joking":
        # sprint 7 fix round: a laugh marker never lowers a disclosure ("i want to die lol" is a full self-harm alert;
        # the alert includes 988). Stricter than sprint 6 (R3 care line).
        framing = "report"
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
    if not out.kind and out.mentioned_kind and out.framing == "hypothetical" and _SAME_MSG_NOW.search(message) \
            and not _HABITUAL.search(message):
        # "what's the policy if a tenant's stove catches fire? because mine just did": the question names the hazard,
        # the anaphoric clause reports it now
        out.kind, out.framing, out.mentioned_kind = out.mentioned_kind, "report", None
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
    if not out.kind and prev and fr.states and not fr.look_alike:
        # sprint 8: "mi hijo se tomó algo" ... "ahora está muy mareado": a swallowed product or unknown substance in
        # the last turns plus a body sign now is a poisoning report
        for m in reversed(prev[-2:]):
            pf = analyse(m)
            if unknown_ingestion(normalize(m)) and pf.ongoing not in ("hypothetical", "past", "media") and \
                    [w for w in pf.who if w != "pet"]:
                out.kind, out.framing, out.via_window = "poison", "report", True
                break
    _combine(out, fr, message)
    if not out.kind and (_CO_HOUSEHOLD.search(message) and not _CO_OTHER_CAUSE.search(message)
                         or _ALARM_NOW.search(message) and _FUEL_NEAR.search(message)
                         and not _LOW_BATTERY.search(message)):
        # final round (holdout class a): several people in the home with carbon-monoxide symptoms, or a sounding
        # detector next to a fuel-burning appliance, is the CO alert (fresh air first), never a repair intake
        out.kind, out.framing, out.mentioned_kind, out.frame_rule = "co", "report", None, True
    elif not out.kind and _ALARM_NOW.search(message) and not _LOW_BATTERY.search(message) and out.care is None:
        # a detector or alarm sounding now, source unknown: at least the calm 911 line, as a person-danger line (the
        # planner opens no ordinary repair while it shows)
        out.care, out.concern = "danger", True
    if not out.kind and out.care is None and _BARE_HELP.search(message):
        out.care, out.concern = "danger", True  # final round (P1-B): a bare "help" / "ayuda" gets the calm 911 line
    if not out.kind and _MINOR_SHOCK.search(message) and _SHOCK_INJURY.search(message):
        # "a little shock and now my hand is numb and tingling": an injury sign after a shock is a person-danger line
        # (911 if it gets worse), not the property steps
        out.care, out.concern, out.mentioned_kind, out.framing = "danger", True, None, "none"
    elif not out.kind and not out.mentioned_kind and _MINOR_SHOCK.search(message):
        # "i got a little shock when i touched the outlet": the electrical steps as calm info (don't touch it; smoke,
        # sparks or heat: leave and call 911), never silence
        out.mentioned_kind, out.framing, out.happened = "electrical", "past", True
    if out.kind == "medical" and _SELF_CUT.search(message) and not _ACCIDENT.search(message):
        out.self_harm_intent = True  # final round: a self-inflicted cut scored as medical also gets 988
    if out.kind == "poison" and _SELF_QUANTITY.search(message):
        out.self_harm_intent = True  # "i just swallowed a whole bottle of my sleeping pills": 988 with the alert
    if out.kind == "poison" and (intent_to_self_harm(message) or any(intent_to_self_harm(m) for m in prev)):
        out.self_harm_intent = True
    return out


def _may_lower(out: DeterministicRisk, fr: RiskFrame, message: str) -> bool:
    """Monotone-safe lowering (sprint 7 fix round). A rule match is lowered to a mention ONLY when all hold:
    a look-alike framing; a kind that is not self-harm, personal safety or poison; not via the window; no person /
    body state and no frame alert anywhere in the message; and the message WITHOUT the look-alike phrase has no
    hazard of its own (rules and frame). So adding "the smoke detector is old" or "is this a drill?" to a real
    report never lowers it."""
    if out.kind in _NEVER_LOWERED or out.via_window or fr.alert:
        return False
    if fr.states and any(w in fr.who for w in ("self", "child", "elder", "adult", "pronoun")):
        return False  # a body state of a real person anywhere in the message (generic "signs of a stroke" is not)
    rest = without_lookalike(message, fr.look_alike)
    if scan(rest)[0] or analyse(rest).urgency != "none" or possible_risk(rest) in ("distress", "unwell"):
        return False
    return True


def _combine(out: DeterministicRisk, fr: RiskFrame, message: str) -> None:
    """Frame + phrase rules, conservatively (see the module docstring)."""
    if out.kind and fr.look_alike and _may_lower(out, fr, message):
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
