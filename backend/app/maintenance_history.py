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
    found = utt.problem_objects(text) or utt.things(text)
    found = {_SAME.get(o, o) for o in found}
    for part, whole in _PART_OF.items():
        if part in found:
            found.discard(whole)
    specific = found - GENERIC_PARTS
    return specific or found


def related(a: str, b: str) -> bool:
    """True when two request texts are about the same thing (see the grouping rule)."""
    shared = objects(a) & objects(b)
    if not shared:
        return False
    if shared <= WHOLE_HOME:
        return True
    room_a, room_b = utt.room_in(a), utt.room_in(b)
    return not (room_a and room_b and room_a != room_b)


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
            if i.category == "maintenance" and i.interaction_id not in exclude and related(issue, i.subject or ""):
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


__all__ = ["RepeatHistory", "RelatedRequest", "current_time", "objects", "related", "related_history",
           "summary_line"]
