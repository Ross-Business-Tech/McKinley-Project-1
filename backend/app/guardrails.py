"""The small deterministic policy layer: what the language model is never trusted with.

1. Consent: a request is saved only by the Send button or an explicit typed send ("send it"). A bare "yes", "ok" or a
   model proposal never saves anything.
2. Privacy: requests for another resident's data, a claimed identity that isn't the signed-in account, or a claimed
   staff/admin role are refused here, before the model is asked (the model never sees other residents' data anyway;
   this keeps the refusal short and stops the signed-in resident's own records being shown as a "fallback").
3. Property information: only approved knowledge-base answers (labelled samples in a supervised local demo).

Safety (emergencies) is NOT here: it is `app.risk` + `app.emergency`, run on every turn before anything else.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

KB_PATH = Path(__file__).resolve().parent / "content" / "knowledge_base.json"

# ---- 1. consent ---------------------------------------------------------------------------------------------------
# Remediation P2: "pls" / "plz" are the same politeness as "please" ("ok pls send it"). Still only an explicit send
# instruction for the card: a bare "ok", "pls" or "sounds good" never matches.
_PLEASE = r"(?:please|pls|plz|plse|kindly)"
_SEND = re.compile(rf"^\W*(?:(?:ok(?:ay)?|kk|yes|yeah|yep|sure|great|perfect|looks good|that'?s (?:right|correct)|"
                   rf"{_PLEASE}|alright)[\s,.!]+)*(?:{_PLEASE}\s+)?(?:go ahead and\s+)?(?:send|submit|file)\s+(?:it|"
                   rf"that|this|the (?:request|note|repair request|tour request))(?:\s+(?:now|{_PLEASE}|in|over|after "
                   rf"all|thanks|thank you|thx))*\W*$|"
                   rf"^\W*(?:(?:s[ií]|ok|vale|bueno|por favor)[\s,.!]+)*(?:env[ií]el[oa]|m[aá]ndel[oa])"
                   rf"(?:\s+(?:ya|ahora|por favor|gracias))*\W*$", re.I)
_QUESTION = re.compile(r"[?¿？﹖‽⁇⁈⁉؟]")


_SEPARATE = re.compile(r"\b(?:a |it'?s a |it is a )?(?:different|separate|another|new|second) (?:problem|issue|"
                       r"request|repair|one)\b|\botro problema\b|\bsolicitud aparte\b", re.I)


def says_separate(message: str) -> bool:
    """'it's a different problem, save it as a new request': consent for a second, similar repair record."""
    return bool(_SEPARATE.search(message or ""))


def explicit_send(message: str) -> bool:
    """'send it', 'ok please submit the request', 'envíelo'. Never 'yes', 'ok', 'sounds good'. PR #18 review: never a
    question ("send it?", "¿envíelo?"): asking about sending is not consent; the card waits for Send or a clear reply.
    """
    m = message or ""
    return not _QUESTION.search(m) and bool(_SEND.search(m))


# ---- 2. privacy -----------------------------------------------------------------------------------------------------
_DATA = (r"(?:(?:open |old |past |previous )?(?:maintenance |repair )?(?:requests?|work orders?|tickets?|repairs?|"
         r"histor(?:y|ies)|records?)|apartment details|account(?: details)?|contact (?:info|details)|phone numbers?|"
         r"emails?|names?|balances?|leases?|details|info(?:rmation)?|units?|addresses)")
_OTHER = (r"(?:my (?:neighbou?r|roommate|flatmate|friend|partner|landlord)(?:'?s)?|(?:his|her|their)|"
          r"(?!(?:What|That|It|There|Here|Where|Who|How|He|She|Let|This|Today|McKinley|Mckinley)'s)"
          r"(?-i:[A-Z][a-z]+)'s|other (?:residents|tenants|people)'?s?|every(?:one|body)'?s|all (?:the )?residents'?)")
_PATTERNS = {
    "role": re.compile(r"\byou(?:'re| are) now\b[^.]{0,40}\b(?:admin(?:istrator)?|staff|manager|developer|root)\b|"
                       r"\b(?:act|behave|pretend)\s+(?:as|like)\s+(?:an?|the)?\s*(?:mckinley\s+)?(?:admin(?:istrator)?|"
                       r"staff|(?:property )?manager)\b|\b(?:i'?m|i am)\s+(?:an?|the)\s+(?:mckinley\s+)?"
                       r"(?:admin(?:istrator)?|staff member|property manager)\b|"
                       r"\b(?:admin|developer) (?:mode|access)\b",
                       re.I),
    "other": re.compile(rf"\b{_OTHER}\s+(?:\w+\s+){{0,2}}{_DATA}\b|\b(?:list|show|give|export)\b(?:\s+\w+){{0,2}}?\s+"
                        r"(?:all|every)\b(?:\s+the)?\s+(?:residents?|tenants?|names|accounts?)\b", re.I),
}
_SELF_NAME = re.compile(r"\b(?:i'?m|i am|this is|my name is)\s+(?-i:([A-Z][a-z]{1,20}))\b(?!['’]s)", re.I)
_RESIDENT_ID = re.compile(r"\b(R\d{3})\b", re.I)
_NOT_NAMES = {"Sorry", "Not", "Just", "Here", "Back", "Fine", "Good", "Still", "Locked", "New", "Moving", "Looking",
              "Trying", "Ready", "Done", "Sure", "So", "Really", "Very", "Also", "Actually", "Currently", "Having",
              "Getting", "In", "At", "On", "From", "Worried", "Calling", "Writing", "Interested", "Outside", "Home"}

REFUSAL = {
    "role": ("I can't take on a staff or admin role, so I can't list residents or anyone's history. I can help with "
             "your own questions here.",
             "No puedo actuar como personal ni administrador, así que no puedo listar residentes ni historiales."),
    "identity": ("This chat is signed in as {name}, so I can only help with {name}'s own account. Another name or "
                 "resident ID doesn't switch accounts here.",
                 "Este chat tiene la sesión de {name}, así que solo puedo ayudar con la cuenta de {name}. Otro nombre "
                 "o ID de residente no cambia de cuenta aquí."),
    "guest_identity": ("Saying who you are in chat doesn't unlock any account details here, so there's nothing I "
                       "can look up. I can still help you put a note together for the office.",
                       "Decir quién es en el chat no desbloquea datos de ninguna cuenta. Igual puedo ayudarle a "
                       "preparar una nota para la oficina."),
    "other": ("I can't share another resident's requests or details.",
              "No puedo compartir las solicitudes ni los datos de otro residente."),
}


def denied(message: str, own_name: str | None, own_id: str | None) -> str | None:
    """'role' | 'identity' | 'other' | None. Only chooses a refusal; access itself is enforced by the scoped store."""
    if _PATTERNS["role"].search(message):
        return "role"
    ids = {m.upper() for m in _RESIDENT_ID.findall(message)}
    if ids and (own_id or "").upper() not in ids:
        return "identity"
    m = _SELF_NAME.search(message)
    if m and m.group(1) not in _NOT_NAMES and (not own_name or m.group(1).lower() != own_name.lower()) and \
            re.search(r"\b(?:my|show|see|check|look up|what)\b", message, re.I):
        return "identity"
    if _PATTERNS["other"].search(message):
        return "other"
    return None


# The same refusal twice in a row: a shorter line, so the conversation doesn't loop on one long sentence.
REFUSAL_AGAIN = ("As I said, I can only help with this account's own information here.",
                 "Como le dije, aquí solo puedo ayudar con la información de esta cuenta.")


def refusal(reason: str, lang: str, name: str | None, previous_reply: str = "") -> str:
    key = "guest_identity" if reason == "identity" and not name else reason
    text = REFUSAL[key][1 if lang == "es" else 0].format(name=name or "")
    return REFUSAL_AGAIN[1 if lang == "es" else 0] if previous_reply.startswith(text) else text


# ---- 4. claims in a model reply that only the backend can make true ----------------------------------------------
# The model writes the words; the backend decides what happened. A sentence that states a save, an identity/permission
# change, a reference, or a piece of the person's history is checked against this turn's backend state.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_COMPLETED = re.compile(r"\b(?:saved|submitted|sent|filed|forwarded|logged|recorded|passed (?:it )?(?:on|along)|"
                        r"with (?:the )?(?:office|staff|team|maintenance|manager) now)\b", re.I)
_NOT_DONE = re.compile(r"\b(?:not|n'?t|never|yet|once|when|after|if|until|before|press|tap|pressing|tapping|to save|"
                       r"to send|can|could|will|would|ready|want|like)\b", re.I)
_IDENTITY = re.compile(r"\b(?:signed in as|logged in as|switched (?:you|your account|accounts?|to)|(?:you'?re|you are) "
                       r"now (?:an? )?(?:admin\w*|staff|manager|signed in|verified)|"
                       r"(?:granted|gave) you (?:admin|staff|access)|"
                       r"updated your (?:account|permissions|role))\b", re.I)
_HISTORY = re.compile(r"\b(?:before|previous(?:ly)?|last (?:time|week|month|year)|again|\d+ times|history|on (?:your )?"
                      r"record|reported|fixed|repaired|still open|open request)\b", re.I)
_REF = re.compile(r"\b(?:DEMO-[A-Z]+-\d+|I\d{3})\b")


def unsupported_claims(reply: str, *, saved_refs: set[str], known_refs: set[str], history_text: str,
                       own_name: str | None, saved_now: bool = False) -> list[str]:
    """`saved_refs`: records that really exist for this person; `saved_now`: something was saved this turn."""
    from app.utterance import things
    out = []
    known_things = things(history_text)
    for sent in _SENTENCE.split(reply or ""):
        refs = set(_REF.findall(sent))
        if refs - known_refs:
            out.append(f"unknown reference {sorted(refs - known_refs)}")
        elif _COMPLETED.search(sent) and not _NOT_DONE.search(sent) and not (
                (refs & saved_refs) or (saved_now and not refs)):
            out.append("claims something was saved or sent")
        if _IDENTITY.search(sent) and not (own_name and own_name.lower() in sent.lower()):
            out.append("claims an identity or permission change")
        if _HISTORY.search(sent) and (objs := things(sent)) and not objs & known_things and not refs:
            out.append(f"history not on record: {sorted(objs)}")
    return out


# ---- 3. property information -----------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _kb() -> list[dict[str, Any]]:
    return json.loads(KB_PATH.read_text(encoding="utf-8")).get("topics", [])


def property_facts(samples: bool = False) -> str:
    """Approved answers the model may use (and, in a supervised local demo, clearly labelled sample answers)."""
    out = []
    for t in _kb():
        if t.get("status") == "approved" and t.get("answer"):
            out.append(f"- {t['label']}: {t['answer']}")
        elif samples and t.get("sample_answer"):
            out.append(f"- {t['label']} (SAMPLE, made-up; say it is an example): {t['sample_answer']}")
        else:
            out.append(f"- {t['label']}: no approved answer; say you don't have it and offer a note for the office")
    return "\n".join(out)


# ---- 4. legal / fair housing (acceptance MN9) ------------------------------------------------------------------------
# The assistant never decides what the law requires, allows or prohibits, and never decides accommodation, assistance-
# animal, eligibility or discrimination questions: those go to people. A reply that states such a conclusion is
# replaced by a referral. The wording comes from the knowledge base topic "fair_housing": its `answer` once McKinley
# approves one, otherwise the PROVISIONAL `pending_reply` (team draft), and the status says which one was shown.
_LEGAL_CONCLUSION = re.compile(
    r"\b(?:fair housing|federal|state|local|the)? ?(?:law|laws|act|fha|ada|hud)\b[^.?!]{0,40}?\b(?:prohibits?|"
    r"requires?|allows?|permits?|forbids?|protects?|bans?|says|means|lets)\b|"
    r"\b(?:by|under|against) (?:the )?(?:law|fair housing(?: law| rules| act)?|federal law|state law|the fha|"
    r"the ada)\b|"
    r"\blegally\b[^.?!]{0,30}?\b(?:can(?:not|'t)?|must|required|allowed|entitled|have to|obligated|permitted)\b|"
    r"\b(?:is|are|would be|it'?s|that'?s) (?:not )?(?:illegal|unlawful|legal|a fair housing violation)\b|"
    r"\byou (?:have|'ve got|are entitled to) (?:a |the )?(?:legal )?right to\b|"
    r"\b(?:service|assistance|support|emotional support) (?:animals?|dogs?|cats?)\b[^.?!]{0,60}?(?:\bnot (?:a |"
    r"considered |treated as )?pets?\b|\b(?:can(?:not|'t)|may not|won'?t|don'?t|do not|aren'?t|are not|isn'?t|is not)"
    r" (?:be )?(?:charged|required to pay|subject to|have to pay)\b|\bexempt\b)|"
    r"(?:\b(?:are|is)|'re|'s) (?:not )?(?:entitled|eligible) (?:to|for) (?:an? )?(?:reasonable )?accommodation",
    re.I)

# Describing a community by who lives there (familial status, age, origin...) is steering, whatever the question was.
_RESIDENT_PROFILE = re.compile(
    r"\b(?:fewer|more|lots of|mostly|mainly|largely|primarily|many|a lot of|full of|not many|very few|few|plenty of)"
    r"\s+(?:\w+\s+)?(?:families|kids|children|seniors|elderly(?: people)?|retirees|students|young (?:people|"
    r"professionals|couples)|older (?:people|adults|residents)|immigrants|singles)\b|"
    r"\b(?:residents|tenants|neighbou?rs|people (?:who live|living) (?:there|here))"
    r"(?:\s+(?:there|here|at \w+(?: \w+)?))?\s+(?:are|tend to be)\s+(?:mostly|"
    r"mainly|largely|primarily|generally|older|younger)\b|\b(?:family|kid|child)[- ]free\b|\badults?[- ]only\b", re.I)
# Review (Copilot, PR #20): the same determinations without a named law ("landlords must waive pet rent for service
# animals", "the property is obligated to approve this accommodation"), in English and Spanish. A decision verb AND an
# accommodation-type object are both required in the sentence, so ordinary instructions ("you must press Send", "the
# leasing team must confirm the time", "pets must be on a leash") are not matched.
_OBJ = (r"(?:accommodat\w*|modification\w*|animals?|dogs?|cats?|pets?|rent|deposits?|fees?|charges?|ramps?|grab bars?|"
        r"wheelchairs?|disabilit\w*|requests?|parking|esas?)")
_SUBJ = (r"(?:landlords?|owners?|housing providers?|(?:the |this |your |that )?(?:property|properties|management|"
         r"community|communities|building|leasing (?:office|team)|office|complex)|mckinley|they|we)")
_MOD = (r"(?:must(?: not)?|have to|has to|need to|needs to|(?:are|is) (?:not )?(?:required|obligated|obliged|allowed|"
        r"permitted|supposed) to|(?:are|is) (?:not )?(?:prohibited|forbidden|barred) from|(?:are|is)n'?t (?:allowed|"
        r"permitted|required) to|can(?:not|'t)?(?: legally)?|may(?: not)?|(?:are|is) not able to)")
_VERB = (r"(?:approve|approving|grant|granting|accept|accepting|allow|allowing|permit|permitting|waive|waiving|charge|"
         r"charging|deny|denying|refuse|refusing|reject|rejecting|evict|evicting|accommodate|collect|collecting|"
         r"require|requiring|build|install|ask (?:you )?for)")
_LEGAL_OBLIGATION = re.compile(
    rf"\b{_SUBJ}\b[^.?!]{{0,25}}?\b{_MOD}\s+(?:\w+\s+)?{_VERB}\b[^.?!]{{0,60}}?\b{_OBJ}\b|"
    rf"\b(?:pet (?:rent|fees?|deposits?)|(?:a|an|the|any|your|this) (?:fees?|deposits?|charges?|accommodation|"
    rf"request|modification|ramp))\b[^.?!]{{0,30}}?\b(?:can(?:not|'t)|may not|must(?: not)?|has to|have to|will|"
    rf"should) be (?:approved|granted|waived|charged|denied|refused|allowed|accepted|built|installed|collected)\b|"
    rf"\byou (?:qualify|are eligible|'re eligible|are entitled|'re entitled|have a right|'ve got a right)\b|"
    rf"\byou (?:don'?t|do not|won'?t|will not|shouldn'?t|should not) (?:have to |need to )?(?:pay|be charged)\b"
    rf"[^.?!]{{0,40}}?\b(?:pet|animal|deposit|fee|rent)|"
    rf"\byou (?:can(?:not|'t)|won'?t|will not|may not) be (?:charged|required to pay|denied|refused|evicted|turned "
    rf"down)\b|\b(?:is|are|would be|it'?s|that'?s) (?:not )?(?:discrimination|discriminatory)\b", re.I)

_OBJ_ES = (r"(?:adaptaci[oó]n\w*|acomod\w+|ajustes?|modificaci[oó]n\w*|animal\w*|perr[oa]s?|gat[oa]s?|mascotas?|renta|"
           r"dep[oó]sitos?|cuotas?|cargos?|tarifas?|rampas?|silla de ruedas|discapacidad\w*|solicitud\w*|"
           r"estacionamiento)")
_MOD_ES = (r"(?:deben?|tienen? que|est[aá]n? obligad[oa]s? a|no pued\w+|pued\w+|no deben?|est[aá]n? prohibid[oa]s? "
           r"(?:de )?|tienen? prohibido)")
_VERB_ES = (r"(?:aprobar|aceptar|permitir|conceder|otorgar|eximir|exonerar|cobrar|cobrarle|cobrarles|negar|negarle|"
            r"rechazar|desalojar|construir|instalar|pedir|exigir)")
_LEGAL_ES = re.compile(
    r"\b(?:la|las|esta|esa|una) ley(?:es)?\b[^.?!]{0,40}?\b(?:proh[ií]be\w*|exige\w*|requiere\w*|permite\w*|obliga\w*|"
    r"protege\w*|establece\w*|dice\w*)|"
    r"\b(?:por|seg[uú]n (?:la|las)|bajo la|conforme a la|de acuerdo con la|en contra de la) (?:ley|leyes|normativa|"
    r"ley de vivienda justa|ley federal|ada|fair housing)\b|"
    r"\blegalmente\b[^.?!]{0,30}?\b(?:pued\w+|deb\w+|tien\w+ que|obligad\w+|permitid\w+|prohibid\w+)|"
    r"\b(?:es|ser[ií]a|eso es) (?:ilegal|legal|discriminaci[oó]n|discriminatori[oa])\b|"
    r"\b(?:tiene|tienes|usted tiene) (?:el |todo el )?derecho (?:legal )?a\b|"
    r"\b(?:califica|calificas|es elegible|eres elegible)\b[^.?!]{0,30}?\b(?:adaptaci[oó]n|acomodo|ajuste)|"
    r"\b(?:animal(?:es)?|perr[oa]s?|gat[oa]s?) de (?:servicio|apoyo(?: emocional)?|asistencia)\b[^.?!]{0,60}?"
    r"(?:\bno (?:son|es|se consideran?|cuentan? como) mascotas?\b|\bno (?:se (?:les? )?)?(?:pued\w+ )?(?:cobr\w+|"
    r"pag\w+)\b|\bexent\w+|\bexonerad\w+)|"
    rf"\b(?:el |la |los |las )?(?:propietari[oa]s?|arrendador(?:es|a)?|administraci[oó]n|comunidad(?:es)?|"
    rf"due[ñn][oa]s?|edificio|oficina|equipo de arrendamiento|mckinley|ellos)\b[^.?!]{{0,20}}?\b{_MOD_ES}\s+"
    rf"(?:le |les |lo |la )?{_VERB_ES}\b[^.?!]{{0,60}}?\b{_OBJ_ES}|"
    rf"(?:^|[.,;:¡!]\s*)(?:entonces |as[ií] que |por eso )?{_MOD_ES}\s+(?:le |les |lo |la )?{_VERB_ES}\b"
    rf"[^.?!]{{0,60}}?\b{_OBJ_ES}|"
    rf"\bno (?:le|les|te) (?:pued\w+|deb\w+) (?:cobrar|negar|rechazar|exigir|pedir)\b[^.?!]{{0,60}}?\b{_OBJ_ES}|"
    r"\b(?:su |la |esta )?(?:solicitud|adaptaci[oó]n|rampa)\b[^.?!]{0,30}?\b(?:debe|tiene que|ser[aá]|tendr[aá] que) "
    r"ser (?:aprobad[oa]|concedid[oa]|aceptad[oa]|instalad[oa]|construid[oa])", re.I)
_RESIDENT_PROFILE_ES = re.compile(
    r"\b(?:menos|m[aá]s|muchas?|muchos|pocas?|pocos|mayor[ií]a de)\s+(?:\w+\s+)?(?:familias|ni[ñn]os|ni[ñn]as|"
    r"personas mayores|jubilados|estudiantes|inmigrantes)\b|\b(?:los )?(?:residentes|inquilinos|vecinos)\s+"
    r"(?:\w+\s+)?son\s+(?:mayormente|principalmente|en su mayor[ií]a|mayores|j[oó]venes)\b", re.I)
# "I don't know what the law says", "whether the law allows", "no sé si la ley lo permite", "no sé qué dice la ley"
_NOT_A_CLAIM = re.compile(r"\b(?:what|whether|if|si|qu[eé]|lo que)\s+(?:\S+\s+)?$", re.I)
# Text the reply quotes (usually the person's own words) is not the assistant's statement
_QUOTED = re.compile(r"\"[^\"]{1,300}\"|“[^”]{1,300}”|«[^»]{1,300}»")


# Accommodation / fair-housing / legal topics (EN + ES), used only to ROUTE a note to people who can answer it. This
# is the one pattern kept from the pre-MVP gate list (the other gates had MVP equivalents: see docs/SECURITY.md).
_LEGAL_TOPIC = re.compile(
    r"discriminat|fair housing|lawyer|attorney|\bsue\b|\bsuing\b|lawsuit|evict|reasonable accommodation|"
    r"(?:take|taking|go|going|see|seeing) (?:you |this |it |us )?(?:to |in )court|small claims|legal action|"
    r"press charges|retaliat|accommodation|disabilit|disabled|wheelchair|grab bars?|accessib|service (animal|dog)|"
    r"autis\w*|adhd|special needs|medical condition|mobility|blind(?!s)|deaf|hearing impair|"
    r"(emotional )?support (animal|dog|cat)|assistance animal|\besa\b|discapacidad|adaptaci[oó]n|discrimina|"
    r"\b(?:animal(?:es)?|perr[oa]s?|gat[oa]s?) de (?:servicio|apoyo|asistencia|gu[ií]a)\b|\bvivienda justa\b|"
    r"\bajustes? razonables?\b|\bsilla de ruedas\b|\brampa\b|\b(?:es|ser[ií]a) (?:legal|ilegal)\b|\babogad[oa]\b|"
    r"\bdemanda(?:r|rlos)?\b|\bdesalo(?:jo|jar)\b", re.I)


def legal_sensitive(message: str) -> bool:
    """Fair housing, accommodation, disability, assistance animal or legal action (EN + ES): routing only."""
    from app.safety import normalize_for_matching
    return bool(_LEGAL_TOPIC.search(normalize_for_matching(message or "")))


def _legal_match(reply: str) -> tuple[str, str] | None:
    """(controlled reason code, matched text) for the first determination in a reply, or None."""
    text = _QUOTED.sub(" ", reply or "")
    for pat in (_LEGAL_CONCLUSION, _LEGAL_OBLIGATION, _LEGAL_ES):
        for m in pat.finditer(text):
            if not _NOT_A_CLAIM.search(text[max(0, m.start() - 20):m.start()]):
                return "legal_determination", m.group(0)
    for pat in (_RESIDENT_PROFILE, _RESIDENT_PROFILE_ES):
        if m := pat.search(text):
            return "resident_profile", m.group(0)
    return None


def legal_conclusion(reply: str) -> str | None:
    """The first legal determination, or description of a community by who lives there, stated in a reply."""
    hit = _legal_match(reply)
    return hit[1] if hit else None


def legal_conclusion_kind(reply: str) -> str | None:
    """Controlled code only ('legal_determination' / 'resident_profile'), for logs: never the matched text."""
    hit = _legal_match(reply)
    return hit[0] if hit else None


# Controlled diagnostic reason codes for failed reply checks (review: every failed check gets one). Never text.
_CHECK_REASON = {"terminology": "non_mckinley_term", "no_false_action_claim": "unbacked_action_claim",
                 "no_invented_price": "price_not_in_context", "no_invented_time": "time_not_in_context",
                 "no_pii": "personal_data_pattern", "no_risky_diy": "risky_diy_instruction",
                 "no_invented_offer": "offer_not_in_context", "no_secret_leak": "secret_pattern",
                 "emergency_guidance": "emergency_guidance_missing"}
_CLAIM_REASON = (("unknown reference", "unknown_reference"), ("claims something was saved", "unbacked_save_claim"),
                 ("claims an identity", "identity_claim"), ("history not on record", "history_not_on_record"))


def reason_codes(checks: list[Any], problems: list[str], legal_kind: str | None) -> list[str]:
    """'check:reason' for every failed check, from fixed vocabularies only (no reply or message text)."""
    out = set()
    for c in checks:
        if c.passed:
            continue
        if c.code == "grounded_claims":
            for p in problems or [""]:
                out.add("grounded_claims:" + next((r for k, r in _CLAIM_REASON if p.startswith(k)), "unspecified"))
        elif c.code == "no_legal_conclusion":
            out.add(f"no_legal_conclusion:{legal_kind or 'unspecified'}")
        else:
            out.add(f"{c.code}:{_CHECK_REASON.get(c.code, 'unspecified')}")
    return sorted(out)


def legal_referral(lang: str, prospect: bool) -> tuple[str, str]:
    """(text, wording status: 'approved' or 'provisional'). Never a legal answer; offers a note, never sends one."""
    topic = next((t for t in _kb() if t.get("id") == "fair_housing"), {})
    approved = topic.get("status") == "approved" and topic.get("answer")
    es = lang == "es"
    text = (topic.get("answer_es" if es else "answer") if approved else
            topic.get("pending_reply_es" if es else "pending_reply")) or ""
    team = ("nuestro equipo de arrendamiento" if prospect else "nuestro equipo de administración") if es else (
        "our leasing team" if prospect else "our management team")  # the team the note is routed to (run_turn)
    return text.replace("{team}", team), "approved" if approved else "provisional"
