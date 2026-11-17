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
_NOT_A_CLAIM = re.compile(r"\b(?:what|whether|if)\s+$|\b(?:what|whether|if)\s+\S*$", re.I)


def legal_sensitive(message: str) -> bool:
    """Fair housing, accommodation, disability, assistance animal or legal action (the existing gate pattern)."""
    from app.safety import gate_matches
    return gate_matches("fair_housing_or_legal", message)


def legal_conclusion(reply: str) -> str | None:
    """The first legal determination, or description of a community by who lives there, stated in a reply."""
    text = reply or ""
    for m in _LEGAL_CONCLUSION.finditer(text):
        if not _NOT_A_CLAIM.search(text[max(0, m.start() - 12):m.start() + 1]):  # "I don't know what the law says"
            return m.group(0)
    m = _RESIDENT_PROFILE.search(text)
    return m.group(0) if m else None


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
