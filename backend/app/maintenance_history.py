"""Related maintenance history for a repeat issue (Sprint 8, Workstream C).

When the repeat-issue flag fires, the reply and the saved request explain the recurrence from AUTHORIZED history only:

- the signed-in demo resident's own workbook interactions (`Resident.interactions`, maintenance category), which the
  planner receives only for a verified resident (chat_engine passes `resident=None` otherwise), and
- that principal's own prototype records (`ScopedStore.records(persona_id=...)`: this persona only; nothing for a guest
  or after "I'm not the account holder"). As defence in depth, records whose persona is not the caller's are dropped
  here too, whatever store is passed in.

Grouping rule (one rule for both sources): two requests are related when they are about the same THING, read with the
shared object lexicon in `app.utterance` (EN + ES; no separate keyword list here):
- the objects of a text are what it says is wrong (`utterance.problem_objects`; a landmark such as "next to the fridge"
  is not the problem), falling back to every object it names (`utterance.things`) when the structure finds none;
- generic parts (drain, pipe, wall, floor, ceiling, cabinet, vent, fixture) count only when the text names no specific
  fixture ("kitchen sink drain" is about the sink; "the drain is clogged" is about the drain); a part of a fixture wins
  over the fixture (a lock or doorknob over the door, the ice maker over the fridge);
- "hot water" and "water heater" are one thing;
- when both texts name a room and the rooms differ, a room-bound fixture is a different one (the kitchen sink is not the
  bathroom sink). Whole-home systems (AC, heat, thermostat, water heater, vents) are the same system in any room.
Texts with no object never relate to anything (no history claim from wording alone).

Counting rule (fix round): only REPAIR REQUESTS are counted, never every contact. A workbook subject counts when it
reports a problem; a contact ABOUT an earlier repair is not a second request and is skipped: a question ("Is the AC
getting replaced?", "When will the ceiling be fixed?"), a callback or follow-up ("Callback: HVAC vendor visit", "Pest
follow-up"), a vendor visit or evaluation, an inspection, a notice or a reminder. Prototype records of kind
`maintenance_request` are always requests. The wording therefore always says "maintenance requests".

Inclusion rule: PRIOR requests only. The draft being written now is never a record yet, so it is never counted; any
record id passed in `exclude` (e.g. the request just saved) is skipped too. The wording says "related maintenance
requests", meaning earlier ones, never "including this one".

Window rule: computed from real timestamps against an injectable `now` (`current_time()`, patched in tests). The window
starts at the EARLIEST dated related request: within 7 days -> "over the last 7 days"; within 30 days -> "over the last
30 days"; older -> "since <Month>" (with the year when it is not the current year). Undated items are counted but
do not set the window; if none is dated there is no window phrase at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app import utterance as utt

GENERIC_PARTS = frozenset({"drain", "pipe", "wall", "floor", "ceiling", "cabinet", "vent", "fixture"})
WHOLE_HOME = frozenset({"ac", "heat", "thermostat", "water heater", "vent"})
_PART_OF = {"lock": "door", "doorknob": "door", "peephole": "door", "doorbell": "door", "ice maker": "fridge"}
_SAME = {"hot water": "water heater"}
# Spellings the shared lexicon reads under another name (kept here so grouping, not the lexicon, changes)
_ALIASES = [(re.compile(r"\bbath ?tubs?\b", re.I), "tub")]
# A contact ABOUT an earlier repair (see the counting rule); matched on the short subject only
_NOT_A_REQUEST = re.compile(
    r"\?\s*$|^\W*(?:callback|call ?back|follow[- ]?up|seguimiento|llamada|re:|status|update|estado)\b|"
    r"\b(?:follow[- ]?up|vendor (?:visit|evaluation|appointment)|evaluation|inspection|notice|reminder|aviso|"
    r"recordatorio|inspecci[oó]n|evaluaci[oó]n)\b|^\W*(?:when|is|are|will|can|did|has|why|cu[aá]ndo|por qu[eé])\b",
    re.I)
MAX_REFERENCES = 10

_MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"],
           "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                  "noviembre", "diciembre"]}


def current_time() -> datetime:
    """The fixed point every window is computed from (naive UTC). Tests patch this function."""
    return datetime.now(UTC).replace(tzinfo=None)


def objects(text: str) -> set[str]:
    """The thing(s) a request is about, per the grouping rule in the module docstring."""
    for pat, name in _ALIASES:
        text = pat.sub(name, text or "")
    found = utt.problem_objects(text) or utt.things(text)
    found = {_SAME.get(o, o) for o in found}
    for part, whole in _PART_OF.items():
        if part in found:
            found.discard(whole)
    if "pests" in found:  # different pests are different requests (a mouse is not the roach problem)
        species = {name for name, pat in _SPECIES if pat.search(text or "")}
        if species:
            found = (found - {"pests"}) | species
    specific = found - GENERIC_PARTS
    return specific or found


_SPECIES = [("roaches", re.compile(r"roach|cucarach", re.I)), ("ants", re.compile(r"\bants?\b|hormig", re.I)),
            ("rodents", re.compile(r"\bmice\b|\bmouse\b|\brats?\b|rodent|rat[oó]n|ratones", re.I)),
            ("bedbugs", re.compile(r"bed ?bugs?|chinches?", re.I))]


def related(a: str, b: str) -> bool:
    """True when two request texts are about the same thing (see the grouping rule)."""
    shared = objects(a) & objects(b)
    if not shared:
        return False
    if shared <= WHOLE_HOME:
        return True
    room_a, room_b = utt.room_in(a), utt.room_in(b)
    return not (room_a and room_b and room_a != room_b)


# Symptom classes (last fix round): which open request a new report is about, when one thing has several open
# requests ("AC rattling" vs "AC quit cooling"). A generic failure ("not working", "died", "out", "broke") is
# compatible with any symptom; two reports with specific symptoms are the same request only when a class is shared.
_SYMPTOMS: list[tuple[str, re.Pattern[str]]] = [
    ("noise", re.compile(r"rattl|nois|loud|buzz|hum+(?:s|ing)?\b|click|bang|grind|squeak|squeal|whistl|hiss|"
                         r"pop+(?:s|ing)?\b|ruido|zumb|tru?en", re.I)),
    ("leak", re.compile(r"leak|drip|puddl|\bwet\b|water on|soak|overflow|gote|fuga|charco|moja", re.I)),
    ("cooling", re.compile(r"cool|warm|hot air|\b[89]\d ?(?:degrees|in here)|enfr|calor", re.I)),
    ("heating", re.compile(r"\bheat(?:ing)?\b(?! ?pump)|cold air|blowing cold|freezing|no calienta|calefacc|fr[ií]o",
                           re.I)),
    ("clog", re.compile(r"clog|drain|backed up|backing up|slow|gurgl|tapad|atascad|no drena|desag", re.I)),
    ("smell", re.compile(r"smell|stink|odor|olor|huele", re.I)),
    ("stuck", re.compile(r"stuck|stick|jamm|won'?t (?:open|close|lock|latch|stay (?:closed|shut|open))|off track|"
                         r"trabad|no (?:abre|cierra)|no se (?:queda|mantiene) cerrad", re.I)),
    # a PART of the thing failed (last round): a latch, hinge, handle, seal... a new problem, not "it died again"
    ("part", re.compile(r"latch|hinge|\bhandles?\b|knob|\bseals?\b|gasket|\bracks?\b|shelf|drawer|button|panel|"
                        r"filter|\bcords?\b|burner|"
                        r"snapp|broke off|fell off|came off|bisagra|manija|perilla|empaque|pestillo|bot[oó]n|repisa",
                        re.I)),
    ("power", re.compile(r"spark|flicker|no power|tripp|breaker|dead outlet|sin luz|chispa", re.I)),
    ("pests", re.compile(r"roach|\bants?\b|\bmice\b|\bmouse\b|\bbugs?\b|\brats?\b|cucarach|hormig|rat[oó]n", re.I)),
    ("damage", re.compile(r"crack|broken glass|torn|peel|stain|mold|mould|moho|mancha|rot[oa]?\b", re.I)),
]


def symptoms(text: str) -> set[str]:
    """The specific symptom classes a request text names (empty for a generic 'not working')."""
    return {name for name, pat in _SYMPTOMS if pat.search(text or "")}


def match_score(new: str, old: str) -> int:
    """0 when `old` is not the same request as `new`; otherwise 1 (same thing) + 2 per shared symptom class.
    - same thing, a generic new report ("it died again", "still not working"): the same request as any open one;
    - a SPECIFIC new symptom ("the door latch snapped") against an old GENERIC request ("dishwasher died"): a new
      problem (0); with specific symptoms on both, the same request only when every new symptom is already on the open
      one ("not cooling AND noisy" is not just the open "AC rattling")."""
    if not related(new, old):
        return 0
    a, b = symptoms(new), symptoms(old)
    if a - b:  # a specific symptom the open request does not have is a new problem
        return 0
    return 1 + 2 * len(a & b)


_LABEL_ES = {"ac": "aire acondicionado", "heat": "calefacción", "water heater": "calentador de agua",
             "sink": "fregadero", "faucet": "grifo", "toilet": "inodoro", "shower": "ducha o tina",
             "dishwasher": "lavaplatos",
             "fridge": "refrigerador", "oven": "estufa u horno", "microwave": "microondas", "disposal": "triturador",
             "washer": "lavadora", "dryer": "secadora", "window": "ventana", "door": "puerta", "lock": "cerradura",
             "fan": "ventilador", "light": "luz", "outlet": "enchufe", "ceiling": "techo", "pests": "plagas",
             "drain": "desagüe", "detector": "detector", "roaches": "cucarachas", "ants": "hormigas",
             "rodents": "ratones", "bedbugs": "chinches", "closet": "clóset"}
_LABEL_EN = {"ac": "AC", "pests": "pest", "oven": "stove or oven", "shower": "shower or tub", "heat": "heating",
             "roaches": "roach", "ants": "ant", "rodents": "mouse or rat", "bedbugs": "bed bug"}


def request_label(text: str, lang: str = "en") -> str:
    """How the assistant cites a saved request: by what it is about, never by the resident's raw words.
    'your AC repair request' / 'su solicitud de reparación: aire acondicionado'."""
    objs = sorted(objects(text), key=lambda o: _position(o, text))
    if lang == "es":
        names = ", ".join(_LABEL_ES.get(o, o) for o in objs)
        return f"su solicitud de reparación: {names}" if names else "su solicitud de reparación"
    # adjacent objects are one compound thing ("closet light"); others are joined with "and"
    parts: list[str] = []
    for i, o in enumerate(objs):
        word = _LABEL_EN.get(o, o)
        if i and _position(o, text) - _end(objs[i - 1], text) <= 1:
            parts[-1] = f"{parts[-1]} {word}"
        else:
            parts.append(word)
    names = " and ".join(parts)
    return f"your {names} repair request" if names else "your repair request"


def _span(obj: str, text: str) -> tuple[int, int]:
    pats = [pat for name, pat in utt._THINGS if name == obj] + [pat.pattern for name, pat in _SPECIES if name == obj]
    for pat in pats:
        if m := re.search(pat, text or "", re.I):
            return m.start(), m.end()
    return len(text or ""), len(text or "")


def _position(obj: str, text: str) -> int:
    return _span(obj, text)[0]


def _end(obj: str, text: str) -> int:
    return _span(obj, text)[1]


@dataclass(frozen=True)
class RelatedRequest:
    reference: str
    source: str  # "resident_history" | "prototype_store"
    when: datetime | None
    subject: str


@dataclass
class RepeatHistory:
    count: int = 0
    earliest: date | None = None
    latest: date | None = None
    window_days: int | None = None
    items: list[RelatedRequest] = field(default_factory=list)
    now: date | None = None

    @property
    def references(self) -> list[str]:
        return [i.reference for i in self.items][:MAX_REFERENCES]

    def window(self, lang: str = "en", singular: bool = False) -> str:
        """'over the last 30 days' / 'since June' (singular: 'in the last 30 days' / 'from June'); '' when undated."""
        if self.earliest is None or self.window_days is None or self.now is None:
            return ""
        es = lang == "es"
        if self.window_days <= 30:
            n = 7 if self.window_days <= 7 else 30
            if es:
                return f"de los últimos {n} días" if singular else f"en los últimos {n} días"
            return f"in the last {n} days" if singular else f"over the last {n} days"
        month = _MONTHS["es" if es else "en"][self.earliest.month - 1]
        if self.earliest.year != self.now.year:
            month += f" de {self.earliest.year}" if es else f" {self.earliest.year}"
        if es:
            return f"de {month}" if singular else f"desde {month}"
        return f"from {month}" if singular else f"since {month}"

    def to_record(self) -> dict[str, Any]:
        """What the saved request carries (prototype_records data `repeat_history`). Prior requests only."""
        return {"count": self.count, "window": self.window("en"), "earliest": _iso(self.earliest),
                "latest": _iso(self.latest), "references": self.references, "includes_current_request": False,
                "source": "signed-in resident's own history and prototype requests"}


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _as_naive(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v.astimezone(UTC).replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str) and v.strip():
        try:
            return _as_naive(datetime.fromisoformat(v.strip().replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def is_repair_request(subject: str) -> bool:
    """A history subject that reports a problem, not a question/callback/follow-up about one (counting rule)."""
    return bool((subject or "").strip()) and not _NOT_A_REQUEST.search(subject.strip())


def _record_text(r: dict[str, Any]) -> str:
    issue = next((str(f.get("value") or "") for f in r.get("fields") or [] if f.get("key") == "issue"), "")
    return issue or str(r.get("title") or "")


def related_history(issue: str, *, resident: Any = None, records: list[dict[str, Any]] | None = None,
                    persona_id: str | None = None, exclude: set[str] | frozenset[str] = frozenset(),
                    now: datetime | None = None) -> RepeatHistory:
    """Earlier maintenance requests about the same thing as `issue`, from the caller's own history only.

    `resident` must be the verified resident (or None); `records` the principal's own prototype records. A guest
    (`persona_id` None) gets nothing from records. The current draft is not a record, so it is never counted."""
    now_dt = _as_naive(now) or current_time()
    found: list[RelatedRequest] = []
    if not objects(issue):
        return RepeatHistory(now=now_dt.date())
    if resident is not None:
        for i in getattr(resident, "interactions", []) or []:
            if i.category == "maintenance" and i.interaction_id not in exclude and \
                    is_repair_request(i.subject or "") and related(issue, i.subject or ""):
                found.append(RelatedRequest(i.interaction_id, "resident_history", _as_naive(i.timestamp),
                                            i.subject or ""))
    if persona_id:
        for r in records or []:
            if r.get("kind") != "maintenance_request" or (r.get("persona_id") or None) != persona_id or \
                    r.get("id") in exclude or r.get("status") == "cancelled":
                continue
            if related(issue, _record_text(r)):
                found.append(RelatedRequest(str(r.get("id")), "prototype_store", _as_naive(r.get("created_at")),
                                            str(r.get("title") or "")))
    seen: set[str] = set()
    items = [x for x in found if not (x.reference in seen or seen.add(x.reference))]  # type: ignore[func-returns-value]
    items.sort(key=lambda x: (x.when is None, x.when or datetime.min))
    dated = [x.when for x in items if x.when is not None]
    earliest = min(dated).date() if dated else None
    latest = max(dated).date() if dated else None
    days = max(0, (now_dt.date() - earliest).days) if earliest else None
    return RepeatHistory(count=len(items), earliest=earliest, latest=latest, window_days=days, items=items,
                         now=now_dt.date())


def summary_line(h: RepeatHistory, lang: str = "en") -> str:
    """Card / staff line: '3 earlier related requests since June (I002, I003, I008)'. '' for none."""
    if h.count == 0:
        return ""
    one = h.count == 1
    win = h.window(lang, singular=one)
    refs = ", ".join(h.references)
    if lang == "es":
        head = "1 solicitud anterior relacionada" if one else f"{h.count} solicitudes anteriores relacionadas"
    else:
        head = "1 earlier related request" if one else f"{h.count} earlier related requests"
    return re.sub(r"\s+", " ", f"{head} {win} ({refs})").strip()


__all__ = ["RelatedRequest", "RepeatHistory", "current_time", "is_repair_request", "match_score", "objects",
           "related", "related_history", "request_label", "summary_line", "symptoms"]
