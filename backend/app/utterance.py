"""Structural analysis of one customer message (Sprint 7).

Why this exists: the Sprint 6 understanding layer asked many independent regex detectors ("is this a status
check?", "a history question?", "more detail after Send?") and the first one that matched won. Each detector had
its own word list, so a paraphrase that one list missed fell through to the next step (a status question became a
new repair card, "it is the one next to the fridge" became a duplicate repair). This module computes the shared
structure ONCE:

- `normalize`: everyday abbreviations ("tmrw", "pls", "2morrow") become words, so no detector needs to list them;
- `analyze` -> `Utterance`: the mood (question / information request / statement / addition), the problem schema
  (object + symptom, with landmark nouns like "next to the fridge" kept apart from the problem's object), and what the
  message is about (requests, the past, a visit), all from small semantic-field lexicons (EN + ES);
- `field_refs` / `field_corrections`: ONE resolver for "which card field does this message name" (every field of
  every card kind, EN + ES synonyms) and the value it gives, used for corrections before and after Send;
- `segments`: the message split into clauses, each tagged with the workflow it asks for (repair, person, tour,
  question), so two different needs in one message are both kept.

Everything here is data. It never changes state; `app.understanding` and `actions.plan_turn` decide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.intake import appliance_in, city_in, community_in, extract_days, extract_location, extract_time_of_day

# ---- normalisation ---------------------------------------------------------------------------------------------

_ABBREV: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:tmrw|tmrow|tmr|tmw|2morrow|2moro|tomoz|tomorow|tommorow|tommorrow)\b", re.I), "tomorrow"),
    (re.compile(r"\b(?:pls|plz|plez)\b", re.I), "please"),
    (re.compile(r"\b(?:thx|thnx|tnx)\b", re.I), "thanks"),
    (re.compile(r"\bb4\b", re.I), "before"),
    (re.compile(r"\bnxt\b", re.I), "next"),
    (re.compile(r"\bappt\b", re.I), "appointment"),
    (re.compile(r"\bw/(?=\s)", re.I), "with"),
    (re.compile(r"\bw/o\b", re.I), "without"),
    (re.compile(r"\brn\b(?=\W*$)", re.I), "right now"),
]


def normalize(msg: str) -> str:
    """Everyday chat abbreviations as words ('tmrw morning pls' -> 'tomorrow morning please'). Nothing else
    changes: no lowercasing, no spelling correction, so the person's own words are kept on the card."""
    out = msg
    for pat, rep in _ABBREV:
        out = pat.sub(rep, out)
    return out


# ---- semantic-field lexicons (EN + ES) -------------------------------------------------------------------------

_FILLER = r"(?:(?:so|ok(?:ay)?|and|but|wait|um+|uh+|hey|hi|also|well|then|y|pero|oye|bueno|entonces)\W+)*"
_WH = (r"(?:what|what's|whats|which|when|where|who|who's|whos|why|how|qu[eé]|cu[aá]l(?:es)?|cu[aá]ndo|d[oó]nde|"
       r"qui[eé]n(?:es)?|por qu[eé]|c[oó]mo|cu[aá]nt[oa]s?)")
_AUX = (r"(?:is|are|was|were|do|does|did|can|could|will|would|should|has|have|had|may|might|am|any|anything|"
        r"tengo|tiene|tienen|hay|puedo|puede|pueden|van|va|est[aá]|sigue|siguen)")
_QUESTION = re.compile(rf"\?|^\W*¿|^\W*{_FILLER}(?:{_WH}|{_AUX})\b|\b{_WH}\W*$", re.I)
_INFO_REQUEST = re.compile(
    r"^\W*(?:(?:please|can you|could you|would you|pls)\W+)*(?:list|show|tell|give|pull up|bring up|look up|check|"
    r"display|send me|let me see|let me know|remind me|recap|summari[sz]e|mu[eé]strame|mu[eé]streme|dime|d[ií]game|"
    r"d[eé]me|ens[eé][ñn]ame|rev[ií]s[ae])\b|\bi(?:'d| would)? (?:want|need|like) to (?:see|know|check|review)\b|"
    r"\bcan i (?:see|get|have) (?:a |my |the )?(?:list|history|record|summary|rundown)\b", re.I)
_ADDITION = re.compile(
    r"\b(?:btw|by the way|fyi|for your info\w*|also|one more thing|another thing|forgot to (?:say|mention|add)|"
    r"i forgot|"
    r"forgot|just so you know|should (?:mention|add|say)|i should add|small detail|quick add|to add|adding|p\.?s\.?|"
    r"oh and|and also|plus|se me olvid[oó]|otra cosa|por cierto|tambi[eé]n|adem[aá]s|olvid[eé] (?:decir|mencionar))\b",
    re.I)
_CORRECTION_SIGNAL = re.compile(
    r"\b(?:actually|sorry|oops|my bad|my mistake|i meant|i mean|meant|wrong|correction|not right|incorrect|mistake|"
    r"perd[oó]n|me equivoqu[eé]|quise decir|en realidad|est[aá] mal|incorrect[ao])\b", re.I)

_THINGS: list[tuple[str, str]] = [
    ("ac", r"\bac\b|\ba/c\b|air ?condition\w*|\bhvac\b|\baire(?: acondicionado)?\b"),
    ("heat", r"\bheat(?:er|ing)?\b|\bfurnace\b|\bradiator\b|calefacci[oó]n"),
    ("water heater", r"\bwater heater\b|\bcalentador\b"), ("hot water", r"\bhot water\b|agua caliente"),
    ("sink", r"\bsinks?\b|fregadero|lavabo"), ("faucet", r"\bfaucets?\b|\btaps?\b|\bgrifo\b"),
    ("toilet", r"\btoilets?\b|\binodoro\b|\bescusado\b"), ("shower", r"\bshowers?\b|\btubs?\b|\bba[ñn]era\b|\bducha\b"),
    ("dishwasher", r"\bdishwasher\b|lavaplatos|lavavajillas"),
    ("fridge", r"\bfridge\b|refrigerator|\bfreezer\b|refrigerador|nevera|\brefri\b"),
    ("oven", r"\boven\b|\bstove\b|\brange\b|\bhorno\b|\bestufa\b"), ("microwave", r"microwave|microondas"),
    ("disposal", r"\bdisposal\b|triturador"), ("washer", r"\bwasher\b|washing machine|\blavadora\b"),
    ("dryer", r"\bdryer\b|\bsecadora\b"), ("window", r"\bwindows?\b|\bventanas?\b"),
    ("door", r"\bdoors?\b|\bpuertas?\b"), ("lock", r"\blocks?\b|deadbolt|cerradura"),
    ("fan", r"\bfans?\b|ventilador"), ("light", r"\blights?\b|\bbulbs?\b|\bluz\b|\bluces\b|\bl[aá]mparas?\b"),
    ("outlet", r"\boutlets?\b|enchufes?"), ("ceiling", r"\bceiling\b|\btecho\b"), ("wall", r"\bwalls?\b|\bpared\b"),
    ("pipe", r"\bpipes?\b|plumbing|tuber[ií]as?|\btubos?\b"), ("drain", r"\bdrains?\b|desag[uü]e"),
    ("pests", r"roach\w*|\bants?\b|\bmice\b|\bmouse\b|pests?\b|bugs?\b|hormigas|cucarachas|ratones"),
    ("detector", r"(?:smoke|co) (?:detector|alarm)|\bdetector\b"), ("blinds", r"\bblinds\b|persianas"),
    ("cabinet", r"\bcabinets?\b|\bcupboards?\b|gabinete|alacena"), ("closet", r"\bcloset\b|cl[oó]set"),
    ("thermostat", r"thermostat|termostato"), ("vent", r"\bvents?\b|\bducts?\b"), ("carpet", r"\bcarpet\b|alfombra"),
    ("mailbox", r"\bmail ?box(?:es)?\b|\bbuz[oó]n\b"), ("gate", r"\bgates?\b|\bport[oó]n\b"),
    ("ice maker", r"ice maker"), ("floor", r"\bfloor(?:ing|boards?)?\b|\bpiso\b"),
]
_SYMPTOM = re.compile(
    r"\b(?:leak\w*|leaky|drip\w*|broke\w*|busted|bust|cracked|crack\w*|not (?:cold|cool|hot|warm|working|cooling|"
    r"heating|draining|"
    r"turning on|closing|locking|opening|flushing)|won'?t|wont|doesn'?t|does not|isn'?t|is not|stopped|dead|stuck|"
    r"jamm?ed|clog\w*|backed up|backing up|overflow\w*|flood\w*|noise|noisy|loud|buzz\w*|rattl\w*|grind\w*|squeak\w*|"
    r"squeal\w*|hum+(?:s|ing)?|click\w*|bang\w*|knock\w*|whistl\w*|hiss\w*|smell\w*|stinks?|mo[u]?ld|mildew|stain\w*|"
    r"flicker\w*|burn(?:t|ed)? out|(?:is|are|went|goes|keeps going) (?:also |still |now )?out|out too|loose|wobbl\w*|"
    r"fell (?:off|down)|missing|"
    r"torn|peeling|warm|freezing|too (?:hot|cold)|no (?:hot water|heat|power|water|ac|a/c)|running|keeps|"
    r"infest\w*|chirp\w*|beep\w*|swollen|rot\w*|rust\w*|puddl\w*|wet|soak\w*|"
    r"gotea\w*|fuga|roto|rota|no (?:funciona|sirve|prende|enfr[ií]a|calienta|cierra|abre|jala)|ruido\w*|"
    r"huele|olor|moho|atascad[oa]|tapad[oa]|descompuest[oa])\b", re.I)
_LANDMARK_PREP = re.compile(r"(?:next to|by|near|beside|behind|under(?:neath)?|beneath|above|below|across from|"
                            r"close to|left of|right of|over|al lado de(?:l)?|junto a(?:l)?|cerca de(?:l)?|"
                            r"debajo de(?:l)?|encima de(?:l)?|detr[aá]s de(?:l)?)\s+(?:the |my |a |el |la |mi )?$",
                            re.I)
_OWN_SPACE = re.compile(r"\b(?:in|inside|from|at) (?:my|our|the) (?:unit|apartment|apt|place|home|room|bathroom|"
                        r"kitchen|bedroom|walls?|ceiling)\b|\ben (?:mi|el) (?:apartamento|depa|departamento|casa|"
                        r"cuarto|ba[ñn]o|cocina)\b", re.I)

_REQUEST_NOUN = re.compile(
    r"\b(?:requests?|tickets?|work ?orders?|orders|repairs?|maintenance(?: requests?| tickets?| issues?)?|cases?|"
    r"service requests?|solicitud(?:es)?|reparaci[oó]n(?:es)?|[oó]rden(?:es)?(?: de trabajo)?|reportes?|pedidos?)\b",
    re.I)
_OPEN = re.compile(
    r"\b(?:open|opened|pending|outstanding|active|unresolved|in progress|still (?:open|waiting|pending|going)|"
    r"not (?:yet )?(?:closed|fixed|done|resolved|finished)|haven'?t been (?:closed|fixed|done|resolved)|"
    r"waiting|abiert[oa]s?|pendientes?|en (?:curso|proceso)|sin resolver)\b", re.I)
_PAST = re.compile(
    r"\b(?:before|ever|previous(?:ly)?|past|prior|last time|history|historial|record|records|already|earlier|"
    r"been (?:done|fixed|repaired|worked on|looked at|serviced)|have i had|had (?:any|problems|issues|trouble)|"
    r"antes|pasad[oa]s?|anteriores?|he tenido|han hecho|han arreglado|ya (?:arreglaron|vinieron)|"
    r"(?:have|did) i (?:ever |already )?(?:report|put in|file|submit|ask|request|make|made)\w*|he (?:hecho|reportado|"
    r"pedido))\b", re.I)
_REPAIR_VERB = re.compile(r"\b(?:fix(?:ed)?|repair(?:ed|s)?|work(?:ed)? on|done|serviced|replaced|problems?|issues?|"
                          r"maintenance|arregl\w*|repar\w*|problemas?)\b", re.I)
_VISIT = re.compile(
    r"\b(?:who(?:'s| is| will)?|some(?:one|body)|any(?:one|body)|a (?:tech|technician|plumber|person|repair ?(?:man|"
    r"person))|tech(?:nician)?s?|"
    r"maintenance|they|you guys|the office|staff|a human)\b[^.?!]{0,30}?\b(?:com(?:e|es|ing)|show(?:ing)? up|"
    r"on (?:the|their|his|her) way|(?:be )?sent(?: out)?|send(?:ing)?|stop(?:ping)? by|arriv\w*|be here|get here|"
    r"fix(?:ing)? it|call(?:ing)? me|get(?:ting)? back|follow(?:ing)? up|contact(?:ing)? me|here)\b|"
    r"\bwhat (?:happens|now|next)\b|\bwhat'?s next\b|\bnow what\b|\bso now\b|\bwhat do i do now\b|"
    r"\bdo i (?:need|have) to (?:wait|be home|stay home|be there)\b|"
    r"\b(?:alguien|el t[eé]cnico|mantenimiento)\b[^.?!]{0,25}\b(?:va a venir|vendr[aá]|viene|vienen|llamar[aá]?)\b|"
    r"\bcu[aá]ndo (?:vienen|viene|vendr[aá]n?|llegan?)\b|\by ahora qu[eé]\b|\bqu[eé] sigue\b", re.I)
_PERSON_WORD = re.compile(r"\b(?:person|human|manager|supervisor|staff|office|leasing|someone|somebody|agent|"
                          r"representative|team|alguien|persona|oficina|gerente)\b", re.I)
_TOUR_WORD = re.compile(r"\b(?:tour|visit|viewing|showing|see (?:the|a|it|the place|an?)|come (?:see|by|look)|"
                        r"recorrido|visita|visitar|ver el|ver un)\b", re.I)


def things(text: str) -> set[str]:
    """Every object noun in a text (typed names, EN + ES)."""
    found = {name for name, pat in _THINGS if re.search(pat, text or "", re.I)}
    if "water heater" in found:
        found.discard("heat")
    return found


def problem_objects(text: str) -> set[str]:
    """The objects a text says something is WRONG with. A landmark ('it's the one next to the fridge', 'the cabinet
    under the sink') locates the problem; it is not a second problem."""
    out: set[str] = set()
    for name, pat in _THINGS:
        for m in re.finditer(pat, text or "", re.I):
            if not _LANDMARK_PREP.search(text[:m.start()]):
                out.add(name)
    if "water heater" in out:
        out.discard("heat")
    return out


def has_symptom(text: str) -> bool:
    return bool(_SYMPTOM.search(text or ""))


@dataclass
class Utterance:
    """The structure of one message. Data only."""

    text: str
    question: bool = False
    info_request: bool = False  # "list my open requests", "show me my repair history"
    addition: bool = False  # "btw", "also", "forgot to say", "se me olvidó"
    correction: bool = False  # "actually", "sorry", "wrong", "my mistake"
    objects: set[str] = field(default_factory=set)  # problem objects (landmarks excluded)
    landmarks: set[str] = field(default_factory=set)
    symptom: bool = False
    own_space: bool = False
    about_requests: bool = False
    open_marker: bool = False
    past_marker: bool = False
    about_visit: bool = False
    names_person: bool = False
    names_tour: bool = False

    @property
    def asks(self) -> bool:
        return self.question or self.info_request

    @property
    def problem(self) -> bool:
        """A new problem schema: something (an object or the person's own space) plus a symptom."""
        return self.symptom and bool(self.objects or self.own_space)

    @property
    def asks_open_requests(self) -> bool:
        """'list my open maintenance requests', 'what's open right now?', 'tengo solicitudes abiertas?'"""
        if not self.asks or self.problem or self.past_marker and not self.open_marker:
            return False
        return self.about_requests or (self.open_marker and bool(re.search(
            r"\b(?:what'?s|whats|what is|anything|something|my|for me|on my|for my|i have|do i have|tengo|mis)\b",
            self.text, re.I)))

    @property
    def asks_history(self) -> bool:
        """'what repairs have been done in my apartment?', 'have I had AC problems before', 'historial de
        reparaciones'. A history question has a past marker plus something repair-shaped, and no new symptom."""
        if self.symptom and self.objects and not re.search(r"\b(?:problems?|issues?|trouble|problemas?)\b", self.text,
                                                           re.I):
            return False
        hist_word = bool(re.search(r"\bhistor(?:y|ial)\b|\brecords?\b", self.text, re.I)) or bool(
            self.past_marker and self.about_requests and not self.symptom and len(self.text.split()) <= 6)
        return (self.asks or hist_word) and (self.past_marker or hist_word) and (
            self.about_requests or bool(_REPAIR_VERB.search(self.text)) or bool(self.objects) or hist_word)

    @property
    def asks_timing(self) -> bool:
        """'how long will it take', 'how soon can someone come', 'any idea how long?', '¿cuánto tardan?'"""
        return self.asks and not self.problem and bool(re.search(
            r"\bhow (?:long|soon|quickly|fast)\b|\b(?:usual|typical|normal)? ?wait\b|\bwhen (?:can|will|should|do|"
            r"might)"
            r" (?:i|they|someone|somebody|maintenance|a tech\w*) (?:expect|come|get|be|fix|show)|\bthis week\b|"
            r"\btake (?:days|long|weeks)\b|\btill it'?s fixed\b|\bcu[aá]nto (?:tardan?|tiempo|demoran?)\b", self.text,
            re.I))

    @property
    def asks_visit(self) -> bool:
        """'so is someone actually coming?', 'what happens now?', '¿cuándo vienen?' (about a visit or follow-up)."""
        return self.asks and self.about_visit and not self.problem


def analyze(msg: str) -> Utterance:
    text = normalize(msg or "")
    objs = problem_objects(text)
    return Utterance(
        text=text, question=bool(_QUESTION.search(text)), info_request=bool(_INFO_REQUEST.search(text)),
        addition=bool(_ADDITION.search(text)), correction=bool(_CORRECTION_SIGNAL.search(text)),
        objects=objs, landmarks=things(text) - objs, symptom=has_symptom(text), own_space=bool(_OWN_SPACE.search(text)),
        about_requests=bool(_REQUEST_NOUN.search(text)), open_marker=bool(_OPEN.search(text)),
        past_marker=bool(_PAST.search(text)), about_visit=bool(_VISIT.search(text)),
        names_person=bool(_PERSON_WORD.search(text)), names_tour=bool(_TOUR_WORD.search(text)))


def adds_to(u: Utterance, sent_text: str) -> bool:
    """More detail about a request already saved (not a new problem): an addition or a descriptive statement whose
    problem objects are already on that request (or that names none), with no question. 'it is the one next to the
    fridge btw', 'oh it's the right side cabinet', 'and it's been going for 2 days', 'se me olvidó, es el de la
    izquierda'. A different object with a symptom ('also the bathroom fan is loud') is a new problem."""
    if u.question or u.info_request or re.search(r"^\W*(?:(?:and|so|ok(?:ay)?|what about|how about|status of)\W+)*"
                                                 r"(?:the|my|that) (?:\w+ )?(?:one|request|ticket|repair)\s+(?:for|"
                                                 r"about|"
                                                 r"with|on|regarding|re)\b", u.text, re.I):
        return False  # "the one for the sink leak" points AT a request (status), it adds nothing to it
    sent_objs = things(sent_text)
    new_objs = u.objects - sent_objs - {"cabinet", "pipe", "floor", "wall"}  # parts of the same fixture
    if new_objs and u.symptom:
        return False
    descriptive = bool(re.search(
        r"^\W*(?:(?:oh|ah|and|also|so|um+|ok(?:ay)?|btw|fyi|y|oye)\W+)*(?:it'?s|its|it is|it was|it'?s been|"
        r"it only|it (?:leaks|drips|happens|gets|started|seems)|this is|that'?s|the (?:one|leak|drip|water|problem|"
        r"issue|cabinet|pipe)|there'?s|es (?:el|la)|est[aá]|sale|son|fue)\b|\bthe one\b|\bel de\b|\bla de\b|"
        r"\bonly (?:when|at|if)\b|\bsince\b|\bfor (?:\d+|a|two|three) (?:days?|weeks?|hours?)\b|\bdays?\b", u.text,
        re.I))
    return u.addition or (descriptive and not (u.objects - sent_objs))


_ROOMS_EXTRA: list[tuple[str, str]] = [
    ("Garage", r"\bgarage\b|\bgaraje\b|\bcochera\b"), ("Closet", r"\bcloset\b|\bcl[oó]set\b|\barmario\b"),
    ("Basement", r"\bbasement\b|\bs[oó]tano\b"), ("Attic", r"\battic\b|\b[aá]tico\b"),
    ("Entryway", r"\bentry ?way\b|\bfoyer\b|\bentrada\b"), ("Office or den", r"\bhome office\b|\bden\b"),
    ("Stairs", r"\bstairs\b|\bstaircase\b|\bescaleras?\b"), ("Storage", r"\bstorage(?: room| unit)?\b|\bbodega\b"),
    ("Porch", r"\bporch\b|\bdeck\b|\bterraza\b"),
]


def room_in(text: str) -> str | None:
    """A room or place in the home: the intake rooms first, then other places people name (garage, closet...)."""
    if loc := extract_location(text or ""):
        return loc
    return next((label for label, pat in _ROOMS_EXTRA if re.search(pat, text or "", re.I)), None)


# ---- one field-reference resolver for every card kind ----------------------------------------------------------

FIELD_LEXICON: dict[str, dict[str, list[str]]] = {
    "maintenance_request": {
        "issue": ["description", "problem", "issue", "what's wrong", "whats wrong", "what is wrong", "summary",
                  "wording", "descripci[oó]n", "problema"],
        "location": ["location", "room", "place", "spot", "ubicaci[oó]n", "cuarto", "habitaci[oó]n", "lugar",
                     "sitio"],
        "entry": ["entry permission", "entry", "permission to enter", "permission", "access", "entrada", "permiso",
                  "acceso"],
        "contact": ["contact preference", "contact method", "contact", "how to reach me", "how you reach me",
                    "contacto", "forma de contacto"],
        "entry_window": ["best time for visits", "best time", "visit time", "visit window", "time window", "window",
                         "availability", "horario", "hora de visita"],
        "notes": ["notes", "note", "nota", "notas"],
    },
    "tour_request": {
        "area": ["community", "property", "building", "complex", "location", "area", "place", "comunidad", "edificio",
                 "lugar"],
        "days": ["tour date", "tour day", "visit date", "visit day", "date", "day", "days", "fecha", "d[ií]a"],
        "time": ["time of day", "tour time", "visit time", "time", "hora", "horario"],
        "move_in": ["move-in date", "move in date", "move-in", "move in", "move date", "moving date",
                    "fecha de mudanza", "mudanza"],
        "beds": ["bedrooms", "bedroom count", "beds", "floor plan", "rec[aá]maras", "habitaciones"],
        "budget": ["budget", "price range", "presupuesto"],
    },
    "staff_handoff": {
        "message": ["message", "note", "what it says", "mensaje", "nota"],
        "contact": ["contact preference", "contact method", "contact", "how to reach me", "contacto"],
    },
}


def _field_alt(kind: str) -> list[tuple[str, str]]:
    pairs = [(f, syn) for f, syns in FIELD_LEXICON.get(kind, {}).items() for syn in syns]
    return sorted(pairs, key=lambda p: -len(p[1]))  # longest synonym first ("best time" before "time")


def field_refs(msg: str, kind: str) -> list[tuple[str, int, int]]:
    """Every card field the message NAMES, as (field, start, end), longest synonym first, no overlaps."""
    taken: list[tuple[int, int]] = []
    out: list[tuple[str, int, int]] = []
    for f, syn in _field_alt(kind):
        for m in re.finditer(rf"(?<![\w-]){syn}(?![\w-])", msg, re.I):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append((f, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


_NEG_SEG = re.compile(r"\b(?:not|no|instead of|rather than|en vez de|en lugar de|y no)\s+(?:in\s+|the\s+|my\s+|el\s+|"
                      r"la\s+|en\s+(?:el|la)\s+)?[\w-]+(?:\s+(?!(?:but|it|its|it's)\b)[\w-]+)?", re.I)
# A value after the field reference: "the room is wrong, it's the bathroom", "change the location to bathroom",
# "put bathroom as the location", "wrong spot. bathroom", "la ubicación está mal, es el baño".
_FRAME_AFTER = (r"(?:\s+(?:is|was|'s|es|est[aá]|esta)\s+(?:wrong|incorrect|off|not right|mal|incorrect[ao])|"
                r"\s+(?:should|must|needs? to|has to|tiene que|debe)\s+(?:be|say|read|ser|decir)|"
                r"\s*[:=→-]|\s+(?:is|es)(?=\s)|\s+(?:to|a|por|as)(?=[\s:]))")
_LEADS = (r"(?:change|set|update|switch|fix|correct|make|edit|put|cambi\w*|corrig\w*|pon(?:ga|er)?|actualiz\w*)\s+"
          r"(?:the |my |your |el |la |mi )?")


def _value_after(msg: str, end: int) -> str:
    rest = msg[end:]
    rest = re.sub(r"^\s*(?:(?:is|was|'s|es|est[aá]|esta)\s+(?:wrong|incorrect|off|not right|mal|incorrect[ao])|"
                  r"(?:should|must|needs? to|has to|tiene que|debe)\s+(?:be|say|read|ser|decir)|[:=→-]|is|es|to|as|a|"
                  r"por|into)(?=\W|$)", "", rest, flags=re.I)
    rest = re.sub(r"^[\s,.;:!?—–-]*(?:(?:it'?s|its|it is|it should be|should be|make it|use|actually|es|son|"
                  r"the|el|la|en el|en la|in the|in)\s+)*", "", rest, flags=re.I)
    return rest.strip(" .,;:!?\"'")


def _value_before(msg: str, start: int) -> str:
    m = re.search(r"\bput\s+(?P<v>.{2,40}?)\s+(?:as|for|in|como)\s+(?:the |el |la )?$", msg[:start], re.I)
    return m.group("v").strip() if m else ""


def parse_value(field_name: str, kind: str, raw: str) -> str | None:
    """A value of the field's TYPE from free text, or None ('bathroom not kitchen' -> 'Bathroom' for location)."""
    kept = _NEG_SEG.sub(" ", raw)
    if field_name == "location":
        return room_in(kept)
    if field_name == "area":
        return community_in(kept) or city_in(kept)
    if field_name == "days":
        return extract_days(kept)
    if field_name == "time":
        return extract_time_of_day(kept)
    if field_name == "contact":
        for name, pat in (("call", r"\b(?:call|phone|llamad[ao]|llamar)\b"), ("text", r"\b(?:text|sms|mensaje)\b"),
                          ("email", r"\b(?:e-?mail|correo)\b"), ("portal", r"\bportal\b")):
            if re.search(pat, kept, re.I):
                return name
        return None
    if field_name in ("issue", "message", "notes"):
        v = re.sub(r"^(?:(?:it'?s|its|it is|it should be|should be|make it|actually|that|the|my)\s+)+", "", raw.strip(),
                   flags=re.I).strip(" .,;:!?\"'")
        return v[0].upper() + v[1:] if len(v) >= 3 else None
    return None  # entry, entry_window, move_in, beds, budget: their own typed parsers in app.understanding


def field_corrections(msg: str, kind: str | None) -> list[tuple[str, str]]:
    """Corrections that NAME a field, by one shared grammar for every card kind: '(the) F is wrong, it's V',
    'wrong F, V', 'change/set/update the F to V', 'put V as the F', 'F should be V', 'F: V', 'la F está mal, es V',
    'cambie la F a V'. The value must parse as the field's type; with no value right after the field ('can you fix
    the room? it's the bathroom') the rest of the message is read."""
    if not kind:
        return []
    out: list[tuple[str, str]] = []
    text = normalize(msg)
    for f, start, end in field_refs(text, kind):
        before = text[max(0, start - 40):start]
        after = text[end:end + 30]
        framed = bool(re.search(rf"{_LEADS}$", before, re.I) or re.search(r"\bwrong\s+$|\bincorrect\s+$", before, re.I)
                      or re.match(_FRAME_AFTER, after, re.I) or re.search(r"\bput\s+.{2,40}\s+(?:as|for|como)\s+"
                                                                         r"(?:the |el |la )?$", text[:start], re.I))
        if not framed:
            continue
        nxt = next((st for _, st, _ in field_refs(text, kind) if st > end), len(text))
        seg = re.sub(r"[,;\s]*(?:(?:and|but|y)\s+)?(?:the|my|el|la)?\s*$", "", text[end:nxt])
        tail = re.split(r"[.;!?]\s+|,\s*(?=(?:and |but )?(?:the|my|el|la)\s+\w+\s+(?:is|should|es)\b)", seg)[0]
        raw = _value_before(text, start) or (_value_after(text, end) if f not in ("issue", "message", "notes") else
                                             re.sub(rf"^\s*{_FRAME_AFTER}\s*:?\s*", "", tail, flags=re.I))
        val = parse_value(f, kind, raw) if raw else None
        if val is None and f in ("location", "area", "days", "time", "contact"):
            val = parse_value(f, kind, text[end:])
        if val and not any(x[0] == f for x in out):
            out.append((f, val))
    return out


def room_swap(msg: str, current: str | None) -> str | None:
    """Two rooms, one ruled out ('no, not kitchen — bathroom', 'it's in the bathroom actually, not the kitchen',
    'bathroom not kitchen'), or one new room said as a correction ('oops wrong spot. bathroom', 'it's the bathroom
    one, my mistake', 'sorry I meant the bathroom sink'): the room the person wants, if it differs from the card's."""
    text = normalize(msg)
    kept = room_in(_NEG_SEG.sub(" ", text))
    ruled_out = [room_in(m.group(0)) for m in _NEG_SEG.finditer(text)]
    if kept and kept != current and (any(ruled_out) or _CORRECTION_SIGNAL.search(text)):
        return kept
    return None


# ---- two problems in one message -------------------------------------------------------------------------------

_PROBLEM_JOIN = re.compile(
    r"\s*(?:[.;!]+\s+|,|\+|&|\b(?:and also|also|plus|as well as|along with|oh and|and|y tambi[eé]n|tambi[eé]n|"
    r"adem[aá]s|y aparte|aparte|y)\b|\b(?:two|2) things\W*|\(?\b\d[.)]\s+)\s*", re.I)


_PARTS = {"cabinet", "floor", "pipe"}  # parts around a fixture: more about the same problem, not a second one
_ANAPHOR = re.compile(r"\b(?:under|behind|near|next to|around|below|above|beside|from|in|on|inside)\s+(?:it|them|that)"
                      r"\b|^\W*(?:it|it'?s|its|they|that|this)\b", re.I)


def split_problems(msg: str) -> list[str]:
    """Two or more problems by STRUCTURE: clauses that each have their own problem object and a symptom, with
    different objects ('leaky sink, also busted bathroom fan', 'sink leak + bathroom fan not working', 'X, and the
    bathroom fan is also broken'). A clause with no object of its own, only a part (cabinet, floor, pipe) or a pronoun
    back to the last one ('the cabinet under it is wet') stays with the clause before. One problem -> [msg]."""
    text = normalize(msg)
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _PROBLEM_JOIN.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    groups: list[tuple[int, int]] = []
    for a0, b0 in spans:
        c = text[a0:b0].strip(" ,.;:")
        if not c:
            continue
        objs = problem_objects(c)
        if groups and (not objs or objs <= problem_objects(text[groups[-1][0]:groups[-1][1]]) or objs <= _PARTS
                       or _ANAPHOR.search(c)):
            groups[-1] = (groups[-1][0], b0)  # more about the same problem: keep the person's own wording
        else:
            groups.append((a0, b0))
    texts = [text[a0:b0].strip(" ,.;:") for a0, b0 in groups]
    probs = [g for g in texts if problem_objects(g) and has_symptom(g)]
    if len(probs) < 2:
        return [msg]
    seen: set[str] = set()
    for g in probs:
        if problem_objects(g) & seen:
            return [msg]
        seen |= problem_objects(g)
    return [g[0].upper() + g[1:] for g in probs]


# ---- multi-intent segmentation ---------------------------------------------------------------------------------

_CLAUSE_JOIN = re.compile(
    r"\s*(?:[.;!?]+\s+|\s+-\s+|\s*[+&]\s*|,?\s*\b(?:and also|also|plus|separately|on top of that|another thing|"
    r"oh and|but also|"
    r"y tambi[eé]n|adem[aá]s|aparte|por otro lado)\b[,:]?|,\s*(?:and\s+)?(?=(?:can|could|would|please|i(?:'d| would)? "
    r"(?:like|want|need)|i'?m|have|get|quiero|necesito|pueden|puede)\b)|\s+and\s+(?=(?:can|could|would|please|i(?:'d| "
    r"would)? (?:like|want|need)|have (?:someone|somebody|a|the)|get (?:someone|somebody|me)|i want|i need)\b)|"
    r"\s+y\s+(?=(?:quiero|necesito|que (?:alguien|me)|pueden|puede)\b)|^\W*(?:two|2) things\W*)\s*", re.I)


@dataclass
class Segment:
    text: str
    workflow: str  # repair | person | tour | question | other


def segments(msg: str, classify_person: Any) -> list[Segment]:
    """The message as clauses, each tagged with the workflow it asks for. `classify_person` is
    `app.understanding.requests_human` (passed in to avoid an import cycle)."""
    text = normalize(msg)
    out: list[Segment] = []
    for raw in _CLAUSE_JOIN.split(text):
        c = (raw or "").strip(" ,.;:")
        if len(c.split()) < 2:
            continue
        u = analyze(c)
        if classify_person(c) or re.search(r"\bcall ?back\b|\bcall me back\b", c, re.I) or (re.search(
                r"\b(?:call|ring|phone|contact|reach|text|e-?mail)\s+me\b|\bme llame\b|\bme contacte\b", c, re.I)
                and u.names_person):
            wf = "person"
        elif u.problem or (u.objects and u.symptom) or (appliance_in(c) and u.symptom):
            wf = "repair"
        elif u.names_tour:
            wf = "tour"
        elif u.question:
            wf = "question"
        else:
            wf = "other"
        out.append(Segment(c, wf))
    return out


# ---- dates: read back what was understood ----------------------------------------------------------------------

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]
_NUMERIC = re.compile(r"(?<![\d/])(?P<a>\d{1,2})/(?P<b>\d{1,2})(?:/(?P<y>\d{2,4}))?(?![\d/])")
_RELATIVE = re.compile(r"\b(?P<w>day after tomorrow|tomorrow|today|tonight|pasado ma[ñn]ana|"
                       r"(?<!la )(?<!por la )(?<!en la )(?<!de la )ma[ñn]ana(?! (?:por|en) la ma[ñn]ana)|hoy|"
                       r"esta noche)\b",
                       re.I)


def date_readback(text: str, lang: str, today: date | None = None) -> tuple[str, str] | None:
    """(value for the card, read-back line) for a date the person wrote in a form that could be misread: a numeric
    date ('3/4': March 4 here, April 3 in many countries) or a relative day ('tmrw'). None when there's nothing to
    clarify. The read-back states what was written so the person can correct it; nothing is booked."""
    today = today or date.today()
    text = normalize(text)
    m = _NUMERIC.search(text)
    if m:
        a, b = int(m.group("a")), int(m.group("b"))
        if 1 <= a <= 12 and 1 <= b <= 31:
            us = f"{_MONTHS[a - 1]} {b}" if lang == "en" else f"{b} de {_MESES[a - 1]}"
            alt = (f"{_MONTHS[b - 1]} {a}" if lang == "en" else f"{a} de {_MESES[b - 1]}") if b <= 12 and a != b else ""
            return f"{m.group(0)} ({us})", us if not alt else f"{us}|{alt}"
    r = _RELATIVE.search(text)
    if r:
        w = r.group("w").lower()
        delta = 2 if w.startswith(("day after", "pasado")) else 0 if w in ("today", "tonight", "hoy", "esta noche") \
            else 1
        d = today + timedelta(days=delta)
        shown = (f"{d.strftime('%A')}, {_MONTHS[d.month - 1]} {d.day}" if lang == "en"
                 else f"{d.day} de {_MESES[d.month - 1]}")
        return shown, shown
    return None


__all__ = ["normalize", "analyze", "Utterance", "things", "problem_objects", "has_symptom", "adds_to",
           "split_problems", "room_in", "FIELD_LEXICON", "field_refs", "field_corrections", "parse_value", "room_swap",
           "segments", "Segment",
           "date_readback"]
