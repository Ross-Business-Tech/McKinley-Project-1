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


_VIETNAMESE = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.IGNORECASE)


def non_latin_script(message: str) -> bool:
    """Message is in a language the prototype has no approved templates for (Arabic, CJK, Cyrillic, Vietnamese...)."""
    return bool(_OTHER_LANGUAGE.search(message)) or len(_VIETNAMESE.findall(message)) >= 2


# ---- request detectors ----------------------------------------------------------------------------------

# I-06 DRAFT: standard US short-code keywords. Compliance (McKinley + legal) must approve the list and wording.
SMS_OPT_OUT = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "opt out", "optout"}


def is_sms_opt_out(message: str) -> bool:
    return message.strip().strip(".!").lower() in SMS_OPT_OUT


_STATUS = re.compile(
    r"\bstatus\b|(any )?(update|news) (on|about|with) (my|the)|where (is|are) (my|the) (request|repair|"
    r"work order|ticket)|(check|see|look up) (on )?(my )?(open )?(requests?|work orders?|tickets?|repairs?)|"
    r"\bmy (open )?(requests?|work orders?|tickets?|repairs?)\b|when (is|will|are) (maintenance|someone|anyone|"
    r"they|a tech\w*|the tech\w*|somebody) (coming|come|going to come|gonna come|be here|fix)|"
    r"(is|are) (a tech\w*|someone|anyone|maintenance|they) (coming|on (the|their) way)|has anyone (looked|been)|"
    r"did (that|it|my request) go (thru|through)|what'?s (going on|happening) with (my|the)|nobody (came|showed)|"
    r"estado de mi|mi solicitud|cu[aá]ndo (vienen|viene|van a venir)|alguien viene",
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
    r"(fewest|fewer|less|least|most|mostly|many|lots of|a lot of|no|any|full of) (families|kids|children|immigrants|"
    r"foreigners|minorities|seniors|older (folks|people)|old people|young people|students|singles|section 8 "
    r"(people|tenants)|black|white|hispanic|latino|asian|muslim|christian|jewish) ?(people|residents|tenants)?|"
    r"(ethnic|racial|religious) (makeup|mix|composition)|what (race|religion|nationality|kind of (people|neighbors|"
    r"residents|tenants)|type of (people|neighbors|residents))|"
    r"(white|black|hispanic|latino|asian|christian|muslim|jewish) (neighborhood|area|building|community|people)|"
    r"(safe|good|nice|bad|dangerous|sketchy) (area|neighborhood|part of town|place) (for|to)|is (it|the area|the "
    r"neighborhood|that area) (safe|dangerous|sketchy|good)|\bcrime\b|adults? only|no kids|kid[- ]free|"
    r"seniors? only|55\s?\+|over 55|without (kids|children|families)",
    re.IGNORECASE)


def is_steering_question(message: str) -> bool:
    return bool(_STEERING.search(message))


_AFFIRM_WORD = (r"(yes|yep|yeah|yup|sure|ok(ay)?|correct|right|that'?s (right|correct|it)|looks (good|right|"
                r"fine)|all good|perfect|send( it)?( now)?|submit( it)?|go ahead|confirm(ed)?|please do|do it|"
                r"s[ií]|claro|correcto|env[ií]alo|de acuerdo|est[aá] bien|vale)")
_AFFIRM = re.compile(rf"^\s*{_AFFIRM_WORD}(\W+{_AFFIRM_WORD})*(\W+(please|thanks|thank you|por favor|gracias))?"
                     r"[\s.!,]*$", re.IGNORECASE)
_SEND_COMMAND = re.compile(r"\b(send|submit) (it|that|this|the (note|request|tour request|repair request))\b|"
                           r"\bgo ahead( and send)?\b|\bplease send\b|\benv[ií]e?(lo|la)\b", re.IGNORECASE)
_NON_CONSENT = re.compile(r"\b(but|wait|don'?t|do not|not yet|hold on|change|wrong|instead|actually|later|never ?mind|"
                          r"cancel|no\b|pero|todav[ií]a|espera|cambi)", re.IGNORECASE)


def is_affirmative(message: str) -> bool:
    """Consent to send a READY card: the whole message is a yes/send phrase, or an explicit send command with no
    hedge ('yes but wait', 'ok wait, the room is wrong', 'ok thanks' alone are NOT consent)."""
    m = message.strip()
    if len(m) > 80 or _NON_CONSENT.search(m):
        return False
    if re.fullmatch(r"\s*(ok(ay)?|thanks|thank you|gracias)[\s.!,]*(thanks|thank you|gracias)?[\s.!,]*", m, re.I) \
            and re.search(r"thank|gracias", m, re.I):
        return False
    return bool(_AFFIRM.match(m) or _SEND_COMMAND.search(m))


def is_bare_yes(message: str) -> bool:
    return bool(re.fullmatch(r"\s*(yes|yep|yeah|ok(ay)?|sure|s[ií]|claro)[\s.!,]*(please|por favor)?[\s.!,]*",
                             message, re.I))


def is_bare_no(message: str) -> bool:
    return bool(re.fullmatch(r"\s*(no|nope|no thanks|no gracias)[\s.!,]*", message, re.I))


_CANCEL = re.compile(r"\b(never ?mind|nevermind|forget (it|about it)|cancel (it|that|this)|don'?t send( it)?|"
                     r"no need|not anymore|olv[ií]delo|no lo env[ií]e|cancel[ae]lo)\b|^\s*(cancel|stop|no)[\s.!]*$",
                     re.IGNORECASE)
_CORRECTION_LEAD = re.compile(r"^\s*(no+|nope|wait|oops|sorry|actually|correction|no wait|no,? actually)\b[\s,.!-]*",
                              re.IGNORECASE)


def is_decline(message: str) -> bool:
    """Cancel the open card. 'no wait, it's the bathroom' is a correction, not a decline."""
    if not _CANCEL.search(message):
        return False
    rest = _CANCEL.sub("", message)
    rest = re.sub(r"\b(please|thanks|it|that|the request|my neighbor fixed[\w\s']*|i fixed[\w\s']*|"
                  r"it'?s fixed|fixed it|all good now)\b", "", rest, flags=re.I)
    return len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest)) <= 6 and not re.search(r"\b(room|kitchen|bathroom|bedroom|"
                                                                         r"instead)\b", rest, re.I)


def strip_correction_lead(message: str) -> str:
    return _CORRECTION_LEAD.sub("", message, count=1)


_STAFF = re.compile(
    r"(talk|speak|chat) (to|with) (the |a |an |someone (at|in) the )?(office|leasing( team)?|staff|someone|somebody|"
    r"person|human|manager|agent|representative|rep|operator|salesperson|sales|leasing agent)|"
    r"send (a |the )?note to the office|contact (the )?(office|staff|leasing)|"
    r"^\W*(agent|representative|rep|operator|human|a human|person|real person|manager|supervisor)\W*(please|now|pls)?"
    r"\W*$|\b(get|give) me (a |an |the )?(human|person|manager|agent|representative)\b|(want|need) (a |an |to talk to "
    r"a |to speak to a )?(human|real person|manager|supervisor)\b|someone (can|could) (just )?(talk|call|explain)|"
    r"hablar con (la oficina|arrendamiento|alguien|una persona|un humano|un agente|el gerente|un representante)|"
    r"quiero (una persona|un humano|un agente)|enviar (una )?nota a la oficina|"
    r"nói chuyện với (nhân viên|người)|gặp (nhân viên|quản lý)", re.IGNORECASE)


def is_staff_request(message: str) -> bool:
    """Quick-action / plain request to reach the office (softer than 'real person, not a bot')."""
    return bool(_STAFF.search(message))


_SAYS_RESIDENT = re.compile(r"\bi (live|rent) (at|in|here)|i'?m a (current )?resident|vivo en", re.IGNORECASE)


def says_resident(message: str) -> bool:
    return bool(_SAYS_RESIDENT.search(message))


_TOUR = re.compile(r"\btours?\b|\bvisit\b|see (it|one|a place|an apartment|a unit|a \d|an? \w+ bed|the "
                   r"(place|apartment|unit|community|property))|come (by|see|look)|check (it|the place|the apartment) "
                   r"out|check out (the|a|an|your)|look at (the|a|an) (place|apartment|unit)|\bshow me\b|"
                   r"walk ?through|in person|visitar|recorrido|ver el apartamento", re.IGNORECASE)


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
_ENTRY_NO = re.compile(r"(don'?t|dont|do not|please don'?t|no,? (don'?t|do not)) (come in|enter|go in)|without me\b|"
                       r"(call|contact|text|message) (me )?(first|before)|only (when|if) i'?m (home|there)|"
                       r"i (want|need) to be "
                       r"(home|there)|no entr|llamen antes|av[ií]senme antes", re.IGNORECASE)


_ENTRY_WITH_NOTICE = re.compile(r"(can|may|ok to|okay to|fine to) (come in|enter|go in)\W+(?:\w+\W+){0,4}(but|after|"
                                r"if|as long as) (they |you )?(text|call|message|contact|let me know|tell)|"
                                r"(text|call|message) me (first|before)\W+(?:\w+\W+){0,3}(then|and) (they |you )?"
                                r"(can|may) (come in|enter)", re.IGNORECASE)


def extract_entry(message: str) -> str | None:
    if _ENTRY_WITH_NOTICE.search(message):
        return "May enter after contacting me first"
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


# ---- added after the independent review (see docs/UX_REVIEW.md) ---------------------------------------

_BOOKING_Q = re.compile(r"\b(am i|are we|is it|is that) (booked|confirmed|scheduled|set)|\bconfirm (the |that |my )?"
                        r"(time|slot|appointment|\d)|\bbook (me|it|a time)|\bis (\w+ ){0,3}(open|available)\b|"
                        r"\b(what|which) time (is|was) (my|the) tour|reserv(e|ation)|est[aá] confirmad", re.I)


def is_booking_question(message: str) -> bool:
    return bool(_BOOKING_Q.search(message))


_PHONE_Q = re.compile(r"phone number|number (for|of|to) the (office|leasing|maintenance)|office number|call the office|"
                      r"what'?s the number|n[uú]mero (de|del) (tel[eé]fono|la oficina)", re.I)


def is_phone_question(message: str) -> bool:
    return bool(_PHONE_Q.search(message))


_EVICTION = re.compile(r"kick (me|us) out|evict|lose my (home|apartment)|throw (me|us) out|desalojar|echarme", re.I)


def is_eviction_worry(message: str) -> bool:
    return bool(_EVICTION.search(message))


_CANCEL_SUBMITTED = re.compile(r"\bcancel\b.{0,30}\b(request|work order|repair|tour|note|appointment|DEMO-\w+-\d+)\b|"
                               r"\bDEMO-(WO|TOUR|TASK)-\d+\b.{0,20}\bcancel|cancel (it|that)\b.{0,40}(fixed|sent)",
                               re.I)


def is_cancel_submitted(message: str) -> bool:
    return bool(_CANCEL_SUBMITTED.search(message))


_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s?(am|pm|a\.m\.|p\.m\.)|\b(noon|midday|mediod[ií]a)\b", re.I)


def extract_clock_preference(message: str) -> tuple[str, str] | None:
    """('Afternoon', 'around 4 PM') from '4pm'. A preference only; never offered back as a booked slot."""
    m = _CLOCK.search(message)
    if not m:
        return None
    if m.group(4):
        return "Midday", "around noon"
    hour, minute, ampm = int(m.group(1)), m.group(2) or "00", m.group(3).lower().replace(".", "")
    h24 = hour % 12 + (12 if ampm.startswith("p") else 0)
    part = "Morning" if h24 < 12 else "Afternoon" if h24 < 17 else "Evening"
    label = f"{hour}{':' + minute if minute != '00' else ''} {'AM' if ampm.startswith('a') else 'PM'}"
    return part, f"around {label}"


_MOVE_IN = re.compile(r"\b(asap|as soon as possible|right away|soon|within (a|\d+|two|three|a few) (days?|weeks?|"
                      r"months?)|next (week|month)|this (week|month)|in (\d+|two|three|a few) (weeks?|months?)|"
                      r"by (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*( \d+)?|"
                      r"(in|for|starting) (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)\b", re.I)


def extract_move_in(message: str) -> str | None:
    m = _MOVE_IN.search(message)
    return m.group(0)[0].upper() + m.group(0)[1:] if m else None


_US_STATES = {"michigan": "Michigan", "florida": "Florida", "ohio": "Ohio", "indiana": "Indiana", "georgia": "Georgia",
              "texas": "Texas", "mi": "Michigan", "fl": "Florida"}
_FILLER = re.compile(r"\b(yes|yeah|yep|no|ok(ay)?|sure|please|pls|thanks|thank you|maybe|i think|probably|um+|uh+|"
                     r"hmm+|the|a|an|community|area|city|one|in|at|near|around|actually|instead|not|rather|"
                     r"i'?d like|i want|let'?s do|how about|what about|either|or|somewhere)\b", re.I)
_DAYWORDS = re.compile(r"\b(mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?|sun)(day)?s?\b|morning|afternoon|evening|"
                       r"weekend|weekday|today|tomorrow|week|month|bed|beds|studio|tour|visit", re.I)


def extract_area_correction(message: str) -> str | None:
    """'actually Orlando not Tampa', 'Orlando instead', 'make it Tampa', 'Orlando, FL', 'the Ann Arbor community'."""
    pats = [r"(?:actually|instead|rather|make it|change (?:it )?to|switch (?:it )?to|how about|what about)\s+"
            r"(?:the\s+)?"
            r"([A-Za-z][a-z]+(?: [A-Za-z][a-z]+){0,2})",
            r"([A-Za-z][a-z]+(?: [A-Za-z][a-z]+){0,2})\s*(?:,)?\s*(?:not|instead of|rather than)\s+[A-Za-z]",
            r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,2}),\s*(?:FL|MI|OH|IN|GA|TX|Florida|Michigan)\b",
            r"\bthe ([A-Z][a-z]+(?: [A-Z][a-z]+){0,2}) (?:community|property|apartments|location)\b",
            r"\b(?:to|in|near|around|at) ([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})\b"]
    for p in pats:
        for m in re.finditer(p, message):
            name = re.sub(r"\b(not|instead|please)\b.*$", "", m.group(1), flags=re.I).strip()
            if name and not _DAYWORDS.search(name) and name.split()[0].lower() not in {"the", "a", "my", "i"}:
                return name.title()
    return None


def bare_area_answer(message: str) -> str | None:
    """A short answer to 'which city or community?'. Filler and affirmations never become a place name."""
    if is_affirmative(message) or is_bare_no(message) or _DAYWORDS.search(message) or re.search(r"\d", message):
        return None
    words = _FILLER.sub(" ", message.strip().strip(".!?")).split()
    if not words or len(words) > 4 or any(not re.fullmatch(r"[A-Za-zÀ-ÿ'.-]+", w) for w in words):
        return None
    name = " ".join(words)
    return _US_STATES.get(name.lower(), name.title())
