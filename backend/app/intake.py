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
    r"mantenimiento|solicitud|estado|sí|usted|español|espanol|el|la|los|las|refrigerador|enfría|enfria|"
    r"funciona|lavaplatos|ba[ñn]era|ducha|calefacci[oó]n|aire|luz|puede|pueden|entrar|hay|muy|también)\b",
    re.IGNORECASE)


def detect_language(message: str, preferred: str | None = None) -> str:
    """'es' when the message reads as Spanish (>=2 marker words) or the record prefers Spanish and the
    message is not clearly English. Anything else is 'en'. Other languages fall back to 'en' + staff offer."""
    hits = len(_ES_WORDS.findall(message))
    if hits >= 2 or re.search(r"[¿¡ñ]", message) or re.search(r"\b(in|en) (spanish|espa[nñ]ol)\b|hablo espa", message,
                                                              re.I):
        return "es"
    if preferred and preferred.lower().startswith("span") and hits >= 1:
        return "es"
    if preferred and preferred.lower().startswith("span") and not re.search(
            r"\b(the|is|my|and|please|what|when|can|not|it|in|i|an|to|of|on|with|this|that|me|you|keeps?|"
            r"working|broken|hello|hi|thanks|hot|water|heat|door|detector|smoke|ac|leak\w*|again|need|help|yes|ok)\b",
            message, re.IGNORECASE):
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
    r"estado de mi|mi solicitud|cu[aá]ndo (vienen|viene|van a venir)|alguien viene|"
    r"^\W*(any )?(updates?|status|news)\W*\??\W*$|what (open )?(repairs?|requests?|work orders?) (do i have|are open)|"
    r"(any )?update on (my|the) (\w+ )?(thing|request|repair|issue)|"
    r"did (u|you) (save|get|send|submit) (that|it|my)|did (that|it) (save|get saved|send)|"
    r"did (my|the) [\w ]{0,20}(thing|request|repair|ticket|order|note) (even )?(go|get) (thru|through|sent|saved)",
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
    r"seniors? only|55\s?\+|over 55|without (kids|children|families)|"
    r"(pregnant|having a baby|have a baby|expecting|kids?|children|family|families)\W+(?:\w+\W+){0,8}(problem|"
    r"allowed|okay|ok|issue|welcome|matter)|(we'?re|we are|i'?m|i am) (muslim|christian|jewish|hindu|catholic|sikh|"
    r"buddhist|black|hispanic|latino|asian|gay|lesbian|trans\w*|immigrants?)|welcoming to (us|muslims|christians|"
    r"jews|families|immigrants)|section 8 (people|tenants)",
    re.IGNORECASE)


def is_steering_question(message: str) -> bool:
    return bool(_STEERING.search(message))


_AFFIRM_WORD = (r"(yes|yep|yeah|yup|sure|ok(ay)?|correct|right|that'?s (right|correct|it)|looks (good|right|"
                r"fine)|all good|perfect|send( it| all( of it)?| everything| it all| them| the (note|request))?( now)?|"
                r"submit( it)?|go ahead( and send( it)?)?|confirm(ed)?|please do|do it|"
                r"s[ií]|claro|correcto|env[ií]alo|de acuerdo|est[aá] bien|vale)")
_AFFIRM = re.compile(rf"^\s*{_AFFIRM_WORD}(\W+{_AFFIRM_WORD})*(\W+(please|thanks|thank you|por favor|gracias))?"
                     r"[\s.!,]*$", re.IGNORECASE)
# Explicit send phrases, anchored to the whole message ('Can I go ahead and paint my walls?' is not consent).
_SEND_COMMAND = re.compile(r"^\W*(please |ok(ay)?,? |yes,? |fine\.? )?(send|submit) (it|that|this|all( of it)?|"
                           r"everything|"
                           r"it all|them|the (note|request|tour request|repair request))( now)?( please)?\W*"
                           r"(and [^?]{0,40})?$|^\W*env[ií]e?(lo|la)\W*$", re.IGNORECASE)
_NON_CONSENT = re.compile(r"\?|\bto the\b|\b(not|but|wait|don'?t|do not|not yet|hold on|change|wrong|instead|actually|"
                          r"later|never ?mind|"
                          r"cancel|no\b|pero|todav[ií]a|espera|cambi)", re.IGNORECASE)


def is_affirmative(message: str) -> bool:
    """Consent to send a READY card: the whole message is a yes/send phrase, or an explicit send command with no
    hedge ('yes but wait', 'ok wait, the room is wrong', 'ok thanks' alone are NOT consent)."""
    m = message.strip()
    if len(m) > 80 or _NON_CONSENT.search(m):
        return False
    m = re.sub(r"^\W*fine\W+", "", m, flags=re.I)
    if re.fullmatch(r"\s*(ok(ay)?|thanks|thank you|gracias)[\s.!,]*(thanks|thank you|gracias)?[\s.!,]*", m, re.I) \
            and re.search(r"thank|gracias", m, re.I):
        return False
    return bool(_AFFIRM.match(m) or _SEND_COMMAND.search(m))


def is_bare_yes(message: str) -> bool:
    return bool(re.fullmatch(r"\s*(um+|uh+|hmm+|well)?[\s,.]*(i guess|i think( so)?|probably)?[\s,.]*(yes|yep|yeah|"
                             r"ok(ay)?|sure|s[ií]|claro|fine|i guess so|i think so)[\s.!,?]*(i guess|i think)?[\s.!,?]*"
                             r"(please|por favor)?[\s.!,?]*", message, re.I))


def is_bare_no(message: str) -> bool:
    return bool(re.fullmatch(r"\s*(no|nope|no thanks|no gracias)[\s.!,]*", message, re.I))


_CANCEL = re.compile(r"\b(never ?mind|nevermind|nvm|forget (it|about it|the (tour|request|note))|"
                     r"cancel (it|that|this)|don'?t send( it)?|not (right )?now|not yet|"
                     r"(don'?t|do not) want (a|the|to) (tour|visit|book|send)\w*|no (tour|visit)s? (now|yet|for now)|"
                     r"no need|not anymore|olv[ií]delo|no lo env[ií]e|cancel[ae]lo)\b|^\s*(cancel|stop|no)[\s.!]*$",
                     re.IGNORECASE)
_CORRECTION_LEAD = re.compile(r"^\s*(no+|nope|wait|oops|sorry|actually|correction|no wait|no,? actually)\b[\s,.!-]*",
                              re.IGNORECASE)


def is_decline(message: str) -> bool:
    """Cancel the open card. 'no wait, it's the bathroom' is a correction; 'no need to call first, you can enter' is
    an answer."""
    if not _CANCEL.search(message) or extract_entry(message) or extract_location(message):
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
    r"can (someone|somebody|you) (just )?(text|call|email|contact) me|can (someone|somebody) (just )?(talk|speak|call|"
    r"explain|help)|\bescalate\b|"
    r"(get|find|bring) me (the |a |my |your )?(property |community |building |site |general )?manager|"
    r"(talk|speak|chat) (to|with) (the |a |my |your )?(property|community|building|site|general) manager|"
    r"(speak|talk) (to|with) whoever(?:'s| is)? in charge|(flag|send|pass|escalate) (it|this|that) (to|for) (the )?"
    r"(property )?manager|(want|need) (a |to talk to a |to speak to a )?(salesperson|sales person|sales rep|"
    r"leasing agent)|^\W*(sales(person)?|leasing agent|leasing)\W*(please|now|pls)?\W*$|"
    r"who (do|should|can) i (talk|speak) to|who do i (call|contact|ask)|"
    r"(want|make sure|need) (the |my )?(property )?manager (to )?(know|see|hear)|(tell|let) the (property )?manager|"
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
    if wants_to_rent(message):
        return True
    return _is_tour_request(message)


def _is_tour_request(message: str) -> bool:
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
    ("Front door", r"front door|entry door|entrance door|puerta principal"),
    ("Outside or common area", r"hallway|parking lot|stairwell|common area|pasillo|estacionamiento"),
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


_ENTRY_YES = re.compile(r"\b(yes|ok|okay|sure|si|sí)\b\W+(?:\w+\W+){0,2}(enter|come in|go in)\b|"
                        r"(yes|ok|okay|fine|sure)[, ]*(you |they |maintenance |the tech\w* )?(can|may) (come in|"
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
    r"crack|flicker|fell off|clog|overflow|toliet|lock|leak|drip|broken|not working|won'?t|doesn'?t|stopped|clog|no"
    r" (heat|hot water|water|power|ac|a/c)|noise|"
    r"rattl|smell|mold|pest|roach|ant|mouse|mice|bug|crack|stuck|loose|running|cooling|heating|knock|bang|grind|"
    r"squeak|buzz|humm|clank|"
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
    rf"\b(this|next) (week|weekend|{_DAYS})\b|\b(tomorrow|today|this afternoon|tonight|weekends?|weekdays?|"
    rf"any ?day|anytime this week)\b|\b(?:on |this |next )?(?:{_DAYS})s?\b|\b(lunes|martes|mi[ée]rcoles|"
    rf"jueves|viernes|s[áa]bado|domingo|ma[ñn]ana)\b", re.IGNORECASE)
_TIME_OF_DAY = re.compile(r"\b(morning|mornings|afternoon|afternoons|evening|evenings|after work|lunch ?time|"
                          r"before work|ma[ñn]ana|tarde|noche)\b", re.IGNORECASE)
_BEDS = re.compile(r"\b(\d|one|two|three|four|dos|tres|una?)\s?-?\s?(?:bed|br|bedroom|rec[aá]mara|habitaci[oó]n|"
                   r"habitaciones|cuarto|dormitorio)s?\b|\bstudio\b", re.IGNORECASE)
_WORDNUM = {"one": "1", "two": "2", "three": "3", "four": "4", "un": "1", "una": "1", "dos": "2", "tres": "3"}
_AREA = re.compile(r"\b(?:in|near|around|at) ((?:[A-Z][a-z]+)(?: [A-Z][a-z]+){0,2})")
_NOT_AREA = {"The", "My", "A", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
             "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December", "I"}


_ES_MORNING = re.compile(r"\b(por|en|de) la ma[ñn]ana\b", re.I)


def extract_days(message: str) -> str | None:
    found = [m.group(0).strip() for m in _DAY_PHRASE.finditer(_ES_MORNING.sub(" ", message))]
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

_BOOKING_Q = re.compile(r"\b(am i|are we|is it|is that) (booked|confirmed|scheduled|set)|\b(i'?m|we'?re|i am|we are) "
                        r"(booked|confirmed|scheduled|all set)|(what|which) time (do|should|can) (i|we) (show up|come|"
                        r"arrive|be there)|\bshow up\b|\bconfirm (the |that |my )?"
                        r"(time|slot|appointment|\d)|\bbook (me|it|a time)|\bis (\w+ ){0,3}(open|available)\b|"
                        r"\b(what|which) time (is|was) (my|the) tour|reserv(e|ation)|est[aá] confirmad", re.I)


def is_booking_question(message: str) -> bool:
    return bool(_BOOKING_Q.search(message))


_PHONE_Q = re.compile(r"phone number|emergency (maintenance )?(number|line|phone)|number (for|of|to) the (office|"
                      r"leasing|"
                      r"maintenance)|office number|call the office|"
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
        b = re.search(r"\b(?:around|at|about|by|after|before)\s(\d{1,2})(?::(\d{2}))?\b(?!\s?(?:%|\$|bed|br|days?|"
                      r"weeks?|"
                      r"months?|years?|people|units?|inch))|\b(\d{1,2})\s?ish\b", message, re.I)
        if not b:
            return None
        hour = int(b.group(1) or b.group(3))
        if not 1 <= hour <= 12:
            return None
        ampm = "am" if 8 <= hour <= 11 else "pm"
        h24 = hour % 12 + (12 if ampm == "pm" else 0)
        part = "Morning" if h24 < 12 else "Afternoon" if h24 < 17 else "Evening"
        return part, f"around {hour}{':' + b.group(2) if b.group(2) else ''} {ampm.upper()}"
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


_MONTH_DAY = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|"
                        r"th)?\b|"
                        r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", re.I)
_MOVE_CONTEXT = re.compile(r"\bmov(e|ing)\b|move-?in|lease start|start(ing)? (the|my) lease|mudar|mudanza|"
                           r"\b(make|change) (it|that)\b|\bactually\b|\binstead\b", re.I)


def extract_move_in(message: str) -> str | None:
    """Move-in timing. The LAST date in the message wins ('March 1, no wait, May 1' -> 'May 1'). Week-only phrases
    ('this week') count only when the person talks about moving, so a tour day isn't saved as a move-in date."""
    found = [m for m in _MONTH_DAY.finditer(message)]
    move = bool(_MOVE_CONTEXT.search(message))
    if not found:
        found = [m for m in _MOVE_IN.finditer(message)
                 if move or not re.match(r"(this|next) (week|month)|in (\d+|two|three|a few) weeks?", m.group(0), re.I)]
    if not found:
        return None
    v = found[-1].group(0)
    return v[0].upper() + v[1:]


_US_STATES = {"michigan": "Michigan", "florida": "Florida", "ohio": "Ohio", "indiana": "Indiana", "georgia": "Georgia",
              "texas": "Texas", "mi": "Michigan", "fl": "Florida"}
_FILLER = re.compile(r"\b(yes|yeah|yep|no|ok(ay)?|sure|please|pls|thanks|thank you|maybe|i think|probably|um+|uh+|"
                     r"hmm+|the|a|an|community|area|city|one|in|at|near|around|actually|instead|not|rather|"
                     r"i'?d like|i want|let'?s do|how about|what about|either|or|somewhere)\b", re.I)
_DAYWORDS = re.compile(r"\b(mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?|sun)(day)?s?\b|morning|afternoon|evening|"
                       r"weekend|weekday|today|tomorrow|week|month|bed|beds|studio|tour|visit", re.I)


_NOT_PLACE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*$|^(spanish|english|espa[nñ]ol|ingl[eé]s|utilities|"
    r"parking|pets?|fees?|rent|price|budget|section|voucher|church|school|work|town|downtown|person|someone|"
    r"something|need|soon|maybe|weekend|weekdays?|morning|afternoon|evening|tour|visit|apartment|unit|place|"
    r"home|house|lease|month|year|week|bed|beds|studio|monday|tuesday|wednesday|thursday|friday|saturday|"
    r"sunday|today|tomorrow|tonight|i|the|a|my|hola|hello|hi|hey|gracias|thanks|buenas|buenos|ok|okay|yes|no)$", re.I)


def _place(name: str | None) -> str | None:
    if not name:
        return None
    name = re.sub(r"\s+(i guess|i think|maybe|please|probably|instead|area)$", "", name.strip(), flags=re.I)
    words = name.split()
    if not words or len(words) > 3 or any(_NOT_PLACE.match(w) for w in words):
        return None
    return _US_STATES.get(name.lower(), " ".join(w[0].upper() + w[1:] for w in words))


# Demo communities in the synthetic workbook (D-01). Recognised anywhere in a message, any capitalisation.
_COMMUNITIES = [("Heron Lake Apartments", r"heron ?lake"), ("Birchwood Commons", r"birch ?wood"),
                ("Sandpiper Pointe", r"sand ?piper"), ("Fernhill Apartments", r"fern ?hill")]


def community_in(message: str) -> str | None:
    for name, pat in _COMMUNITIES:
        if re.search(rf"\b{pat}\b", message, re.I):
            return name
    return None


def extract_area_correction(message: str) -> str | None:
    """Capitalised place names only: 'actually Orlando not Tampa', 'Orlando instead', 'Orlando, FL', 'Ann Arbor, 2
    bed', 'the Ann Arbor community', 'in Lansing', 'en Orlando'. Months, languages and common nouns never count."""
    cap = r"([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})"
    pats = [rf"(?i:actually|instead|rather|make it|change (?:it )?to|switch (?:it )?to|how about|what about)\s+"
            rf"(?:the\s+)?{cap}\b",
            rf"\b{cap}\s*,?\s*(?i:not|instead of|rather than)\s+[A-Za-z]",
            rf"\b{cap},\s*(?:FL|MI|OH|IN|GA|TX|Florida|Michigan)\b",
            rf"^\s*{cap}\s*,",
            rf"\bthe {cap} (?i:community|property|apartments|location)\b",
            rf"\b(?i:to|in|near|around|at|en|cerca de) {cap}\b",
            rf"^\s*{cap}\s*[.!]?\s*$"]
    for p in pats:
        for m in re.finditer(p, message):
            if place := _place(m.group(1)):
                return place
    return None


def bare_area_answer(message: str) -> str | None:
    """A short answer to 'which city or community?' ('tampa please', 'ann arbor'). Filler never becomes a place."""
    if is_affirmative(message) or is_bare_no(message) or _DAYWORDS.search(message) or re.search(r"\d", message):
        return None
    if re.search(r"\b(need|want|something|soon|not sure|idk|dunno|anywhere|somewhere|help|speak|looking|guess)\b",
                 message, re.I):
        return None
    words = _FILLER.sub(" ", message.strip().strip(".!?")).split()
    if not words or len(words) > 3 or any(not re.fullmatch(r"[A-Za-zÀ-ÿ'.-]+", w) for w in words):
        return None
    return _place(" ".join(words))


def steering_kind(message: str) -> str:
    """Which neutral reply fits: safety of an area, family status, or a general 'who lives there' question."""
    if re.search(r"\b(safe|dangerous|sketchy|crime)\b", message, re.I):
        return "steering_safety"
    if re.search(r"pregnan|baby|expecting|kids?|children|famil", message, re.I) and not re.search(
            r"fewe|most|many|lots|no kids|kid[- ]free|without", message, re.I):
        return "steering_family"
    return "steering"


_SPANISH_HELP = re.compile(r"\b(in|en) (spanish|espa[nñ]ol)\b|hablo espa[nñ]ol|habla espa[nñ]ol|speak spanish", re.I)


def asks_for_spanish(message: str) -> bool:
    return bool(_SPANISH_HELP.search(message))


_PROMISE = re.compile(r"\bpromise\b|guarantee|\bby (mon|tues|wednes|thurs|fri|satur|sun)day\b|in writing|\b(rent"
                      r" )?credit\b|"
                      r"compensat|reimburs|refund|money back|discount on (my )?rent|prom[eé]tame|garant", re.I)


def asks_for_promise(message: str) -> bool:
    """Demands for a date, a credit or a written commitment: the assistant can't decide these."""
    return bool(_PROMISE.search(message))


_NOISE = re.compile(r"\b(noise|noisy|loud|music|party|parties|barking|stomping)\b|upstairs (neighbor|guy)|ruido|"
                    r"m[uú]sica alta", re.I)


_NEIGHBOR = re.compile(r"neighbou?r|upstairs|downstairs|next door|music|party|parties|bark|dog|stomp|\btv\b|"
                       r"yell|scream|people|vecino|m[uú]sica", re.I)
_BUILDING_NOISE = re.compile(r"\b(fan|ac|a/c|air ?condition\w*|heater|furnace|fridge|refrigerator|dishwasher|disposal|"
                             r"pipes?|wall|ceiling|vent|duct|toilet|water heater|washer|dryer|motor|rattl\w*|grind\w*|"
                             r"knock\w*|hum+ing|buzz\w*|squeal\w*|squeak\w*|clank\w*|bang\w* (?:in|from) the|"
                             r"compressor|thermostat|smoke detector|alarm)\b", re.I)


def is_noise_complaint(message: str) -> bool:
    """Noise between neighbours. Fan, AC, pipe or wall noise is a repair (maintenance), unless a neighbour is named."""
    if not _NOISE.search(message) and not re.search(r"\bknock\w*\b", message, re.I):
        return False
    if _BUILDING_NOISE.search(message) and not _NEIGHBOR.search(message):
        return False
    return bool(_NOISE.search(message))


_PETS = re.compile(r"\b(i have|we have|with|plus|got) (a |an |one |two |three |\d )?(big |small |little )?(dogs?|cats?|"
                   r"pets?|puppy|kitten)\b", re.I)


def extract_pets(message: str) -> str | None:
    m = _PETS.search(message)
    return m.group(0)[0].upper() + m.group(0)[1:] if m else None


def is_issue_description(message: str) -> bool:
    return bool(_ISSUE_HINT.search(message))


def frustration_only(message: str) -> bool:
    """Venting with no new repair detail ('are you even listening', 'why do i have to keep telling you')."""
    return bool(re.search(r"are you (even )?listening|keep telling|why do i (have|need) to|ugh+|seriously\??$|"
                          r"hello\?+$|anyone there", message, re.I)) and not _ISSUE_HINT.search(message)


# ---- sprint 2: corrections, preferences, follow-ups, policy questions, unsafe do-it-yourself ----------------

_ISSUE_SWAP = re.compile(
    r"(?:^|\b)(?:it'?s|its|it is|that'?s) not (?:the |my |a )?(?P<old>[\w /-]{2,30}?)[,.;!-]+\s*(?:it'?s|its|it is|"
    r"it'?s actually|the problem is)?\s*(?:the |my |a )?(?P<new>[^.?!]{3,})|"
    r"^\W*(?:wait|no|actually|sorry|oops)\W+(?:it'?s|its|it is)? ?not (?:the |my )?(?P<old2>[\w /-]{2,30}?)\W+"
    r"(?:it'?s |its |it is )?(?:the |my )?(?P<new2>[^.?!]{3,})", re.I)


def extract_issue_swap(message: str) -> str | None:
    """'wait, it's not the AC, it's the bathroom fan' -> 'bathroom fan' (replaces the issue, never appends)."""
    m = _ISSUE_SWAP.search(message)
    if not m:
        return None
    new = (m.group("new") or m.group("new2") or "").strip(" ,.;")
    old = (m.group("old") or m.group("old2") or "").strip()
    rooms = r"(kitchen|bath ?room|bedroom|living room|hallway|hall|closet|laundry|garage|balcony|dining room)"
    if re.fullmatch(rooms, old, re.I) or re.fullmatch(rooms, new, re.I):
        return None  # "not the kitchen, it's the bedroom ceiling" is a location correction
    if not new or re.fullmatch(r"(kitchen|bathroom|bedroom|living room|hallway)", new, re.I):
        return None  # a room swap is a location correction
    return new[0].upper() + new[1:]


_LOC_CHANGE = re.compile(r"\bchange (?:the )?(?:location|room|place|where it is|spot) to (?:the |my"
                         r" )?(?P<loc>[^.?!,]{3,40})|"
                         r"\b(?:it'?s|its|it is) (?:actually )?in (?:the |my )(?P<loc2>[^.?!,]{3,30})", re.I)


def extract_location_change(message: str) -> str | None:
    m = _LOC_CHANGE.search(message)
    if not m:
        return None
    loc = (m.group("loc") or m.group("loc2") or "").strip()
    return loc[0].upper() + loc[1:] if loc else None


_CONTACT_PREF = re.compile(
    r"\b(?:only|just) (?:text|call|email)(?:ing)? me\b[^.?!]{0,30}|\btext(?:s)? only\b[^.?!]{0,30}|"
    r"\b(?:pls |please )?(?:stop|don'?t|dont|do not|no) call(?:ing|s)? me\b[^.?!]{0,30}|"
    r"\bchange my (?:contact|phone|preference)\w*[^.?!]{0,30}|\b(?:text|email|call) me instead\b[^.?!]{0,20}|"
    r"\bno calls? (?:before|after) \d{1,2}[^.?!]{0,10}|\bonly (?:after|before) \d{1,2} ?(?:am|pm)?\b|"
    r"\bsolo (?:mensajes?|textos?)\b[^.?!]{0,30}|\bno me llamen\b[^.?!]{0,30}", re.I)


def extract_contact_pref(message: str) -> str | None:
    """A contact preference the person states ('only text me after 6pm'). Recorded as 'you said', never applied to
    the account here (no integration)."""
    m = _CONTACT_PREF.search(message)
    if not m:
        return None
    v = m.group(0).strip(" ,.;")
    return v[0].upper() + v[1:]


_AFTER_SEND_Q = re.compile(
    r"\bwhen (?:will|are|is|do|does) (?:they|someone|somebody|anyone|the (?:office|team|tech|leasing team)|a tech|"
    r"maintenance|leasing)\b[^.?!]{0,30}(?:call|text|email|come|contact|get back|reach|fix|be here|respond)|"
    r"\bdid (?:someone|anyone|anybody|they|the office|the team|the manager|leasing|maintenance) (?:get|see|receive|"
    r"read|"
    r"confirm|look at)|\b(?:is|so) (?:a tech|someone|somebody|maintenance|the tech) (?:coming|on the way)|"
    r"\bso (?:tomorrow|today|tonight|this)(?: morning| afternoon| evening| week)?(?: then| right)?\W*$|"
    r"\bso (?:a tech|someone|the manager|they) (?:is|are|will|knows?)|\bdoes the manager know|"
    r"\bis it (?:fixed|done|scheduled|booked|confirmed) (?:now|yet)?|\bdid (?:someone|anyone) confirm my tour|"
    r"\b(?:tell me|i need to know) when\b|\bwhat happens next\b|\bwhat'?s next\b|\bnow what\b", re.I)


def is_after_send_question(message: str) -> bool:
    """A question about what happens to something already sent ('when will they call me?', 'so a tech is coming?')."""
    return bool(_AFTER_SEND_Q.search(message))


_POLICY_TOPICS = [
    ("guests", r"\bguests?\b|visitors?|overnight|stay with me"),
    ("packages", r"\bpackages?\b|deliver(y|ies)|parcel|amazon|mail ?room"),
    ("trash and recycling", r"\btrash\b|garbage (pick ?up|day|room|chute)|recycl\w*|dumpster|bulk (item|pickup)"),
    ("quiet hours", r"quiet hours|noise (rule|policy|hours)"),
    ("parking", r"\bpark(ing)?\b|garage spot|guest spot|tow\w*"),
    ("pets", r"\bpets?\b|\bdogs?\b|\bcats?\b|pet (fee|rent|deposit)"),
    ("amenities", r"\bpool\b|\bgym\b|fitness|clubhouse|amenit\w*"),
    ("smoking", r"\bsmok(e|ing)\b|\bvap(e|ing)\b"),
    ("grills", r"\bgrills?\b|\bbbq\b|barbecue"),
    ("subletting", r"sublet|sub-?lease|airbnb|roommate (add|change)|add (a )?roommate"),
    ("rent payment", r"rent (is )?due|pay (my )?rent|late fee|payment portal|when is rent"),
    ("lease terms", r"month[- ]to[- ]month|lease (term|length|options)|shorter lease|break (my|the) lease"),
    ("deposits and fees", r"\bdeposit\b|application fee|admin fee|\bfees?\b"),
    ("move-in specials", r"specials?|concessions?|months? free|promo\w*|discount"),
]
_QUESTIONISH = re.compile(r"\?|^\W*(what|when|where|how|can|is|are|do|does|may|any|whats|wheres|hows)\b|"
                          r"\b(policy|policies|rules?|allowed|allow)\b", re.I)


def policy_topic(message: str) -> str | None:
    """The community-policy topic of a question, if any ('where do packages go' -> 'packages')."""
    if not _QUESTIONISH.search(message.strip()) and len(message.split()) > 3:
        return None
    for name, pat in _POLICY_TOPICS:
        if re.search(pat, message, re.I):
            return name
    return None


_PRICE_CLAIM = re.compile(
    r"(website|site|ad|listing|zillow|apartments\.com|your (page|flyer)|online|you (guys )?(said|advertise|listed|"
    r"posted))\W+(?:\w+\W+){0,8}(\$\s?\d|\d+ (weeks?|months?) free|special|discount)|"
    r"(lock|hold|honou?r|guarantee) (in )?(that|the|this|a|my)? ?(price|rate|special|\$\s?\d+)|"
    r"(\$\s?\d[\d,]*|\d+ (weeks?|months?) free)[^.?!]{0,40}\b(right|correct|yes)\s*\?", re.I)


def states_price_claim(message: str) -> bool:
    """The person asserts a price/special or asks to lock one in (the assistant must not agree or confirm)."""
    return bool(_PRICE_CLAIM.search(message))


_UNSAFE_DIY = [
    ("breaker", r"\b(tape|tie|zip ?tie|hold|wedge|jam)\b[^.?!]{0,25}\bbreaker|\bbreaker\b[^.?!]{0,40}\b(tape|tie|"
                r"stays? on|keep it on|hold it)"),
    ("disposal", r"\b(hand|fingers?|reach|arm)\b[^.?!]{0,20}\b(in|into|down)\b[^.?!]{0,15}\b(disposal|garbage "
                 r"disposal)|\b(disposal)\b[^.?!]{0,40}\b(stick|put|reach) (my )?(hand|fingers?)"),
    ("wiring", r"which wires? (go|goes)|swap\w* (the |an |my )?(outlet|switch|light fixture)|rewir\w*|"
               r"(replace|fix|change) (the |an |my )?(outlet|switch|wiring|breaker|panel) (myself|my ?self)|"
               r"(open|take apart) (the )?(electrical )?panel"),
    ("space_heater", r"space heater[^.?!]{0,50}\b(bath\w*|shower|tub)|\b(bath\w*|shower|tub)\b[^.?!]{0,50}"
                     r"space heater"),
    ("detector_battery", r"\b(take|pull|remove|rip|disconnect|unplug)\b[^.?!]{0,20}\b(the )?(batter\w*|detector|"
                         r"alarm)\b[^.?!]{0,40}\b(smoke|co|carbon)|(smoke|co|carbon monoxide) (detector|alarm)"
                         r"[^.?!]{0,80}\b(take|pull|remove|rip|disconnect|unplug)\b[^.?!]{0,15}\b(batter\w*|it "
                         r"(out|off|down))"),
    ("gas_diy", r"(relight|light|fix|tighten) (the )?(pilot|gas (line|valve|leak|pipe))[^.?!]{0,20}(myself|my ?self)?|"
                r"fix (the )?gas"),
]


def unsafe_diy_kind(message: str) -> str | None:
    """A do-it-yourself step that could hurt someone (taping a breaker, hand in the disposal, rewiring...)."""
    for kind, pat in _UNSAFE_DIY:
        if re.search(pat, message, re.I):
            return kind
    return None


_TOUR_INTENT = re.compile(r"\b(want|wanna|would like|like) (to )?see (the |an? |your )?(apartments?|place|units?|"
                          r"homes?)|\bi want see\b|\blook(?:ing)? for (an? |some )?(apartment|place|unit|home|\d"
                          r" ?(bed|br|"
                          r"room))\w*|\b(apartment|place) for rent\b|\brent (an? )?(apartment|place)\b|"
                          r"\b(need|want) (an? )?(apartment|place to live|\d ?(bed|br)\w*)|\bdo you (guys )?have (any"
                          r" )?(places|"
                          r"apartments|units|communities|properties|anything) (in|near|around)\b|"
                          r"\bbusco (un |una )?(apartamento|departamento|lugar|casa)|\bquiero (ver|rentar) (un |una"
                          r" )?(apartamento|departamento|casa)",
                          re.I)


def wants_to_rent(message: str) -> bool:
    return bool(_TOUR_INTENT.search(message))


_APPLIANCE = re.compile(r"\b(dishwasher|fridge|refrigerator|freezer|oven|stove|range|microwave|washer|dryer|"
                        r"disposal|garbage disposal|ice maker|water heater|furnace|ac|a/c|heater|thermostat|fan|"
                        r"toilet|sink|faucet|tap|shower|tub|outlet|light|blinds|closet door|door|window|lock)\b", re.I)


def appliance_in(message: str) -> str | None:
    m = _APPLIANCE.search(message)
    return m.group(0) if m else None
