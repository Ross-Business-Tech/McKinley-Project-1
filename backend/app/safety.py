"""Deterministic redaction, injection screening, pre-model policy gates and post-model output checks.

These rules are intentionally simple and auditable. They supplement, not replace, model instructions.
"""

import re
import unicodedata

from app.models import OutputCheck, PolicySignal

# ---- redaction ---------------------------------------------------------------

_EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]{1,64}(?:@|\s?\(at\)\s?|\s?\[at\]\s?)[A-Za-z0-9-]{1,63}"
                    r"(?:(?:\.|\s?\(dot\)\s?|\s?\[dot\]\s?)[A-Za-z0-9-]{1,63}){1,4}(?![\w-])", re.IGNORECASE)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|(?:ssn|social security|social|seguro social)\D{0,15}"
                  r"\d{3}[ -]?\d{2}[ -]?\d{4}\b", re.IGNORECASE)
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_CARD_EXTRA = re.compile(r"\b(?:exp(?:iry|iration|ires|\.)?(?: date)?|vence|"
                         r"vencimiento)\W{0,3}(?:\d{1,2}\s?[/-]\s?\d{2,4}|\d{4})\b|"
                         r"\b(?:cvv2?|cvc|csc|security code|c[oó]digo de seguridad)\W{0,3}\d{3,4}\b", re.I)
_PHONE = re.compile(r"(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\b\d{3}[ .-]?)\d{3}[ .-]?\d{4}\b|\b\d{3}[.-]\d{4}\b")
_DOB = re.compile(
    r"\b(?:dob|date of birth|born(?: on)?|birthday|nac[ií]\w*)\b[:\s]*\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}", re.IGNORECASE
)


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def _card_sub(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[card number redacted]" if 13 <= len(digits) <= 19 and _luhn(digits) else m.group(0)


def redact(text: str) -> str:
    """Mask contact details and sensitive identifiers. Order matters: SSN/card before phone."""
    text = _EMAIL.sub("[email redacted]", text)
    text = _SSN.sub("[SSN redacted]", text)
    text = _CARD.sub(_card_sub, text)
    text = _CARD_EXTRA.sub(" [card detail redacted]", text)
    text = re.sub(r"\](?=\w)", "] ", text)
    text = _DOB.sub("[DOB redacted]", text)
    text = _PHONE.sub("[phone redacted]", text)
    return text


def contains_pii(text: str) -> list[str]:
    found = []
    for name, pat in (("email", _EMAIL), ("ssn", _SSN), ("phone", _PHONE), ("dob", _DOB)):
        if pat.search(text):
            found.append(name)
    if any(_card_sub(m) != m.group(0) for m in _CARD.finditer(text)):
        found.insert(2, "card")
    return found


# ---- injection screen for untrusted data fields ----------------------------------

_INJECTION = re.compile(
    r"ignore (all|any|previous|prior|the above)|disregard|system prompt|you are now|new instructions|"
    r"api[ _-]?key|secret|password|reveal|jailbreak|developer mode|</?\s*(system|safe_context)|"
    r"\boverride\b|act as|\b(?:assistant|system|ai|bot) instructions?\b|(?:^|\n)\s*>?\s*(?:system|assistant)\s*:|"
    r"reply (?:only )?with ['\"]",
    re.IGNORECASE,
)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def sanitize_field(text: str, max_len: int = 120) -> str | None:
    """Return a redacted, length-capped value, or None when the value should be dropped."""
    if not text:
        return None
    clean = " ".join(str(text).split())
    if looks_like_injection(clean):
        return None
    clean = redact(clean)
    return clean[:max_len] + ("…" if len(clean) > max_len else "")


# ---- pre-model policy gates (run on the user message) ------------------------------

_GATES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "human_requested",
        "human_requested",
        re.compile(
            r"(talk|speak|connect)( me)? (to|with) (a |an |the )?(person|human|real person|someone|manager|"
            r"agent|staff|representative)|\b(human|real person) please\b|can someone (call|explain|help)|"
            r"hablar con (una persona|alguien|un humano|el gerente|un agente)|nói chuyện với",
            re.IGNORECASE,
        ),
        "Resident or prospect asked for a person.",
    ),
    (
        "sensitive_data_request",
        "sensitive_data_request",
        re.compile(
            r"\b(ssn|social security|credit card|card number|cvv|bank account|routing number|"
            r"date of birth|\bdob\b)\b",
            re.IGNORECASE,
        ),
        "Message references highly sensitive identifiers; never collect or repeat them in chat.",
    ),
    (
        "fair_housing_or_legal",
        "fair_housing_or_legal",
        re.compile(
            r"discriminat|fair housing|lawyer|attorney|\bsue\b|\bsuing\b|lawsuit|evict|reasonable accommodation|"
            r"(?:take|taking|go|going|see|seeing) (?:you |this |it |us )?(?:to |in )court|small claims|"
            r"legal action|press charges|"
            r"retaliat|"
            r"accommodation|disabilit|disabled|wheelchair|grab bars?|accessib|service (animal|dog)|autis\w*|adhd|"
            r"special needs|medical condition|mobility|blind(?!s)|deaf|hearing impair|"
            r"(emotional )?support (animal|dog|cat)|assistance animal|\besa\b|discapacidad|adaptaci[oó]n|"
            r"discrimina",
            re.IGNORECASE,
        ),
        "Fair-housing, accommodation or legal topic needs authorized staff.",
    ),
    (
        "financial_or_lease",
        "financial_or_lease",
        re.compile(
            r"payment plan|can'?t (afford|pay)|late fee|dispute|refund|security deposit|break (my|the) lease|"
            r"renewal (offer|price|cost|rate)|rent increase|rent (go|going|went) up|worried about the cost|kick (me|"
            r"us) out|"
            r"rent credit|\bcredit\b|compensat|reimburs|\bbalance\b|what do i owe|cu[aá]nto debo|"
            r"no (puedo|me alcanza)\W+(?:\w+\W+){0,3}(pagar|la renta)|sube la renta|aumento de (la )?renta|"
            r"plan de pago|desalojo|me van a (echar|sacar)",
            re.IGNORECASE,
        ),
        "Financial or lease-term question cannot be decided by the assistant.",
    ),
    (
        "voucher_eligibility",
        "policy_or_eligibility",
        re.compile(r"voucher|section 8|housing choice|subsid", re.IGNORECASE),
        "Voucher eligibility details must be verified by staff (all properties accept vouchers).",
    ),
    (
        "repeat_language",
        "repeat_issue",
        re.compile(r"\bagain\b|multiple times|keeps (happening|breaking)|still (broken|not)|third time|"
                   r"second time", re.IGNORECASE),
        "Message describes a recurring problem.",
    ),
]


def normalize_for_matching(text: str) -> str:
    """NFKC-fold (fullwidth -> ASCII) and drop zero-width/format characters so patterns can't be dodged."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def pre_model_gates(message: str) -> list[PolicySignal]:
    from app.emergency import LABEL, emergency_kind

    message = normalize_for_matching(message)
    kind = emergency_kind(message)
    emergency = [PolicySignal(code="emergency_hazard", category="safety_emergency",
                              detail=f"{LABEL[kind]}: emergency channels must be prioritized.")] if kind else []
    return emergency + [
        PolicySignal(code=code, category=cat, detail=detail)  # type: ignore[arg-type]
        for code, cat, pat, detail in _GATES
        if pat.search(message)
    ]


# ---- post-model output checks -------------------------------------------------------

# Leasing vocabulary: McKinley says "beds" / "floor plans", so "bedroom" is banned as a UNIT SIZE ("2-bedroom",
# "three bedrooms", "a one bedroom apartment", "how many bedrooms"). The room itself is fine in a maintenance reply
# ("your bedroom AC", "the bedroom window", "both bedrooms").
_NUM_WORD = r"(?:\d|one|two|three|four|five|single|double|a one|a two)"
_UNIT_NOUN = (r"(?:apartments?|units?|homes?|floor ?plans?|layouts?|options?|places?|flats?|condos?|townhomes?|"
              r"houses?|rentals?)")
_BANNED_TERMS = re.compile(
    rf"\b{_NUM_WORD}[\s-]?bed[\s-]?rooms?\b|\bbed\s?rooms?\s+(?:and \w+ baths?\s+)?{_UNIT_NOUN}\b|"
    r"\bhow many bed\s?rooms\b|\bbed\s?rooms? (?:available|do you need|are you looking)|"
    r"\bunit\s?types?\b|\b[1-4]\s?BR\b|\bstudio unit type\b", re.IGNORECASE)
_APOS = "['\u2019]"  # straight or curly apostrophe
_ACTION_CLAIMS = re.compile(
    rf"\bI(?:{_APOS}ve| have)? (?:just |already )?(?:notified|alerted|contacted|emailed|texted|called|messaged|"
    r"escalated|forwarded|submitted|created|opened|filed|scheduled|booked|dispatched|reserved|transferred|"
    r"passed (?:this|it|your \w+) (?:along|on)|put in (?:a|your|the) \w+|"
    r"sent (?:this|it|your \w+) (?:to|along))\b|"
    r"\b(?:work order|ticket|request|appointment|tour)(?: (?:#|no\.? ?)?\w*\d\w*)? (?:has been|is now|was) "
    r"(?:created|submitted|opened|scheduled|booked|confirmed)\b|"
    r"\b(?:a technician|maintenance|someone|the team|staff) (?:is|has been|will be) (?:on (?:their|the) way|"
    r"dispatched)\b|"
    rf"\bI(?:{_APOS}ll| will) (?:go ahead and |now )?(?:call|text|email|notify|schedule|book|escalate|connect|"
    r"pass|forward|submit|send|arrange|contact|reach out|file|create|open|set up|put in|let (?:the|our) \w+ know)\b|"
    rf"\b(?:we|they|the team|someone|staff){_APOS}?(?:ll| will) (?:reach out|contact you|call you|text you|"
    r"email you|follow up with you|be in touch|get back to you|send you)\b|"
    r"\b(?:a |the |our )?(?:tech(?:nician)?|plumber|electrician|maintenance|someone|somebody|help|staff|"
    r"the (?:on-call|team|office|manager)|on-call \w+)(?: is| are|'s)? (?:coming|on (?:the|their|its) way|"
    r"heading (?:over|your way)|be there|come by|stop by|dispatched)\b|"
    r"\bwill (?:come|be there|be by|stop by|arrive|call you|text you|reach out)\b|"
    r"\b(?:has|have) been (?:notified|alerted|informed|assigned|scheduled|booked|confirmed|dispatched|told)\b|"
    r"\b(?:is|was|are|were) (?:confirmed|scheduled|booked|assigned) (?:for|to|on)\b|"
    rf"\bI(?:{_APOS}ve| have)? (?:let|told|informed|logged|added|reached out to|looped in)\b|"
    rf"\bwe(?:{_APOS}ve| have) (?:booked|scheduled|confirmed|notified|sent|logged)\b|"
    r"\b(?:all |it'?s |that'?s )?taken care of\b|\bassigned to\b|\bwithin \d+ (?:minutes|hours|days|business days)\b|"
    r"\bconfirmad[oa]\b|\bprogramad[oa]\b|\benvi[eé] (?:su|la|el)\b|\ben camino\b|\ble (?:llamaremos|"
    r"escribiremos)\b|\bhemos (?:programado|enviado|confirmado|agendado)\b|\bagendad[oa]\b",
    re.IGNORECASE,
)

_PRICE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]*(?:\.\d{2})? ?(?:dollars|usd|d[oó]lares)\b|"
                    r"\b\d{1,2} ?% ?off\b", re.IGNORECASE)
_CLOCK_TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:a\.?m|p\.?m)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\bnoon\b|"
                         r"\bmidnight\b", re.IGNORECASE)
_RISKY_DIY = re.compile(
    r"disassembl|take apart|remove the (cartridge|valve|panel|cover)|unscrew the|replace the (washer|cartridge)|"
    r"shut off the (gas|breaker)|open the (electrical|breaker) panel|recharge (the )?refrigerant|"
    r"turn off the main water valve and",
    re.IGNORECASE,
)


_OFFER = re.compile(
    r"\b(discount|waive[ds]?|waiver|concession|free month|month(s)? (is |are )?free|price match|promo\w*|"
    r"lock in (your|a) (rate|price)|"
    r"lower (your|the) rent|reduce (your|the) rent|guarantee[ds]?)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(can'?t|cannot|can\u2019t|not|unable to|don'?t|no)\W+(?:\w+\W+){0,5}$", re.IGNORECASE)
_SECRET_LEAK = re.compile(r"api[ _-]?key|system prompt|\bsk-[A-Za-z0-9]|safe_context|my instructions",
                          re.IGNORECASE)
_EMERGENCY_GUIDANCE = re.compile(r"911|emergency", re.IGNORECASE)


# Sprint 5.1 (L-4): checked only when the caller says nothing was sent this turn (`nothing_sent=True`). A promise that
# staff will follow up / call is false while the card is still being filled in or no contact was collected. Honest
# conditionals ("once you send it, staff can review it") and offers ("would you like me to...") are allowed.
_PENDING_PROMISE = re.compile(
    r"\b(?:a |the |our |one of our )?(?:staff(?: member)?s?|team members?|(?:property |community |leasing )?managers?|"
    r"someone|somebody|the (?:office|team|leasing team|maintenance team)|maintenance(?: staff| team)?|leasing(?: "
    r"team)?|a (?:person|specialist|technician|tech))\W+(?:\w+\W+){0,2}(?:should|will|would|is going to|are going "
    r"to|can|to)?\s?(?:follow up|call you|reach out|contact you|get back to you|be in touch|text you|email you|"
    r"call|phone you|get in touch)\b|"
    rf"\bI(?:{_APOS}m| am) (?:now |currently |also )?(?:flagging|escalating|forwarding|notifying|alerting|routing|"
    r"passing|sending|submitting|filing|logging|handing)\b(?! (?:you|over the (?:steps|options)))",
    re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(?:once|after|when|if|as soon as)\s+(?:you|it|this|that|the (?:note|request|card))\b|"
                          r"\bwould you like\b|\bdo you want\b|\bshall i\b|\bif you(?:'d| would)? like\b", re.I)


def _pending_promise(reply: str) -> str | None:
    for m in _PENDING_PROMISE.finditer(reply):
        start = max(reply.rfind(".", 0, m.start()), reply.rfind("?", 0, m.start()), reply.rfind("!", 0, m.start()))
        clause = reply[start + 1:m.end()]
        if _CONDITIONAL.search(clause) or _NEGATION.search(reply[max(0, m.start() - 60):m.start()]):
            continue
        return m.group(0)
    return None


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s?k?\b", re.I)


def _amounts(text: str) -> set[float]:
    out: set[float] = set()
    for raw in _NUMBER.findall(text):
        r = raw.replace(",", "").strip().lower()
        mult = 1000.0 if r.endswith("k") else 1.0
        try:
            out.add(round(float(r.rstrip("k").strip()) * mult, 2))
        except ValueError:
            continue
    return out


def _unnegated(pat: re.Pattern[str], text: str) -> str | None:
    """First match not preceded (within ~5 words) by a negation, e.g. 'I can't offer a discount' is fine."""
    for m in pat.finditer(text):
        if not _NEGATION.search(text[max(0, m.start() - 60):m.start()]):
            return m.group(0)
    return None


def output_checks(reply: str, allowed_text: str = "", urgency: str | None = None, user_text: str = "",
                  nothing_sent: bool = False) -> list[OutputCheck]:
    """Check a model reply. `allowed_text` = safe context text; times/prices found there are not 'invented'.
    `user_text` = what the person typed in this conversation: a price that only echoes their own number (their
    budget) is not invented. `nothing_sent` = no record was written this turn: staff follow-up promises are false."""
    checks: list[OutputCheck] = []

    term = _BANNED_TERMS.search(reply)
    checks.append(OutputCheck(
        code="terminology",
        passed=term is None,
        detail=f"Found non-McKinley term: '{term.group(0)}'" if term else "Uses beds / floor plans vocabulary",
    ))

    claim_text = _unnegated(_ACTION_CLAIMS, reply)  # "No one has been dispatched" is honest, not a claim
    if claim_text is None and nothing_sent:
        claim_text = _pending_promise(reply)
    checks.append(OutputCheck(
        code="no_false_action_claim",
        passed=claim_text is None,
        detail=f"Possible claimed action: '{claim_text}'" if claim_text else "No claimed side-effect actions",
    ))

    said = _amounts(user_text) if user_text else set()
    invented_prices = [p for p in _PRICE.findall(reply) if p not in allowed_text
                       and not (said and _amounts(p) and _amounts(p) <= said and "%" not in p)]
    checks.append(OutputCheck(
        code="no_invented_price",
        passed=not invented_prices,
        detail=f"Price not in verified context: {invented_prices}" if invented_prices else "No unverified prices",
    ))

    invented_times = [t for t in _CLOCK_TIME.findall(reply) if t.lower() not in allowed_text.lower()]
    checks.append(OutputCheck(
        code="no_invented_time",
        passed=not invented_times,
        detail=(f"Clock time not in verified context: {invented_times}" if invented_times
                else "No unverified appointment times"),
    ))

    pii = contains_pii(reply)
    checks.append(OutputCheck(
        code="no_pii",
        passed=not pii,
        detail=f"Reply contained: {pii} (redacted before display)" if pii else "No contact/PII patterns",
    ))

    diy = _RISKY_DIY.search(reply)
    checks.append(OutputCheck(
        code="no_risky_diy",
        passed=diy is None,
        detail=f"Possible risky DIY instruction: '{diy.group(0)}'" if diy else "No risky repair instructions",
    ))

    offer = _unnegated(_OFFER, reply)
    checks.append(OutputCheck(
        code="no_invented_offer",
        passed=offer is None,
        detail=f"Possible unsupported offer/guarantee: '{offer}'" if offer else "No invented discounts or guarantees",
    ))

    leak = _SECRET_LEAK.search(reply)
    checks.append(OutputCheck(
        code="no_secret_leak",
        passed=leak is None,
        detail=f"Reply mentions internal material: '{leak.group(0)}'" if leak else "No internal/prompt leakage",
    ))

    if urgency == "emergency":
        ok = bool(_EMERGENCY_GUIDANCE.search(reply))
        checks.append(OutputCheck(
            code="emergency_guidance",
            passed=ok,
            detail="Reply points to 911 / emergency line" if ok
            else "Emergency reply lacks 911/emergency guidance (deterministic safety notice shown instead)",
        ))
    return checks


CRITICAL_CHECKS = {"no_pii", "no_false_action_claim", "no_risky_diy", "no_secret_leak", "emergency_guidance",
                   "no_invented_offer"}
