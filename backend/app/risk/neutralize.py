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

# a conditional clause: hypothetical unless a live marker sits inside it
_COND_START = re.compile(
    r"(?<!\bas )(?<!\beven )(?<!\bonly )(?<!\bknow )(?<!\bsure )(?<!\bcheck )(?<!\bsee )(?<!\btell )"
    r"(?<!\bwonder )(?<!\bwondering )(?<!\bse )(?<!\bsé )(?<!\bsaber )(?<!\bver )(?<!\bchecking )(?<!\bunclear )"
    r"\b(?:what if|in case|if|en caso de que|en caso de|y si|si)\b(?=\s+\w)", _F)
_COND_END = re.compile(
    r"[,.;!?¿]|\s+(?:what (?:do|should|would|can)|who (?:do|should)|should (?:i|we)|do (?:i|we)|can (?:i|we)|"
    r"how (?:do|should|can)|is it|que (?:hago|debo|hacemos)|qué (?:hago|debo|hacemos)|debo|debemos|a qui[eé]n|"
    r"c[oó]mo (?:le|lo|la)|then|entonces)\b", _F)
_LIVE = re.compile(r"\b(?:now|right now|still|currently|again|at the moment|as we speak|ahora|ahorita|todav[ií]a|"
                   r"sigue|otra vez|en este momento)\b", _F)
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
_CLAUSE = re.compile(r"[,.;!?¿¡]+|\s+(?:but|and|though|although|pero|y|aunque|anyway|anyways|so)\s+", _F)


@dataclass
class Spans:
    benign: str  # message with title / fiction / training / device / idiom / activity spans removed
    reasons: list[str] = field(default_factory=list)
    hypothetical: str | None = None  # remainder after also removing conditional clauses
    clauses: list[str] = field(default_factory=list)  # the conditional clauses removed (without "if")
    conditional_specific: bool = False  # a conditional clause names a specific person (not "someone", not "ever")
    recovered: str | None = None  # remainder after also removing past clauses + recovery statements


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
        if _LIVE.search(clause):
            continue  # "if he can't breathe right now": a live report inside a conditional
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
    out = Spans(benign=t, reasons=reasons)
    hyp, removed, specific = _conditionals(t)
    if removed:
        out.hypothetical, out.conditional_specific, out.clauses = hyp, specific, removed
    out.recovered = _recovered(t)
    return out
