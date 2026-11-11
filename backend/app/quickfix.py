"""Quick-fix tips before a repair request (Sprint 8, workstream D). Pure functions: no store, no model, no side effects.

For a few clearly low-risk, commonly resolved issues (tripped breaker, GFCI outlet, garbage disposal reset, slow drain
with no leak) the planner may offer up to 3 short tips from the content file, ask whether that fixed it, and:
  yes            -> close the troubleshooting flow, no record is written;
  no / unsure    -> normal repair intake with the original issue kept;
  skip / "just send maintenance" (in the first message or as the answer) -> repair intake directly;
  anything else  -> asked once more, then intake (the resident is never trapped).
At most one round of tips per issue per conversation.

Order of checks in `check_eligibility` (the order is the specification):
  1. content mode (off -> nothing);
  2. a NEGATIVE safety finding is required: a RiskDecision with response "none", no person danger, no staff need,
     not via an earlier incident. No decision passed = no tips (fail closed);
  3. the deterministic safety detector (app/risk/detect, read-only) must also see no hazard, no mention, no care tier;
  4. universal exclusions (gas, smoke/fire, burning, sparks/wiring/shock, water/leak/flood/overflow, CO, injury,
     alarm, sewage, urgency words) in EN + ES;
  5. the resident's own choice: "just send maintenance" / "already tried" -> no tips;
  6. repeat issue (triage level repeat or a repeat flag) -> no tips;
  7. one entry must match its trigger family; then that entry's own exclusions;
  8. degraded / uncertain safety classifier + any possible-risk word (hot, warm, smell, noise...) -> no tips;
  9. not already offered for this entry in this conversation;
 10. content approval: approved_only serves only status "approved"; demo_drafts serves drafts, labelled.
Wording around the tips (intro, question, resolved line, draft label) lives in app/templates.py (Agent C); the
proposed keys are DRAFT_LABEL here only as the fallback for module tests. NEEDS McKINLEY REVIEW.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.content.quickfix_drafts import APPROVED_STATUS, ENTRIES

Mode = Literal["off", "approved_only", "demo_drafts"]
ReplyKind = Literal["resolved", "not_resolved", "skip", "unclear"]
MEM_KEY = "quickfix"  # planner memory: {"state": "offered", "entry": id, "asked": n} (flags/ids only, never text)
USED_KEY = "quickfix_used"  # planner memory: entry ids already offered in this conversation
MAX_TIPS = 3

# NEEDS McKINLEY REVIEW. Shown above draft tips in demo_drafts mode (the hook uses templates "quickfix_draft_label").
DRAFT_LABEL = {
    "en": "Draft tips for this demo, not yet approved by McKinley. If you'd rather not try them, just say "
          "\"send a request\".",
    "es": "Consejos en borrador para esta demostración, aún no aprobados por McKinley. Si prefiere no probarlos, "
          "solo diga \"envíen una solicitud\".",
}


def effective_mode(settings: Any, local_request: bool = True) -> Mode:
    """The mode this request may use. Fail closed: a hosted backend (or a request that did not come straight from this
    machine) never serves draft tips; an unknown value is "off"."""
    mode = getattr(settings, "quickfix_content_mode", "off")
    if mode not in ("off", "approved_only", "demo_drafts"):
        return "off"
    if mode == "demo_drafts" and (getattr(settings, "app_env", "hosted") != "local" or not local_request):
        return "approved_only"
    return mode  # type: ignore[return-value]


@dataclass(frozen=True)
class QuickFixResult:
    eligible: bool
    reason: str  # why (eligible: "ok"; otherwise the first check that refused, e.g. "excluded:water")
    entry_id: str | None = None
    category: str | None = None
    tips: list[str] = field(default_factory=list)
    draft: bool = False  # True = DRAFT content (demo_drafts only); the reply must show the draft label
    label: str | None = None


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(parts), re.I)


# ---- universal exclusions (any one -> no tips; checked before any entry) -----------------------------------------
EXCLUSIONS: dict[str, re.Pattern[str]] = {
    "gas": _rx(r"\bgas\b", r"propane", r"rotten eggs?", r"\bpropano\b"),
    "smoke_fire": _rx(r"\bsmok(e|ed|ing|y)\b", r"\bfire\b", r"\bflames?\b", r"\bon fire\b", r"\bhumo\b", r"\bfuego\b",
                      r"\bllamas?\b", r"incendi", r"\bhumea"),
    "burning": _rx(r"\bburn(ing|t|ed)?\b", r"scorch", r"\bmelt(ed|ing)?\b", r"\bchar(red)?\b", r"quemad", r"quema",
                   r"chamusc", r"derreti"),
    "sparks_wiring": _rx(r"spark", r"\barc(ing|ed)?\b", r"\b(exposed|bare|loose|frayed|hanging|live) wires?\b",
                         r"\bwir(es|ing)\b", r"\bshock(ed)?\b", r"\bzap(ped)?\b", r"electrocut", r"chispa",
                         r"cables? (expuest|pelad|suelt|colgand)", r"\bdescarga", r"\bme dio (un )?toque\b",
                         r"electrocut"),
    "water": _rx(r"\bleak", r"\bflood", r"overflow", r"water (is )?(on|all over) the floor", r"\bpuddles?\b",
                 r"water (under|beneath|below|around|coming out|everywhere|dripping)", r"\bdripping\b", r"\bwet\b",
                 r"\bdamp\b", r"\bsoak", r"back(ing|ed)? ?up", r"spill(ing|ed)? over", r"gote", r"\bfugas?\b",
                 r"inund", r"desbord", r"\bcharcos?\b", r"agua (en|por) (el|todo el) (piso|suelo)", r"mojad",
                 r"h[uú]med", r"rebos", r"se (sale|regresa|devuelve) el agua", r"agua (debajo|abajo|alrededor)"),
    "co": _rx(r"carbon monoxide", r"\bco (alarm|detector)\b", r"mon[oó]xido"),
    "injury": _rx(r"\bhurt", r"injur", r"bleed", r"\bblood", r"\bcut (my|his|her|their)", r"burned (my|his|her)",
                  r"\bherid", r"sangr", r"me cort[eé]", r"me quem[eé]", r"lastim", r"\bfinger", r"\bhand (is )?stuck",
                  r"\bdedo", r"\bmano\b"),
    "alarm": _rx(r"\balarm", r"detector (is )?(beep|going off|chirp)", r"\balarma"),
    "sewage": _rx(r"sewage", r"sewer", r"aguas negras", r"drenaje huele", r"huele a (drenaje|cloaca)"),
    "urgent_danger": _rx(r"\bdanger", r"\bunsafe\b", r"\bemergenc", r"\burgent", r"\bscared\b", r"\bafraid\b",
                         r"\bpeligr", r"emergencia", r"urgente", r"\bmiedo\b", r"\bsmell(s|ing)? (weird|funny|bad|"
                         r"strange|like)", r"huele (raro|feo|mal|a)"),
}

# ---- the resident's own choice -------------------------------------------------------------------------------------
_SKIP = _rx(
    r"\bjust (send|get|have|put in|submit|file|open|make|start)\b",
    r"send (someone|somebody|a tech|maintenance|the request|a request|it|the repair)",
    r"(submit|put in|file|open|make|start|create) (a|the|my) (ticket|request|work order|repair request|"
    r"maintenance request)",
    r"\bwork order\b", r"no tips", r"don'?t need (tips|help|advice|steps)", r"\bskip\b", r"rather (not|you send|just)",
    r"have (someone|maintenance|a tech) (come|look|fix)", r"\bmanden?\b", r"env[ií]en",
    r"solo quiero (la|una) solicitud", r"\bsin consejos\b", r"no quiero consejos",
    r"que venga (alguien|mantenimiento|un t[eé]cnico)", r"\bomit",
    r"\bsaltar\b", r"(hagan|abran|levanten|pongan) (una|la) (solicitud|orden)")
_ALREADY = _rx(r"already (tried|reset|flipped|pressed|checked|did|cleaned|plunged)", r"(tried|trying) (to )?(reset|"
               r"flip|press|unclog|plung|clean)", r"\bi (reset|flipped|pressed) (it|the)", r"reset (it|the \w+) "
               r"(already|twice|again)", r"\bya (lo |la )?(reinici|intent|prob|presion|limpi|baj|sub|resete)",
               r"\bintent[eé]\b")
_REPEAT_WORDS = _rx(r"keeps? (tripping|happening|clogging|going out|shutting off|turning off|clicking off|popping)",
                    r"\b(again|every time|each time|repeatedly|constantly|over and over|all the time)\b",
                    r"(second|third|\d+(st|nd|rd|th)) time", r"\botra vez\b", r"\bde nuevo\b", r"cada vez",
                    r"se sigue", r"sigue (bot|salt|tap|baj)", r"siempre (se|pasa)", r"varias veces")
# a degraded / uncertain classifier: any possible-risk word is enough to stay out
_POSSIBLE_RISK = _rx(r"\bhot\b", r"\bwarm\b", r"\bheat", r"\bsmell", r"\bodor", r"\bnois", r"\bloud\b", r"\bweird\b",
                     r"\bstrange\b", r"\bpop(ped|ping|s)?\b", r"\bbang", r"\bcrack", r"\bsizzl", r"\bcaliente",
                     r"\bolor", r"\bhuele", r"\bruido", r"\braro\b", r"\bextra[nñ]o")

# ---- trigger families (structure: object + symptom, EN + ES) -------------------------------------------------------
_NOT_WORKING = (r"(not|n'?t|stopped|quit|no longer|won'?t|doesn'?t|isn'?t|aren'?t|don'?t) ?(be )?(work|turn|run|"
                r"start|com|power|go)\w*|\bdead\b|\bbroken?\b|\bno power\b|\bwon'?t (turn|go) on\b|\bnothing happens\b|"
                r"\bno (funciona|sirve|prende|enciende|jala|da (luz|corriente))\w*|dej[oó] de (funcionar|servir|"
                r"prender)|\bse (apag|muri)\w*|\bsin (luz|corriente)\b|\bout\b")
_ROOM = (r"(bed ?room|kitchen|living room|bathroom|bath|dining|office|hall(way)?|den|laundry|closet|garage|"
         r"one room|half|part|side|rec[aá]mara|cuarto|habitaci[oó]n|cocina|sala|comedor|ba[nñ]o|lavander[ií]a|"
         r"pasillo|mitad|parte)")
_BREAKER_WORD = _rx(r"\b(circuit )?breakers?\b", r"tripped (a |the |my )?(circuit|breaker)", r"\bpastillas?\b",
                    r"disyuntor", r"\bel breaker\b", r"se (bot|baj|salt|cay)[oó] (el|la) (breaker|pastilla|"
                    r"interruptor|disyuntor)", r"interruptor (autom[aá]tico|del panel|de circuito)")
_POWER_OUT = _rx(r"\b(lost|no|lose|losing) (power|electricity)\b", r"power (went|is|has gone|cut) (out|off)",
                 r"(outlets?|plugs?|lights?|lamps?) (and|&|y) (outlets?|plugs?|lights?|lamps?)",
                 r"(half|some|several|all|most|a few|two|three) (of )?(my |the )?(outlets|plugs|sockets)",
                 r"\bse (fue|cort[oó]) la luz\b", r"\b(sin|no hay) (luz|electricidad|corriente)\b",
                 r"(la mitad|varios|algunos|todos) (de )?(los )?(enchufes|tomacorrientes|contactos)",
                 r"(enchufes|tomacorrientes|contactos) y (luces|focos)", r"(luces|focos) y (enchufes|tomacorrientes)")
_GFCI_WORD = _rx(r"\bgfci?s?\b", r"\bgfi\b", r"outlet with (the |a )?(test|reset|buttons)", r"(test|reset) (and|&|/) "
                 r"(test|reset) button", r"(reset|test) buttons? on the (outlet|plug)", r"bot[oó]n(es)? (de )?(test|"
                 r"reset|prueba)")
_OUTLET = _rx(r"\boutlets?\b", r"\bplugs?\b", r"\bsockets?\b", r"\benchufes?\b", r"tomacorrientes?", r"\bcontactos?\b")
_WET_ROOM = _rx(r"bath(room)?", r"kitchen", r"laundry", r"garage", r"patio", r"balcon", r"outdoor", r"outside",
                r"near the sink", r"by the sink", r"counter", r"ba[nñ]o", r"cocina", r"lavander", r"garaje",
                r"terraza", r"exterior", r"fregadero", r"lavabo")
_DISPOSAL = _rx(r"\bdisposal\b", r"\bdisposer\b", r"\bgarburator\b", r"triturador", r"\bmoledor")
_DISPOSAL_SYMPTOM = _rx(_NOT_WORKING, r"\bhum(s|ming|med)?\b", r"\bjamm?ed\b", r"\bstuck\b", r"\bzumb", r"atasc",
                        r"\btrab(ad|[oó])")
_FIXTURE = _rx(r"\bsinks?\b", r"\b(bath)?tubs?\b", r"\bshowers?\b", r"\bbasin\b", r"\blavabos?\b", r"fregadero",
               r"lavamanos", r"lavaplatos", r"\btinas?\b", r"ba[nñ]era", r"regadera", r"\bducha\b", r"\bdrains?\b",
               r"desag[uü]e", r"cola?dera")
_CLOG = _rx(r"\bclog", r"\bslow(ly)?\b.{0,20}\bdrain", r"\bdrain\w* (really |very |so )?slow", r"\bslow drain",
            r"(won'?t|doesn'?t|isn'?t|not|n'?t) drain", r"stopped up", r"\bstanding water\b", r"water (just )?"
            r"(sits|stays|pools)", r"\btapad", r"\btap[oó]\b", r"atascad", r"\batasc", r"drena (muy )?lento",
            r"no (drena|baja|se va)( el agua)?", r"se queda el agua", r"agua estancada", r"tarda en (drenar|bajar)")
_TOILET = _rx(r"toilet", r"\bloo\b", r"commode", r"inodoro", r"escusado", r"excusado", r"\btaza\b", r"\bwc\b")

_ENTRY_EXCLUSIONS: dict[str, dict[str, re.Pattern[str]]] = {
    "qf-breaker-reset": {
        "repeat_trip": _REPEAT_WORDS,
        "panel_not_accessible": _rx(r"main (breaker|panel)", r"(hallway|hall|garage|basement|meter|utility|electrical|"
                                    r"common|locked|outside) (panel|room|closet|box)", r"panel (is )?(outside|in the "
                                    r"hall|locked|in the garage)", r"(can'?t|cannot|don'?t know how to) (find|reach|"
                                    r"open|get to)", r"cover (is )?(off|missing|open)", r"no (s[eé]|encuentro|alcanzo)",
                                    r"(panel|caja) (principal|de afuera|cerrad)", r"pastilla principal"),
        "outage": _rx(r"whole (building|complex|street|block|apartment|unit|place|house)", r"(entire|every) "
                      r"(building|complex|unit)", r"neighbou?rs?", r"(everyone|everybody|the whole)", r"todo el "
                      r"(edificio|complejo|departamento|apartamento)", r"vecin", r"toda la (casa|cuadra)"),
        "electrical_sign": _rx(r"\bbuzz", r"\bhum(s|ming)?\b", r"\bhot\b", r"\bwarm\b", r"crackl", r"\bpop(ped|ping)\b",
                               r"\bflicker", r"caliente", r"zumb", r"parpade"),
    },
    "qf-gfci-reset": {
        "repeat_trip": _REPEAT_WORDS,
        "wont_stay": _rx(r"won'?t (stay|reset|click|push)", r"doesn'?t (stay|reset|click)", r"(no|ni) se queda",
                         r"no (se )?resetea"),
        "electrical_sign": _rx(r"\bbuzz", r"\bhot\b", r"\bwarm\b", r"crackl", r"\bcrack(ed)?\b", r"\bbroken (cover|"
                               r"plate)", r"\bloose\b", r"caliente", r"zumb", r"\brot[oa]\b", r"suelt"),
    },
    "qf-disposal-reset": {
        "object_inside": _rx(r"(fell|dropped|stuck|lodged|is) (in|into|inside|down)", r"something (in|inside|stuck)",
                             r"(spoon|fork|knife|ring|glass|bone|toy|bottle cap|jewelry)", r"(cay[oó]|se me cay[oó]|"
                             r"atorad[oa]|metid[oa]) (en|dentro|adentro)", r"(cuchara|tenedor|cuchillo|anillo|vidrio|"
                             r"hueso|juguete)", r"\bglass\b"),
    },
    "qf-slow-drain": {
        "toilet": _TOILET,
        "several_drains": _rx(r"(all|both|every|multiple|several|two|three) (of )?(the |my )?(drains|sinks|fixtures)",
                              r"(sink|tub|shower) and (the )?(sink|tub|shower|toilet)", r"(todos|ambos|varios) (los )?"
                              r"(desag[uü]es|lavabos|fregaderos)",
                              r"(lavabo|fregadero|tina|regadera|ducha) y (el |la )?"
                              r"(lavabo|fregadero|tina|regadera|ducha|inodoro)"),
        "chemical": _rx(r"drano", r"liquid.?plumr", r"drain cleaner", r"chemical", r"\bbleach\b", r"\blye\b",
                        r"\bacid\b", r"destapa(ca[nñ]os|dor)", r"qu[ií]mic", r"\bcloro\b", r"\bsosa\b", r"[aá]cido"),
        "repeat_clog": _REPEAT_WORDS,
        "outside_home": _rx(r"parking", r"\blot\b", r"street", r"sidewalk", r"\byard\b", r"courtyard", r"\bpool\b",
                            r"\broof", r"gutter", r"storm drain", r"floor drain", r"estacionamiento", r"\bcalle\b",
                            r"banqueta", r"\bpatio\b", r"azotea", r"alberca", r"piscina", r"coladera de la calle"),
    },
}


def _gfci_shape(text: str) -> bool:
    if _GFCI_WORD.search(text):
        return True
    return bool(_OUTLET.search(text) and _WET_ROOM.search(text) and re.search(_NOT_WORKING, text, re.I))


def _breaker_shape(text: str) -> bool:
    if _BREAKER_WORD.search(text):
        return True
    return bool(_POWER_OUT.search(text) and re.search(_ROOM, text, re.I))


def _disposal_shape(text: str) -> bool:
    return bool(_DISPOSAL.search(text) and _DISPOSAL_SYMPTOM.search(text))


def _drain_shape(text: str) -> bool:
    return bool(_FIXTURE.search(text) and _CLOG.search(text))


# GFCI before breaker: "the bathroom outlet stopped working" is a GFCI first; a named breaker always wins.
_MATCHERS: list[tuple[str, Any]] = [("qf-gfci-reset", _gfci_shape), ("qf-breaker-reset", _breaker_shape),
                                    ("qf-disposal-reset", _disposal_shape), ("qf-slow-drain", _drain_shape)]
_BY_ID = {e["id"]: e for e in ENTRIES}


def match_entry(message: str) -> str | None:
    """The entry whose trigger family this message fits (structure, not safety). A named breaker beats GFCI."""
    if _BREAKER_WORD.search(message) and not _GFCI_WORD.search(message):
        return "qf-breaker-reset"
    return next((eid for eid, fn in _MATCHERS if fn(message)), None)


def exclusion(message: str) -> str | None:
    """The first universal exclusion class this message hits (None = none)."""
    return next((name for name, pat in EXCLUSIONS.items() if pat.search(message)), None)


def wants_intake(message: str) -> bool:
    """The resident asks for the repair request itself ("just send maintenance", "no tips", "manden a alguien")."""
    return bool(_SKIP.search(message))


def _no(why: str) -> QuickFixResult:
    return QuickFixResult(eligible=False, reason=why)


def check_eligibility(message: str, risk: Any, *, mode: Mode, lang: str = "en", urgency: str | None = None,
                      repeat: bool = False, used: list[str] | tuple[str, ...] = (),
                      semantic_level: str | None = None) -> QuickFixResult:
    """Whether tips may be shown for THIS message. `risk` is this turn's app.risk RiskDecision (the planner passes it);
    `urgency` the gate urgency; `repeat` a repeat-issue triage; `used` the entry ids already offered;
    `semantic_level` the classifier's risk level when known ("uncertain" counts like a degraded classifier)."""
    if mode not in ("approved_only", "demo_drafts"):
        return _no("mode_off")
    if risk is None:
        return _no("no_safety_decision")
    if getattr(risk, "response", None) != "none" or getattr(risk, "person_danger", False) or \
            getattr(risk, "needs_human", False) or getattr(risk, "incident", None) or getattr(risk, "kind", None) or \
            getattr(risk, "care", None):
        return _no("safety_decision")
    if urgency == "emergency":
        return _no("safety_decision")
    from app.risk.detect import detect  # read-only second look at the message (Agent A's deterministic layer)

    det = detect(message, None)
    if det.kind or det.mentioned_kind or det.care or det.concern:
        return _no("safety_detector")
    if ex := exclusion(message):
        return _no(f"excluded:{ex}")
    if wants_intake(message):
        return _no("resident_wants_intake")
    if _ALREADY.search(message):
        return _no("already_tried")
    if repeat:
        return _no("repeat_issue")
    eid = match_entry(message)
    if eid is None:
        return _no("no_matching_entry")
    for name, pat in _ENTRY_EXCLUSIONS.get(eid, {}).items():
        if pat.search(message):
            return _no(f"excluded:{name}")
    if (getattr(risk, "degraded", False) or semantic_level == "uncertain") and _POSSIBLE_RISK.search(message):
        return _no("classifier_uncertain_possible_risk")
    if eid in used:
        return _no("already_offered")
    entry = _BY_ID[eid]
    approved = entry.get("status") == APPROVED_STATUS and bool(entry.get("approved_by")) and \
        bool(entry.get("approved_on"))
    if not approved and mode != "demo_drafts":
        return _no("no_approved_content")
    steps = entry["steps"].get(lang) or entry["steps"]["en"]
    return QuickFixResult(eligible=True, reason="ok", entry_id=eid, category=entry["category"],
                          tips=list(steps[:MAX_TIPS]), draft=not approved,
                          label=None if approved else DRAFT_LABEL.get(lang, DRAFT_LABEL["en"]))


# ---- the follow-up turn --------------------------------------------------------------------------------------------
_RESOLVED = _rx(r"\b(yes|yeah|yep|yup|sure did|it did)\b", r"(that|it|this) (worked|fixed it|did it|did the trick|"
                r"helped|solved it)", r"\bworks?( now| again)?\b", r"working (now|again)", r"\bfixed\b", r"all good",
                r"(back|came back) on", r"\bsolved\b", r"\bperfect\b", r"\bs[ií]\b", r"funcion[oó]", r"ya (funciona|"
                r"sirve|qued[oó]|jala|prende|baja|drena)", r"se (arregl|solucion)[oó]", r"\blisto\b", r"\bresuelto\b")
_NOT_RESOLVED = _rx(r"^\W*(no|nope|nah|negative)\b", r"not really", r"(didn'?t|did not|doesn'?t|does not|won'?t|isn'?t)"
                    r" (work|help|fix|stay|change|do)", r"\bstill\b", r"no luck", r"same (thing|as before|problem)",
                    r"tripped again", r"(clicked|went) (off|out) again", r"nothing (happened|changed)",
                    r"no (funcion[oó]|sirvi[oó]|cambi[oó]|ayud[oó]|se arregl[oó])", r"\bsigue\b", r"todav[ií]a",
                    r"a[uú]n no", r"\bigual\b", r"\bmaybe\b", r"not sure", r"\bkind of\b", r"no s[eé]",
                    r"\bcan'?t (find|reach|open|see)\b", r"no (encuentro|alcanzo|veo)", r"\bwhere is\b",
                    r"no (lo|la) (encuentro|veo)")


def classify_reply(message: str) -> ReplyKind:
    """The answer to "did that fix it?". Order: skip, not resolved, resolved, unclear. A "yes" that also names an
    exclusion ("yes but now there's water under the sink") is not resolved."""
    if wants_intake(message):
        return "skip"
    if _NOT_RESOLVED.search(message) or exclusion(message):
        return "not_resolved"
    if _RESOLVED.search(message):
        return "resolved"
    return "unclear"


FlowAction = Literal["close_resolved", "intake", "ask_again", "none"]


@dataclass(frozen=True)
class FlowStep:
    action: FlowAction
    reply: ReplyKind | None = None
    entry_id: str | None = None


def offered_memory(mem: dict[str, Any], result: QuickFixResult) -> None:
    """Record an offer in planner memory (ids and counts only)."""
    mem[MEM_KEY] = {"state": "offered", "entry": result.entry_id, "asked": 0}
    mem[USED_KEY] = list(dict.fromkeys([*(mem.get(USED_KEY) or []), result.entry_id]))[-8:]


def follow_up(pending: dict[str, Any] | None, message: str, risk: Any) -> tuple[FlowStep, dict[str, Any] | None]:
    """The turn after an offer. `pending` is mem[MEM_KEY] popped by the planner at the start of the turn (so an offer
    lives for one turn only). Returns the step and the memory to keep (None = the flow is over).
    Any safety signal this turn ends the flow and the message is handled normally (safety steps come first)."""
    if not pending or pending.get("state") != "offered":
        return FlowStep("none"), None
    eid = pending.get("entry")
    if risk is None or getattr(risk, "response", "none") != "none" or getattr(risk, "person_danger", False):
        return FlowStep("none", entry_id=eid), None
    kind = classify_reply(message)
    if kind == "resolved":
        return FlowStep("close_resolved", kind, eid), None
    if kind in ("not_resolved", "skip"):
        return FlowStep("intake", kind, eid), None
    if match_entry(message) is None and len(message.split()) > 6:
        return FlowStep("none", kind, eid), None  # a different topic: never trap it in the tips flow
    if int(pending.get("asked", 0)) >= 1:
        return FlowStep("intake", kind, eid), None  # asked once already: the repair request, not a third question
    return FlowStep("ask_again", kind, eid), {**pending, "asked": int(pending.get("asked", 0)) + 1}


_ANSWER_LEAD = re.compile(r"^\W*(?:no+|nope|nah|yes|yeah|ok(?:ay)?|s[ií]|it|that|this)?\W*(?:it\s+)?(?:still\s+)?"
                          r"(?:didn'?t|did not|doesn'?t|isn'?t|won'?t|not)?\s*(?:work(?:ing)?|help|fix(?:ed)?(?: it)?)?"
                          r"\W*", re.I)


def issue_from_recent(recent: list[str] | None, entry_id: str | None) -> str | None:
    """The message that triggered the offer: the latest earlier message (recent ends with this turn) that fits the
    entry's trigger family. Message text stays in the conversation history, never in planner memory."""
    for text in reversed((recent or [])[:-1]):
        if entry_id and match_entry(text) == entry_id:
            return text
    return None


def intake_message(issue: str | None, reply: str) -> str:
    """What the repair intake reads: the original issue, plus extra details from the answer ("no, it's the hall
    bathroom, come in any time"); an answer that is only "no" / "send maintenance" adds nothing."""
    if not issue:
        return reply
    rest = _SKIP.sub(" ", _ANSWER_LEAD.sub("", reply, count=1)).strip(" ,.;!-")
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", rest)
    return f"{issue.rstrip('. ')}. {rest}" if len(words) >= 3 else issue
