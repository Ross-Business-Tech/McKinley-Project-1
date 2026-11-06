"""Deterministic slot extraction and request detectors for the customer workflows (F2, F3, F4, F5, F6, F8).

Everything here is regex over the already-redacted message. Nothing calls a model, nothing has side effects.
Patterns are TEAM DRAFTS: the lists McKinley must approve (I-06 opt-out keywords, I-13 fair-housing topics,
I-15 tour questions, I-19 intake fields) are marked as such in docs/WORKFLOW_TRACEABILITY.md.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

KB_PATH = Path(__file__).resolve().parent / "content" / "knowledge_base.json"

# ---- language (prototype: English primary, Spanish secondary) ------------------------------------------

_ES_WORDS = re.compile(
    r"\b(hola|gracias|por favor|necesito|tengo|mi|mis|está|esta|no funciona|ayuda|cocina|baño|bano|puerta|"
    r"agua|luz|renta|contrato|cuándo|cuando|quiero|hablar|persona|apartamento|horno|fuga|gotea|olor|"
    r"mantenimiento|solicitud|estado|sí|usted|español|espanol)\b", re.IGNORECASE)


def detect_language(message: str, preferred: str | None = None) -> str:
    """'es' when the message reads as Spanish (>=2 marker words) or the record prefers Spanish and the
    message is not clearly English. Anything else is 'en'. Other languages fall back to 'en' + staff offer."""
    hits = len(_ES_WORDS.findall(message))
    if hits >= 2 or re.search(r"[¿¡ñ]", message):
        return "es"
    if preferred and preferred.lower().startswith("span") and hits >= 1:
        return "es"
    if preferred and preferred.lower().startswith("span") and not re.search(
            r"\b(the|is|my|and|please|what|when|can)\b", message, re.IGNORECASE):
        return "es"
    return "en"


_OTHER_LANGUAGE = re.compile(r"[Ѐ-ӿ؀-ۿऀ-ॿ一-鿿぀-ヿ가-힯]")


def non_latin_script(message: str) -> bool:
    """Message is written in a script the prototype has no approved templates for (Arabic, CJK, ...)."""
    return bool(_OTHER_LANGUAGE.search(message))


# ---- request detectors ----------------------------------------------------------------------------------

# I-06 DRAFT: standard US short-code keywords. Compliance (McKinley + legal) must approve the list and wording.
SMS_OPT_OUT = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "opt out", "optout"}


def is_sms_opt_out(message: str) -> bool:
    return message.strip().strip(".!").lower() in SMS_OPT_OUT


_STATUS = re.compile(
    r"status of (my|the)|(any )?(update|news) (on|about) (my|the)|where (is|are) (my|the) (request|repair|"
    r"work order|ticket)|(check|see|look up) (on )?(my )?(open )?(requests?|work orders?|tickets?|repairs?)|"
    r"\bmy (open )?(requests?|work orders?|tickets?|repairs?)\b|when (is|will) (maintenance|someone|the tech"
    r"\w*) (coming|come)|has anyone (looked|been)|estado de mi|mi solicitud",
    re.IGNORECASE)


def is_status_request(message: str) -> bool:
    return bool(_STATUS.search(message))


_CHANGE_REQUEST = re.compile(
    r"\b(cancel|reschedule|change|update(?! on| about)|edit|add (a |some )?(note|photo|detail)s? to)\b.{0,30}\b"
    r"(my |the )?"
    r"(request|work order|ticket|appointment|repair)", re.IGNORECASE)


def is_change_request(message: str) -> bool:
    """F7 update path. I-24 (what residents may change at each status) is not approved, so staff handle it."""
    return bool(_CHANGE_REQUEST.search(message))


_VENDOR = re.compile(
    r"\b(i'?m|i am|this is) (the |a |an |from )?(\w+ )?(contractor|vendor|plumber|electrician|technician|"
    r"hvac (company|tech|contractor)|supplier|delivery company|landscap\w*)\b|\binvoice\b|\bpurchase order\b|"
    r"\b(gate|door|lockbox|access) code\b", re.IGNORECASE)


def is_vendor_contact(message: str) -> bool:
    return bool(_VENDOR.search(message))


# I-13 DRAFT (steering half). Questions that ask the assistant to describe or sort people by a protected trait.
# Accommodation / disability / voucher topics are handled by safety.py and routed to staff, never declined.
_STEERING = re.compile(
    r"(fewer|less|more|lots of|a lot of|no|any) (families|kids|children|immigrants|foreigners|minorities|"
    r"seniors|old people|young people|students)|(ethnic|racial|religious) (makeup|mix|composition)|"
    r"what (race|religion|nationality|kind of people)|"
    r"(white|black|hispanic|latino|asian|christian|muslim|jewish) (neighborhood|area|building|community|people)|"
    r"(neighborhood|building|area) .{0,20}(safe|good) for (a )?(single )?(women|woman|families|christians|"
    r"muslims|gays?)|adults? only|no kids",
    re.IGNORECASE)


def is_steering_question(message: str) -> bool:
    return bool(_STEERING.search(message))


_AFFIRM = re.compile(r"^\s*(yes|yep|yeah|sure|ok(ay)?|correct|that'?s (right|correct)|looks (good|right)|send"
                     r"( it)?|submit( it)?|go ahead|confirm|s[ií]|correcto|env[ií]alo|de acuerdo)\b[\s.!,]*",
                     re.IGNORECASE)


def is_affirmative(message: str) -> bool:
    return bool(_AFFIRM.match(message)) and len(message) <= 60


_DECLINE = re.compile(r"^\s*(no|nope|never ?mind|cancel( that)?|forget it|not now|don'?t send)\b",
                      re.IGNORECASE)


def is_decline(message: str) -> bool:
    return bool(_DECLINE.match(message)) and len(message) <= 60


_STAFF = re.compile(r"(talk|speak) (to|with) (the )?(office|leasing( team)?|staff|someone)|send (a |the )?note to "
                    r"the office|contact (the )?(office|staff|leasing)|hablar con (la oficina|arrendamiento|alguien)|"
                    r"enviar (una )?nota a la oficina", re.IGNORECASE)


def is_staff_request(message: str) -> bool:
    """Quick-action / plain request to reach the office (softer than 'real person, not a bot')."""
    return bool(_STAFF.search(message))


_SAYS_RESIDENT = re.compile(r"\bi (live|rent) (at|in|here)|i'?m a (current )?resident|vivo en", re.IGNORECASE)


def says_resident(message: str) -> bool:
    return bool(_SAYS_RESIDENT.search(message))


_TOUR = re.compile(r"\btours?\b|\bvisit\b|see (it|one|a place|an apartment|the "
                   r"(place|apartment|unit|community))|come (by|see)|"
                   r"\bshow me\b|walk ?through|visitar|recorrido", re.IGNORECASE)


def is_tour_request(message: str) -> bool:
    return bool(_TOUR.search(message))


# ---- maintenance intake slots (I-19 DRAFT) --------------------------------------------------------------

_LOCATIONS = [
    ("Kitchen", r"kitchen|cocina"),
    ("Bathroom", r"bath ?room|restroom|shower|tub|toilet|baño|bano"),
    ("Bedroom", r"bed ?room|dormitorio|recámara"),
    ("Living room", r"living room|lounge|sala"),
    ("Laundry area", r"laundry|washer|dryer|lavadora|secadora"),
    ("Balcony or patio", r"balcony|patio|balc[oó]n"),
    ("Whole apartment", r"whole (apartment|unit|place)|everywhere|all rooms|entire (apartment|unit)|todo el"),
    ("Outside or common area", r"hallway|parking lot|stair|common area|outside|pasillo|estacionamiento"),
]


def extract_location(message: str) -> str | None:
    for label, pat in _LOCATIONS:
        if re.search(rf"\b(?:{pat})\b", message, re.IGNORECASE):
            return label
    return None


_APPLIANCE_ROOM = [
    ("Kitchen", r"oven|stove|range|fridge|refrigerator|freezer|dishwasher|microwave|disposal|horno|estufa|"
                r"refrigerador|lavaplatos"),
    ("Bathroom", r"toilet|shower|tub|inodoro|ducha"),
    ("Laundry area", r"washer|dryer|lavadora|secadora"),
]


def infer_location(message: str) -> str | None:
    """Room implied by an appliance ('the oven' -> Kitchen). Shown as the assistant's guess, editable."""
    for label, pat in _APPLIANCE_ROOM:
        if re.search(rf"\b(?:{pat})\b", message, re.IGNORECASE):
            return label
    return None


_ENTRY_YES = re.compile(r"(yes|ok|okay|fine|sure)[, ]*(you |they |maintenance |the tech\w* )?(can|may) (come in|"
                        r"enter|go in)|(can|may) (come in|enter)( anytime| any time| if i'?m not home)?|"
                        r"enter (without me|if i'?m not (home|there))|permission to enter|"
                        r"pueden entrar|puede entrar", re.IGNORECASE)
_ENTRY_NO = re.compile(r"(don'?t|do not|please don'?t|no,? (don'?t|do not)) (come in|enter)|"
                       r"(call|contact|text|message) (me )?(first|before)|only (when|if) i'?m (home|there)|"
                       r"i (want|need) to be "
                       r"(home|there)|no entr|llamen antes|av[ií]senme antes", re.IGNORECASE)


def extract_entry(message: str) -> str | None:
    if _ENTRY_NO.search(message):
        return "Contact me first; only enter when I'm home"
    if _ENTRY_YES.search(message):
        return "Yes, maintenance may enter if I'm not home"
    return None


_ISSUE_HINT = re.compile(
    r"leak|drip|broken|not working|won'?t|doesn'?t|stopped|clog|no (heat|hot water|water|power|ac|a/c)|noise|"
    r"rattl|smell|mold|pest|roach|ant|mouse|mice|bug|crack|stuck|loose|running|cooling|heating|"
    r"no funciona|gotea|fuga|roto|no calienta|no enfr",
    re.IGNORECASE)


_GREETING = re.compile(r"^\s*(hi|hello|hey|hola|buenos d[ií]as|buenas tardes|good (morning|afternoon|evening))"
                       r"( there)?[,.!\s]+", re.IGNORECASE)


def strip_greeting(message: str) -> str:
    out = _GREETING.sub("", message, count=1).strip()
    return (out[:1].upper() + out[1:]) if out else message


_GENERIC_REPORT = re.compile(r"^\s*(i (want|need|would like) to |can i |help me )?(report|submit|make|file|start)"
                             r"( a| an| my)? (new )?(repair|maintenance)( request| issue)?[.!?]?\s*$|"
                             r"^\s*(i need )?(a )?(repair|maintenance)[.!?]?\s*$|^\s*reportar una reparaci[oó]n\s*$",
                             re.IGNORECASE)


def describes_issue(message: str) -> bool:
    """True unless the message is only a generic 'report a repair' request."""
    return not _GENERIC_REPORT.match(message)


# ---- tour slots (I-15 DRAFT: McKinley leasing has not supplied required tour questions) -------------------

_DAYS = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun"
_DAY_PHRASE = re.compile(
    rf"\b(this|next) (week|weekend|{_DAYS})\b|\b(tomorrow|today|this afternoon|tonight|weekend|weekdays?|"
    rf"any ?day|anytime this week)\b|\b(?:on |this |next )?(?:{_DAYS})s?\b|\b(lunes|martes|mi[ée]rcoles|"
    rf"jueves|viernes|s[áa]bado|domingo|ma[ñn]ana)\b", re.IGNORECASE)
_TIME_OF_DAY = re.compile(r"\b(morning|mornings|afternoon|afternoons|evening|evenings|after work|lunch ?time|"
                          r"before work|ma[ñn]ana|tarde|noche)\b", re.IGNORECASE)
_BEDS = re.compile(r"\b(\d|one|two|three|four)\s?-?\s?(?:bed|br|bedroom)s?\b|\bstudio\b", re.IGNORECASE)
_WORDNUM = {"one": "1", "two": "2", "three": "3", "four": "4"}
_AREA = re.compile(r"\b(?:in|near|around|at) ((?:[A-Z][a-z]+)(?: [A-Z][a-z]+){0,2})")
_NOT_AREA = {"The", "My", "A", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
             "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December", "I"}


def extract_days(message: str) -> str | None:
    found = [m.group(0).strip() for m in _DAY_PHRASE.finditer(message)]
    if not found:
        return None
    seen = list(dict.fromkeys(f[0].upper() + f[1:] for f in found))
    return ", ".join(seen[:3])


def extract_time_of_day(message: str) -> str | None:
    m = _TIME_OF_DAY.search(message)
    if not m:
        return None
    t = m.group(1).lower()
    for key, label in (("morning", "Morning"), ("afternoon", "Afternoon"), ("evening", "Evening"),
                       ("after work", "Evening"), ("before work", "Morning"), ("lunch", "Midday"),
                       ("tarde", "Afternoon"), ("noche", "Evening"), ("ma", "Morning")):
        if t.startswith(key):
            return label
    return t.capitalize()


def extract_beds(message: str) -> str | None:
    m = _BEDS.search(message)
    if not m:
        return None
    if m.group(0).lower().startswith("studio"):
        return "Studio"
    n = _WORDNUM.get(m.group(1).lower(), m.group(1))
    return f"{n} bed" + ("s" if n != "1" else "")


def extract_area(message: str) -> str | None:
    for m in _AREA.finditer(message):
        name = m.group(1)
        if name.split()[0] not in _NOT_AREA:
            return name
    return None


# ---- knowledge base (D-07 / I-12) ------------------------------------------------------------------------


@dataclass(frozen=True)
class KBTopic:
    id: str
    label: str
    status: str  # approved | pending_approval | live_data_unavailable
    answer: str | None
    answer_es: str | None
    source: str


@lru_cache
def knowledge_base() -> tuple[str, list[tuple[KBTopic, list[str]]]]:
    data: dict[str, Any] = json.loads(KB_PATH.read_text(encoding="utf-8"))
    topics = [(KBTopic(id=t["id"], label=t["label"], status=t["status"], answer=t.get("answer"),
                       answer_es=t.get("answer_es"), source=t["source"]), [k.lower() for k in t["keywords"]])
              for t in data["topics"]]
    return data["version"], topics


def match_faq(message: str) -> list[KBTopic]:
    low = message.lower()
    _, topics = knowledge_base()
    return [t for t, kws in topics if any(re.search(rf"(?<![a-z]){re.escape(k)}", low) for k in kws)]
