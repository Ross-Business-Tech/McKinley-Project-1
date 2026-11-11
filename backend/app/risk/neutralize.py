"""Layer 1d (sprint 8): benign-span neutraliser. The five-way distinction the UI needs:

  active emergency | highly concerning but ambiguous | hypothetical safety question | past or resolved | look-alike

Earlier sprints fixed look-alikes phrase by phrase inside each detector. This module instead finds SPANS of the
message that cannot describe a real person or hazard right now, removes them, and lets app.risk.detect run the same
rules on what is left. A span is one of these classes (EN + ES):

  title      a quoted or named title: a song / film / game / perfume / sauce "called X", "'Can't Breathe' is stuck in
             my head", "Breathless is my favorite perfume"
  fiction    a film / show / book / story / game / dream "where / about ..." up to the next real-world clause
  training   a drill, CPR / first-aid class, a dummy or mannequin, a "fake" or "pretend" emergency
  device     a phone / laptop / computer / app / car as the subject of "died", "won't wake up", "not responding"
  idiom      "can't breathe from laughing", "dying of laughter", "won't wake up for school", "out of breath from the
             stairs", "fell asleep"
  activity   a posture with an ordinary activity ("lying on the floor fixing the pipe", "napping on the floor mat",
             "on the floor doing yoga")
  conditional  an "if / in case / what if / si" clause (not "I don't know if ..."): a hypothetical question
  recovered  a past-time clause together with a recovery statement ("had a heart attack in 2019, he's doing great
             now", "se cayó el mes pasado, ya está bien")

How detect() uses it (monotone-safe by construction):
  - detection runs on the original AND on the remainder; the result can only be LOWER when the remainder is lower;
  - self-harm and personal safety are never lowered, nor an alert that came from the conversation window;
  - conditional and recovered spans lower only when the remainder has NO sign at all (no alert, no care line), so
    "my mom fell and if she can't get up what do I do" stays an alert;
  - a live marker (now, right now, still, again, ahora, todavia, otra vez) inside a conditional keeps it live;
  - a decoration added to a real report never removes the report itself, because spans are bounded (a fiction span
    stops at "and my / but now / y mi ..."), so the metamorphic invariants (tests/test_sprint7_safety_invariants.py)
    still hold.

A conditional about a SPECIFIC person with a serious stative sign ("if my dad can't breathe, what should I do?") is
returned as `conditional_danger`: the policy shows the approved notice as safety info with the category contacts
(UI state "concern"), and no incident is opened. A present-tense sign in the same or a later message is an alert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_F = re.I

# where a span describing something unreal / past stops and the real world may start again
_CUT = (r"(?=\s*(?:[.;!?]|,?\s+(?:and|but|y|pero)\s+(?:now|right now|then|my|our|his|her|he|she|they|i|we|someone|"
        r"mi|mis|su|ahora|el|ella|alguien)\b|\b(?:right now|ahora mismo|actually|de verdad|for real|"
        r"in real life)\b)|$)")

_TITLE_NOUN = (r"song|track|album|band|movie|film|show|series|book|novel|game|video ?game|app|perfume|cologne|scent|"
               r"fragrance|candle|sauce|hot sauce|drink|cocktail|beer|wine|brand|product|podcast|play|musical|"
               r"cancion|pelicula|serie|libro|juego|perfume|vela|salsa|bebida|marca")
_QUOTED = re.compile(r"[\"“”«]([^\"“”«»]{1,60})[\"“”»]|‘([^’]{1,60})’|(?<!\w)'(.{1,60}?)'(?!\w)", _F)
_CALLED = re.compile(r"\b(?:called|named|titled|brand|llamad[oa]|se llama|de nombre)\s+((?:[A-Z][\w'’-]*\s*){1,5})")
_IS_FAV = re.compile(
    rf"^\s*((?:[A-Z][\w'’-]*\s*){{1,4}})\s+(?:is|was|es)\s+(?:the name of|my (?:favorite|favourite|new|go-to)|our "
    rf"(?:favorite|favourite|new)|a (?:great |new |good |popular )?(?:{_TITLE_NOUN})|mi (?:\w+ )?favorit[oa])", re.M)
_FAV_IS = re.compile(rf"\b(?:favorite|favourite|new|the|mi|my)\s+(?:{_TITLE_NOUN})\s+(?:is|was|es|called|named)\s+"
                     rf"((?:(?!\b(?:and|but|y|pero|so|because|porque|while|mientras)\b)[^.,;!?]){{1,40}})", _F)

_FICTION = re.compile(
    rf"\b(?:movie|film|show|series|episode|novel|book|story|stories|game|video|scene|cartoon|anime|documentary|"
    rf"podcast|dream|nightmare|play|tv|news|pelicula|serie|episodio|novela|libro|cuento|historia|juego|sueno|sueño|"
    rf"pesadilla|caricatura|noticias)\b(?:\W+\w+){{0,3}}?\W+(?:where|about|in which|when|that|donde|en (?:la|el) que|"
    rf"sobre|de como)\b.*?{_CUT}", _F)
_TRAINING = re.compile(
    rf"\b(?:drill|drills|simulacro|simulacros|cpr|first[- ]aid|primeros auxilios|rcp|dummy|dummies|mannequin|"
    rf"maniqu[ií]|training doll|fake (?:emergency|victim|patient|scenario)|pretend\w*|role[- ]?play\w*|"
    rf"practic(?:e|ed|ing)(?! (?:the|my|a) (?:piano|guitar))|practicamos|simulaci[oó]n)\b.*?{_CUT}", _F)
_DEVICE = re.compile(
    rf"\b(?:phone|cell ?phone|iphone|android|laptop|computer|pc|tablet|ipad|tv|television|screen|monitor|app|"
    rf"website|portal|router|wifi|wi-fi|modem|printer|console|xbox|playstation|ps5|switch|car|battery|remote|"
    rf"celular|tel[eé]fono|computadora|compu|pantalla|tele|televisi[oó]n|impresora|carro|coche|bater[ií]a|control)\b"
    rf"(?:\W+\w+){{0,3}}?\W+(?:died|is dead|dead|froze|frozen|crashed|won'?t (?:wake|turn on|respond|start)|wont "
    rf"(?:wake|turn on|respond|start)|isn'?t responding|is not responding|not responding|stopped responding|"
    rf"unresponsive|no responde|no prende|no enciende|se muri[oó]|se trab[oó]|se congel[oó]|no reacciona)\b.*?{_CUT}",
    _F)
_IDIOM = re.compile(
    r"\b(?:can'?t|cannot|couldn'?t|can not) breathe? (?:from|for|because of|with) (?:laugh\w*|giggl\w*)\b|"
    r"\blaugh\w* so hard (?:that )?(?:i|we) (?:can'?t|couldn'?t) breathe?\b|\b(?:dying|died|dead) (?:of|from|with) "
    r"(?:laugh\w*|embarrassment|boredom|cuteness)\b|\bme muero de (?:risa|verg[uü]enza|aburrimiento)\b|"
    r"\bno puedo respirar de la risa\b|"
    r"\b(?:won'?t|wont|doesn'?t|never|can'?t get (?:him|her|them) to) (?:\w+ )?(?:wake up|get up) (?:for|in time for|"
    r"on time|in the mornings?|early|before (?:noon|\d))(?:\s+(?:school|work|class|church|the bus|practice))?\b|"
    r"\bno se (?:quiere )?(?:despierta|levanta|despertar|levantar) (?:para|a tiempo)(?: (?:la escuela|el trabajo|"
    r"clase))?\b|"
    r"\b(?:out of breath|winded|sin aliento) (?:from|after|by|de|despu[eé]s de) (?:the |climbing |walking |running |"
    r"carrying |subir )?(?:stairs|steps|run\w*|jog\w*|walk\w*|gym|workout|working out|exercis\w*|hike|hiking|"
    r"carrying|las escaleras|correr|caminar|hacer ejercicio)\b|"
    r"\bstuck in (?:my|his|her|their|our) (?:head|mind)\b|\bme (?:qued[oó]|tiene) (?:pegad[oa]|en la cabeza)\b|"
    r"\b(?:fell|falls|falling) asleep\b|\bse (?:qued[oó]|durmi[oó])(?: dormid[oa])?\b|"
    r"\b(?:is|are|'s|'re|was|esta|está) (?:fast |sound |still )?(?:asleep|sleeping|napping|dormid[oa]|durmiendo)\b"
    r"(?! (?:and|but|y|pero) (?:won'?t|wont|can'?t|isn'?t|not|no)\b)", _F)
_ACTIVITY = re.compile(
    r"\b(?:lying|laying|sitting|on (?:the|his|her) (?:back|stomach)|(?:on|in) the (?:\w+ )?(?:floor|ground|mat)|"
    r"(?:en|sobre) el (?:piso|suelo|tapete))\b(?:\W+\w+){0,3}?\W+(?:fixing|repairing|doing|playing|stretching|"
    r"reading|watching|working|looking for|searching|cleaning|painting|assembling|building|installing|under the "
    r"sink|exercising|meditating|napping|sleeping|resting|coloring|drawing|arreglando|jugando|haciendo|leyendo|"
    r"limpiando|pintando|descansando|durmiendo)\b(?:\W+\w+){0,4}|"
    r"\b(?:fixing|repairing|doing (?:yoga|pilates|stretches|push-?ups|sit-?ups|exercises?)|playing|stretching|"
    r"napping|sleeping|resting|haciendo (?:yoga|ejercicio)|jugando|durmiendo)\b(?:\W+\w+){0,3}?\W+(?:on|in) "
    r"(?:the|his|her|my) (?:\w+ )?(?:floor|ground|mat)\b|"
    r"\b(?:on|in) the (?:\w+ )?(?:floor|ground|mat) (?:doing|playing|stretching|fixing) (?:\w+ ?){0,3}", _F)

# fix round: a small amount of water contained in or under one appliance, and "is that a flood?" about it, is a repair
_APPLIANCE = (r"dishwasher|washer|washing machine|fridge|refrigerator|freezer|ice maker|ac|a/c|air conditioner|drip "
              r"pan|tray|water heater pan|tub|sink|lavavajillas|lavaplatos|lavadora|refri\w*|nevera|congelador|"
              r"fregadero|lavabo")
_CONTAINED = re.compile(
    rf"\b(?:a little|a bit of|some|a small (?:amount|puddle) of|a small puddle|a puddle of|a few drops(?: of)?|a "
    rf"little puddle(?: of)?|un poco de|poquita|algo de|un charquito de)\s+(?:standing |pooled |leftover |clean )?"
    rf"(?:water|agua)\b[^.?!]{{0,40}}?\b(?:{_APPLIANCE})\b(?:[^.?!]{{0,30}}?\b(?:after (?:it )?(?:runs|a cycle)|"
    rf"(?:at|in) the bottom))?|\b(?:{_APPLIANCE})\b[^.?!]{{0,30}}?\b(?:has|had|is|with|tiene) (?:a little|a bit of|"
    rf"some|un poco de) (?:standing |pooled )?(?:water|agua)\b[^.?!]{{0,30}}", _F)
_CONTAINED_Q = re.compile(r"\b(?:is|was) (?:that|this|it) (?:a |an )?(?:flood\w*|leak\w*|normal|bad|a problem|"
                          r"emergency|dangerous|serious)\b\??|\b(?:es|ser[aá]) (?:una )?(?:inundaci[oó]n|fuga|normal|"
                          r"grave|peligroso)\b\??", _F)
_EXTENT = re.compile(r"\b(?:gushing|pouring|spraying|everywhere|all over|won'?t stop|wont stop|keeps (?:coming|rising)|"
                     r"rising|spreading|outlets?|electrical|wires?|ceiling|inches|ankle|into the (?:hall|hallway|"
                     r"bedroom|living)|por todas partes|no para|enchufe|techo|"
                     # never near an ingestion: "drank some of the drano under the sink" is a poisoning
                     r"drank|drink\w*|swallow\w*|ate|took|bebi\w*|tom[oó]|trag\w*|kid|child|baby|son|daughter|"
                     r"toddler|year old|hij[oa]|beb[eé]|niñ[oa])\b", _F)


# a conditional clause: hypothetical unless a live marker sits inside it
_COND_START = re.compile(
    r"(?<!\bas )(?<!\beven )(?<!\bonly )(?<!\bsure )(?<!\bcheck )(?<!\bsee )"
    r"(?<!\bwonder )(?<!\bwondering )(?<!\bse )(?<!\bsé )(?<!\bsaber )(?<!\bver )(?<!\bchecking )(?<!\bunclear )"
    r"\b(?:what if|in case|if|en caso de que|en caso de|y si|si)\b(?=\s+\w)", _F)
# fix round: every whitespace-led alternative starts at the beginning of a whitespace run ((?<!\s)), so a long run of
# spaces is scanned once (linear), not once per position
_COND_END = re.compile(
    r"[,.;!?¿]|(?<!\s)\s+(?:what (?:do|should|would|can)|who (?:do|should)|should (?:i|we)|do (?:i|we)|can (?:i|we)|"
    r"how (?:do|should|can)|is it|que (?:hago|debo|hacemos)|qué (?:hago|debo|hacemos)|debo|debemos|a qui[eé]n|"
    r"c[oó]mo (?:le|lo|la)|then|entonces)\b", _F)
_LIVE = re.compile(r"\b(?:now|right now|still|currently|again|at the moment|as we speak|ahora|ahorita|todav[ií]a|"
                   r"sigue|otra vez|en este momento|just now|"
                   r"(?:a few|an?|\d+|ten|five|twenty|thirty) (?:min\w*|seconds|hours?) (?:ago|now)|for (?:a few|\d+|"
                   r"several|the (?:last|past)) \w+|hace (?:un|una|unos|unas|\d+|poco|rato) ?\w*|reci[eé]n|"
                   r"acaba de|acabo de)\b", _F)
# fix round (P1-1): inside "is it bad / what do i do if ...", a COMPLETED event about a specific person, an
# observed appearance or a duration is a live report ("if my kid swallowed a magnet", "if my neighbor collapsed",
# "what if my husband's lips are blue", "if my roommate's been unresponsive"). Ability statives ("if my dad can't
# breathe") stay conditional (rule R5c).
_COMPLETED = re.compile(
    r"\b(?:swallowed|drank|ate|took|taken|has taken|got into|inhaled|overdosed|od'?d|collapsed|fell|fainted|passed "
    r"out|blacked out|hit (?:his|her|their) head|stopped breathing|cut (?:himself|herself|themselves)|(?:has|have|'s|"
    r"s) been|se (?:trag[oó]|tom[oó]|comi[oó]|bebi[oó]|cay[oó]|desmay[oó]|golpe[oó])|tom[oó]|bebi[oó]|trag[oó]|"
    r"comi[oó])\b|\b(?:lips?|skin|face|fingers|labios|piel|cara)\b(?:\W+\w+){0,2}?\W+(?:are|is|look|looks|went|turned|"
    r"turning|est[aá]n?|se ven?) (?:\w+ )?(?:blue|purple|gr[ae]y|azul\w*|morad\w*)\b", _F)
_NOT_KNOWING = re.compile(r"\b(?:don'?t|do not|didn'?t|can'?t|cannot|not|no|never|unable to)\s+(?:\w+\s+)?"
                          r"(?:know|tell|s[eé]|saber|figure out)\s*$", _F)
# a general question about a hazard's properties, nobody named, nothing perceived ("is carbon monoxide dangerous?")
_GENERAL_Q = re.compile(
    r"^\s*¿?\s*(?:how (?:dangerous|bad|toxic|deadly|harmful|flammable)|qu[eé] tan (?:peligros|t[oó]xic|grave|"
    r"mortal)\w*)\b[^.?!]*\?|"
    r"^\s*¿?\s*(?:is|are|can|could|does|do|what happens|es|son|puede|qu[eé] pasa)\b[^.?!]*\b(?:dangerous|toxic|"
    r"deadly|harmful|poisonous|flammable|safe|bad for (?:you|kids|pets|babies)|explode|kill|peligros[oa]s?|"
    r"t[oó]xic[oa]s?|mortal(?:es)?|venenos[oa]s?)\b[^.?!]*\?", _F | re.M)
_PERCEIVED = re.compile(r"\b(?:smell\w*|hear\w*|see|seeing|beep\w*|going off|in here|right now|my|our|i have|we "
                        r"have|i'?m|we'?re|huele|escucho|veo|tengo|mi|nuestr[oa])\b", _F)
# fix round: a small hazard the resident reports already controlled in the same message ("small grease fire, I put it
# out, everyone is fine"): calm safety info, no incident, the repair can follow
_CONTROLLED = re.compile(
    r"(?<!tried to )(?<!try to )(?<!couldnt )(?<!couldn't )(?<!cant )(?<!can't )(?<!cannot )"
    r"\b(?:(?:i|we|he|she|they) (?:already |just )?"
    r"(?:put (?:it|the fire|the flames) out|put out (?:the )?(?:fire|flames?)|smothered it|extinguished it|shut (?:it |"
    r"the (?:gas|water|valve|main|breaker) )?off|turned (?:it |the (?:gas|water|valve|burner|stove|breaker) )?off)|"
    r"(?:the )?(?:fire|flames?) (?:is|are|went) (?:all )?out\b|it'?s (?:all )?out now|(?:the )?(?:water|leak) "
    r"(?:has )?stopped|apagu[eé] (?:el fuego|las llamas|la estufa|el gas)|lo apagu[eé]|ya (?:se )?apag[oó]|ya est[aá] "
    r"apagad[oa]|cerr[eé] (?:la llave|el gas|el agua))", _F)
_STILL_LIVE = re.compile(r"\b(?:still|spreading|again|keeps?|won'?t|can'?t|cannot|out of control|everywhere|getting "
                         r"(?:worse|bigger)|hurt|burn(?:ed|t) (?:my|his|her)|smoke (?:is )?(?:everywhere|filling)|"
                         r"sigue|otra vez|se extiende|no (?:puedo|se apaga))\b", _F)
_SPECIFIC = re.compile(r"\b(?:my|our|his|her|mi|mis|nuestr[oa]|su)\s+(?:\w+\s+)?\w+|\b(?:he|she|they|him|her|"
                       r"them|[eé]l|ella)\b", _F)
_GENERIC = re.compile(r"\b(?:someone|somebody|anyone|anybody|a (?:person|kid|child|baby|toddler|resident|tenant)|"
                      r"people|alguien|una persona|un (?:niñ|nin)[oa]|un beb[eé])\b|\bever\b|\balguna vez\b", _F)

# past + recovery ("had a heart attack in 2019, he's doing great now")
_PAST = re.compile(
    r"\b(?:last (?:year|month|week|weekend|summer|winter|spring|fall|time|christmas|night)|yesterday|the other day|"
    r"(?:a|one|two|three|few|\d+) (?:days?|weeks?|months?|years?) ago|(?:years?|months?|weeks?) ago|a while (?:ago|"
    r"back)|back in|in (?:19|20)\d\d|when (?:he|she|i|we|they) (?:was|were) (?:\d+|little|young|a baby|younger)|"
    r"el (?:a[nñ]o|mes) pasado|la semana pasada|el fin de semana pasado|ayer|hace (?:\w+ )?(?:a[nñ]os?|meses|mes|"
    r"semanas?|d[ií]as)|cuando (?:era|eramos|éramos) (?:niñ|nin|chic)\w*)\b", _F)
_RECOVERED = re.compile(
    r"\b(?:(?:he|she|they|i|we|it)(?:'s| is| are|'re| am|'m| was| were)?|(?:he|she|they) (?:has|have)|"
    r"everyone(?:'s| is)?)\s+(?:totally |completely |fully |all |doing |been |feeling )?(?:fine|ok|okay|good|great|"
    r"better|alright|all right|recovered|stable|well)\b(?:\s+now)?|\bdoing (?:great|well|fine|better|ok|okay) "
    r"(?:now)?|\b(?:the |her |his |our )?doctors? (?:said|says|told)\b[^.;!?]*|\bno big deal\b|\ball good(?: now)?\b|"
    r"\bfully recovered\b|\bwas just (?:dehydrat\w*|a scare|a bruise)\b|\bya (?:est[aá]n?|estoy|estamos) bien\b|"
    r"\bya pas[oó]\b|\best[aá] bien (?:ahora|ya)\b|\bse recuper[oó]\b|\bel (?:doctor|m[eé]dico) dijo\b[^.;!?]*", _F)
_CLAUSE = re.compile(r"[,.;!?¿¡]+|\b(?:but|and|though|although|pero|y|aunque|anyway|anyways|so)\b", _F)


@dataclass
class Spans:
    benign: str  # message with title / fiction / training / device / idiom / activity spans removed
    reasons: list[str] = field(default_factory=list)
    hypothetical: str | None = None  # remainder after also removing conditional clauses
    clauses: list[str] = field(default_factory=list)  # the conditional clauses removed (without "if")
    conditional_specific: bool = False  # a conditional clause names a specific person (not "someone", not "ever")
    recovered: str | None = None  # remainder after also removing past clauses + recovery statements
    controlled: bool = False  # a small hazard reported already under control in this message


def _sub(pat: re.Pattern[str], text: str, why: str, reasons: list[str]) -> str:
    out = pat.sub(" , ", text)
    if out != text:
        reasons.append(why)
    return out


def _titles(text: str, reasons: list[str]) -> str:
    out = text
    for pat in (_QUOTED, _CALLED, _IS_FAV, _FAV_IS):
        out2 = pat.sub(lambda m: " " + m.group(0).replace(next(g for g in m.groups() if g), " ") + " ", out)
        if out2 != out:
            reasons.append("title")
            out = out2
    return out


def _conditionals(text: str) -> tuple[str, list[str], bool]:
    """(text without conditional clauses, the clauses removed, a removed clause names a specific person)."""
    out, removed, specific, pos = [], [], False, 0
    for m in _COND_START.finditer(text):
        if m.start() < pos:
            continue
        end = _COND_END.search(text, m.end())
        stop = end.start() if end else len(text)
        clause = text[m.end():stop]
        if _NOT_KNOWING.search(text[max(0, m.start() - 40):m.start()]):
            continue  # "i don't know if he's breathing": a live, uncertain report
        if _LIVE.search(clause) or (_SPECIFIC.search(clause) and not _GENERIC.search(clause)
                                    and _COMPLETED.search(clause)):
            continue  # "if he can't breathe right now", "if my kid swallowed a magnet": a live report
        out.append(text[pos:m.start()])
        pos = stop
        removed.append(clause)
        specific = specific or (bool(_SPECIFIC.search(clause)) and not _GENERIC.search(clause))
    out.append(text[pos:])
    return " ".join(out), removed, specific


def _recovered(text: str) -> str | None:
    if not (_PAST.search(text) and _RECOVERED.search(text)):
        return None
    keep = [c for c in _CLAUSE.split(text) if c and c.strip() and not _PAST.search(c) and not _RECOVERED.search(c)]
    return " , ".join(keep)


def spans(message: str) -> Spans:
    reasons: list[str] = []
    t = _titles(message, reasons)
    t = _sub(_FICTION, t, "fiction", reasons)
    t = _sub(_TRAINING, t, "training", reasons)
    t = _sub(_DEVICE, t, "device", reasons)
    t = _sub(_IDIOM, t, "idiom", reasons)
    t = _sub(_ACTIVITY, t, "activity", reasons)
    if _CONTAINED.search(t) and not _EXTENT.search(t):
        t = _sub(_CONTAINED, _sub(_CONTAINED_Q, t, "contained", reasons), "contained appliance water", reasons)
    out = Spans(benign=t, reasons=reasons)
    hyp, removed, specific = _conditionals(t)
    for m in _GENERAL_Q.finditer(hyp):
        if not _PERCEIVED.search(m.group(0)):  # "is carbon monoxide dangerous?" (not "is the smell in here dangerous?")
            removed.append(m.group(0))
            hyp = hyp.replace(m.group(0), " , ")
    if removed:
        out.hypothetical, out.conditional_specific, out.clauses = hyp, specific, removed
    out.recovered = _recovered(t)
    out.controlled = bool(_CONTROLLED.search(t) and not _STILL_LIVE.search(_CONTROLLED.sub(" ", t)))
    return out
