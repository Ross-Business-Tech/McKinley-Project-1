"""Synthetic XLSX import, Residents/Interactions join and the allowlisted SAFE_CONTEXT builder.

Raw rows never leave this module. Callers receive a `SafeContext` that contains only allowlisted,
redacted, topic-relevant facts with provenance. `full_text`, contact details, rent, balances and raw
staff notes are never forwarded.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import openpyxl

from app.models import ContextField, SafeContext
from app.safety import looks_like_injection, sanitize_field

RESIDENT_COLUMNS = [
    "resident_id", "first_name", "last_name", "email", "phone", "preferred_contact", "preferred_language",
    "community", "region", "unit_type", "household_size", "roommates", "pets", "vehicles", "move_in_date",
    "lease_start", "lease_end", "lease_term_months", "monthly_rent", "renewal_status", "autopay",
    "current_balance", "late_payments_last_12mo", "renters_insurance", "lead_source",
    "permission_to_enter_default", "preferred_entry_window", "amenities_used", "work_orders_last_12mo",
    "open_work_orders", "notes_for_staff",
]
INTERACTION_COLUMNS = [
    "interaction_id", "resident_id", "timestamp", "channel", "category", "subject", "full_text", "status",
    "resolved_date", "follow_up_needed",
]
REQUIRED_RESIDENT = {"resident_id", "first_name", "community", "preferred_contact", "preferred_language"}
REQUIRED_INTERACTION = {"interaction_id", "resident_id", "timestamp", "category", "subject", "status"}

# Fields that exist in the source but are never forwarded to the model.
NEVER_FORWARDED = [
    "last_name", "email", "phone", "unit_type", "monthly_rent", "current_balance",
    "late_payments_last_12mo", "autopay", "household_size", "roommates", "vehicles", "pets", "lead_source",
    "permission_to_enter_default", "notes_for_staff (raw)", "Interactions.full_text",
]

DATA_REFERENCE_DATE = date(2026, 10, 30)  # "today" in the synthetic workbook README


class WorkbookError(Exception):
    pass


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    resident_id: str
    timestamp: datetime | None
    channel: str
    category: str
    subject: str
    full_text: str  # kept server-side only; used for nothing that reaches the model
    status: str
    resolved_date: date | None
    follow_up_needed: bool


@dataclass(frozen=True)
class Resident:
    resident_id: str
    row: dict[str, str]  # normalized strings for every source column (missing -> "")
    interactions: list[Interaction] = field(default_factory=list)

    def get(self, key: str) -> str:
        return self.row.get(key, "")


@dataclass
class Workbook:
    residents: dict[str, Resident]
    interaction_count: int
    warnings: list[str]
    source: str


def _norm(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return " ".join(str(v).split())


def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _sheet_rows(wb: openpyxl.Workbook, name: str, required: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    if name not in wb.sheetnames:
        raise WorkbookError(f"Missing required sheet '{name}'")
    rows = list(wb[name].iter_rows(values_only=True))
    if not rows:
        raise WorkbookError(f"Sheet '{name}' is empty")
    header = [_norm(h) for h in rows[0]]
    missing = required - set(header)
    if missing:
        raise WorkbookError(f"Sheet '{name}' missing required columns: {sorted(missing)}")
    out = []
    for r in rows[1:]:
        if r is None or all(c is None for c in r):
            continue
        out.append({h: _norm(c) for h, c in zip(header, r, strict=False) if h})
    return header, out


def load_workbook(path: Path) -> Workbook:
    if not path.exists():
        raise WorkbookError(f"Workbook not found at {path}. Place the synthetic XLSX there (see README).")
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # corrupt/non-xlsx file
        raise WorkbookError(f"Could not open workbook: {type(exc).__name__}") from exc

    warnings: list[str] = []
    r_header, r_rows = _sheet_rows(wb, "Residents", REQUIRED_RESIDENT)
    i_header, i_rows = _sheet_rows(wb, "Interactions", REQUIRED_INTERACTION)
    wb.close()
    for col in set(RESIDENT_COLUMNS) - set(r_header):
        warnings.append(f"Residents column '{col}' absent; treated as missing")
    for col in set(INTERACTION_COLUMNS) - set(i_header):
        warnings.append(f"Interactions column '{col}' absent; treated as missing")

    interactions_by_resident: dict[str, list[Interaction]] = {}
    for row in i_rows:
        rid = row.get("resident_id", "")
        if not rid or not row.get("interaction_id"):
            warnings.append("Skipped interaction row without IDs")
            continue
        resolved = _parse_dt(row.get("resolved_date", ""))
        interactions_by_resident.setdefault(rid, []).append(Interaction(
            interaction_id=row["interaction_id"],
            resident_id=rid,
            timestamp=_parse_dt(row.get("timestamp", "")),
            channel=row.get("channel", ""),
            category=row.get("category", "").lower(),
            subject=row.get("subject", ""),
            full_text=row.get("full_text", ""),
            status=row.get("status", "").lower() or "unknown",
            resolved_date=resolved.date() if resolved else None,
            follow_up_needed=row.get("follow_up_needed", "").upper() == "Y",
        ))

    residents: dict[str, Resident] = {}
    for row in r_rows:
        rid = row.get("resident_id", "")
        if not rid:
            warnings.append("Skipped resident row without resident_id")
            continue
        full = {c: row.get(c, "") for c in RESIDENT_COLUMNS}
        items = sorted(interactions_by_resident.pop(rid, []), key=lambda i: i.timestamp or datetime.min)
        residents[rid] = Resident(resident_id=rid, row=full, interactions=items)
    orphans = sum(len(v) for v in interactions_by_resident.values())
    if orphans:
        warnings.append(f"{orphans} interaction rows reference unknown residents; ignored")

    return Workbook(
        residents=residents,
        interaction_count=len(i_rows),
        warnings=warnings,
        source=path.name,
    )


# ---- topic relevance -----------------------------------------------------------------

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "hvac": ["ac", "a/c", "air condition", "cooling", "cool", "heat", "heater", "hvac", "thermostat",
             "furnace", "compressor", "air handler",
             # Spanish (minimal; R012 prefers Spanish). Other languages: see docs/GATE_DESIGN.md limitations.
             "aire acondicionado", "calefacción", "calefaccion", "no enfría", "no enfria"],
    "plumbing": ["leak", "drip", "faucet", "sink", "toilet", "pipe", "drain", "clog", "water heater",
                 "shower", "tub", "water", "toliet", "clogd", "overflow", "fuga", "gotea", "grifo", "llave",
                 "fregadero",
                 "inodoro", "tubería", "agua caliente"],
    "appliance": ["dishwasher", "fridge", "refrigerator", "oven", "stove", "washer", "dryer", "microwave",
                  "disposal", "horno", "estufa", "lavadora", "secadora", "refrigerador", "lavaplatos"],
    "pest": ["roach", "bug", "pest", "mice", "mouse", "ants", "rodent", "cucaracha", "hormiga", "ratón", "raton",
             "ratones", "chinche", "plaga"],
    "renewal": ["renew", "renewal", "lease", "offer", "move out", "move-out", "notice", "renovar", "renovación",
                "renovacion", "contrato"],
    "billing": ["rent", "balance", "payment", "pay", "bill", "charge", "fee", "late"],
    "package": ["package", "delivery", "delivered", "mail"],
    "noise": ["noise", "neighbor", "loud", "upstairs"],
    "amenity": ["pool", "gym", "fitness", "clubhouse", "dog park", "amenity"],
    "contact_preference": ["call me", "don't call", "dont call", "text me", "email me", "contact me",
                           "sleeping", "reach me", "phone", "call"],
}
MAINTENANCE_TOPICS = {"hvac", "plumbing", "appliance", "pest"}
CATEGORY_TOPIC = {"renewal": "renewal", "billing": "billing", "package": "package",
                  "noise or neighbor": "noise", "amenity": "amenity"}


def detect_topics(text: str) -> list[str]:
    t = f" {text.lower()} "
    topics = []
    for topic, words in TOPIC_KEYWORDS.items():
        for w in words:
            if re.search(rf"(?<![a-z]){re.escape(w)}(?:e?s)?(?![a-z])", t):
                topics.append(topic)
                break
    generic_maint = re.search(r"broken|repair|fix|maintenance|work order|not working|stopped|no funciona|"
                              r"roto|reparar|mantenimiento|no calienta|chirp|beep|smoke detector|outlet|"
                              r"light (is out|won'?t)|lock (is|won'?t|sticks)|window (won'?t|is stuck)|ceiling|mold|"
                              r"door (won'?t|is stuck|sticks)|crack|flicker|locked out|lockout|fell off|came off|"
                              r"window|light (bulb|fixture|switch)|lights? (is|are|keep)|\block\b|no heat|heater|"
                              r"overflow|toliet|clogd|no tengo agua|no hay agua|se cay[oó]|no prende", t)
    if generic_maint and not (set(topics) & MAINTENANCE_TOPICS):
        topics.append("maintenance_general")
    return topics


def interaction_topics(i: Interaction) -> set[str]:
    """Classify a history item from its category + short subject only (not full_text)."""
    topics = set(detect_topics(i.subject)) - {"contact_preference"}
    if i.category in CATEGORY_TOPIC:
        topics.add(CATEGORY_TOPIC[i.category])
    if i.category == "maintenance" and not topics & MAINTENANCE_TOPICS:
        topics.add("maintenance_general")
    return topics


def tenure_band(move_in: str) -> str | None:
    dt = _parse_dt(move_in)
    if not dt:
        return None
    months = (DATA_REFERENCE_DATE.year - dt.year) * 12 + DATA_REFERENCE_DATE.month - dt.month
    if months < 0:
        return "upcoming move-in"
    if months < 6:
        return "under 6 months"
    if months < 12:
        return "6-12 months"
    if months < 36:
        return "1-3 years"
    return "3+ years"


_CONTACT_CLAUSE = re.compile(
    r"\b(call|text|email|phone|contact|reach|before \d|after \d|a\.?m\.?|p\.?m\.?|spanish|english|in writing)\b",
    re.IGNORECASE,
)


def contact_note_clauses(note: str) -> list[str]:
    """Keep only contact-timing/channel clauses of a staff note. Everything else is withheld."""
    if not note or looks_like_injection(note):
        return []
    out = []
    for clause in re.split(r"[;.]\s*", note):
        clause = clause.strip()
        if clause and _CONTACT_CLAUSE.search(clause):
            safe = sanitize_field(clause, 100)
            if safe:
                out.append(safe)
    return out


def _fmt_date(d: datetime | date | None) -> str:
    if d is None:
        return "unknown date"
    return d.strftime("%Y-%m-%d")


def build_resident_context(res: Resident, message: str, persona_id: str) -> SafeContext:
    topics = detect_topics(message)
    is_maint = bool(set(topics) & (MAINTENANCE_TOPICS | {"maintenance_general"}))
    fields: list[ContextField] = []
    dropped: list[str] = []

    def add(name: str, value: str | None, source: str) -> None:
        if value:
            fields.append(ContextField(name=name, value=value, source=source))

    add("first_name", sanitize_field(res.get("first_name"), 40), "Residents.first_name")
    add("community", sanitize_field(res.get("community"), 60), "Residents.community")
    add("tenure", tenure_band(res.get("move_in_date")), "Residents.move_in_date (banded)")
    add("preferred_language", sanitize_field(res.get("preferred_language"), 30), "Residents.preferred_language")
    add("preferred_contact_channel", sanitize_field(res.get("preferred_contact"), 30),
        "Residents.preferred_contact")

    if "renewal" in topics:
        add("renewal_status", sanitize_field(res.get("renewal_status"), 40), "Residents.renewal_status")
    if is_maint:
        add("open_maintenance_requests", res.get("open_work_orders") or None, "Residents.open_work_orders")
        add("preferred_entry_window", sanitize_field(res.get("preferred_entry_window"), 40),
            "Residents.preferred_entry_window")

    if "contact_preference" in topics or "renewal" in topics or is_maint:
        note = res.get("notes_for_staff")
        clauses = contact_note_clauses(note)
        if note and not clauses and looks_like_injection(note):
            dropped.append("notes_for_staff: dropped by instruction-injection screen")
        for c in clauses:
            add("staff_noted_contact_preference", c, "Residents.notes_for_staff (contact clause only)")

    # Relevant history: same topic(s) as the message, summarized from structured columns + subject only.
    msg_topics = set(topics) - {"contact_preference"}
    relevant = [i for i in res.interactions if interaction_topics(i) & msg_topics] if msg_topics else []
    for i in relevant[-6:]:
        subject = sanitize_field(i.subject, 80)
        if subject is None:
            dropped.append(f"Interactions[{i.interaction_id}].subject: dropped by injection screen")
            subject = "(subject withheld)"
        status = i.status if i.status != "closed" else f"closed {_fmt_date(i.resolved_date)}"
        follow = "; follow-up still owed to resident" if i.follow_up_needed and i.status == "open" else ""
        add("related_history",
            f"{_fmt_date(i.timestamp)} · {i.category} · \"{subject}\" · {status}{follow}",
            f"Interactions[{i.interaction_id}]")
    if msg_topics:
        maint_related = [i for i in relevant if i.category == "maintenance"]
        if msg_topics <= {"maintenance_general"}:  # generic wording: "related" needs a shared word
            maint_related = [i for i in maint_related if _shares_word(message, i.subject)]
        open_followups = [i for i in relevant if i.follow_up_needed and i.status == "open"]
        add("related_history_count", str(len(relevant)) if relevant else "0",
            "Interactions (topic-matched count)")
        if len(maint_related) >= 2:
            add("repeat_issue_flag", f"{len(maint_related)} related maintenance contacts on record",
                "Interactions (derived)")
        if open_followups:
            add("open_commitment_flag", f"{len(open_followups)} related item(s) open with follow-up owed",
                "Interactions (derived)")

    return SafeContext(
        persona_id=persona_id,
        persona_kind="resident",
        audience="resident",
        record_found=True,
        topics=topics,
        fields=fields,
        withheld_fields=NEVER_FORWARDED,
        dropped_items=dropped,
        notes=[
            "History is summarized from category/subject/status columns; full transcripts are not forwarded.",
            "Interactions are a sample of history and may be incomplete.",
        ],
    )


_STOP = {"again", "still", "there", "about", "with", "from", "this", "that", "have", "keeps", "not", "working",
         "broken", "repair", "please", "after", "before", "when", "will"}


def _shares_word(a: str, b: str) -> bool:
    """Crude relatedness for generic maintenance wording: a shared content word (5-char prefix)."""
    def words(x: str) -> set[str]:
        return {w[:5] for w in re.findall(r"[a-záéíóúñ]{4,}", x.lower()) if w not in _STOP}
    return bool(words(a) & words(b))


def render_context_block(ctx: SafeContext) -> str:
    """Text block placed inside <safe_context> in the aware-mode user turn."""
    lines = [
        f"audience: {ctx.audience}",
        f"record_found: {'yes' if ctx.record_found else 'no'}",
        f"message_topics: {', '.join(ctx.topics) or 'none detected'}",
    ]
    for f in ctx.fields:
        lines.append(f"{f.name}: {f.value}")
    for n in ctx.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)
