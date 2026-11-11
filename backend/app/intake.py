"""Deterministic slot extraction and request detectors for the customer workflows (F2, F3, F4, F5, F6, F8).

Everything here is regex over the already-redacted message. Nothing calls a model, nothing has side effects.
Patterns are TEAM DRAFTS: the lists McKinley must approve (I-06 opt-out keywords, I-13 fair-housing topics,
I-15 tour questions, I-19 intake fields) are marked as such in docs/workflows/traceability.md.
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
    r"reportar|reparaci[oó]n|solicitudes|una|oficina|ver|env[ií]elo|"
    r"agua|luz|renta|contrato|cuándo|cuando|quiero|hablar|persona|apartamento|horno|fuga|gotea|olor|"
    r"mantenimiento|solicitud|estado|sí|usted|español|espanol|el|la|los|las|refrigerador|enfría|enfria|"
    r"funciona|lavaplatos|ba[ñn]era|ducha|calefacci[oó]n|aire|luz|puede|pueden|entrar|hay|muy|también|"
    # Sprint 7: prospects' Spanish ("busco un apartamento de 1 recámara", "me gustaría visitar ... el sábado")
    r"busco|buscando|interesa|rec[aá]maras?|departamento|gustar[ií]a|visitar|visita|recorrido|barato|rentar|"
    r"cu[aá]nto|cuesta|precio|mascotas|dep[oó]sito|d[oó]nde|ubicados|s[aá]bado|domingo|lunes|martes|mi[eé]rcoles|"
    r"jueves|viernes|tarde|noche|un|una|de|del|con|para|que|es|agendar|disponibles?|lugar|pr[oó]ximo|mes|ba[ñn]os)\b",
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
            r"working|broken|hello|hi|thanks|hot|water|heat|door|detector|smoke|ac|leak\w*|again|need|help|yes|ok|"
            r"kitchen|bathroom|bedroom|sink|tap|faucet|toilet|drip\w*|fridge|light|window|floor|wall|ceiling|noise|"
            r"update|status|repair|any|thing)\b",
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
    r"\bstatus\b|estado de (?:mi|mis|la)|ver mis (?:solicitudes|reparaciones|pedidos)|mis solicitudes|"
    r"(any )?(update|news) (on|about|with) (my|the)|where (is|are) (my|the) (request|repair|"
    r"work order|ticket)|(check|see|look up) (on )?(my )?(open )?(requests?|work orders?|tickets?|repairs?)|"
    r"\bmy (open )?(requests?|work orders?|tickets?|repairs?)\b|when (is|will|are) (maintenance|someone|anyone|"
    r"they|a tech\w*|the tech\w*|somebody) (coming|come|going to come|gonna come|be here|fix)|"
    r"(is|are) (a tech\w*|someone|anyone|maintenance|they) (coming|on (the|their) way)|has anyone (looked|been)|"
    r"did (that|it|my request) go (thru|through)|what'?s (going on|happening) with (my|the)|nobody (came|showed)|"
    r"estado de mi|mi solicitud|cu[aá]ndo (vienen|viene|van a venir)|alguien viene|"
    r"^\W*(any )?(updates?|status|news)\W*\??\W*$|what (open )?(repairs?|requests?|work orders?) (do i have|are open)|"
    r"(any )?update on (my|the) (\w+ )?(thing|request|repair|issue)|^\W*(ok|so|and)?\W*any (updates?|news) on "
    r"(it|that|this)\b|"
    r"did (u|you) (save|get|send|submit) (that|it|my)|did (that|it) (save|get saved|send)|"
    r"did (my|the) [\w ]{0,20}(thing|request|repair|ticket|order|note) (even )?(go|get) (thru|through|sent|saved)",
    re.IGNORECASE)


_STATUS2 = re.compile(
    r"\bwhen (?:they'?ll|they will|someone'?ll|will they) (?:come|be here|fix|show up)|\bwhen (?:is|will) (?:it|"
    r"this|that) "
    r"(?:be )?(?:fixed|done|repaired)|\b(?:my|the) (?:old|past|previous|earlier) (?:requests?|repairs?|work orders?)|"
    r"\bdo you have my (?:requests?|history|old requests?)|\bcu[aá]ndo vienen\b", re.I)


def is_status_request(message: str) -> bool:
    return bool(_STATUS.search(message)) or bool(_STATUS2.search(message))


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


# Sprint 6 (judge H-5): a plain yes to "may they enter?" said a little more fully ("ok yes", "yes go ahead",
# "yeah that's fine"). Only used when the entry question is the one being answered.
_ENTRY_PLAIN_YES = re.compile(
    r"\s*(?:ok(?:ay)?|sure|yeah|yep|yes|fine)?[\s,.!]*(?:yes|yeah|yep|sure)[\s,.!]*(?:go ahead|that'?s fine|thats fine|"
    r"that works|they can|you can|of course|no problem|please)?[\s,.!]*|\s*(?:yes|yeah|yep|sure|ok(?:ay)?)?[\s,.!]*"
    r"(?:go ahead|that'?s fine|thats fine|that works|no problem)[\s,.!]*", re.I)


def is_entry_plain_yes(message: str) -> bool:
    return bool(_ENTRY_PLAIN_YES.fullmatch(message))


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
    r"(?:want|need|like|have|get) (?:someone|somebody|a person|an agent|a human|a real person|leasing|the office|"
    r"the manager|a manager|staff) to (?:call|text|email|contact|reach|phone) me|\bcall me back\b|"
    r"have (?:someone|somebody) (?:call|text|email|contact) me|\bask the office\b|preguntar a la oficina|"
    r"\b(?:send|submit) (?:my|the|a|that|this) note\b|\bsend (?:that|it|this) to (?:whoever|the office|someone|a "
    r"person|staff)|env[ií]e la nota|"
    r"quiero que (?:alguien|una persona) me (?:llame|"
    r"contacte)|"
    r"^\W*(agent|representative|rep|operator|human|a human|person|real person|manager|supervisor)\W*(please|now|pls)?"
    r"\W*$|\b(get|give) me (a |an |the )?(human|person|manager|agent|representative)\b|(want|need) (a |an |to talk to "
    r"a |to speak to a )?(human|real person|manager|supervisor)\b|someone (can|could) (just )?(talk|call|explain)|"
    r"can (someone|somebody|you) (just )?(text|call|email|contact) me|can (someone|somebody) (just )?(talk|speak|call|"
    r"explain|help)|\bescalate\b|"
    r"(get|find|bring) me (the |a |my |your )?(property |community |building |site |general )?manager|"
    r"(get|give|find) me (a |an |the )?(real |actual |live )?(human|person|agent|representative|rep|salesperson|"
    r"sales ?person|someone|somebody)\b|"
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
    return bool(_STAFF.search(message)) or asks_for_person(message)


_SAYS_RESIDENT = re.compile(r"\bi (live|rent) (at|in|here)|i'?m a (current )?resident|vivo en", re.IGNORECASE)


def says_resident(message: str) -> bool:
    return bool(_SAYS_RESIDENT.search(message))


_TOUR = re.compile(r"\btours?\b|\bvisit\b|see (it|one|a place|an apartment|a unit|a \d|an? \w+ bed|the "
                   r"(place|apartment|unit|community|property))|come (by|see|look)|check (it|the place|the apartment) "
                   r"out|check out (the|a|an|your)|look at (the|a|an) (place|apartment|unit)|\bshow me\b|"
                   r"walk ?through|in person|visitar|recorrido|ver el apartamento", re.IGNORECASE)


_NO_TOUR = re.compile(r"\bno tours?\b|(?:don'?t|do not|dont|doesn'?t) (?:want|need)(?: \w+)? (?:a |to )?(?:tour|visit)|"
                      r"\bnot (?:ready )?(?:for |to )?(?:a |do a |book a )?(?:tour|visit)|without (?:a )?tour|(?:skip|"
                      r"forget) the tour|no (?:quiero|necesito) (?:una )?visita|sin visita|"
                      # Sprint 7 final round: "no visit please", "still not looking to visit"
                      r"\bno (?:visits?|viewings?|showings?)\b|"
                      r"\bnot (?:looking|wanting|planning|trying|going) to (?:visit|"
                      r"tour|come see|come by)\b|\bno quiero (?:visitar|ir a ver)\b", re.I)


def refuses_tour(message: str) -> bool:
    return bool(_NO_TOUR.search(message))


# Claims that something was already decided ("the manager said the fee is waived", "you approved my reduction").
_PREMISE = re.compile(
    r"\b(?:you|the (?:manager|office|leasing (?:office|agent)|landlord|staff)|someone|they|he|she|management)\b"
    r"(?:\W+\w+){0,3}\W+(?:already )?(?:said|told me|agreed|approved|promised|confirmed|waived|okayed|ok'?d|"
    r"authori[sz]ed|guaranteed)\b[^.?!]{0,80}\b(?:fee|fees|rent|reduction|credit|lease|penalty|waive\w*|refund|"
    r"discount|deposit|scheduled|appointment|work order|free|break)|\b(?:confirm|verify) (?:that )?(?:it|this|my|the)"
    r"\b[^.?!]{0,40}\b(?:waived|approved|scheduled|free|reduced|credited)", re.I)


def claims_prior_decision(message: str) -> bool:
    return bool(_PREMISE.search(message))


def is_tour_request(message: str) -> bool:
    if refuses_tour(message):
        return False
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
    ("Dining room", r"dining (?:room|area)|comedor"),
    ("Laundry area", r"laundry|washer|dryer|washing machine|lavadora|secadora"),
    ("Balcony or patio", r"balcony|patio|balc[oó]n"),
    ("Whole apartment", r"whole (apartment|unit|place)|everywhere|all rooms|entire (apartment|unit)|todo el"),
    ("Front door", r"front door|entry door|entrance door|puerta principal"),
    # D-7: a hallway in the person's own home is in the apartment, not a common area
    ("Hallway", r"(?:my|our) hall(?:way)?|hall(?:way)? (?:is )?(?:in|inside) (?:my|our|the) (?:apartment|unit|place)|"
                r"(?:mi|nuestro) pasillo"),
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
    ("Heating / cooling system", r"aire acondicionado|calefacci[oó]n|termostato"),
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
                        r"(fine|ok|okay|alright|all right) (for them |for you )?to (enter|come in|go in)|"
                        r"(you|they) can (just )?(go|come|let yourselves) in|no need to (call|text|contact|wait for)"
                        r"( me)?( first)?|"
                        r"pueden entrar|puede entrar|"
                        # W-12: "just go in", "go ahead and go in", "let yourselves in"
                        r"^\W*(?:ok(?:ay)?\W+|yes\W+|so\W+)?just (?:go|come) (?:on |right )?in\b|"
                        r"\bgo ahead and (?:go|come|let yourselves) in\b|\blet yourselves in\b|"
                        r"\bwhatever works means (?:just )?(?:go|come) in\b", re.IGNORECASE)
_ENTRY_NO = re.compile(r"(don'?t|dont|do not|please don'?t|no,? (don'?t|do not)) (come in|enter|go in)|without me\b|"
                       r"(call|contact|text|message) (me )?(first|before)|only (when|if) i'?m (home|there)|"
                       r"i (want|need) to be "
                       r"(home|there)|no entr|llamen antes|av[ií]senme antes", re.IGNORECASE)


_ENTRY_WITH_NOTICE = re.compile(r"(can|may|ok to|okay to|fine to) (come in|enter|go in)\W+(?:\w+\W+){0,4}(but|after|"
                                r"if|as long as) (they |you )?(text|call|message|contact|let me know|tell)|"
                                r"(text|call|message) me (first|before)\W+(?:\w+\W+){0,3}(then|and) (they |you )?"
                                r"(can|may) (come in|enter)", re.IGNORECASE)


_ENTRY_NO_ES = re.compile(r"\bque me avisen (?:primero|antes)|\bav[ií]s(?:e|en)me (?:primero|antes)|"
                          r"\bcont[aá]ct(?:e|en)me (?:primero|antes)|\bll[aá]m(?:e|en)me (?:primero|antes)|"
                          r"\bescr[ií]b(?:a|an)me (?:primero|antes)|\bsolo (?:cuando|si) (?:yo )?est(?:oy|[eé])\b|"
                          r"\bno entren\b|\bllamen antes\b|\bno (?:pueden|puede|deben) (?:entrar|pasar)\b", re.I)
_ENTRY_YES_ES = re.compile(r"\b(?:pueden|puede) (?:entrar|pasar)\b|\best[aá] bien que entren\b", re.I)


def extract_entry(message: str) -> str | None:
    if _ENTRY_WITH_NOTICE.search(message):
        return "May enter after contacting me first"
    if _ENTRY_NO.search(message) or _ENTRY_NO_ES.search(message):
        return "Contact me first; only enter when I'm home"
    if _ENTRY_YES_ES.search(message) and not re.search(r"\bno (?:pueden|puede)\b", message, re.I):
        return "Yes, maintenance may enter if I'm not home"
    if _ENTRY_YES.search(message):
        return "Yes, maintenance may enter if I'm not home"
    return None


_ISSUE_HINT = re.compile(
    r"crack|flicker|fell off|clog|overflow|toliet|lock|leak|drip|broken|not working|won'?t|doesn'?t|stopped|clog|no"
    r" (heat|hot water|water|power|ac|a/c)|noise|"
    r"rattl|smell|mold|pest|roach|\bants?\b|mouse|mice|bug|crack|stuck|loose|running|cooling|heating|knock|bang|grind|"
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


_ES_MORNING = re.compile(r"\b(por|en|de) la ma[ñn]ana\b", re.I)


_ES_DAYS = r"lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?"
_NEG_DAY = re.compile(rf"\b(?:not|no|except|but not|never|can'?t do|cannot do|can'?t make|can'?t on|not on|no el|no lo"
                      rf"s|"
                      rf"menos el|excepto el?)\s+(?:on\s+|the\s+|el\s+|los\s+)?(?:this |next )?(?P<d>(?:{_DAYS})s?|"
                      rf"{_ES_DAYS})\b", re.I)


def negated_days(message: str) -> list[str]:
    """Days the person rules out ('not saturday', 'no el sábado')."""
    return [m.group("d").rstrip("s").lower()[:3] for m in _NEG_DAY.finditer(message)]


def extract_days(message: str) -> str | None:
    message = _NEG_DAY.sub(" ", message)
    scan = _ES_MORNING.sub(" ", message)
    # D-8: 'moving this week, tour saturday': a week phrase in a clause about moving is not a tour day
    found = [m.group(0).strip() for m in _DAY_PHRASE.finditer(scan)
             if not (move_clause(scan, m.start()) and re.match(r"(this|next) (week|month)", m.group(0), re.I))]
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
    rng = re.search(r"\b(\d|one|two|three|four)\s?(?:or|-|to|–)\s?(\d|one|two|three|four)\s?-?\s?(?:bed|br|"
                    r"bedroom)s?\b",
                    message, re.I)
    if rng:  # "2 or 3 bedrooms" is a range, not the last number
        a, b = (_WORDNUM.get(x.lower(), x) for x in rng.groups())
        return f"{a}–{b} beds"
    m = _BEDS.search(message)
    if not m:
        return None
    if m.group(0).lower().startswith("studio"):
        return "Studio"
    n = _WORDNUM.get(m.group(1).lower(), m.group(1))
    return f"{n} bed" + ("s" if n != "1" else "")


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


_FAQ_ALIASES: dict[str, str] = {  # Spanish (and a few English) ways to ask an existing KB topic
    "vouchers": r"secci[oó]n 8|section 8|vales? de vivienda|vale de vivienda|cup[oó]n de vivienda",
    "pricing": r"cu[aá]nto cuesta|cu[aá]nto es la renta|precio|\b(?:under|less than|below) \$?\d{3,}|"
               r"\d{3,} (?:dollars|bucks|"
               r"a month|per month)|\bbudget\b|price range|\bafford\b|presupuesto|menos de \$?\d{3,}",
    "pets": r"mascotas?|\bperros?\b|\bgatos?\b",
    "parking": r"estacionamiento|parqueo",
    "utilities": r"servicios (?:incluidos|p[uú]blicos)|\butilidades\b",
    "floor_plans": r"\bplanos?\b",
    "availability": r"disponib",
}


def match_faq(message: str) -> list[KBTopic]:
    low = message.lower()
    _, topics = knowledge_base()
    return [t for t, kws in topics if any(re.search(rf"(?<![a-z]){re.escape(k)}", low) for k in kws)
            or (t.id in _FAQ_ALIASES and re.search(_FAQ_ALIASES[t.id], low))]


# ---- added after the independent review (see docs/evaluation/ux-review.md) ---------------------------------------

_BOOKING_Q = re.compile(r"\b(am i|are we|is it|is that) (booked|confirmed|scheduled|set)|\b(i'?m|we'?re|i am|we are) "
                        r"(booked|confirmed|scheduled|all set)|(what|which) time (do|should|can) (i|we) (show up|come|"
                        r"arrive|be there)|\bshow up\b|\bconfirm (the |that |my )?"
                        r"(time|slot|appointment|\d)|\bbook (me|it|a time)|\bis (\w+ ){0,3}(open|available)\b|"
                        r"\b(what|which) time (is|was) (my|the) tour|reserv(e|ation)|est[aá] confirmad", re.I)


_BOOKING_Q2 = re.compile(r"\bis (?:my|the) (?:tour|visit|appointment) (?:booked|confirmed|scheduled|set)\b|"
                         r"\b(?:tour|it|that|visit|appointment)(?: is|'s) (?:booked|confirmed|scheduled|set) for\b|"
                         r"\b(?:booked|confirmed|scheduled) for (?:mon|tues|wednes|thurs|fri|satur|sun|tomorrow|"
                         r"today|next)",
                         re.I)


def is_booking_question(message: str) -> bool:
    return bool(_BOOKING_Q.search(message)) or bool(_BOOKING_Q2.search(message))


_PHONE_Q = re.compile(r"phone number|emergency (maintenance )?(number|line|phone)|number (for|of|to) the (office|"
                      r"leasing|"
                      r"maintenance)|office number|call the office|"
                      r"what'?s the number|n[uú]mero (de|del) (tel[eé]fono|la oficina)|"
                      # A-4: "is there a number i can call right now"
                      r"\b(?:a|any|the) (?:phone )?number (?:i|we) (?:can|could) call\b|\bnumber to call\b|"
                      r"\bis there (?:a|any) (?:phone|number)\b|\bcan i (?:just )?call (?:someone|somebody|the office|"
                      r"a person|you)\b", re.I)


def is_phone_question(message: str) -> bool:
    return bool(_PHONE_Q.search(message))


_EVICTION = re.compile(r"kick (me|us) out|evict|lose my (home|apartment)|throw (me|us) out|desalojar|echarme", re.I)


def is_eviction_worry(message: str) -> bool:
    return bool(_EVICTION.search(message))


_CANCEL_SUBMITTED = re.compile(r"\b(cancel|delete|withdraw|take back|remove|retract)\b.{0,30}\b(request|work order|"
                               r"repair|"
                               r"tour|note|appointment|complaint|message|DEMO-\w+-\d+)\b|"
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


_OLD_VALUE = re.compile(r"\b(?:not|instead of|rather than)\s+(?:the\s+|on\s+)?$", re.I)


def extract_move_in(message: str) -> str | None:
    """Move-in timing. The LAST date in the message wins ('March 1, no wait, May 1' -> 'May 1'). Week-only phrases
    ('this week') count only when the person talks about moving, so a tour day isn't saved as a move-in date."""
    # C-1: "january 15 not dec 1": a date after "not" / "instead of" is the old value, never the new one
    found = [m for m in _MONTH_DAY.finditer(message) if not tour_clause(message, m.start())
             and not _OLD_VALUE.search(message[:m.start()])]
    move = bool(_MOVE_CONTEXT.search(message))
    if not found:  # D-8: 'moving next month, tour this week' -> the tour clause's week is not the move-in
        found = [m for m in _MOVE_IN.finditer(message)
                 if not re.search(r"\bnot\s+$", message[:m.start()], re.I)
                 and ((move and not tour_clause(message, m.start()))
                      or not re.match(r"(this|next) (week|month)|in (\d+|two|three|a few) weeks?", m.group(0), re.I))]
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
    """The community named (first in the message), skipping one named as the OLD value ('Fernhill not Birchwood')."""
    hits = sorted((m.start(), name) for name, pat in _COMMUNITIES for m in re.finditer(rf"\b{pat}\b", message, re.I)
                  if not _OLD_VALUE.search(message[:m.start()]))
    return hits[0][1] if hits else None


# A message giving contact details ('Alex Rivera, alex@example.com', 'my name is…', a redacted email/phone) is never
# an answer to "which city or community?": a capitalised name before a comma must not become the tour area.
_CONTACT_DETAILS = re.compile(r"@|\[(?:email|phone)|\b(?:my name is|me llamo|call me|text me at|email me)\b|"
                              r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", re.I)


def extract_area_correction(message: str) -> str | None:
    """Capitalised place names only: 'actually Orlando not Tampa', 'Orlando instead', 'Orlando, FL', 'Ann Arbor, 2
    bed', 'the Ann Arbor community', 'in Lansing', 'en Orlando'. Months, languages and common nouns never count."""
    if _CONTACT_DETAILS.search(message):
        return None
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
    if _CONTACT_DETAILS.search(message):
        return None
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


_ENGLISH_HELP = re.compile(r"^\W*(?:(?:in |speak |use |reply in |answer in |respond in )?english,? ?(?:please|pls|plz)"
                           r"?|"
                           r"(?:can|could) (?:you|we) (?:speak|talk|write|continue|do this|switch to|go back to) "
                           r"(?:in )?english\W*\w*|en ingl[eé]s(?:,? por favor)?|ingl[eé]s,? por favor|"
                           r"(?:switch|go back|change) to english\W*\w*|no spanish\W*\w*|i don'?t (?:speak|understand) "
                           r"spanish\W*\w*)\W*$", re.I)


# D-6: an explicit request for English anywhere in a longer message ("ok english again please. is this sent?").
_ENGLISH_ANY = re.compile(r"\b(?:reply|answer|respond|write|speak|talk|continue)(?: to me)? in english\b|"
                          r"\b(?:back|switch|go back|change) to english\b|\benglish (?:again|please|pls|plz)\b|"
                          r"\bi don'?t (?:speak|understand|read) (?:much |a lot of |any )?spanish\b|"
                          r"\b(?:in|en) ingl[eé]s,? por favor\b|\bno spanish\b", re.I)


def asks_for_english(message: str) -> bool:
    return bool(_ENGLISH_HELP.search(message.strip())) or bool(_ENGLISH_ANY.search(message))


def strip_language_request(message: str) -> str:
    """The rest of a message once the English/Spanish request clause is removed."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", message)
             if not (_ENGLISH_ANY.search(p) or _ENGLISH_HELP.search(p.strip()) or _SPANISH_HELP.search(p))]
    return " ".join(parts).strip()


_PROMISE = re.compile(r"\bpromise\b|guarantee|\bby (mon|tues|wednes|thurs|fri|satur|sun)day\b|in writing|\b(rent"
                      r" )?credit\b|"
                      r"compensat|reimburs|refund|money back|discount on (my )?rent|prom[eé]tame|garant", re.I)


def asks_for_promise(message: str) -> bool:
    """Demands for a date, a credit or a written commitment: the assistant can't decide these."""
    return bool(_PROMISE.search(message))


_NOISE = re.compile(r"\b(noise|noisy|loud|music|party|parties|bark\w*|stomping)\b|upstairs (neighbor|guy)|ruido|"
                    r"m[uú]sica alta", re.I)


_NEIGHBOR = re.compile(r"neighbou?r|upstairs|downstairs|next door|music|party|parties|bark|dog|stomp|\btv\b|"
                       r"yell|scream|people|vecino|m[uú]sica", re.I)
_BUILDING_NOISE = re.compile(r"\b(fan|ac|a/c|air ?condition\w*|heater|furnace|fridge|refrigerator|dishwasher|disposal|"
                             r"pipes?|wall|ceiling|vent|duct|toilet|water heater|washer|dryer|motor|rattl\w*|grind\w*|"
                             r"knock\w*|hum+ing|buzz\w*|squeal\w*|squeak\w*|clank\w*|bang\w* (?:in|from) the|"
                             r"compressor|thermostat|smoke detector|alarm|aire|aire acondicionado|nevera|refri\w*|"
                             r"lavadora|secadora|calentador|ventilador|tuber[ií]as?|motor|lavaplatos|inodoro)\b", re.I)


def is_noise_complaint(message: str) -> bool:
    """Noise between neighbours. Fan, AC, pipe or wall noise is a repair (maintenance), unless a neighbour is named."""
    if not _NOISE.search(message) and not re.search(r"\bknock\w*\b", message, re.I):
        return False
    if _BUILDING_NOISE.search(message) and not _NEIGHBOR.search(message):
        return False
    # Sprint 7 (judge H-6): a sound IN the person's own home or from a thing ("a weird noise in my unit", "a clicking
    # noise in my bathroom", "un ruido raro en mi apartamento") is a repair unless a neighbour or people are named
    from app.utterance import things

    if not _NEIGHBOR.search(message) and (things(message) or re.search(
            r"\b(?:in|inside|from|coming from) (?:my|our|the) (?:unit|apartment|apt|place|kitchen|bathroom|bedroom|"
            r"wall|walls|ceiling|floor|closet|vents?|living room)\b|\ben (?:mi|el) (?:apartamento|depa|departamento|"
            r"ba[ñn]o|cocina|cuarto)\b|\b(?:weird|strange|odd|funny|raro|extra[ñn]o)\b", message, re.I)):
        return False
    return bool(_NOISE.search(message))


_PETS = re.compile(r"\b(i have|we have|with|plus|got) (a |an |one |two |three |\d )?(big |small |little )?(dogs?|cats?|"
                   r"pets?|puppy|kitten)\b", re.I)


def extract_pets(message: str) -> str | None:
    m = _PETS.search(message)
    return m.group(0)[0].upper() + m.group(0)[1:] if m else None


def is_issue_description(message: str) -> bool:
    return bool(_ISSUE_HINT.search(message))


_ISSUE_JOIN = re.compile(r"\s*(?:,?\s*\band also\b|,?\s*\balso\b|\bplus\b|\band then\b|\banother thing(?: is)?\b|"
                         # Sprint 6: more joins between two problems ("X, the oven won't heat", "X as well as Y",
                         # "two things: X and Y", "X, oh and Y"); split_issues still needs a named thing on each side
                         r"^\W*(?:i have )?(?:two|2|a couple of|a few) (?:things|problems|issues)\W*|\bas well as\b|"
                         r",?\s*\boh and\b|,\s*(?=(?:the|my|our)\b)|"
                         r"\bon top of that\b|;|\.\s+|,?\s*\band\s+(?=(?:the|my|our|a)\b)|\by tambi[eé]n\b|"
                         r"\badem[aá]s\b|,?\s*\by\s+(?=(?:el|la|los|las|mi)\b)|"
                         # Sprint 6 fix round: "X and separately Y", "X. Separately, Y", "1) X 2) Y", "y aparte"
                         r",?\s*\b(?:and )?separately\b|\b(?:\d|[a-c])\)\s*|\(\d\)\s*|"
                         r"\b(?:first|second|third)(?:ly)?[,:]\s*|"
                         r",?\s*\by aparte\b|,?\s*\baparte\b)\s*", re.I)


_ES_THING = re.compile(r"\b(?:inodoro|puerta|ventana|lavaplatos|refrigerador|nevera|estufa|horno|lavadora|secadora|"
                       r"aire(?: acondicionado)?|calentador|luz|enchufe|grifo|llave|ducha|ba[ñn]era|techo|"
                       r"cerradura|smoke detector|detector|carpet|alfombra)\b", re.I)


def _ES_THING_FN(text: str) -> str | None:  # noqa: N802 - a named thing the English appliance list misses
    m = _ES_THING.search(text)
    return m.group(0).lower() if m else None


def split_issues(message: str) -> list[str]:
    """'the dishwasher won't drain and also the bedroom window lock is broken' -> two separate problems.
    Only splits when each part names its own thing (appliance or room + a problem); otherwise one issue."""
    from app.context import detect_topics

    parts = [p.strip(" ,.;") for p in _ISSUE_JOIN.split(message) if p and p.strip(" ,.;")]
    out: list[tuple[str, str]] = []
    for p in parts:
        if len(p.split()) < 2:
            continue
        thing = appliance_in(p) or extract_location(p) or _ES_THING_FN(p) or next(
            (tp for tp in detect_topics(p) if tp not in ("contact_preference", "billing", "renewal")), None)
        if thing and (is_issue_description(p) or re.search(r"broke|broken|out\b|off\b|loose|fell|missing|torn|jammed|"
                                                           r"rattl|squeak|smell|won'?t|doesn'?t|not|leak|drip|stuck|"
                                                           r"loud|noise|clog|crack|mold|roto|no funciona|gotea|"
                                                           r"warm|\bhot\b|\bcold\b|dead|dim\b|buzz|flicker|beep|"
                                                           r"chirp|keeps|slow|hums?\b|jam|stain|takes \d|no (?:deja|"
                                                           r"cierra|enfr[ií]a|prende|sirve|abre|sale)|no hay", p,
                                                           re.I)):
            if all(thing != t for _, t in out):
                out.append((p, thing))
    if len(out) >= 2:
        return [p for p, _ in out]
    from app.utterance import split_problems  # Sprint 7: the structural split (object + symptom per clause)

    return split_problems(message)


def frustration_only(message: str) -> bool:
    """Venting with no new repair detail ('are you even listening', 'why do i have to keep telling you')."""
    return bool(re.search(r"are you (even )?listening|keep telling|why do i (have|need) to|ugh+|seriously\??$|"
                          r"hello\?+$|anyone there", message, re.I)) and not _ISSUE_HINT.search(message)


# ---- sprint 2: corrections, preferences, follow-ups, policy questions, unsafe do-it-yourself ----------------

_ISSUE_SWAP = re.compile(
    r"(?:^|\b)(?:it'?s|its|it is|that'?s) not (?:the |my |a )?(?P<old>[\w /-]{2,30}?)[,.;!-]+\s*(?:it'?s|its|it is|"
    r"it'?s actually|the problem is)?\s*(?:the |my |a )?(?P<new>[^.?!]{3,})|"
    r"^\W*(?:wait|no|actually|sorry|oops)\W+(?:it'?s|its|it is) not (?:the |my )?(?P<old2>[\w /-]{2,30}?)\W+"
    r"(?:it'?s |its |it is )?(?:the |my )?(?P<new2>[^.?!]{3,})|"
    r"^\W*(?:(?:wait|no|actually|sorry|oops)\W+)*(?:it'?s|its|it is) (?:actually )?(?:the |my |a )?(?P<new3>[\w /-]{3,"
    r"40}?)"
    r",? (?:and )?not (?:the |my |a )?(?P<old3>[\w /-]{2,30}?)\W*$", re.I)


def extract_issue_swap(message: str) -> str | None:
    """'wait, it's not the AC, it's the bathroom fan' -> 'bathroom fan' (replaces the issue, never appends)."""
    m = _ISSUE_SWAP.search(message)
    if not m:
        return None
    new = (m.group("new") or m.group("new2") or m.group("new3") or "").strip(" ,.;")
    old = (m.group("old") or m.group("old2") or m.group("old3") or "").strip()
    rooms = r"(kitchen|bath ?room|bedroom|living room|hallway|hall|closet|laundry|garage|balcony|dining room)"
    if re.fullmatch(rooms, old, re.I) or re.fullmatch(rooms, new, re.I):
        return None  # "not the kitchen, it's the bedroom ceiling" is a location correction
    if not new or re.fullmatch(r"(kitchen|bathroom|bedroom|living room|hallway)", new, re.I):
        return None  # a room swap is a location correction
    if (extract_location(new) or _LOC_DETAIL.search(new)) and not appliance_in(new) and len(new.split()) <= 4:
        return None  # "it's the hall bathroom not the master": the room changes, not the problem
    if (extract_entry(new) or _CONTACT_PREF.search(new) or _CHANNEL_SAID.search(new)) and not _ISSUE_HINT.search(new):
        return None  # B-3: "its not cooling. contact me first" -> entry wording, never the new problem
    return new[0].upper() + new[1:]


# R-1: the person restates the problem outright ("the problem is…", "change the description to: …").
_ISSUE_SHOULD_SAY = re.compile(r"\b(?:it|that|this|the (?:problem|issue|what'?s wrong(?: part| field)?)) should (?:say|"
                               r"read|be)\s*:?\s*(?:that |the |my )?(?P<new>[^;.!?]{3,160})|"
                               r"\bchange (?:the )?(?:what'?s|whats|what is) wrong(?: part| field)? to\s*:?\s*"
                               r"(?:that |the |my )?(?P<new2>[^;.!?]{3,160})", re.I)
_ISSUE_RESTATE = re.compile(r"\b(?:the (?:problem|issue) is|change (?:the )?(?:description|problem|issue) to|"
                            r"(?:description|problem|issue)\s*:)\s*:?\s*(?:that |the |"
                            r"my )?(?P<new>[^,;.!?]{3,120})", re.I)


# Sprint 6 (judge H-1): "the location is wrong, it should say kitchen" names ANOTHER field;
# it never rewrites the problem.
_OTHER_FIELD_SUBJECT = re.compile(
    r"\b(?:the )?(?:location|room|where|place|spot|area|entry(?: permission)?|permission|contact(?: preference)?|"
    r"phone|email|(?:visit |best )?time|date|day)(?: field| part| bit| line)?\s*(?:is|was|'s|are)\s+"
    r"(?:wrong|incorrect|not right|off|a mistake)|"
    r"\b(?:location|room|where|entry|contact|time)(?: field| part)? (?:should|must) (?:say|read|be)\b|"
    r"\b(?:change|fix|correct|update) (?:the )?(?:location|room|where|entry|contact|time)(?: field| part)?\b", re.I)
_OTHER_FIELD_VALUE = re.compile(r"\b(?:should (?:say|read|be)|to)\s*:?\s*(?:the |my |in the )?(?P<v>[^;.!?]{2,60})",
                                re.I)


def names_other_field(message: str) -> bool:
    return bool(_OTHER_FIELD_SUBJECT.search(message))


def extract_issue_restate(message: str) -> str | None:
    if names_other_field(message):
        return None
    s = _ISSUE_SHOULD_SAY.search(message)  # D-4: "the problem is wrong. it should say X" -> X, never "Wrong"
    if s:
        new = (s.group("new") or s.group("new2") or "").strip(" ,.;:")
        return new[0].upper() + new[1:] if new else None
    m = _ISSUE_RESTATE.search(message)
    if m and re.fullmatch(r"(?:wrong|incorrect|not right|off|bad)\W*", m.group("new").strip(), re.I):
        return None
    if not m:
        return None
    new = m.group("new").strip(" ,.;:")
    return new[0].upper() + new[1:] if new else None


_LOC_CHANGE_ES = re.compile(r"\b(?:en realidad |de hecho |no,? )?(?:es|est[aá]) (?:en )?(?:el |la )(?P<loc>ba[ñn]o"
                            r"(?: del pasillo| principal| de visitas)?|cocina|sala|dormitorio|rec[aá]mara|pasillo|"
                            r"balc[oó]n|lavander[ií]a)\b", re.I)
_LOC_CHANGE = re.compile(r"\bchange (?:the )?(?:location|room|place|where it is|spot) to (?:the |my"
                         r" )?(?P<loc>[^.?!,]{3,40})|"
                         r"\b(?:it'?s|its|it is) (?:actually )?in (?:the |my )(?P<loc2>[^.?!,]{3,30})|"
                         r"\b(?:the |my )?(?P<loc3>hall(?:way)?) is (?:inside|in) (?:my|the|our) "
                         r"(?:apartment|unit|place)",
                         re.I)


_QUAL = (r"hall|hallway|main|master|guest|second|2nd|upstairs|downstairs|other|front|back|kids'?|primary|half|small|"
         r"big|spare|kid'?s|first|1st")
_LOC_DETAIL = re.compile(rf"\b(?<!not )(?<!not the )(?:the |my )?(?P<q>{_QUAL})\s+(?P<room>bath ?rooms?|bath|bedroom|"
                         rf"closet|kitchen|room|one)\b", re.I)


_ROOMS = (r"kitchen|bath ?room|bedroom|living room|dining room|laundry(?: area)?|balcony|patio|hallway|front door|"
          r"entry door")
_LOC_CHANGE2 = re.compile(rf"\b(?:the )?(?:location|room|place|where)\s*(?:is|:)\s*(?:the |my |"
                          rf"in the )?(?P<loc>[^.?!,]{{3,40}})|"
                          rf"\b(?:it'?s|its|it is) (?:actually )?(?:the |my |"
                          rf"in the )?(?P<loc2>{_ROOMS})\b[^,.;!?]{{0,30}},?\s*"
                          rf"not (?:the |my |in the )?(?:{_ROOMS})\b", re.I)


def extract_location_change(message: str, current: str | None = None) -> str | None:
    """'change the location to the bedroom', "it's in the hall bathroom", 'the hall one, not the main one'."""
    if re.search(r"\b(?:location|room|where|place|spot)\b", message, re.I) and names_other_field(message):
        for v in _OTHER_FIELD_VALUE.finditer(message):
            if (loc := extract_location(v.group("v"))) and loc != current:
                return loc
    m2 = _LOC_CHANGE2.search(message)
    if m2:
        loc = (m2.group("loc") or m2.group("loc2") or "").strip()
        if loc and (extract_location(loc) or _LOC_DETAIL.search(loc)):
            detail = _LOC_DETAIL.search(loc)
            if detail:
                q = detail.group("q").lower().replace("hallway", "hall")
                return f"{q[0].upper() + q[1:]} {detail.group('room').lower()}"
            return extract_location(loc)
    m = _LOC_CHANGE.search(message)
    if not m and (es := _LOC_CHANGE_ES.search(message)) and len(message.split()) <= 10:
        loc = es.group("loc")
        return loc[0].upper() + loc[1:]
    if not m:
        d = _LOC_DETAIL.search(re.sub(rf"\b(?:not|isn'?t|no) (?:the |my )?(?:{_QUAL})\s+\w+", " ", message, flags=re.I))
        if not d or len(message.split()) > 12:
            return None
        room = d.group("room").lower()
        if room == "one":
            if not current:
                return None
            room = current.lower()
        q = d.group("q").lower().replace("hallway", "hall")
        return f"{q[0].upper() + q[1:]} {room}"
    if m.group("loc3"):
        return "Hallway"
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


_META_Q = re.compile(
    r"\bdid (?:that|it|this|they|my (?:\w+ ){0,2}(?:request|note|repair|order)) (?:actually )?(?:go|get) "
    r"(?:in|through|thru|sent|submitted)|\b(?:is|was|are|were) (?:the |my |that |it |this )?(?:actual |real )?(?:repai"
    r"r "
    r"|maintenance |work )?(?:request|order|ticket|note|it|that|anything|one)s? (?:actually |really )?(?:in|sent|"
    r"submitted|saved|through|filed)\b|\bjust (?:a |some )?notes?\b|\bdid you (?:actually |really )?(?:send|submit|"
    r"notify|tell|pass|forward|file|save|put)|\bwill (?:a |any )?(?:human|person|real person|someone|anyone|staff)"
    r" (?:actually |ever )?(?:read|see|get|look at)|\bwhen (?:will|do|would) i hear back|\bwhat did you (?:send|"
    r"submit|save|do)|\bwhat (?:have|has) (?:you |been )?(?:sent|submitted|saved)|\bse envi[oó]|\blo envi[oó]|"
    r"\bya se mand[oó]|\bwhat (?:got|was) sent|\bdid (?:both|they|those|all|them|everything|all of them) (?:go|get)"
    r" (?:in|through|sent)|\b(?:is|will) (?:a |the )?(?:manager|human|person|someone|anyone|staff)(?: actually| really|"
    r" ever)? (?:going to |gonna )?(?:see|read|look at|get) (?:it|this|that|my)|\bis (?:the|my) [\w ]{1,30} "
    r"(?:fixed|done|repaired|scheduled|sorted) (?:yet|now)?\b", re.I)


_LOCKOUT = re.compile(r"locked out|lock(?:ed)? (?:my ?self|me) out|can'?t get (?:in|into|back in(?:to)?) (?:my |the )?"
                      r"(?:apartment|unit|place|home|house)|lost (?:my |the )?keys?|keys? (?:are |is )?(?:locked )?"
                      r"inside|lockout|me qued[eé] (?:afuera|fuera)|no puedo entrar (?:a|en) (?:mi|el)|perd[ií] (?:mis|"
                      r"las) llaves", re.I)


_WITHHOLD = re.compile(r"withh[oe]ld(?:ing)? (?:my |the )?rent|(?:not|won'?t|stop|refuse to) (?:going to |gonna )?pay("
                       r"?:ing)? "
                       r"(?:my |the |any )?rent|rent strike|no (?:voy a )?pagar (?:la )?renta", re.I)
_ACCOMMODATION = re.compile(r"accommodat|disab|wheelchair|service (?:animal|dog)|support animal|\besa\b|ramp|grab bar|"
                            r"hearing|deaf|blind\b|mobility|discapacidad|silla de ruedas", re.I)
_OTHER_PERSON = re.compile(
    # Sprint 7: "on" needs someone else's device ("on her phone"); "anything still open on my account?" is a status
    # question by the account holder
    r"\b(?:this is (?:actually |not )?(?:\w+ )?(?:from|in) (?:unit|apt|apartment) \w+|(?:using|borrowed) (?:my "
    r"|her |his |their )?(?:\w+'s )?(?:phone|account|login)|\bon (?:her |his |their |my \w+'s |\w+'s )(?:phone|"
    r"account|login)|let me use (?:her|his|their|my \w+'s) (?:phone|"
    r"account|login)|this isn'?t my account|not (?:my|the) account holder|i'?m not (?:the person|the resident|the "
    r"account holder)|(?:her|his|their|my \w+'s) (?:account|phone|login),? (?:not mine|but))", re.I)


def is_rent_withholding(message: str) -> bool:
    return bool(_WITHHOLD.search(message))


def is_accommodation(message: str) -> bool:
    return bool(_ACCOMMODATION.search(message))


def not_account_holder(message: str) -> bool:
    """'This is actually Jordan from unit 2C, Casey let me use her phone.'"""
    return bool(_OTHER_PERSON.search(message))


def is_lockout(message: str) -> bool:
    return bool(_LOCKOUT.search(message))


_META_Q_ES = re.compile(r"\b(?:ya )?(?:lo|la) (?:enviaron|mandaron|recibieron)\b|\bya (?:est[aá]|"
                        r"qued[oó]) (?:enviad|guardad)|"
                        r"\bse (?:mand[oó]|guard[oó])\b", re.I)


def is_meta_question(message: str) -> bool:
    """'did that go in?', 'is the actual repair request in or just notes', 'will a human read it?'"""
    return bool(_META_Q.search(message)) or bool(_META_Q_ES.search(message))


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
    return bool(_AFTER_SEND_Q.search(message)) or is_after_send_followup(message)


_POLICY_TOPICS = [
    ("guests", r"\bguests?\b|visitors?|overnight|stay with me"),
    ("packages", r"\bpackages?\b|deliver(y|ies)|parcel|amazon|mail ?room"),
    ("trash and recycling", r"\btrash\b|garbage (pick ?up|day|room|chute)|recycl\w*|dumpster|bulk (item|pickup)"),
    ("quiet hours", r"quiet hours|noise (rule|policy|hours)"),
    ("parking", r"\bpark(ing)?\b|garage spot|guest spot|tow\w*"),
    ("pets", r"\bpets?\b|\bdogs?\b|\bcats?\b|pet (fee|rent|deposit)"),
    ("amenities", r"\bpool\b|\bgym\b|fitness|clubhouse|amenit\w*"),
    ("smoking", r"\bsmok(e|ing)\b(?! (?:detector|alarm))|\bvap(e|ing)\b"),
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
    if is_noise_complaint(message) or is_cancel_submitted(message):
        return None
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
    ("mix_chemicals", r"\b(mix\w*|combin\w*)\b[^.?!]{0,30}\b(bleach|ammonia|vinegar|drain cleaner)\b[^.?!]{0,30}"
                      r"\b(and|with|plus)\b[^.?!]{0,20}\b(bleach|ammonia|vinegar|cleaner|acid)"),
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


# ---- sprint 5: conversation recovery, requests for a person, follow-ups after sending (D-8..D-22) -------------

# D-12: the person is lost or says the chat isn't helping. About the CHAT, not the repair: "the dishwasher isn't
# working" never matches. Venting already handled elsewhere ("are you even listening") is left to frustration_only.
_LOST = re.compile(
    r"\bwhat (?:do|should|am) i (?:supposed to )?do (?:now|next|here)\b|\bwhat do i do\W*\?|"
    r"\b(?:this|that|you|it)(?: chat| bot| thing)? (?:is|are|was)?\s?(?:n'?t|not) (?:helping|helpful|any help)|"
    r"\bthis isnt helping\b|\b(?:not|no) help(?:ful)? at all\b|\bnot helpful\b|"
    r"\b(?:you'?re|you are|ur|this is|that'?s|this bot is|this chat is) (?:so |totally |completely )?(?:useless|"
    r"pointless|no help|worthless|a waste of time)\b|\b(?:useless|pointless) (?:bot|chat|assistant)\b|"
    r"\bi (?:already|just) (?:told|said|gave|answered) (?:you|that|this|it)\b|\bi'?ve already (?:told|said|answered)\b|"
    r"\bi'?m (?:so |really |totally )?(?:lost|confused)\b|\bi don'?t (?:understand|get it|know what (?:to do|you "
    r"want))\b|\byou'?re not (?:understanding|getting it)\b|\bgoing in circles\b|"
    r"^\W*\?{2,}\W*$|^\W*(?:huh|what)\W*\?{2,}\W*$|"
    r"\bno me (?:est[aá] )?ayuda\b|\bno sirve (?:de nada|para nada)\b|\besto no sirve\b|\bya (?:le|te) (?:dije|"
    r"lo dije)\b|"
    r"\bno entiendo\b|\by ahora qu[eé]\b|\bqu[eé] hago ahora\b", re.I)


def is_lost_or_frustrated_with_chat(message: str) -> bool:
    """'what do I do now??', 'this isn't helping', '???', 'i already told you', "you're useless" (D-12)."""
    return bool(_LOST.search(message)) and not frustration_only(message)


# D-11: more ways to ask for a person. Kept separate from _STAFF (extend, don't merge). "I need someone to fix it" is
# a repair, not a request for a person, so 'someone' only counts with talk/speak/connect.
_PERSON_ASK = re.compile(
    r"\b(?:want|need|like|prefer)(?: to (?:talk|speak|chat) (?:to|with))? (?:a |an |the )?(?:real |actual |live )?"
    r"(?:person|human|team member|staff member|people)\b(?! to (?:fix|come|look|repair|check|enter))|"
    r"\b(?:talk|speak|chat) to (?:a |an )?(?:real |actual |live )?(?:person|human|people)\b|"
    r"\b(?:connect|put|transfer) me (?:to|through to|with) (?:a |an |the |someone|somebody)|"
    r"^\W*(?:can i |could i |may i )?(?:talk|speak) (?:to|with) (?:someone|somebody)\b|"
    r"^\W*(?:the |a |your |my )?(?:property |community |building )?(?:manager|supervisor|management)\W*(?:please|pls|"
    r"plz|now)?\W*$|\b(?:i want|i need|i'?d like|let me (?:talk|speak) to|i'?ll talk to) (?:to (?:talk|speak) (?:to|"
    r"with) )?(?:the |a |your |my )?(?:property |community |building )?(?:manager|supervisor|management)\b|"
    r"\bquiero hablar con (?:alguien|una persona|el gerente|la gerente)\b|\bun(?:a)? persona,? por favor\b|"
    r"^\W*ask (?:the )?leasing(?: team| office)?\W*$|^\W*preguntar a arrendamiento\W*$", re.I)


def asks_for_person(message: str) -> bool:
    return bool(_PERSON_ASK.search(message))


_MANAGER = re.compile(r"\b(?:manager|supervisor|management|gerente|whoever(?:'s| is) in charge)\b", re.I)


def asks_for_manager(message: str) -> bool:
    """A request for a person that names a manager: routes to the management team, not leasing (D-11)."""
    return bool(_MANAGER.search(message))


# D-9: follow-up questions about something already sent. Extends _AFTER_SEND_Q.
_AFTER_SEND_Q2 = re.compile(
    r"\bwill (?:someone|somebody|anyone|they|the (?:office|team|leasing team|leasing office|manager)|leasing|"
    r"maintenance|a person) (?:actually |ever )?(?:call|email|e-mail|text|contact|reach|get back to|confirm|follow up)|"
    r"\bwhen (?:will|do|does|would|is|are) (?:they|someone|the (?:office|team|leasing team)|leasing|i) "
    r"(?:\w+ ){0,2}(?:confirm|hear|get (?:a |an )?(?:call|email|text|confirmation))|"
    r"\bwill i (?:get|receive|hear) (?:a |an |back|anything)|\bhow (?:will|do|would) i (?:know|hear)\b|"
    r"\bwho (?:will|is going to) (?:call|email|contact|reach) me\b|\bis (?:someone|anyone) going to (?:call|email|"
    r"contact|text)|\b(?:did|has) (?:it|that|my (?:tour|request|note)) (?:been |get |got )?(?:confirmed|booked)\b|"
    r"\bme van a (?:llamar|escribir|contactar)\b|\bcu[aá]ndo (?:me )?(?:confirman|llaman)\b|"
    r"\bwhat happens now\b|\b(?:so )?(?:it'?s|its|it is|is it|that'?s) (?:all )?(?:done|sent|in)(?: right| now)?\W*\?|"
    r"\b(?:someone|somebody|anyone|a tech) (?:is |'s )?coming\b|\b(?:anyone|"
    r"someone) (?:actually )?going to (?:look|see|read|"
    r"check|call|come)|\bwhen (?:they'?ll|they will) (?:come|call|email|text|confirm|be here)|"
    r"\bwill they (?:call|email|text|contact|reach) me\b|"
    # A-12: "is a manager going to call me today?", "will a manager actually call me"
    r"\b(?:is|are) (?:a |the |my )?(?:manager|office|leasing team|team|staff|person) (?:actually |really )?"
    r"(?:going to|gonna) (?:call|text|email|contact|reach|come)|\bwill (?:a |the )?(?:manager|staff|team member) "
    r"(?:actually |really |ever )?(?:call|text|email|contact|reach)", re.I)


def is_after_send_followup(message: str) -> bool:
    return bool(_AFTER_SEND_Q2.search(message))


# B1: how a prospect will be reached. Contact details are never stored from chat (they are redacted before this).
_HOW_REACHED = re.compile(
    r"\bhow (?:will|would|do|are|can) (?:you|they|the (?:leasing )?(?:team|office)|someone|leasing) (?:\w+ )?(?:reach|"
    r"contact|get (?:a )?hold of|get back to|call|email|text) me|\bhow will i be (?:contacted|reached)|"
    r"\b(?:do|does|did) (?:you|they|the team) (?:have|need|get) my (?:number|phone|email|contact)|"
    r"\b(?:should|can|do|could) i (?:give|send|leave|share) (?:you |them )?my (?:number|phone|email|contact)|"
    r"\bhere'?s my (?:number|phone|email|contact)|\b(?:you can |they can )?(?:reach|contact) me at\b|"
    r"\bmy (?:number|phone|email|cell) is\b|\bc[oó]mo me (?:van a )?contacta", re.I)


def asks_how_reached(message: str) -> bool:
    return bool(_HOW_REACHED.search(message))


# D-14: early move-out / breaking a lease. Not a renewal question.
_LEASE_BREAK = re.compile(
    r"\bmov(?:e|ing) out (?:early|before (?:my|the) lease)|\bmove out (?:in|next) (?:\w+ )?(?:before|early)|"
    r"\bbreak(?:ing)? (?:my|the|our) lease\b|\bend (?:my|the|our) lease (?:early|before)|\bterminat\w* (?:my|the|our) "
    r"lease\b|\bget out of (?:my|the|our) lease\b|\blease (?:break|termination|buy-?out)\b|\bleave before (?:my|the) "
    r"lease\b|\bearly (?:termination|move-?out)\b|\bromper (?:el|mi) contrato\b|\bterminar (?:el|mi) contrato\b|"
    r"\bmudarme antes\b|\bsalir(?:me)? antes de(?:l| que termine el) contrato\b", re.I)


def is_lease_break(message: str) -> bool:
    return bool(_LEASE_BREAK.search(message))


# D-13: a lock that doesn't secure the home. Kept apart from the gate's urgency rules and from emergency.py.
_SECURITY_REPAIR = re.compile(
    r"\b(?:door|deadbolt|lock|latch)\w*\W+(?:\w+\W+){0,3}(?:broken|broke|stuck|jammed|loose|won'?t (?:lock|latch|close|"
    r"shut)|doesn'?t (?:lock|latch|close)|can'?t (?:lock|be locked)|not (?:locking|latching|closing))|"
    r"\b(?:broken|jammed|stuck|loose) (?:door ?)?(?:lock|deadbolt|latch)\b|\bwon'?t lock\b|\bdoesn'?t lock\b|"
    r"\bcan'?t lock (?:my|the) (?:front |entry |apartment )?door\b|\bcerradura\b|\bla puerta no cierra\b", re.I)
_DOOR = re.compile(r"\b(?:door|deadbolt|lock|latch|cerradura|puerta)\b", re.I)


def is_security_repair(message: str) -> bool:
    """'the door lock is broken', 'front door won't lock' (not 'the closet door is off its track', not a lockout)."""
    return bool(_SECURITY_REPAIR.search(message)) and bool(_DOOR.search(message)) and not is_lockout(message) \
        and not re.search(r"\b(?:closet|cabinet|fridge|refrigerator|oven|dishwasher|shower|washer|dryer|microwave)"
                          r" door\b", message, re.I) \
        and not re.search(r"\bmail ?box\b|\bbuz[oó]n\b|\bgarage door opener\b|\bopener\b|\bremote\b|\blocker\b|"
                          r"\bstorage\b", message, re.I)  # Sprint 7: not the home's own entry lock


# D-15: a reference to a request already listed ("the one for the sink leak", "the AC one").
_REF_EXISTING = re.compile(
    r"\bthe (?:one|request|repair|ticket) (?:for|about|with|re) (?:the |my )?(?P<a>[\w /-]{2,40}?)\W*$|"
    r"^\W*(?:what about |and |ok(?:ay)?,? )?(?:the|my) (?P<b>[\w/-]+(?: [\w/-]+){0,2}) (?:one|request|ticket)\W*"
    r"(?:please)?\W*\??\W*$|\b(?:what about|how about|any news on|update on) the (?P<c>[\w/-]+(?: [\w/-]+){0,2}) "
    r"(?:one|request)\b", re.I)
_REF_STOP = {"the", "my", "a", "an", "for", "about", "with", "one", "request", "repair", "ticket", "is", "it", "that",
             "this", "open", "old", "other", "first", "last", "new", "please"}


def existing_request_words(message: str) -> list[str]:
    """Descriptive words of a reference to an existing request, or [] when the message isn't one."""
    m = _REF_EXISTING.search(message.strip())
    if not m:
        return []
    words = re.findall(r"[a-z/]+", (m.group("a") or m.group("b") or m.group("c") or "").lower())
    return [w for w in words if w not in _REF_STOP and len(w) >= 2]


def matches_words(words: list[str], title: str) -> bool:
    """Every descriptive word matches the start of a word in the title ('leak' ~ 'leaking', 'ac' ~ 'AC')."""
    tw = re.findall(r"[a-z/]+", title.lower().replace("a/c", "ac"))
    return bool(words) and all(any(t.startswith(w.replace("a/c", "ac")) or (len(t) >= 4 and w.startswith(t))
                                   for t in tw) for w in words)


# D-8: a message about a move and a tour at once ('moving next month, tour this week'): the clause decides.
_CLAUSE_SPLIT = re.compile(r"[,;.!?…—]+|\s(?:but|and|so|then|y|pero)\s", re.I)
_TOURISH = re.compile(r"\b(?:tour|visit|see (?:it|the|a|an|one|something|anything|some|places|units|apartments)|"
                      r"come (?:by|see|look)|show me|look at|recorrido|visitar)\b", re.I)
_MOVEISH = re.compile(r"\bmov(?:e|ing)\b|move-?in|lease start|mudar|mudanza", re.I)


def _span_clause(message: str, start: int) -> str:
    bounds = [0] + [m.end() for m in _CLAUSE_SPLIT.finditer(message) if m.end() <= start]
    end = next((m.start() for m in _CLAUSE_SPLIT.finditer(message) if m.start() >= start), len(message))
    return message[max(bounds):end]


def tour_clause(message: str, start: int) -> bool:
    """The phrase at `start` sits in a clause about the tour (and not about moving)."""
    c = _span_clause(message, start)
    return bool(_TOURISH.search(c)) and not _MOVEISH.search(c)


def move_clause(message: str, start: int) -> bool:
    c = _span_clause(message, start)
    return bool(_MOVEISH.search(c)) and not _TOURISH.search(c)


# D-8 / p-vague-start: "whenever", "any time", "no preference" answers a days or time question.
_FLEXIBLE = re.compile(r"^\W*(?:um+\W+|idk\W+|honestly\W+)?(?:whenever|any ?time|any ?day|anyday|any of them|"
                       r"flexible|i'?m flexible|no preference|doesn'?t matter|don'?t care|either|whatever works|"
                       r"cuando sea|cualquier (?:d[ií]a|hora|momento)|me da igual)\b", re.I)


_FLEX_DAY_ONLY = re.compile(r"\bany ?day\b|\banyday\b|cualquier d[ií]a", re.I)
_FLEX_TIME_ONLY = re.compile(r"\bany ?time\b|cualquier (?:hora|momento)", re.I)


def flexible_answer(message: str, slot: str | None = None) -> bool:
    """'whenever' answers either question; 'any day' answers only days and 'any time' only time."""
    if not _FLEXIBLE.search(message):
        return False
    if slot == "time" and _FLEX_DAY_ONLY.search(message) and not _FLEX_TIME_ONLY.search(message):
        return False
    if slot == "days" and _FLEX_TIME_ONLY.search(message) and not _FLEX_DAY_ONLY.search(message):
        return False
    return True


# D-17: a bare 'ok' to "may maintenance enter?" is not permission; 'yes' is.
def is_bare_ok(message: str) -> bool:
    return bool(re.fullmatch(r"\s*(?:ok(?:ay)?|k|kk|fine|alright|all right|vale|bueno)[\s.!,]*", message, re.I))


# D-20: a channel stated in chat ("text me first") for the card's contact line.
_CHANNEL_SAID = re.compile(r"\b(?P<c>text|call|email|e-mail|phone)\b (?:me|first)\b|\bmensaje de texto\b|\bllámenme\b|"
                           r"\bescr[ií]banme\b", re.I)


def channel_said(message: str) -> str | None:
    m = _CHANNEL_SAID.search(message)
    if not m:
        return None
    c = (m.group("c") or "").lower()
    if not c:
        return "text" if "texto" in m.group(0).lower() else "call" if "llám" in m.group(0).lower() else "email"
    return {"e-mail": "email", "phone": "call"}.get(c, c)


# D-19: Spanish ways to say a problem came back (English 'again' is already a gate signal).
_REPEAT_ES = re.compile(r"\bya pas[oó] antes\b|\botra vez\b|\bde nuevo\b|\bvolvi[oó] a\b|\bvuelve a\b|\bsigue "
                        r"(?:pasando|igual|fallando|sin)\b|\botra vez lo mismo\b|\bpor (?:segunda|tercera) vez\b", re.I)


def says_repeat_es(message: str) -> bool:
    return bool(_REPEAT_ES.search(message))


# ---- sprint 5 round 2 -----------------------------------------------------------------------------------------

# J-1: "please don't tell the property manager", "who will see this?" (privacy, not a request for a person)
_PRIVACY_ASK = re.compile(
    r"\b(?:don'?t|do not|dont|please don'?t|never) (?:tell|inform|share (?:this|it) with|let) (?:the |my |"
    r"anyone|anybody|"
    r"them|my landlord|the office)|\bkeep (?:this|it) (?:private|between us|secret|confidential|to yourself)|"
    r"\bwho (?:will|can|is going to|gets to) (?:see|read|know)|\bconfidential\b|\bno le (?:diga|digan|cuente|cuenten)|"
    r"\bque no se entere|\bno se lo digan\b", re.I)


def asks_privacy(message: str) -> bool:
    return bool(_PRIVACY_ASK.search(message))


# R-4: asking about, or acting for, another resident (roommate, friend, family). Routing only: the account-holder rule
# itself lives elsewhere and is not changed here.
_OTHER_RESIDENT = re.compile(
    r"\b(?:give|tell|show|send) me (?:his|her|their)\b|\bwhat (?:repairs?|requests?|work orders?) (?:he|she|"
    r"they) (?:has|"
    r"have|had)\b|\b(?:he|she) has (?:open|any)\b|\b(?:his|her) (?:phone|number|email|rent|balance|unit|"
    r"apartment number|"
    r"account|lease|requests?|repairs?|work orders?|ac|a/c) (?:request|status|is|paid)?|\bcall (?:him|her)\b|"
    r"\b(?-i:[A-Z][a-z]+)'s (?:unit|apartment|phone|number|rent|ac|a/c|repairs?|requests?|account|balance|email|"
    r"lease)\b|"
    r"\bwhat unit (?:does )?(?-i:[A-Z][a-z]+) (?:lives?|is)\b|\bwhere (?:does )?(?-i:[A-Z][a-z]+) live\b|"
    r"\b(?:his|her) (?:open |old |current |other )?(?:maintenance |repair )?(?:requests?|repairs?|work orders?|"
    r"tickets?)\b|"  # c01: "what about his open maintenance requests?"
    r"\bmy (?:roommate|neighbou?r|friend|boyfriend|girlfriend)'?s (?:phone|number|rent|account|requests?|repairs?|"
    r"balance|unit)\b", re.I)


def asks_about_other_resident(message: str) -> bool:
    return bool(_OTHER_RESIDENT.search(message))


# P-6: "did you save my email?", "can you put my phone on it?"
_SAVED_CONTACT = re.compile(
    r"\bdid you (?:save|keep|store|get|record|write down|take) my (?:email|e-mail|phone|number|cell|contact|address)|"
    r"\b(?:put|add|save|include|attach) my (?:phone|number|email|e-mail|cell)(?: number)?(?: \[(?:phone|email) "
    r"redacted\])? (?:on|to|in|with)\b|\b(?:can|could|will) you (?:save|keep|store|remember) my (?:number|email|phone|"
    r"contact)|\bguard(?:ó|aron|a) mi (?:correo|tel[eé]fono|n[uú]mero)", re.I)


def asks_saved_contact(message: str) -> bool:
    return bool(_SAVED_CONTACT.search(message))


# P-5 / J-2: "make it urgent", "please make it a priority"
_PRIORITY_ASK = re.compile(r"\bmake (?:it|this|that) (?:urgent|a priority|high priority|a rush|faster|quicker)|"
                           r"\bprioriti[sz]e\b|\bbump (?:it|this|that) up\b|\bexpedite\b|\bmark (?:it|this) (?:as )?"
                           r"urgent|\bhazlo urgente\b|\bh[aá]ganlo urgente\b|\bcon prioridad\b|\bes urgente\b", re.I)


def asks_for_priority(message: str) -> bool:
    return bool(_PRIORITY_ASK.search(message))


# P-2: adding something to a request that was already sent
_ADD_TO_SENT = re.compile(r"\b(?:can i |could i |i want to |i'?d like to |please |"
                          r"i need to )?(?:also )?add (?:that |this "
                          r"|a note that |on that |to (?:it|that|the request|my request) that )(?P<d>.{3,160})|"
                          r"\b(?:also )?include (?:that |this )(?P<d2>.{3,160})", re.I)


def detail_to_add(message: str) -> str | None:
    m = _ADD_TO_SENT.search(message)
    if not m:
        return None
    d = (m.group("d") or m.group("d2") or "").strip(" ?.!,")
    return (d[0].upper() + d[1:]) if d else None


# R-2: the part of a message that asks to switch to Spanish ("perdón, mejor en español.")
_SPANISH_CLAUSE = re.compile(r"[^.?!]*(?:\b(?:in|en) (?:spanish|espa[nñ]ol)\b|hablo espa[nñ]ol|habla espa[nñ]ol|"
                             r"speak spanish)[^.?!]*[.?!]?", re.I)


def strip_spanish_request(message: str) -> str:
    return _SPANISH_CLAUSE.sub(" ", message).strip()


# J-6 / R-3: the person says the problem came back ("third time this month", "AGAIN").
_STATED_REPEAT = re.compile(r"\b(?:second|2nd|third|3rd|fourth|4th|fifth|5th|\d+(?:st|nd|rd|th)) time\b|\bagain\b|"
                            # Sprint 6 fix round: "reported it twice", "for 2 weeks", "marked done but NOT fixed"
                            r"\b(?:reported|asked|called|complained|told you)(?: about)? (?:this|it|that)? ?(?:twice|"
                            r"(?:two|three|\d) times|already|before|last (?:week|month))\b|\b(?:for|over|in) "
                            r"(?:(?:two|three|four|\d+|a couple of|several) weeks|(?:a|one|two|\d+) months?)\b|"
                            r"\bmarked (?:it |my \w+ (?:request )?)?(?:as )?(?:done|fixed|complete|completed|closed|"
                            r"resolved)\b[^.?!]{0,30}\b(?:not|isn'?t|still|never)\b|\bclosed (?:it|the (?:ticket|"
                            r"request|work order)) without fixing\b|\bnever (?:got )?fixed\b|"
                            r"\b(?:tercera|segunda|cuarta) vez\b|"
                            r"\bkeeps? (?:happening|breaking|coming back)\b|\bhappened before\b|"
                            r"\bsame (?:problem|issue) "
                            r"(?:as|again)\b", re.I)


_NOT_REPEAT = re.compile(r"\b(?:answer|answering|repeat|repeating|say|saying|tell|telling|explain|explaining|type|"
                         r"typing|go through|going through)\b[^.?!]{0,25}\bagain\b|\bagain\?\s*$", re.I)


def states_repeat(message: str) -> bool:
    """The PROBLEM came back. "I'm not answering that again" is about the chat, not a repeat."""
    hit = _STATED_REPEAT.search(message)
    if hit and hit.group(0).lower() == "again" and _NOT_REPEAT.search(message):
        hit = None
    return bool(hit) or says_repeat_es(message)


# ---- sprint 5.1: inputs to the dialogue-act step (app/dialogue.py) ---------------------------------------------
# Each detector here answers one narrow question; app/dialogue.classify_turn combines them with the older ones.

# A-3: a cancel stated inside a longer sentence ("actually nevermind. dont send it. last time they made it worse").
_STRONG_CANCEL = re.compile(r"\b(?:never ?mind|nevermind|nvm|(?:don'?t|dont|do not) (?:send|submit|file) "
                            r"(?:it|that|this|"
                            r"anything|the (?:request|note|tour request|repair request))|cancel (?:it|that|this|the "
                            r"(?:request|note))|no lo env[ií]e|no la env[ií]e)\b", re.I)


def cancels_in_sentence(message: str) -> bool:
    return bool(_STRONG_CANCEL.search(message))


# D-3 / B-2: bringing back a card the person declined, in natural words.
_RESTORE_WORDS = re.compile(
    r"\b(?:send|submit) (?:it|that|the (?:note|request|repair request|tour request))(?: \w+)? after all\b|"
    r"\bafter all\b|\bundo\b|\bwrong button\b|\b(?:pressed|hit|tapped|clicked) (?:the )?(?:wrong|don'?t send|cancel)"
    r"\b|\b(?:i )?(?:want|need) (?:it|that|the (?:\w+ )?request|my (?:\w+ )?request) back\b|"
    r"\bbring (?:it|that|the (?:\w+ )?(?:request|note)|my (?:\w+ )?request) back\b|"
    r"\bbring back (?:the|my) (?:\w+ )?(?:request|note|card)\b|\b(?:put|get) (?:it|that) back\b|\brestore\b|"
    r"\bdidn'?t mean to (?:cancel|press|decline|say no)\b|\bchanged my mind\b|\bi do (?:want|need) (?:it|to send)\b|"
    r"\bun-?cancel\b|\benv[ií]elo\b|\bs[ií],? env[ií]", re.I)


def asks_to_restore(message: str) -> bool:
    if not _RESTORE_WORDS.search(message):
        return False
    return not _STRONG_CANCEL.search(message) and not re.search(r"\b(?:don'?t|dont|do not) (?:send|want)\b",
                                                                 message, re.I)


# W-3: an explicit instruction to send. A bare "yes"/"ok"/"sure"/"sí" is not one; "send it", "yes send it",
# "submit it", "go ahead and send", "envíelo" are.
_EXPLICIT_SEND = re.compile(r"\b(?:send|submit)\b|\benv[ií]e(?:lo|la)?\b|\benv[ií]al[oa]s?\b|"
                            r"\bm[aá]nd(?:el|al)[oa]s?\b", re.I)


_ES_SEND = re.compile(r"^\W*(?:s[ií]|ok|vale|claro)?[\s,.!]*"
                      r"(?:env[ií]e?(?:lo|la)s?|env[ií]al[ao]s?|m[aá]nd(?:e|a)(?:lo|la)s?)"
                      r"(?:\s+por favor|\s+ya)?"
                      r"[\s.!]*$", re.I)


# Sprint 7: ONE consent vocabulary for every card kind. The whole message must be a command to send what is on
# screen ("yes please send it", "sure, send it over", "you can send it", "send the note now", "just send whatever you
# need to send"), so the command never becomes a field value and "send me the pool hours" is not consent.
_SEND_COMMAND = re.compile(
    r"^\W*(?:(?:yes|yeah|yep|yup|ok(?:ay)?|sure|alright|all right|fine|please|pls|go ahead(?: and)?|you can|you may|"
    r"wait|no|oh|um+|hmm+|on second thought|do|ok fine|"
    r"can you|could you|just|and|then|actually|now|great|perfect|s[ií]|vale|claro|por favor|ya)\W+)*"
    r"(?:send|submit|file|env[ií]e(?:lo|la|las|los)?|env[ií]al[oa]s?|m[aá]nd(?:e|a)(?:lo|la|las|los)?)"
    r"(?:\s+(?:it|that|this|them|the (?:note|request|repair(?: request)?|tour(?: request)?|message|card|form|"
    r"one|thing)|my (?:note|request)|over|in|through|along|now|right now|already|off|please|pls|por favor|ya|"
    r"ahora|thanks|thank you|whatever (?:you need|is needed|you have)(?: to send)?|it all|everything|"
    r"to (?:the )?(?:office|team|leasing(?: team)?|maintenance)|ahead|anyway|then))*\W*$", re.I)


def is_explicit_send(message: str) -> bool:
    return (is_affirmative(message) and bool(_EXPLICIT_SEND.search(message))) or bool(_ES_SEND.match(message)) or \
        bool(_SEND_COMMAND.match(message)) and len(message.split()) <= 12


# A-2 / C-3: complaints about the assistant itself ("I already told you", "why do you keep asking", "like i said").
_META_COMPLAINT = re.compile(
    r"\bi (?:already |just )?(?:told|said|gave|answered)(?: you| that| this| it)?\b(?! (?:to|in) )|"
    r"\blike i (?:said|told you)"
    r"\b|\bas i (?:said|told you|mentioned)\b|\bi said\b|\bwhy (?:do|are) you (?:keep )?(?:asking|ask)\b|"
    r"\bkeep asking\b|\bstop asking\b|\bwhy do you keep\b|\bya (?:le|te) (?:dije|lo dije)\b|\bcomo (?:le|te) dije\b|"
    r"\bit'?s (?:literally |already )?on (?:your|the|my) record\b", re.I)


def is_meta_complaint(message: str) -> bool:
    return bool(_META_COMPLAINT.search(message))


# Honest answers to questions asked while a card is open (A-4, A-5, A-12, B-7, D-8). Kinds, in priority order.
_QUESTION_KINDS: list[tuple[str, re.Pattern[str]]] = [
    # N-5: "so the technician is coming today right? just confirm" -> an explicit no, never the card text
    ("confirm_visit", re.compile(
        r"\b(?:tech\w*|someone|somebody|maintenance|they|a person|the plumber|the electrician)\b(?: is| are|'s)? "
        r"(?:coming|going to come|gonna come|showing up|on (?:the|their) way)\b[^.!]{0,30}(?:\?|\bright\b|"
        r"\bconfirm\w*)|\bjust confirm (?:the|that|it|a) "
        r"(?:visit|time|appointment)\b", re.I)),
    # N-3: "how many tour requests do i have now?"
    ("count", re.compile(r"\bhow many (?:tour |repair |maintenance )?(?:requests?|tours?|notes?|tickets?|work orders?)"
                         r"\b|\bcu[aá]ntas solicitudes\b", re.I)),
    ("who_sees", re.compile(
        r"\bwho (?:actually |else |all )?(?:sees|reads|gets|looks at|will see|can see|would see|is going to see)\b|"
        r"\bwill (?:my |the )?neighbou?rs? (?:find out|know|see|hear|be told)|\b(?:find out|know) (?:it was me|"
        r"(?:that )?i (?:complained|reported|said))|\bqui[eé]n (?:lo |la )?(?:ve|va a ver|lee)\b|"
        r"\bse va a enterar (?:mi )?vecin", re.I)),
    ("what_send", re.compile(
        r"\bwhat (?:does|will|would) (?:the )?(?:send|sending)(?: button)? (?:do|mean)\b|\bwhat (?:is|does|means) "
        r"['\"]?check,? (?:then|and) send\b|\bwhat happens (?:if|when|after) i (?:press|hit|tap|click|push) "
        r"(?:send|the button|it)\b|\bwhat does (?:pressing|tapping) (?:send|it) do\b|\bqu[eé] (?:significa|hace|pasa "
        r"si pulso) enviar\b|\bpara qu[eé] (?:es|sirve) (?:el bot[oó]n )?enviar\b", re.I)),
    ("cost", re.compile(
        r"\bis (?:it|this|that|sending|the request|the tour) free\b|\bdoes (?:it|this|that|sending) cost\b|"
        r"\bcost (?:me )?(?:any )?money\b|\bam i (?:paying|being charged)\b|\bdid i (?:just )?(?:pay|buy|get "
        r"charged)\b|\b(?:do|will) i (?:have to )?pay (?:for (?:this|it|that|sending)|anything)\b|"
        r"\bis there a (?:fee|charge) (?:for|to) (?:this|sending|send|the request)\b|\bvoy a pagar\b|"
        r"\bcuesta (?:algo|dinero)\b|\bes gratis\b|\bme (?:van a )?cobra", re.I)),
    ("priority", re.compile(
        r"\b(?:so )?is (?:it|this|that|my (?:\w+ )?request) (?:marked )?(?:urgent|a priority|high priority)(?! to\b)"
        r"(?: now| yet)?\b|\bdid (?:you|it) (?:get )?mark(?:ed)? (?:it |this )?(?:as )?urgent\b|"
        r"\bis (?:it|this) going to be (?:urgent|prioriti[sz]ed)\b|\bya es urgente\b", re.I)),
    ("timing", re.compile(
        r"\bwill (?:a |the |my )?(?:manager|someone|somebody|anyone|they|the office|a person|staff|a tech|maintenance)"
        r" (?:actually |really |ever )?(?:call|text|email|contact|come|get back|reach|show up)\b|"
        r"\b(?:is|are) (?:a |the )?(?:manager|someone|somebody|anyone|they|the office|staff|a tech|maintenance) "
        r"(?:actually |really )?(?:going to|gonna) (?:call|text|email|contact|come|reach)\b|"
        r"\bwhen (?:will|do|does) (?:someone|anyone|they|a manager|the office|maintenance|a tech) (?:call|come|"
        r"contact|get back|show up)\b|\bwho sees this and when\b|\bblack hole\b|\bme van a llamar\b", re.I)),
    ("gate_code", re.compile(r"\b(?:gate|door|lockbox|access|building|entry|front door) code\b|"
                             r"\bc[oó]digo (?:de la puerta|del port[oó]n|de acceso)\b", re.I)),
    ("renewal", re.compile(r"\brenew\w*|\blease (?:is )?(?:up|end\w*|expir\w*)\b|\bmy lease up\b|"
                           r"\bwhen (?:is|does) my lease\b|\brenovar\b|\brenovaci[oó]n\b", re.I)),
    ("name", re.compile(r"\b(?:do|did|will) (?:you|they) (?:need|want) my (?:full )?name\b|\bshould i (?:give|tell) "
                        r"(?:you )?my name\b|\bnecesita(?:s|n)? mi nombre\b", re.I)),
    ("budget", re.compile(r"\bwhat (?:did|have) you (?:put|write|wrote|note|noted|record|recorded|got)\w* (?:down )?"
                          r"(?:for )?(?:my )?budget\b|\bis my budget (?:on|in|included|noted)\b|\bdoes (?:it|the "
                          r"(?:request|card|note)) (?:include|have|show|mention) my budget\b", re.I)),
    ("card_status", re.compile(
        r"\bis (?:the |my )?(?:\w+ )?(?:request|repair|tour|note) still (?:going in|going|happening|on)\b|"
        r"\bstill going in\b|\bgoing in too\b|\bwhat happened to (?:my|the) (?:\w+ ){0,2}(?:request|note|thing)\b|"
        r"\bwhere did my (?:\w+ ){0,2}(?:thing|request|note) go\b|\bwhat happend?\b|"
        r"\bis (?:someone|anyone|somebody) coming (?:for|about) (?:my|the)\b|"
        r"^\W*(?:so\W+)?(?:is|was|has) (?:it|this|that) (?:been )?(?:sent|saved|submitted|in)(?: yet)?\W*$|"
        r"\bdid (?:my|the) (?:\w+ ){0,2}(?:request|note) (?:send|go (?:in|through)|get sent)\b", re.I)),
]


_NEIGHBOR_WORD = re.compile(r"\bneighbou?rs?\b|\bvecin", re.I)


def mentions_neighbor(message: str) -> bool:
    return bool(_NEIGHBOR_WORD.search(message))


def question_kinds(message: str) -> list[str]:
    """Every kind of side question in a message (see _QUESTION_KINDS), in priority order."""
    return [k for k, pat in _QUESTION_KINDS if pat.search(message)]


def question_kind(message: str) -> str | None:
    """The main kind of side question in a message, or None."""
    return next(iter(question_kinds(message)), None)


# C-2: a budget the person states ("my max is $1,600", "under 1500 a month", "budget is around 1800").
_BUDGET = re.compile(
    r"\b(?P<w>max(?:imum)?|budget|under|below|up to|no more than|less than|around|about|at most|tops)\b"
    r"(?:\s+(?:is|of|would be|=|:))?(?:\s+(?:around|about|like|roughly))?\s*\$?\s?(?P<n>\d{1,2},?\d{3})\b|"
    r"\$\s?(?P<n2>\d{1,2},?\d{3})\s*(?:a month|/\s?mo(?:nth)?|per month|monthly|max|tops)?", re.I)


def extract_budget(message: str) -> str | None:
    """'Up to $1,600 a month' / 'Around $1,800 a month'. A price QUESTION ('is it $1,600?') is not a budget."""
    m = _BUDGET.search(message)
    if not m:
        return None
    if m.group("n2") and not re.search(r"\b(?:max|budget|under|afford|spend|range|tops|(?:a|per) month|monthly)\b|"
                                       r"/\s?mo\b", message, re.I):
        return None  # "can you beat $1,150" is a price claim, not the person's budget
    if re.search(r"\bbeat\b|\bmatch\b|\bmonths? free\b|\badvertis|\blisted\b|\bwebsite\b", message, re.I):
        return None
    if re.search(r"\bhow much\b|\bwhat(?:'s| is) the (?:rent|price)\b|\bcheapest\b", message, re.I) and \
            not re.search(r"\b(?:max|budget|under|up to|no more than)\b", message, re.I):
        return None
    num = int((m.group("n") or m.group("n2") or "0").replace(",", ""))
    if not 300 <= num <= 20000:
        return None
    word = (m.group("w") or "").lower()
    lead = "Around" if word in ("around", "about") or re.search(r"\b(?:around|about|roughly)\b", m.group(0), re.I) \
        else "Up to"
    # echo the person's own words: never add a "$" or "a month" they didn't say (it would read as a quoted price)
    cur = "$" if "$" in m.group(0) else ""
    per = " a month" if re.search(r"\b(?:a|per) month\b|/\s?mo\b|\bmonthly\b|\ba mo\b", message, re.I) else ""
    return f"{lead} {cur}{num:,}{per}"


# C-6: cities in the demo area, recognised in any capitalisation inside a longer sentence.
_CITIES = [("Ann Arbor", r"ann ?arbor|a2"), ("Ypsilanti", r"ypsilanti|ypsi"), ("Detroit", r"detroit"),
           ("Lansing", r"lansing"), ("Orlando", r"orlando"), ("Tampa", r"tampa")]


def city_in(message: str) -> str | None:
    for name, pat in _CITIES:
        if re.search(rf"\b(?:{pat})\b", message, re.I):
            return name
    return None


# C-4: a calendar date for the tour itself ("can the tour be on dec 6 instead").
_TOUR_DATE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}"
                        r"(?:st|nd|rd|th)?\b",
                        re.I)


def extract_tour_date(message: str) -> str | None:
    if _MOVEISH.search(message):
        return None  # "move in dec 1" is the move-in date, kept apart from the tour
    m = _TOUR_DATE.search(message)
    if not m or _OLD_VALUE.search(message[:m.start()]):
        return None
    v = m.group(0)
    return v[0].upper() + v[1:]


# C-4: "sunday afternoon would work too" adds an option instead of replacing the first one.
_ADDITIVE = re.compile(r"\b(?:too|as well|also works?|also good|would (?:also )?work too|either)\b|\bor\b(?! not)",
                       re.I)


def is_additive(message: str) -> bool:
    return bool(_ADDITIVE.search(message)) and not re.search(r"\binstead\b|\bnot\b|\bchange\b|\bswitch\b", message,
                                                             re.I)


# A-3 / W-12: "change the contact preference to call", "i want a phone call this time not a portal message".
_CONTACT_CHANGE = re.compile(
    r"\b(?:change|switch|update|set|make) (?:the |my )?contact(?: preference| method| pref)?(?: to)? (?:a )?(?P<c>call|"
    r"phone|text|email|e-mail)\b|\bi (?:want|need|prefer|'?d (?:rather|prefer|like)) (?:a )?(?P<c2>phone call|call|"
    r"text|email)\b(?! (?:the|my|a) (?:manager|office|person))|\b(?P<c3>call|text|email) me (?:instead|this time)\b|"
    r"\bprefer (?:a |to be )?(?P<c4>call|called|text|texted|email|emailed)\b", re.I)


def contact_change(message: str) -> str | None:
    """The contact channel the person now wants ('call', 'text', 'email'), or None."""
    m = _CONTACT_CHANGE.search(message)
    if not m:
        return None
    c = next(g for g in (m.group("c"), m.group("c2"), m.group("c3"), m.group("c4")) if g).lower()
    return "call" if "call" in c or c == "phone" else "text" if c.startswith("text") else "email"


# B-5: repairs outside the home (front gate, parking lot, lobby): no room and no entry permission needed.
_COMMON_AREA = re.compile(r"\b(?:front |main |entry |parking |community |pool |building )?gate\b|\bparking (?:lot|"
                          r"garage|deck)\b|\blobby\b|\belevator\b|\bmail ?(?:room|boxes|box area)\b|\bstairwell\b|"
                          r"\bcommon area\b|\bclubhouse\b|\bpool\b|\bgym\b|\bdumpster\b|\b(?:not in|outside) my "
                          r"(?:apt|apartment|unit)\b|\bport[oó]n\b|\bestacionamiento\b", re.I)


def is_common_area(message: str) -> bool:
    return bool(_COMMON_AREA.search(message))


# D-4: no content about the problem ("can you fix it", "the thing again", "something is wrong").
_NO_CONTENT_ISSUE = re.compile(
    r"^\W*(?:(?:hi|hey|hello|so|um+|uh+)\W+)?(?:can|could|will|would) (?:you|someone|somebody|u|y'?all) "
    r"(?:please |pls )?"
    r"(?:fix|repair|look at|check|help with|take care of|come fix) (?:it|this|that|something|my thing)\W*"
    r"(?:please|pls)?\W*$|^\W*(?:the |my )?(?:thing|it|that|this|stuff)(?: again| still)?\W*$|"
    r"^\W*(?:something(?:'s| is)? (?:wrong|broken|off)|i have a problem|there'?s a problem|it'?s broken)\W*$", re.I)


def no_issue_content(message: str) -> bool:
    return bool(_NO_CONTENT_ISSUE.match(message.strip()))


# D-5: a stated repeat counts only for a NAMED problem ("the dishwasher won't drain again"), never "the thing again".
def states_named_repeat(message: str) -> bool:
    return states_repeat(message) and not no_issue_content(message) and bool(
        appliance_in(message) or _ISSUE_HINT.search(message) or extract_location(message))


# A-6 / B-1: words that point at a request already open ("still leaking", "same one i already reported").
_BACK_TO = re.compile(r"^\W*(?:ok(?:ay)?|so|and|anyway)?[\s,]*back to (?:the |my )?(?P<thing>[\w /-]{2,30}?)\W*$", re.I)


def back_to_topic(message: str) -> str | None:
    """'ok back to the fan' -> 'fan' (returning to something already discussed)."""
    m = _BACK_TO.match(message)
    return m.group("thing") if m else None


_EXISTING_REF = re.compile(r"\bstill\b|\bsame (?:one|problem|issue|thing|request)\b|\balready (?:reported|told|"
                           r"submitted|sent|have (?:one|a request))\b|\bi already have one\b|\b(?:my|the) (?:\w+ )?"
                           r"(?:request|work order|ticket) (?:is )?(?:already )?open\b|\b(?:existing|open) (?:one|"
                           r"request)\b|\bmy (?:\w+ ){0,2}request\b", re.I)


def refers_to_existing(message: str) -> bool:
    return bool(_EXISTING_REF.search(message))


# C-7: accepting the offered leasing note in free text ("ok send those questions to the leasing team pls").
_ACCEPT_QUESTIONS = re.compile(r"\b(?:send|pass|forward|give|ask)\b[^.?!]{0,25}\b(?:those|these|the|my|that|this)? ?"
                               r"(?:questions?|it|them|that)\b[^.?!]{0,10}\b(?:to|with)\b[^.?!]{0,8}\b(?:the )?"
                               r"(?:leasing|office|team|staff)|\bask (?:them|the leasing team|leasing|the office) "
                               r"(?:for me|those|that)\b|\b(?:yes|ok|sure),? (?:send|pass) (?:them|those|it) (?:on|"
                               r"along)\b", re.I)


def accepts_question_note(message: str) -> bool:
    return bool(_ACCEPT_QUESTIONS.search(message))


# W-12: extra details for the visit ("add that there's a dog inside", "note: dog in unit", "keep the door shut").
_VISIT_NOTE = re.compile(r"\b(?:dog|dogs|cat|cats|pet|pets|puppy|kitten)\b|\bkeep (?:the )?door (?:shut|closed)\b|"
                         r"\bperro\b|\bgato\b|\bmascota\b", re.I)
_NOTE_LEAD = re.compile(r"^\W*(?:note|nota)\s*:\s*(?P<d>.{3,160})$|\b(?:add|note|put|write|mention) (?:that |down "
                        r"that |in the note that )?(?P<d2>.{3,160})", re.I)


def visit_note(message: str) -> str | None:
    """A detail for the technician that isn't the problem itself (pets, keep the door shut), or None."""
    if not _VISIT_NOTE.search(message):
        return None
    m = _NOTE_LEAD.search(message)
    text = (m.group("d") or m.group("d2")) if m else next(
        (c for c in re.split(r"[,.;!?]+|\bbut\b|\btho(?:ugh)?\b", message) if _VISIT_NOTE.search(c)), message)
    text = re.sub(r"^\W*(?:and|also|but|plus)\W+", "", text.strip(" ,.;!?"), flags=re.I).strip()
    text = re.sub(r"\s+(?:tho|though)$", "", text, flags=re.I)
    return (text[0].upper() + text[1:])[:160] if text else None


# E-7: asking for an ordinary ticket without restating the problem ("just put in a normal repair ticket").
_TICKET_ASK = re.compile(r"\b(?:put in|file|make|open|submit|create|do|start) (?:a |an |the )?(?:normal |regular |"
                         r"standard |non-?emergency |ordinary )?(?:repair |maintenance )?(?:ticket|request|work order)"
                         r"\b", re.I)


def asks_for_plain_ticket(message: str) -> bool:
    return bool(_TICKET_ASK.search(message)) and not _ISSUE_HINT.search(re.sub(r"\bnot an? emergency\b", "",
                                                                                message, flags=re.I))


# j-safe-impersonation: asking for account details (balance, what's on file, rent amount) or claiming to be the
# account holder in chat. Used only when no matching account is signed in; it unlocks nothing.
_ACCOUNT_ASK = re.compile(
    r"\b(?:my|her|his|their|the) (?:current )?(?:balance|account balance|rent amount|rent balance|amount due|"
    r"account (?:details|info\w*)|payment history)\b|\bwhat(?:'s| is) on file\b|\bread me (?:what|my|her|his)\b|"
    r"\bwhat do i owe\b|\bi'?m (?:her|him)\b|\bwhen does my lease (?:end|expire|run out)\b.*\b(?:balance|rent)\b|"
    r"\bmi saldo\b|\bcu[aá]nto debo\b", re.I)


def claims_account_access(message: str) -> bool:
    return bool(_ACCOUNT_ASK.search(message))
