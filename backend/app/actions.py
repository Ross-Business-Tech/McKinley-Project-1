"""Customer action planner and the prototype system of record (F4-F9 behaviour on top of the decision gate).

Rules enforced here, in code rather than in the prompt:
- An action is only ever *proposed* by a chat turn. A prototype record is written only after the person
  explicitly confirms (button -> /api/actions/confirm, or an unambiguous "yes" to a ready read-back), except for
  emergencies, where an urgent staff-queue note is written immediately (F6 "alert on-call, create URGENT").
- Maintenance requests require a verified resident record (I-10/I-11 draft permission matrix). Status lookup (F8)
  requires the same. Claims made in the message text never unlock anything.
- Confirmation re-reads the server-side draft; the browser cannot supply or alter the fields that get saved.
- Records live in SQLite tables labelled prototype. Nothing is sent to Yardi, a CRM, a pager or a person.
"""

import logging
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app import maintenance_history as mh
from app import quickfix
from app import understanding as und
from app import utterance as utt
from app import workflow_state as wf
from app.context import Resident, Workbook, build_resident_context
from app.db import Store
from app.dialogue import Act, classify_turn
from app.handoff import build_handoff
from app.intake import (
    accepts_question_note,
    appliance_in,
    asks_about_other_resident,
    asks_for_english,
    asks_for_manager,
    asks_for_plain_ticket,
    asks_for_priority,
    asks_for_promise,
    asks_for_spanish,
    asks_how_reached,
    asks_privacy,
    asks_saved_contact,
    back_to_topic,
    bare_area_answer,
    channel_said,
    city_in,
    claims_account_access,
    claims_prior_decision,
    community_in,
    contact_change,
    describes_issue,
    detail_to_add,
    detect_language,
    existing_request_words,
    extract_area_correction,
    extract_beds,
    extract_clock_preference,
    extract_contact_pref,
    extract_days,
    extract_entry,
    extract_issue_restate,
    extract_issue_swap,
    extract_location,
    extract_location_change,
    extract_move_in,
    extract_pets,
    extract_time_of_day,
    flexible_answer,
    frustration_only,
    infer_location,
    is_accommodation,
    is_additive,
    is_affirmative,
    is_after_send_question,
    is_bare_no,
    is_bare_ok,
    is_bare_yes,
    is_booking_question,
    is_cancel_submitted,
    is_change_request,
    is_common_area,
    is_decline,
    is_entry_plain_yes,
    is_eviction_worry,
    is_explicit_send,
    is_issue_description,
    is_lease_break,
    is_lockout,
    is_lost_or_frustrated_with_chat,
    is_meta_complaint,
    is_meta_question,
    is_noise_complaint,
    is_phone_question,
    is_rent_withholding,
    is_security_repair,
    is_sms_opt_out,
    is_status_request,
    is_steering_question,
    is_tour_request,
    is_vendor_contact,
    match_faq,
    matches_words,
    mentions_neighbor,
    negated_days,
    no_issue_content,
    non_latin_script,
    not_account_holder,
    policy_topic,
    question_kinds,
    refers_to_existing,
    refuses_tour,
    says_repeat_es,
    says_resident,
    split_issues,
    states_named_repeat,
    states_price_claim,
    states_repeat,
    steering_kind,
    strip_correction_lead,
    strip_greeting,
    strip_language_request,
    strip_spanish_request,
    unsafe_diy_kind,
    visit_note,
)
from app.models import (
    STATUS_LABEL,
    ActionField,
    ActionKind,
    ActionResult,
    Channel,
    FunctionId,
    GateDecision,
    HandoffRecommendation,
    MaintenanceTriage,
    ProposedAction,
    PrototypeRecord,
    SafeContext,
    StatusItem,
    WorkflowId,
    WorkflowSelection,
)
from app.risk.policy import is_people_hazard
from app.safety import looks_like_injection, redact, sanitize_field
from app.templates import CARD_NOTE, CHIPS, CONFIRM, CONFIRM_LABEL, DIY_ADVICE, Lang, t
from app.workflows import LABELS, WORKFLOW_VERSION, legacy_checks_approved, legacy_draft_steps

log = logging.getLogger("mckinley.actions")

PREFIX: dict[ActionKind, str] = {"maintenance_request": "DEMO-WO", "tour_request": "DEMO-TOUR",
                                  "staff_handoff": "DEMO-TASK"}
REQUIRED: dict[ActionKind, list[str]] = {
    "maintenance_request": ["issue", "location", "entry"],  # I-19 DRAFT minimum
    "tour_request": ["area", "days", "time"],  # I-15 DRAFT minimum
    "staff_handoff": [],
}
LABEL: dict[str, dict[Lang, str]] = {
    "issue": {"en": "What's wrong", "es": "Problema"},
    "location": {"en": "Where", "es": "Dónde"},
    "entry": {"en": "Entry permission", "es": "Permiso de entrada"},
    "contact": {"en": "Contact preference", "es": "Preferencia de contacto"},
    "entry_window": {"en": "Best time for visits", "es": "Mejor horario"},
    "priority_note": {"en": "Review", "es": "Revisión"},
    "area": {"en": "Community or city", "es": "Comunidad o ciudad"},
    "days": {"en": "Preferred days", "es": "Días preferidos"},
    "time": {"en": "Time of day", "es": "Hora del día"},
    "beds": {"en": "Beds", "es": "Recámaras"},
    "move_in": {"en": "Move-in", "es": "Mudanza"},
    "pets": {"en": "Pets", "es": "Mascotas"},
    "requests": {"en": "Also asked for (office decides)", "es": "También pidió (decide la oficina)"},
    "topic": {"en": "About", "es": "Tema"},
    "message": {"en": "What you said", "es": "Lo que dijo"},
    "who": {"en": "Account", "es": "Cuenta"},
    "earlier": {"en": "Details so far", "es": "Detalles hasta ahora"},
    "contact_route": {"en": "Contact route", "es": "Vía de contacto"},
    "questions": {"en": "Questions to answer", "es": "Preguntas por responder"},
    "budget": {"en": "Budget (you said)", "es": "Presupuesto (según usted)"},
    "notes": {"en": "Notes for the visit", "es": "Notas para la visita"},
    "related_history": {"en": "Related history", "es": "Historial relacionado"},  # Sprint 8 C: own earlier requests
}
TITLE: dict[ActionKind, dict[Lang, str]] = {
    "maintenance_request": {"en": "Repair request", "es": "Solicitud de reparación"},
    "tour_request": {"en": "Tour request", "es": "Solicitud de visita"},
    "staff_handoff": {"en": "Note for the office", "es": "Nota para la oficina"},
}
TOPIC_LABEL: dict[str, str] = {
    "safety_emergency": "Possible emergency", "repeat_issue": "Repeated repair problem",
    "unresolved_commitment": "Follow-up still owed", "human_requested": "Asked for a person",
    "policy_or_eligibility": "Eligibility question", "financial_or_lease": "Lease or billing question",
    "fair_housing_or_legal": "Accommodation or legal question",
    "leasing_follow_up": "Leasing follow-up", "sensitive_data_request": "Account or sensitive information",
    "other": "Needs a team member", "none": "General question",
}
TEAM_LABEL = {"emergency_maintenance": "Emergency maintenance", "maintenance": "Maintenance",
              "leasing": "Leasing", "accounting": "Accounting", "management": "Property management"}
_TEAM_ES = {"emergency maintenance": "mantenimiento de emergencia", "maintenance": "mantenimiento",
            "leasing": "arrendamiento", "accounting": "contabilidad", "property management": "administración"}


@dataclass
class TurnPlan:
    template: str
    functions: list[FunctionId]
    workflow: WorkflowSelection
    action: ProposedAction | None = None
    records: list[PrototypeRecord] = field(default_factory=list)
    status_items: list[StatusItem] = field(default_factory=list)
    chips: list[str] = field(default_factory=list)
    skip_model: bool = False  # reply is fully deterministic (opt-out, status lookup)
    consumed_by_draft: bool = False  # message answered an assistant question for an active draft
    extra_flags: list[str] = field(default_factory=list)
    force_handoff: bool = False
    handoff: HandoffRecommendation | None = None  # set whenever the plan routes to a person
    memory: dict[str, Any] = field(default_factory=dict)  # small per-session planner memory (logged, no text)
    lang: Lang | None = None  # the language the planner answered in (a Spanish conversation stays Spanish)
    facts: list[str] = field(default_factory=list)  # L-2 / F-4: planner facts the response model must respect
    understanding: dict[str, Any] = field(default_factory=dict)  # Sprint 6: act names and flags only, no text
    transition: dict[str, Any] = field(default_factory=dict)  # Sprint 6: workflow_state transition (metadata)


def _sel(wid: WorkflowId, reason: str) -> WorkflowSelection:
    return WorkflowSelection(id=wid, label=LABELS[wid], reason=reason, instructions_version=WORKFLOW_VERSION)


def _ctx_value(ctx: SafeContext, name: str) -> str | None:
    return next((f.value for f in ctx.fields if f.name == name), None)


def _verified(ctx: SafeContext) -> bool:
    return ctx.persona_kind == "resident" and ctx.record_found


def _who(ctx: SafeContext) -> str:
    if _verified(ctx):
        return "Signed-in resident (demo account)"
    if ctx.persona_kind == "unmatched_resident":
        return "Says they are a resident; not matched to an account"
    if ctx.persona_kind == "prospect":
        return "Prospective resident (demo profile)"
    return "Not signed in"


def identity_note(ctx: SafeContext) -> str:
    name = _ctx_value(ctx, "first_name")
    if _verified(ctx):
        return f"Signed in as {name} (demo account)" if name else "Signed in (demo account)"
    return {"unmatched_resident": "Not matched to a resident account",
            "prospect": "Browsing as a prospective resident (demo profile)"}.get(ctx.persona_kind or "",
                                                                                  "Not signed in")


_ES_VALUES = {
    "Kitchen": "Cocina", "Bathroom": "Baño", "Bedroom": "Dormitorio", "Living room": "Sala",
    "Laundry area": "Lavandería", "Balcony or patio": "Balcón o patio", "Whole apartment": "Todo el apartamento",
    "Outside or common area": "Afuera o área común", "Hallway": "Pasillo",
    "Not needed (common area)": "No hace falta (área común)",
    "Front door": "Puerta principal", "Morning": "Mañana", "Afternoon": "Tarde", "Evening": "Noche",
    "Midday": "Mediodía", "Heating / cooling system": "Calefacción / aire acondicionado",
    "Yes, maintenance may enter if I'm not home": "Sí, mantenimiento puede entrar si no estoy",
    "Contact me first; only enter when I'm home": "Contactarme primero; entrar solo si estoy",
}
_ES_CHANNEL = {"text": "mensaje de texto", "call": "llamada", "email": "correo electrónico", "portal": "portal"}


def _tr(value: str | None, lang: Lang) -> str | None:
    return _ES_VALUES.get(value, value) if (value and lang == "es") else value


def _prefers(channel: str | None, lang: Lang) -> str | None:
    if not channel:
        return None
    return f"Prefiere {_ES_CHANNEL.get(channel.lower(), channel)}" if lang == "es" else f"Prefers {channel}"


def _draft_fields(draft: dict[str, Any], lang: Lang) -> list[ActionField]:
    return [ActionField(key=k, label=LABEL[k][lang] if k in LABEL else k, value=v["value"], source=v["source"])
            for k, v in draft.get("fields", {}).items()]


def _missing(kind: ActionKind, draft: dict[str, Any]) -> list[str]:
    missing = [k for k in REQUIRED[kind] if not draft.get("fields", {}).get(k, {}).get("value")]
    if kind == "maintenance_request" and draft.get("vague_issue") and "issue" not in missing:
        missing.insert(0, "issue")  # "it's not working": ask what, once, before where
    return missing


_VAGUE = re.compile(r"\b(not working|isn'?t working|doesn'?t work|stopped working|broken|broke|acting up|messed up|"
                    r"no funciona|se descompuso)\b", re.I)


def _vague_issue(text: str) -> bool:
    from app.context import MAINTENANCE_TOPICS, detect_topics
    # Sprint 7 final round: a named fixture before the symptom ("doorbell stopped working") is not vague
    named = re.match(r"^\W*(?:the |my |our )?(?P<n>[a-z]{4,})\s+(?:stopped|won'?t|isn'?t|is not|doesn'?t|broke|died|"
                     r"quit)",
                     text or "", re.I)
    if utt.things(text) or (named and named.group("n").lower() not in ("thing", "this", "that", "something", "stuff",
                                                                         "everything", "nothing")):
        return False
    return bool(_VAGUE.search(text)) and len(text.split()) <= 5 and not appliance_in(text) and not (
        set(detect_topics(text)) & MAINTENANCE_TOPICS)


def _proposed(kind: ActionKind, draft: dict[str, Any], lang: Lang) -> ProposedAction:
    missing = _missing(kind, draft)
    stage = "ready" if not missing else "collecting"
    note = CARD_NOTE["open"][kind][lang]  # Sprint 9: the one action-level demo line, shown at the point of Send
    queued = [q for q in (draft.get("queued") or []) if q]
    if kind == "maintenance_request" and queued:  # Sprint 6: the other problems are named, never merged or lost
        note += " " + t("queued_note", lang, items="; ".join(f"\"{q}\"" for q in queued))
    return ProposedAction(kind=kind, stage=stage, title=TITLE[kind][lang], fields=_draft_fields(draft, lang),
                          missing=[LABEL[m][lang] for m in missing],
                          confirm_label=CONFIRM_LABEL[kind][lang] if stage == "ready" else None, note=note)


_LEASING_REFERRAL = re.compile(r"\s*(?:The leasing team (?:can give you accurate[^.]*|has current [^.]*)|El equipo de "
                               r"arrendamiento (?:puede darle información exacta[^.]*|tiene la información actual))\.")
# "will someone call me?", "is anyone going to email me?", "when will I hear back?", "¿me van a llamar?" — the person
# asks to be CONTACTED. Not "is there a text version?" or "can I text a friend?" (Sprint 9 review B-3).
_CHECK_ON = re.compile(r"\bcheck (?:on|in on|up on)\b|\bwellness check|welfare check|"
                       r"make sure (?:she|he|they)(?:'s| is| are) (?:ok|okay|alright|fine)|\bver c[oó]mo est[aá]", re.I)
_OFFICE_HOURS_Q = re.compile(r"\b(?:open|opens|close|closes|closed|hours)\b", re.I)
_WANTS_NOTE = re.compile(r"\b(?:leave|send|write|make|start|pass|drop|put)(?: them| the office| it)?(?: in)? "
                         r"(?:a|the|that)? ?note\b|\bnote (?:for|to) (?:the office|them)\b|"
                         r"\b(?:yes|ok|okay|sure|fine)\W+(?:\w+\W+){0,3}(?:a |the )?note\b|"
                         r"\bd[eé]j(?:e|eles|ame) una nota\b", re.I)
_LEAD_DECLINE = re.compile(r"^\W*(?:nvm|never ?mind|nevermind|forget (?:it|that)|no thanks|nah|scratch that|"
                           r"olv[ií]d(?:elo|alo)|no importa|d[eé]jalo)\b[\s,.;:!-]*", re.I)


def _after_lead_decline(msg: str) -> str:
    """'nvm. whats your phone number' -> 'whats your phone number'; '' when nothing (of 2+ words) follows."""
    m = _LEAD_DECLINE.match(msg or "")
    rest = msg[m.end():].strip() if m else ""
    return rest if len(rest.split()) >= 2 else ""


_ASKS_CONTACT = re.compile(r"\b(?:call|phone|ring|email|e-?mail|text|contact|reach|message)(?:s|ing|ed)? (?:me|us)\b|"
                           r"\b(?:will|is|are|does|did|can|could) (?:someone|anyone|somebody|anybody|they|you|the "
                           r"\w+(?: team)?|staff)(?: going to| gonna)? (?:call|phone|email|e-?mail|text|contact|reach)"
                           r"\b|\bhear (?:back|from (?:you|them|someone|anyone))\b|\bget back to (?:me|us)\b|"
                           r"\bfollow(?:s|ing)?[- ]?up with (?:me|us)\b|\b(?:me|nos) (?:van a |va a )?(?:llam|"
                           r"contact|escrib)\w*|\b(?:llamar[aá]n?|contactar[aá]n?|escribir[aá]n?)\b", re.I)
_UPSET = re.compile(r"\bridiculous|frustrat\w*|fed up|unacceptable|useless|(?:three|four|five|\d+|many|multiple) "
                    r"times|again and again|still (?:not|isn'?t|hasn'?t)|nobody (?:fixed|came|has)|"
                    r"no one (?:fixed|came)|harta|hart[oa]|otra vez", re.I)
_DAY_KEEP = re.compile(r"^(?:mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d)", re.I)


def tour_when(draft: dict[str, Any], lang: Lang) -> str:
    """'next week in the morning' from the tour card's own fields (Sprint 9 read-back in one phrase), or '' when the
    days are missing, skipped or flexible. English only: a Spanish reply uses the sentence without it."""
    if lang != "en":
        return ""
    f = draft.get("fields", {})
    days = str((f.get("days") or {}).get("value") or "").strip()
    time_ = str((f.get("time") or {}).get("value") or "").strip()
    unusable = {_SKIPPED["en"].lower(), _FLEXIBLE["days"]["en"].lower(), _FLEXIBLE["time"]["en"].lower()}
    if not days or days.lower() in unusable or len(days) > 40 or "," in days or re.search(r"\b(?:or|and|y|o)\b",
                                                                                         days, re.I):
        return ""  # a list of days ("this weekend, Next Monday") reads badly in one phrase: the card shows it
    days = re.sub(r"^(?:on|this coming|for)\s+", "", days, flags=re.I) or days  # "on Saturday"
    if not re.match(r"(?:mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d)", days,
                    re.I):
        days = days.lower()  # "Next week" -> "next week"
    days = re.sub(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day\b", lambda m: m.group(0).capitalize(), days, flags=re.I)
    phrase = days
    # "Afternoon (around 3 PM)" -> "in the afternoon, around 3 PM": the time the person gave is read back (review H-3)
    tm = re.match(r"(morning|afternoon|evening)s?\b(?:\s*\((?:around\s+)?([^)]{1,20})\))?", time_, re.I)
    if tm:
        phrase += f" in the {tm.group(1).lower()}" + (f", around {tm.group(2)}" if tm.group(2) else "")
    return phrase


def _set(draft: dict[str, Any], key: str, value: str | None, source: str) -> bool:
    """Set a slot when a value was extracted. Returns True when something changed."""
    if not value:
        return False
    fields = draft.setdefault("fields", {})
    if fields.get(key, {}).get("value") == value:
        if source == "you_said" and fields[key].get("source") != "you_said":
            fields[key]["source"] = "you_said"  # the person confirmed it in their own words
        return False
    fields[key] = {"value": value, "source": source}
    return True


# ---- status lookup (F8) ---------------------------------------------------------------------------------


_PRIVATE_HAZARDS = {"self_harm", "personal_safety", "medical"}


def status_items(store: Store | None, resident: Resident | None, persona_id: str) -> list[StatusItem]:
    """Open items for a VERIFIED resident: prototype requests first, then open maintenance history items.
    Only reference, short subject, status and opened date. Entry windows and notes are never included."""
    items: list[StatusItem] = []
    if store:
        for r in store.records(persona_id=persona_id, limit=20):
            if r["kind"] == "tour_request" or r.get("hazard") in _PRIVATE_HAZARDS:
                continue  # wellbeing notes are staff-only; never listed back to the person
            items.append(StatusItem(reference=r["id"], title=r.get("title", "Repair request"),
                                    status=r.get("status_label", "Submitted"), opened=r["created_at"][:10],
                                    source="prototype_store",
                                    note="Saved through this assistant (demo)."))
    if resident:
        for i in resident.interactions:
            if i.category != "maintenance" or i.status == "closed":
                continue
            subject = sanitize_field(i.subject, 80) or "Maintenance request"
            status = i.status.capitalize() + ("; a follow-up is owed to you" if i.follow_up_needed else "")
            items.append(StatusItem(reference=i.interaction_id, title=subject, status=status,
                                    opened=i.timestamp.strftime("%Y-%m-%d") if i.timestamp else None,
                                    source="resident_history"))
    return items


# ---- prototype records -------------------------------------------------------------------------------------


def _record(store: Store, kind: ActionKind, session_id: str, persona_id: str | None, data: dict[str, Any]
            ) -> PrototypeRecord:
    raw = store.add_record(PREFIX[kind], kind, session_id, persona_id, data)
    return PrototypeRecord.model_validate(raw)


def _record_data(kind: ActionKind, draft: dict[str, Any], lang: Lang) -> dict[str, Any]:
    fields = [f.model_dump() for f in _draft_fields(draft, lang)]
    if kind == "maintenance_request":
        status = "submitted_for_review"
        issue = draft["fields"].get("issue", {}).get("value", "Repair request").split(" Also: ")[0]
        title = issue if len(issue) <= 58 else issue[:58].rsplit(" ", 1)[0] + "…"
    elif kind == "tour_request":
        status = "requested"
        title = "Tour request (community to be decided)" if "area" in draft.get("skipped", []) else \
            f"Tour of {draft['fields'].get('area', {}).get('value', 'a community')}"
    else:
        urgent = draft.get("priority") == "urgent"
        status = "urgent_queued" if urgent else "queued"
        title = draft.get("topic", "Note for the office")
    label = STATUS_LABEL[status]  # Sprint 9: one authoritative, honest label (app/models.py)
    return {"status": status, "status_label": label, "title": title, "summary": draft.get("summary", title),
            "fields": fields, "team": draft.get("team"), "priority": draft.get("priority"),
            "category": draft.get("category"), "repeat": draft.get("repeat", False), "hazard": draft.get("hazard"),
            # Sprint 8 C: the repeat history (prior requests only) and the manager-review marker travel with the request
            **({"repeat_history": draft["repeat_history"]} if kind in ("maintenance_request", "staff_handoff") and
               (draft.get("repeat_history") or (kind == "staff_handoff" and "repeat_history" in draft)) else {}),
            **({"manager_review": True, "review_queue": "community_manager"} if kind in (
                "maintenance_request", "staff_handoff") and draft.get("manager_review") else {})}


def _write(store: Store | None, kind: ActionKind, session_id: str, persona_id: str | None, draft: dict[str, Any],
           lang: Lang) -> PrototypeRecord | None:
    """Write a confirmed draft. Returns None (and logs the error type only) when the write fails."""
    if store is None:
        return None
    data = _record_data(kind, draft, lang)
    try:
        return _record(store, kind, session_id, persona_id, data)
    except Exception as e:  # never claim success for a failed write
        log.warning("prototype write failed: %s", type(e).__name__)
        return None


def _handoff_draft(gate: GateDecision, handoff: HandoffRecommendation | None, ctx: SafeContext, msg: str,
                   lang: Lang, earlier: dict[str, Any] | None, topic: str | None = None,
                   recent: list[str] | None = None) -> dict[str, Any]:
    category = handoff.category if handoff else "human_requested"
    team = handoff.team if handoff else "management"
    topic = topic or TOPIC_LABEL.get(category, "Needs a team member")
    draft: dict[str, Any] = {"fields": {}, "team": team, "priority": handoff.priority if handoff else "normal",
                             "category": category, "topic": topic,
                             "summary": handoff.summary if handoff else f"{gate.audience} · {gate.intent}"}
    _set(draft, "topic", f"{topic}, for the {TEAM_LABEL.get(team, team).lower()} team", "assistant")
    snippet = redact(msg)
    if recent and (_is_quick_action(msg) or is_lost_or_frustrated_with_chat(msg)):
        # a tapped button (or "this isn't helping") says nothing about the need: carry what the person wrote
        snippet = " | ".join(redact(r) for r in recent[-3:] if not _is_quick_action(r)) or snippet
    _set(draft, "message", (snippet[:237] + "…") if len(snippet) > 240 else snippet, "you_said")
    _set(draft, "who", _who(ctx), "on_file" if _verified(ctx) else "assistant")
    if earlier and earlier.get("kind") in ("maintenance_request", "tour_request"):
        bits = [v["value"] for k, v in earlier.get("fields", {}).items()
                if k in ("issue", "location", "area", "days", "time", "beds")]
        _set(draft, "earlier", " · ".join(bits) or None, "you_said")
    if earlier and earlier.get("kind") == "staff_handoff":  # an unsent note is merged, never silently dropped
        ef = earlier.get("fields", {})
        if (old_msg := ef.get("message", {}).get("value")) and old_msg != draft["fields"]["message"]["value"]:
            parts = list(dict.fromkeys([*old_msg.split(" | "), *draft["fields"]["message"]["value"].split(" | ")]))
            _set(draft, "message", " | ".join(parts)[:480], "you_said")  # each thing the person said, once
        if (old_topic := earlier.get("topic")) and old_topic != topic and topic.lower() not in old_topic.lower():
            draft["topic"] = f"{old_topic}; {topic}"
            _set(draft, "topic", f"{draft['topic']}, for the {TEAM_LABEL.get(team, team).lower()} team", "assistant")
        draft["priority"] = _max_priority(earlier.get("priority"), draft["priority"])
    contact = _ctx_value(ctx, "preferred_contact_channel")
    pref = _prefers(contact, lang) or ""  # the channel only: internal staff notes never show on the customer card
    if pref:
        _set(draft, "contact", pref, "on_file")
    elif not _verified(ctx) and ctx.persona_kind != "prospect":
        _set(draft, "contact", "Not collected in this prototype",
             "assistant")
    if earlier:
        # Sprint 6 fix round (simL L-2): asking for a person again rebuilds the note, but what the person already told
        # us stays: the details so far, their questions and budget, and a contact preference they SAID ("CALL me")
        ef = earlier.get("fields", {})
        for k in ("earlier", "questions", "budget"):
            if (ef.get(k) or {}).get("value") and not draft["fields"].get(k):
                draft["fields"][k] = dict(ef[k])
        if (ef.get("contact") or {}).get("source") == "you_said" and ef["contact"].get("value"):
            draft["fields"]["contact"] = dict(ef["contact"])
    if (said := contact_change(msg)) and not re.search(r"\?\s*$", msg):
        _set(draft, "contact", _prefers(said, lang), "you_said")
    elif said2 := und.contact_pref(msg):  # Sprint 7: "I'd rather get a phone call" is on the note, never the old one
        _set(draft, "contact", _prefers(said2, lang), "you_said")
    return draft


# ---- the planner -------------------------------------------------------------------------------------------


_SMALL_TALK = re.compile(r"^\s*(?:(?P<hi>hi|hello|hey|hola|good (morning|afternoon|evening)|buenos d[ií]as|buenas)"
                         r"|(?P<thanks>(?:(?:ok(?:ay)?|cool|great|perfect|awesome|got it|nice|alright|listo|vale|"
                         r"thanks|thank you|gracias|appreciate it)[\s,.!]*)*(?:thanks|thank you|thx|ty|gracias|"
                         r"appreciate it|cool|great|perfect|awesome|got it)(?: (?:so much|a lot|again))?(?:[\s,.!]+"
                         r"(?:bye|that'?s (?:all|it|everything)|nothing else|eso es todo))?)|(?P<bye>bye|goodbye|"
                         r"that'?s all|no thanks|nothing else|i'?m good|"
                         r"adi[oó]s|eso es todo))[\s.!,]*(there|so much|a lot)?[\s.!,]*$", re.I)
_EMERGENCY_FOLLOW = re.compile(r"what (now|next|should i do)|(i'?m|we'?re|i am) (outside|out|safe|ok)|anyone coming|"
                               r"someone coming|is help|ya sal[ií]|alguien viene|y ahora", re.I)
_EMERGENCY_REFUSE = re.compile(
    r"(?:not|n'?t|never) (?:going to |gonna )?(?:leav|go(?:ing)? out|evacuat|get out)\w*|(?:won'?t|wont|can'?t|cant|"
    r"refuse to) (?:leave|go out|get out|evacuate)|just send (?:someone|somebody|help|a tech|maintenance)|"
    r"send (?:someone|somebody|help|a tech) (?:now|over|up)|i'?m (?:fine|ok|okay),? (?:i'?m )?staying|"
    r"staying (?:here|inside|put)|no (?:me )?voy a salir|no (?:quiero|puedo) salir|manden a alguien|"
    # safety engineer's addition: someone else refusing to leave, or the danger being played down
    r"(?:doesn'?t|doesnt|don'?t|dont|does not) want to (?:leave|go (?:out|outside)|get out)|refus\w* to (?:leave|go)|"
    r"says (?:it'?s|its) (?:just|only) ", re.I)
_RESTORE = re.compile(r"\b(send|submit) (it|that|the (note|request))( after all| anyway| please)?\b|\bundo\b|"
                      r"\bafter all\b|changed my mind|i do want (it|to send)|env[ií]elo|s[ií],? env[ií]", re.I)


_TOPIC_ES = {"guests": "visitas", "packages": "paquetes", "trash and recycling": "basura y reciclaje",
             "quiet hours": "horas de silencio", "parking": "estacionamiento", "pets": "mascotas",
             "amenities": "amenidades", "smoking": "fumar", "grills": "parrillas", "subletting": "subarrendar",
             "rent payment": "pago de renta", "lease terms": "plazos del contrato",
             "deposits and fees": "depósitos y cargos", "move-in specials": "promociones de mudanza"}


def _tr_topic(topic: str, lang: Lang) -> str:
    return _TOPIC_ES.get(topic, topic) if lang == "es" else topic


def _is_quick_action(text: str) -> bool:
    """Exact text of a suggestion chip (it carries no information about the problem)."""
    t_ = text.strip().lower()
    return any(t_ == c.lower() for group in CHIPS.values() for lst in group.values() for c in lst)


_NEG_SEGMENT = re.compile(r"\b(not|instead of|rather than)\s+(the\s+|my\s+)?[\w-]+(\s[\w-]+)?", re.I)
PRIORITY_RANK = {"normal": 0, "high": 1, "urgent": 2}
KIND_FN: dict[str, FunctionId] = {"maintenance_request": "F7", "tour_request": "F5", "staff_handoff": "F9"}
KIND_WF: dict[str, WorkflowId] = {"maintenance_request": "maintenance", "tour_request": "tour_request",
                                  "staff_handoff": "human_handoff"}
WHAT: dict[str, dict[Lang, str]] = {
    "maintenance_request": {"en": "repair request", "es": "solicitud de reparación"},
    "tour_request": {"en": "tour request", "es": "solicitud de visita"},
    "staff_handoff": {"en": "note", "es": "nota"},
}


_FLEXIBLE: dict[str, dict[Lang, str]] = {"days": {"en": "Any day (flexible)", "es": "Cualquier día (flexible)"},
                                         "time": {"en": "Any time (flexible)", "es": "Cualquier hora (flexible)"}}
_SKIPPED: dict[Lang, str] = {"en": "Not given yet", "es": "Sin indicar"}  # Sprint 9: nobody "will ask" in the demo
_ROUTE: dict[str, dict[Lang, str]] = {"profile": {"en": "On your profile", "es": "En su perfil"},
                                      "none": {"en": "Not collected in this prototype",
                                               "es": "No se recoge en este prototipo"}}


# D-16: a symptom added later ("now there's water on the floor too") is a repair detail, not small talk.
_LATER_SYMPTOM = re.compile(r"\b(?:water|puddle|wet|soak\w*|damp|mold|mould|stain\w*|spread\w*|worse|overflow\w*|"
                            r"backing up|warm|hot|cold|smell\w*|stinks?|noise|sound\w*|rust\w*|flicker\w*|"
                            r"agua|charco|mojad\w*|peor|ruido)\b", re.I)
_ENGLISH_HINT = re.compile(r"\b(?:the|is|my|and|please|what|when|can|it|you|this|that|thanks|hello|yes|need|help|"
                           r"will|do|does|how|why|are)\b", re.I)
_TIMING_Q = re.compile(r"\b(?:going to|gonna|will) (?:it|this|that|they|someone|anyone|somebody) (?:be )?"
                       r"(?:fix\w*|done|here|come|repair\w*|sorted)\b|\bfixed (?:today|tonight|tomorrow|this week)\b|"
                       r"\bhoy mismo\b|\blo arreglan hoy\b", re.I)
# R-7: who is at risk while it waits ("i have a baby", "its like 85 in here", "50 degrees")
_VULNERABLE = re.compile(r"\b(?:baby|infant|newborn|toddler|elderly|pregnant|oxygen|beb[eé]|reci[eé]n nacido)\b|"
                         r"\b(?:8[5-9]|9\d|1[01]\d|[3-5]\d) ?(?:degrees|in here|inside|°)", re.I)
_FLOOR_Q = re.compile(r"\bhow (?:big|large|many square)\b|\bsquare (?:feet|footage)\b|\bsq\.? ?f(?:ee)?t\b|"
                      r"\bsq\.? ?footage\b|"
                      r"\blayouts?\b|\bfloor ?plans?\b|\bqu[eé] tan grande|\bmetros cuadrados\b", re.I)


def _max_priority(a: str | None, b: str | None) -> str:
    return max([a or "normal", b or "normal"], key=lambda x: PRIORITY_RANK.get(x, 0))


def _slot_only(message: str) -> bool:
    """True when the message only answers a slot question (room, entry, yes/no), not a new description."""
    rest = re.sub(r"\b(yes|no|ok|okay|sure|the|my|it'?s|its|in|is|a|they|can|may|you|please|actually|wait|"
                  r"kitchen|bathroom|bedroom|living room|laundry|balcony|patio|hallway|come in|enter|first|call|text|"
                  r"contact|me|before|home|when|i'?m|only|don'?t|go|without)\b", " ", message, flags=re.I)
    return len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest)) <= 2


# ---- sprint 5.1 helpers ---------------------------------------------------------------------------------------

_ASK_KEY = {"issue": "ask_plain_issue", "location": "ask_plain_location", "entry": "maint_ask_entry_plain",
            "area": "ask_plain_area", "days": "tour_ask_days", "time": "tour_ask_time"}


def _next_step(card: dict[str, Any], lang: Lang) -> tuple[str, list[str]]:
    """The single next step of an open card: the exact missing question, or 'tap Send' when it is ready."""
    kind = card["kind"]
    missing = _missing(kind, card)
    if missing and missing[0] in _ASK_KEY:
        chips = {"location": CHIPS["locations"][lang], "entry": CHIPS["entry"][lang],
                 "days": CHIPS["tour_days"][lang], "time": CHIPS["tour_time"][lang]}.get(missing[0], [])
        return t(_ASK_KEY[missing[0]], lang), chips
    return t("tap_send", lang, what=WHAT[kind][lang]), []


# Sprint 8 C fix round: a clause that only asks for someone to come ("just send maintenance", "can you send someone
# out asap", "have someone come look at it", "manden a alguien", "que venga mantenimiento"). One grammar: an optional
# softener + a send/come verb + a helper noun; the clause names no object and no symptom of its own.
_SERVICE_LEAD = (r"(?:(?:just|please|pls|can you|could you|can u|would you|i need you to|i need|i want|need|so|then|"
                 r"por favor|solo|nada m[aá]s)\s+)*(?:send|get|have|dispatch|need|want|i need|manden|mande|env[ií]en|"
                 r"env[ií]e|necesito|quiero|que venga|que vengan|someone|somebody|alguien)\b")
_SERVICE_ASK = re.compile(
    r"^\W*(?:and |so |but |y |pero )?" + _SERVICE_LEAD + r"[\s\w']{0,40}?\b(?:maintenance|someone|somebody|a tech\w*|"
    r"tech\w*|a plumber|plumber|an electrician|a person|a repair ?(?:man|person)|help|someone out|people|"
    r"mantenimiento|alguien|un t[eé]cnico|t[eé]cnico|plomero|ayuda)\b[\s\w',]{0,40}$", re.I)


# "can I put in a request to fix the stove burner?" -> "fix the stove burner" (the request framing is not the problem)
_ASK_PREFIX = re.compile(
    r"^\W*(?:(?:can|could|may|should) (?:i|we)|i (?:want|need|would like|'d like|wanna)|how (?:do|can) i)\s+"
    r"(?:please\s+)?(?:to\s+)?(?:put in|submit|file|make|open|start|create|place|enter)\s+(?:a |an |another |one )?"
    r"(?:new\s+)?(?:repair |maintenance |service |work )?(?:request|ticket|order|work order)\s+"
    r"(?:to (?:get )?|for (?:the |my )?|about |because )?|^\W*¿?\s*(?:puedo|podr[ií]a|quiero|necesito)\s+"
    r"(?:hacer|poner|abrir|levantar|meter)\s+(?:una )?(?:solicitud|orden|reporte)\s+(?:para |por |de )?", re.I)


def _service_ask_only(clause: str) -> bool:
    c = clause.strip(" ,.;!?-")
    return bool(c) and bool(_SERVICE_ASK.search(c)) and not utt.things(c) and not utt.has_symptom(c)


def _new_request_ask(msg: str) -> bool:
    """'can I put in a request to fix the stove burner?' / '¿puedo hacer una solicitud para el horno?': asks to START a
    repair request about a named thing (not a status question)."""
    return bool(re.search(
        r"\b(?:can|could|may|do|should|how do|how can)\s+(?:i|we|you)\s+(?:please\s+)?(?:put in|submit|file|make|open|"
        r"start|create|place|enter|send|report)\b|\bi (?:want|need|would like|'d like|wanna) to (?:put in|submit|file|"
        r"make|open|start|report)\b|\b(?:quiero|puedo|podr[ií]a|necesito) (?:hacer|poner|abrir|levantar|meter|"
        r"reportar|enviar|mandar)\b", msg, re.I)) and bool(utt.things(msg) or utt.has_symptom(msg))


_PRAISE = re.compile(
    r"\b(?:was|is|'s|were|are|be|so|looks?|sounds?|felt)\s+(?:so |really |totally |super |absolutely |lowkey )?"
    r"(?:fire|lit|killer|sick|dope|amazing|awesome|great|fantastic|incredible|the best|goated|epic|a blast|fun|"
    r"lovely|beautiful|perfect)\b|\b(?:slaps|slapped|rocks|rocked|ate)\b|"
    r"\b(?:love|loved|loving) (?:it|this|the|my)\b|"
    r"\b(?:estuvo|est[aá]|es|qued[oó])\s+(?:bien |muy |s[uú]per )?(?:padre|padr[ií]sim[oa]|chid[oa]|genial|"
    r"incre[ií]ble|buen[ií]sim[oa]|bonit[oa]|perfect[oa]|lo m[aá]ximo|brutal)\b|\bme encant[aó]\b", re.I)
_COMPLAINT = re.compile(
    r"\b(?:can'?t|cannot|couldn'?t) sleep|too (?:loud|much|noisy)|all night|every (?:night|day|weekend)|at \d|"
    r"\d ?(?:am|a\.m\.)|again|still|won'?t stop|keeps?|complain\w*|annoy\w*|ugh|so loud|rude|unbearable|"
    r"not (?:ok|okay|cool|fine)|but\b|broken|leak\w*|not working|help|please|no puedo dormir|toda la noche|otra vez|"
    r"sigue|molest\w*|pero\b|\?", re.I)


def _praise_only(msg: str) -> bool:
    """Sprint 8 C fix round: a compliment in everyday slang with no complaint or request in it. The safety layer runs
    first and is never affected (the caller checks urgency, hazard and care)."""
    return bool(_PRAISE.search(msg)) and not _COMPLAINT.search(msg) and not utt.has_symptom(
        _PRAISE.sub(" ", msg)) and len(msg.split()) <= 25


_PAYMENT_PLAN = re.compile(r"\bpayment ?plan\b|\bpay (?:my |the )?rent (?:in|over) (?:installments|parts|two)|"
                           r"\bsplit (?:my|the) rent\b|\b(?:installments?|instalments?) (?:for|on) (?:my |the )?rent\b|"
                           r"\bplan de pagos?\b|\bpagar (?:la renta )?en partes\b|\bpagos parciales\b", re.I)
_NORMAL_Q = re.compile(r"\b(?:is (?:it|that|this) (?:normal|ok|okay|bad|a problem|safe) (?:for|that|when|if)|"
                       r"is it normal|should (?:my|the|a|an) [\w ]{2,25}? (?:be|make|sound|do)|"
                       r"(?:do|does) (?:a|an|the|my) [\w ]{2,25}? (?:usually|normally)|why (?:does|do|is) (?:my|the|a)|"
                       r"(?:is it|it'?s) normal (?:for|that)|es normal (?:que|qu[eé])|¿?es normal\b|"
                       r"(?:deber[ií]a|debe) (?:mi|el|la) [\w ]{2,25}? (?:hacer|sonar))", re.I)
_NOW_WORDS = re.compile(r"\b(?:right now|now|currently|today|tonight|again|still|it'?s (?:leaking|flooding|sparking|"
                        r"smoking)|ahora|todav[ií]a|otra vez)\b", re.I)


_PROCEED = re.compile(
    r"\b(?:just|only|i (?:just |only )?(?:want|need)(?: you)? to|i (?:just |only )?(?:want|need) it)\s+"
    r"(?:to (?:be )?)?(?:fix|fixed|repair|repaired|get it fixed|sorted)\b|\bjust (?:fix|repair) it\b|"
    r"\bneed it (?:fixed|repaired)\b|\bwant it (?:fixed|repaired)\b|\bquiero que lo (?:arreglen|reparen)\b|"
    r"\bsolo (?:arr[eé]glenlo|rep[aá]renlo)\b|\bnecesito que lo (?:arreglen|reparen)\b", re.I)
_REPORT_IT = re.compile(r"\breport (?:it|that|this)\b|\breport a repair\b|\breportarlo\b|"
                        r"\breportar una reparaci[oó]n\b|\bstart (?:a|the) request\b|\bput (?:it|one) in\b", re.I)
_LIVE_CLASSES = {"smell", "power", "damage", "pests"}  # a fault you can see or smell (a drip or a sound can be normal)
_LIVE_REPORT = re.compile(r"\b(?:went bad|spoil\w*|overnight|puddle|pool of water|on the floor|under it|everywhere|"
                          r"charco|en el piso|since (?:yesterday|this morning|last night)|"
                          r"for (?:\d+|two|three|a few|several) (?:days|hours)|all (?:day|night)|"
                          r"se ech[oó] a perder|desde (?:ayer|anoche)"
                          r")\b", re.I)


_NQ_LEAD = re.compile(r"^\W*¿?\s*(?:is (?:it|that|this) (?:normal|ok|okay)|es normal)\s+(?:for|that|when|if|que)\s+",
                      re.I)


def _normal_q_issue(question: str) -> str:
    """'is it normal for the fridge to hum?' -> 'The fridge to hum (asked whether this is normal)': the problem in
    the person's words for the card, without the question frame."""
    rest = _NQ_LEAD.sub("", question).strip().rstrip("?¿ ").strip()
    if not rest or rest == question.strip():
        return question
    return f"{rest[0].upper()}{rest[1:]} (asked whether this is normal)"


def _live_symptom(msg: str) -> bool:
    """Sprint 8 C: a question that also describes a PRESENT fault of the person's own thing ("... to have a puddle
    under it?", "fridge warm inside? my milk went bad overnight"): a repair, not a general question."""
    if mh.symptoms(msg) & _LIVE_CLASSES or _LIVE_REPORT.search(msg):
        return True
    statements = [c for c in re.split(r"(?<=[.!?;])\s+", msg) if c.strip() and not c.strip().endswith("?")]
    return any(utt.has_symptom(c) and (utt.things(c) or re.search(r"\b(?:my|mi|it|it'?s)\b", c, re.I))
               for c in statements)


def _is_normal_question(msg: str, live_ok: bool = False) -> str | None:
    """Sprint 8 C: 'is it normal for the water heater to pop?' -> 'water heater'. A question about whether something
    is normal, naming a thing, with no report that it is happening now (unless `live_ok`). None otherwise."""
    if not (_NORMAL_Q.search(msg) and ("?" in msg or utt.analyze(msg).question)) or \
            (not live_ok and (_NOW_WORDS.search(msg) or _live_symptom(msg))):
        return None
    objs = sorted(mh.objects(msg))
    if not objs:
        return None
    lang_es = detect_language(msg) == "es"
    return ", ".join((mh._LABEL_ES if lang_es else {"ac": "AC"}).get(o, o) for o in objs)


def _slot_clause(clause: str) -> bool:
    """B-3 / A-10: a clause that only answers a slot (entry, contact, room), never part of "What's wrong"."""
    c = clause.strip(" ,.;!?")
    if not c:
        return True
    if re.fullmatch(r"(?:please |pls )?(?:don'?t|dont|do not|no) (?:call|text|email|phone)(?: me)?(?: please)?", c,
                    re.I):
        return True  # "text me, dont call"
    if clause.strip().endswith("?") and not is_issue_description(c) and not appliance_in(c):
        return True  # "hablas español?" is a question, not part of the problem
    if extract_entry(c) or extract_contact_pref(c) or channel_said(c) or contact_change(c):
        return not (is_issue_description(re.sub(r"\b(?:don'?t|dont|do not)\b", "", c)) and len(c.split()) > 6)
    return bool(extract_location(c)) and _slot_only(c) and not is_issue_description(c) and not appliance_in(c)


def _issue_text(text: str) -> str:
    """The problem in the person's words without the entry/contact/room clauses said in the same message, and without
    a clause that only asks for service ("just send maintenance", "manden a alguien"; Sprint 8 C)."""
    parts = re.split(r"(?<=[.!?;])\s+|,\s+(?=(?:and |but |so )?(?:text|call|email|contact|you can|they can|ok to|"
                     r"okay to|don'?t|dont|do not|please call|pls call)\b)|\s+and\s+(?=(?:text|call|email|contact|"
                     r"you can|they can)\b)|(?:,|\s+-|\s+(?:and|so|y|así que))\s+(?=" + _SERVICE_LEAD + r")", text,
                     flags=re.I)
    asked = any(p.strip() and _service_ask_only(p) for p in parts)
    keep = [p.strip() for p in parts if p.strip() and not _slot_clause(p) and not _service_ask_only(p)]
    if asked and keep:
        keep[-1] = keep[-1].rstrip(" .,;-")  # "the oven doesn't heat. just send a tech" -> "the oven doesn't heat"
    keep = [k for k in (_ASK_PREFIX.sub("", p).rstrip("? ") if _ASK_PREFIX.search(p) else p for p in keep) if k]
    out = re.sub(r"^\W*(?:and|also|but|so)\W+", "", " ".join(keep), flags=re.I).strip(" ,;")
    out = re.sub(r"^\W*(?:(?:oh|ok|okay|um+|uh+)\W+)?(?:sorry|wait|actually|oops)\W+(?:(?:it'?s|its|it is)\s+)?",
                 "", out, flags=re.I) or out  # "oh sorry its the dishwasher, it wont drain" -> "the dishwasher, …"
    return (out[0].upper() + out[1:]) if out else ""  # "" when the message only answered slots


# D-5 / F-4: things a repair is about. A repeat needs the SAME thing on record (a toilet is not the kitchen sink).
_THINGS: list[tuple[str, str]] = [
    ("ac", r"\bac\b|\ba/c\b|air ?condition\w*|\bhvac\b|\bcooling\b|aire acondicionado"),
    ("heat", r"\bheat\w*|\bfurnace\b|\bradiator\b|calefacci[oó]n"), ("sink", r"\bsinks?\b|fregadero|lavabo"),
    ("faucet", r"\bfaucets?\b|\btaps?\b|\bgrifo\b"), ("toilet", r"\btoilets?\b|\binodoro\b"),
    ("tub", r"\btubs?\b|\bshower\b|\bba[ñn]era\b|\bducha\b"), ("dishwasher", r"\bdishwasher\b|lavaplatos"),
    ("fridge", r"\bfridge\b|refrigerator|\bfreezer\b|refrigerador"), ("oven", r"\boven\b|\bstove\b|\bhorno\b"),
    ("disposal", r"\bdisposal\b"), ("washer", r"\bwasher\b|washing machine|lavadora"), ("dryer", r"\bdryer\b"),
    ("window", r"\bwindows?\b|ventana"), ("door", r"\bdoors?\b|\block\b|deadbolt|puerta|cerradura"),
    ("fan", r"\bfan\b"), ("light", r"\blights?\b|\bbulb\b|\bluz\b"), ("outlet", r"\boutlets?\b|enchufe"),
    ("ceiling", r"\bceiling\b|\btecho\b"), ("pests", r"roach\w*|\bants?\b|\bmice\b|\bmouse\b|pest\w*|hormigas"),
    ("water heater", r"water heater"), ("drain", r"\bdrains?\b|\bdraining\b"),
    ("detector", r"detector|smoke alarm|chirp\w*")]


def _things_in(text: str) -> set[str]:
    return {name for name, pat in _THINGS if re.search(pat, text or "", re.I)}


def _history_match(resident: Resident | None, text: str, open_only: bool = False) -> Any:
    """The most recent maintenance history item about the same thing as `text`, or None."""
    if not resident:
        return None
    things = _things_in(text) - {"drain"} or _things_in(text)
    if not things:
        return None
    items = [i for i in resident.interactions if i.category == "maintenance" and (not open_only or i.status != "closed")
             and _things_in(i.subject) & things]
    return items[-1] if items else None


_CANCEL_VERB = re.compile(r"\b(?:i'?ll|i will|i can|i'?m going to) (?:fix|handle|sort out|deal with|take care of)\b\s*"
                          r"(?:the |my )?|\b(?:cancel|scrap|scratch|skip|drop|forget(?: about)?|never ?mind|nvm|remove|"
                          r"ditch|lose|no need "
                          r"for|don'?t need|without|olv[ií]d\w*|quit\w*|cancel\w*)\b\s*(?:the |my |that |el |la )?",
                          re.I)
_KEEP_VERB = re.compile(r"\b(?:keep|just|only|i (?:just |only |still )?want|still want|solo|s[oó]lo|mant[eé]n\w*|"
                        r"quiero)\b\s*(?:the |my |el |la |a |have )?", re.I)
_REPAIR_WORD = re.compile(r"\b(?:repair|request|ticket|fix|work order|reparaci[oó]n|solicitud|arreglo)\b", re.I)


def _cancel_target(msg: str, issue: str) -> str | None:
    """Sprint 7: which of a repair and a queued call a message CANCELS: the object of the cancel verb decides, and
    "keep / just / only / I want X" names what stays ("cancel the oven repair, I just want the call" -> 'repair';
    "forget the call from leasing" -> 'call'). None when the message cancels neither by name."""
    def names(text: str) -> str | None:
        call = bool(_QUEUED_REF.search(text))
        rep = bool(utt.things(text) & utt.things(issue)) or bool(_REPAIR_WORD.search(text))
        return "call" if call and not rep else "repair" if rep and not call else None

    cancelled = kept = None
    for m in _CANCEL_VERB.finditer(msg):
        obj = re.split(r"[,.;!?]|\b(?:and|but|i|just|only|keep)\b", msg[m.end():], flags=re.I)[0]
        cancelled = cancelled or names(obj)
    for m in _KEEP_VERB.finditer(msg):
        obj = re.split(r"[,.;!?]|\b(?:and|but|cancel|not)\b", msg[m.end():], flags=re.I)[0]
        kept = kept or names(obj)
    if cancelled:
        return cancelled
    if kept and (_CANCEL_VERB.search(msg) or re.search(r"\bno\b", msg, re.I)):
        return "call" if kept == "repair" else "repair"
    return None


_ENTRY_FRAMED = re.compile(r"\b(?:enter\w*|come (?:on )?in|go in|let (?:your|them|him|her)sel(?:f|ves) in|key|"
                           r"without me|knock\w*|entrar|pasar|sin m[ií]|primero|antes)\b", re.I)
_NO_NEW_TICKET = re.compile(
    r"\b(?:don'?t|dont|do not|no need to|stop)\s+(?:open|start|make|create|file|put in)\w*\s+(?:another|a new|a second|"
    r"new)\s+(?:ticket|request|one|work order)\b|\bthe (?:first|old|other|last) one (?:is|isn'?t|was|"
    r"wasn'?t)\s+(?:not )?"
    r"(?:done|finished|fixed|closed)\b|\bno (?:abra|abras|hagas|haga) otra (?:solicitud|orden)\b", re.I)
_WAITING = re.compile(r"\bbeen waiting\b|\bwaiting since\b|\bstill waiting\b|\bwaiting (?:for|on) (?:someone|somebody|"
                      r"them|a tech\w*|maintenance)\b|\bllevo esperando\b|\bsigo esperando\b", re.I)
_PLACE_STOP = {"the", "my", "a", "an", "person", "general", "town", "the area", "the morning", "the afternoon",
               "the evening",
               "mind", "touch", "person please", "charge", "advance", "time", "spanish", "english"}


def _unknown_place(text: str) -> str | None:
    """Sprint 7: a place the person names for a tour that is not a demo city or community ("tour in jacksonville
    next sunday") -> 'Jacksonville'. None for anything the demo knows or that is not a place."""
    m = re.search(r"\b(?:in|near|around|en|cerca de)\s+(?P<p>[a-záéíóúñ][a-záéíóúñ .'-]{2,24}?)"
                  r"(?=\s+(?:next|this|on|for|"
                  r"tomorrow|today|sunday|monday|tuesday|wednesday|thursday|friday|saturday|morning|afternoon|evening|"
                  r"at|please|el|la|por|weekend)\b|\s*[,.!?]|\s*$)", text or "", re.I)
    if not m:  # Sprint 9 (holdout): "tour pls grand rapids, any weekday", "i meant kalamazoo not grand rapids"
        m = re.search(r"\b(?:tour|visit|meant)\s+(?:pls\s+|please\s+|in\s+)?(?P<p>[a-záéíóúñ][a-záéíóúñ .'-]{2,24}?)"
                      r"(?=\s+(?:not|instead|next|this|on|for|tomorrow|today|any|morning|afternoon|evening|weekdays?|"
                      r"weekends?|please)\b|\s*[,.!?]|\s*$)", text or "", re.I)
    if not m:
        return None
    p = m.group("p").strip(" .'-")
    if p.lower() in ("pls", "please", "a tour", "it", "that", "this", "the place", "one", "there", "here") or \
            extract_days(p) or extract_clock_preference(p):
        return None
    if p.lower() in _PLACE_STOP or community_in(p) or city_in(p) or utt.room_in(p) or len(p) < 3:
        return None
    return " ".join(w.capitalize() for w in p.split())


_RETRACT = re.compile(r"\bfalse alarm\b|\bfalsa alarma\b|\bit was (?:just |only )?(?:a |the |my )?(?:candle|toast|"
                      r"cooking|incense|steam|smoke from (?:the |my )?(?:toaster|oven|pan))\b|\b(?:everything|all) "
                      r"(?:is |'?s )?(?:fine|ok|okay|good) now\b|\bnothing (?:is |'?s )?wrong\b|\bfue (?:una )?vela\b",
                      re.I)
_QUEUED_REF = re.compile(r"\b(?:call ?back|call|phone call|note|message|leasing|office|renew\w*|lease|manager|"
                         r"person|llamada|nota|oficina|renovaci\w*|contrato)\b", re.I)
_DIFFERENT = re.compile(r"\b(?:save it as a new (?:request|one)|(?:it'?s|this is|that'?s) a (?:different|separate|new|"
                        r"second|another) (?:problem|issue|one|leak|request)|(?:it'?s|this is) not the same\b|"
                        r"(?:a |an )?(?:new|separate|second) request\b|guardar como nueva solicitud|es otro problema|"
                        r"es un problema distinto|es diferente)", re.I)
_STILL = re.compile(r"\b(?:still|never (?:got )?fixed|(?:nobody|no one) (?:came|fixed|has come)|has(?:n'?t| not) "
                    r"been fixed|not fixed|still waiting|for weeks|todav[ií]a|sigue|nunca lo arreglaron)\b", re.I)


_NOISE_CLASS = re.compile(r"\b(?:rattl\w*|noise|noisy|sound\w*|ruido\w*|buzz\w*|hum+ing|click\w*|bang\w*|"
                          r"grind\w*|squeak\w*|loud)\b", re.I)


def _stems(text: str) -> set[str]:
    """5-letter stems; every kind of sound ("rattling", "noise", "ruido") is one stem, so the same fault matches."""
    return {w[:5] for w in re.findall(r"[a-zà-ÿ]{4,}", _NOISE_CLASS.sub(" noise ", (text or "").lower()))}


def _repeat_of_open(resident: Resident | None, text: str) -> Any:
    """Sprint 7: 'my AC is rattling again, it's still not fixed' when "AC rattling" is OPEN on the record: that open
    item (a follow-up note citing it), never a second request. Needs the same thing AND either a 'still / again /
    never fixed' marker or the same symptom word as the open item. A NEW symptom said with 'again' ('my AC is out
    again') is a new repair flagged as a repeat (Sprint 5.1 D-5)."""
    objs = utt.things(text)  # the shared object lexicon (EN + ES), not this module's older list
    hit = next((i for i in reversed(resident.interactions) if i.category == "maintenance" and i.status != "closed"
                and objs and utt.things(i.subject) & objs), None) if resident else None
    if hit is None:
        return None
    subj = _stems(hit.subject) - _stems(" ".join(utt.things(hit.subject)) + " " + hit.subject.split()[0])
    same_symptom = bool(subj & _stems(text))
    said = {m.group(0).lower()[:5] for m in re.finditer(r"\b(?:[a-z]+ing|cools?|heats?|leak\w*|drip\w*|smell\w*|"
                                                         r"noise|broke\w*|dead|out|warm|hot|cold|enfr\w*|calient\w*|"
                                                         r"gotea\w*|fuga|roto|funciona)\b",
                                                         _NOISE_CLASS.sub(" noise ", text), re.I)}
    new_symptom = bool(said - subj - {"still", "again", "makin", "doing", "comin", "going", "happe", "being", "worki",
                                      "nothi", "somet", "anyth", "every", "out"})
    return hit if (_STILL.search(text) or same_symptom) and not new_symptom else None


_CALLBACK_ASK = re.compile(r"\b(?:call|phone|ring) me\b|\bcall ?back\b|\bsomeone (?:to )?call\b|\bll[aá]men?me\b|"
                           r"\bque me llamen\b", re.I)


def _carry_history(hd: dict[str, Any], src: dict[str, Any] | None, recent_records: list[dict[str, Any]],
                   history: Any, lang: Lang) -> None:
    """Sprint 8 C: a note for a person carries the repeat history and manager-review marker of the repair it is about:
    the pending card (or an earlier note being merged), else the repair just saved in this chat, else the history the
    caller computed for the request it follows up."""
    src = src or next((r for r in recent_records if r.get("kind") == "maintenance_request"
                       and r.get("status") != "urgent_queued"), None) or {}
    rh = src.get("repeat_history")
    if rh is None and history is not None and getattr(history, "count", 0):
        rh = history.to_record()
        _set(hd, "related_history", mh.summary_line(history, lang), "on_file")
    if rh:
        hd["repeat_history"] = rh
        f = src.get("fields")
        val = (f.get("related_history") or {}).get("value") if isinstance(f, dict) else next(
            (x.get("value") for x in f or [] if x.get("key") == "related_history"), None)
        if val and not hd["fields"].get("related_history"):
            _set(hd, "related_history", val, "on_file")
    if src.get("manager_review") or (rh and rh.get("count", 0) >= 1 and src.get("repeat")) or (
            rh and history is not None):
        hd["manager_review"] = True


def _latest_open_history(resident: Resident | None, store: Store | None, persona_id: str | None) -> Any:
    """Sprint 8 C: related history (maintenance_history) for this resident's most recent OPEN repair: an own prototype
    request from any session or an open workbook maintenance item, whichever is newest. None when there is none."""
    recs = store.records(persona_id=persona_id, kind="maintenance_request", limit=200) if (store and persona_id) else []
    cands: list[tuple[datetime, str]] = []
    for r in recs:
        if r.get("status") == "submitted_for_review" and r.get("persona_id") == persona_id:
            when = mh._as_naive(r.get("created_at"))
            if when:
                cands.append((when, _rec_issue(r)))
    for i in (resident.interactions if resident else []):
        if i.category == "maintenance" and i.status != "closed" and i.timestamp and mh.is_repair_request(i.subject):
            cands.append((i.timestamp, i.subject))
    if not cands:
        return None
    text = max(cands, key=lambda c: c[0])[1]
    h = mh.related_history(text, resident=resident, records=recs, persona_id=persona_id)
    return h if h.count else None


def _rec_issue(r: dict[str, Any]) -> str:
    return next((str(f.get("value") or "") for f in r.get("fields") or [] if f.get("key") == "issue"), "") or \
        str(r.get("title") or "")


def _own_open_elsewhere(store: Store | None, persona_id: str | None, here: list[dict[str, Any]], text: str
                        ) -> dict[str, Any] | None:
    """Sprint 8 C: this persona's OPEN prototype repair request from another session that is the SAME request as
    `text`: same thing and a compatible symptom (maintenance_history.match_score); the best score wins, then the newest.
    ScopedStore returns only this persona's records; the persona is re-checked here too."""
    if store is None or not persona_id:
        return None
    seen = {r.get("id") for r in here}
    best, best_score = None, 0
    for r in store.records(persona_id=persona_id, kind="maintenance_request", limit=200):  # newest first
        if r.get("id") in seen or r.get("status") != "submitted_for_review" or r.get("persona_id") != persona_id:
            continue
        if (sc := mh.match_score(text, _rec_issue(r))) > best_score:
            best, best_score = r, sc
    return best


def _best_open(text: str, candidates: list[tuple[Any, str]]) -> Any:
    """Sprint 8 C last round: of several open requests about one thing, the one whose symptom matches ("the AC is
    rattling louder" is I008 "AC rattling", not "AC quit cooling"). Candidates are (item, its text); None if none."""
    scored = [(mh.match_score(text, txt), i, item) for i, (item, txt) in enumerate(candidates) if item is not None]
    scored = [x for x in scored if x[0] > 0]
    return max(scored, key=lambda x: (x[0], -x[1]))[2] if scored else None


def _heard_key(count: int) -> str:
    """Sprint 8 C fix round: the empathy line scales with the real number of earlier requests."""
    return "repeat_heard_one" if count == 1 else "repeat_heard_two" if count == 2 else "repeat_heard"


def _history_line(h: mh.RepeatHistory, lang: Lang) -> str:
    """Sprint 8 C: 'I found 3 related maintenance requests over the last 30 days, ...' from real data; '' for none."""
    if h.count == 0:
        return ""
    win = h.window(lang, singular=h.count == 1) or ("en su historial" if lang == "es" else "on your record")
    return t("repeat_history_one" if h.count == 1 else "repeat_history_many", lang, n=str(h.count), window=win)


def _sent_match(records: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    """A request already sent in this chat about the same thing as `text`."""
    things = _things_in(text)
    for r in records:
        if r["kind"] != "maintenance_request":
            continue
        blob = " ".join([r.get("summary") or "", r.get("title") or "",
                         *[str(f.get("value", "")) for f in r.get("fields", []) if f.get("key") == "issue"]])
        if things & _things_in(blob):
            return r
    return None


# ---- Sprint 6 fix round: field-targeted edits, split, partial cancel (step 1c-edit) --------------------------

_WINDOW_ES = {"mornings": "mañanas", "afternoons": "tardes", "evenings": "noches", "morning": "mañana",
              "afternoon": "tarde", "evening": "noche", "after": "después de", "before": "antes de", "only": "solo"}


def _fval(card: dict[str, Any] | None, key: str) -> str:
    return str(((card or {}).get("fields", {}).get(key) or {}).get("value") or "")


def _window_es(value: str) -> str:
    """'afternoons (1-5 PM)' -> 'tardes (1-5 PM)': the on-file visit window in the card's language."""
    return re.sub(r"\b(" + "|".join(_WINDOW_ES) + r")\b", lambda m: _WINDOW_ES[m.group(1).lower()], value, flags=re.I)


def _edit_value(c: Any, lang: Lang) -> str:
    if c.field == "contact" and c.value in ("call", "text", "email", "portal"):
        return _prefers(c.value, lang) or c.value
    if c.field == "entry_window" and lang == "es":
        return _window_es(c.value)
    return _tr(c.value, lang) or c.value


_ADD_TAIL = re.compile(r"(?:^|[.!?;]\s+|,\s*)(?:and |also |plus )?(?:add|also note|note|mention)(?: that)?\s+"
                       r"(?P<v>[^.!?]{3,160})", re.I)


_FIELD_NAME = {"issue": "the problem", "location": "the room", "entry": "entry permission",
               "contact": "your contact preference", "entry_window": "the best time for visits",
               "area": "the community", "days": "the days", "time": "the time of day", "beds": "the number of beds",
               "move_in": "the move-in date", "pets": "pets", "budget": "your budget"}


def _apply_edits(card: dict[str, Any], edits: list[Any], msg: str, lang: Lang) -> str:
    """Replace each named field (never append to "What's wrong") and return the "Updated: X → Y" lines."""
    notes: list[str] = []
    for c in edits:
        val = _edit_value(c, lang)
        if c.field == "location" and _fval(card, "entry") == _tr("Not needed (common area)", lang) and \
                card["fields"]["entry"].get("source") == "assistant" and val != _tr("Outside or common area", lang):
            card["fields"].pop("entry", None)  # inside the home after all: entry permission is needed again
        if c.field == "location" and (old_room := extract_location(_fval(card, "location"))) and \
                (new_room := extract_location(val)) and old_room != new_room and _fval(card, "issue") and \
                not any(x.field == "issue" for x in edits):
            # Sprint 7: "my bathroom faucet" becomes "my kitchen faucet" when the room is corrected (same as step 8)
            card["fields"]["issue"]["value"] = re.sub(rf"\b{re.escape(old_room)}\b", lambda m_: new_room if m_.start()
                                                      == 0 else new_room.lower(), _fval(card, "issue"), flags=re.I)
        if c.field == "issue":
            for k in ("vague_issue",):
                card.pop(k, None)
            if (tail := _ADD_TAIL.search(msg)) and tail.group("v").strip().lower() not in val.lower():
                val = f"{val}. Also: {_cap(tail.group('v').strip())}"[:400]
        _set(card, c.field, val, "you_said")
        also: list[str] = []
        if card["kind"] == "tour_request" and c.field == "area":
            # holdout3: "make that Detroit instead, Friday around 11am" also changes the day and time on the card
            clock = extract_clock_preference(msg)
            for k, v in (("days", extract_days(msg)),
                         ("time", f"{_tr(clock[0], lang)} ({clock[1]})" if clock else
                          _tr(extract_time_of_day(msg), lang))):
                if v and k not in {e.field for e in edits} and _set(card, k, v, "you_said"):
                    also.append(_FIELD_NAME[k])
        name = _FIELD_NAME.get(c.field) if lang == "en" else None  # Sprint 9: a sentence; the card shows the value
        if name and c.field == "area" and also:
            name = ", ".join([name, *also[:-1]]) + f" and {also[-1]}"
        notes.append(t("location_updated", lang, loc=val) if c.field == "location" else
                     t("field_changed", lang, name=name) if name else
                     t("field_updated", lang, label=LABEL[c.field][lang], value=val))
    if card["kind"] == "maintenance_request" and (note := visit_note(msg)) and note.lower() not in \
            _fval(card, "notes").lower():  # "call me first, i have a dog": the dog is a note for the visit
        prev = _fval(card, "notes")
        _set(card, "notes", (f"{prev}; {note}" if prev else note)[:240], "you_said")
        notes.append(t("note_added", lang, value=note))
    return " ".join(notes)


def _cap(v: str) -> str:
    return v[0].upper() + v[1:] if v else v


def _issue_parts(card: dict[str, Any]) -> list[str]:
    """The separate problems written on one repair card ("X Also: Y", "X; also Y", "two things: 1) X 2) Y")."""
    issue = _fval(card, "issue")
    out: list[str] = []
    for chunk in re.split(r"\s+Also:\s+", issue):
        for seg in re.split(r"\s*(?:;|\.\s+|,?\s*\b(?:and also|also|plus|and separately|separately|as well as|y "
                            r"aparte|y tambi[eé]n|adem[aá]s)\b|\b\d\)|,?\s+and\s+(?=(?:the|my|our)\b))\s*",
                            re.sub(r"^\W*(?:i have )?(?:two|2|a couple of) (?:things|problems|issues)\W*", "", chunk,
                                   flags=re.I), flags=re.I):
            seg = seg.strip(" ,.;:")
            if not seg:
                continue
            if out and (not und.things_in(seg) or und.things_in(seg) <= und.things_in(out[-1])):
                out[-1] = f"{out[-1]}, {seg}"  # no new thing named: more about the same problem
            else:
                out.append(seg)
    return [_cap(p.strip(" ,.;")) for p in out if p.strip(" ,.;")]


def _refresh_after_drop(card: dict[str, Any]) -> None:
    """Sprint 7: a problem taken off the card leaves NOTHING behind (summary, security flag, its priority note), so the
    saved record holds only what the person kept."""
    issue = _fval(card, "issue")
    if card.get("security") and not is_security_repair(issue):
        card.pop("security", None)
        if (card.get("fields", {}).get("priority_note") or {}).get("source") == "assistant":
            card["fields"].pop("priority_note", None)
            card["priority"] = "normal"
    room = extract_location(issue)
    loc_f = card.get("fields", {}).get("location") or {}
    if loc_f and (loc_f.get("source") == "assistant" or (room and extract_location(loc_f.get("value") or "") != room)
                  or (not room and extract_location(loc_f.get("value") or "") == "Outside or common area")):
        card["fields"].pop("location", None)  # the dropped problem's place left with it; asked again if needed
        if room:
            _set(card, "location", room, "you_said")
    ent_f = card.get("fields", {}).get("entry") or {}
    if ent_f.get("source") == "assistant":
        card["fields"].pop("entry", None)  # "Not needed (common area)" belonged to the dropped problem
    card["summary"] = " · ".join(x for x in (issue, _fval(card, "location")) if x)[:300] or card.get("summary", "")


def _drop_or_split(card: dict[str, Any], u: Any, lang: Lang) -> tuple[str, str] | None:
    """'never mind the smoke detector, only the faucet' drops one problem; 'those are 2 different things' / 'make the
    oven light its own request' splits the card (one request per problem; the rest queue after Send)."""
    parts = _issue_parts(card)
    queued = [q for q in (card.get("queued") or []) if q]
    if u.split_request and not u.drop_issue and queued and len(parts) < 2 and (
            not u.split_target or any(und.things_in(q) & und.things_in(u.split_target) for q in queued)):
        # already one request per problem: say so, change nothing
        return t("queued_note", lang, items="; ".join(queued)), "Split asked; the problems are already separate."
    if u.drop_issue or u.keep_issue:
        allp = parts + queued
        # Sprint 7: the named part is matched against what is written on the card (objects or a distinctive word,
        # "the mailbox part"), so any problem on the card can be dropped, not only the nouns in a fixed list
        kept = [p for p in allp if not (u.drop_issue and und.part_matches(p, u.drop_issue))]
        if u.keep_issue:
            kept = [p for p in kept if und.part_matches(p, u.keep_issue)] or kept
        if not kept or len(kept) == len(allp):
            return None
        _set(card, "issue", kept[0][:200], "you_said")
        card["queued"] = kept[1:3]
        if room := extract_location(kept[0]):
            _set(card, "location", _tr(room, lang), "you_said")
        _refresh_after_drop(card)
        dropped = (u.drop_issue or ", ".join(p for p in allp if p not in kept)).strip()
        return (t("issue_dropped", lang, detail=("the " + dropped) if lang == "en" and not dropped.lower().startswith(
            ("the ", "my ")) else dropped, issue=kept[0]), "Partial cancel: one problem dropped, the card stays.")
    if len(parts) < 2 and u.split_target:
        tgt = und.things_in(u.split_target)
        if not (und.things_in(parts[0] if parts else "") - tgt):
            parts = []
        elif parts:
            parts = [parts[0], _cap(u.split_target)]
    if len(parts) < 2:
        return t("split_none", lang), "Split asked; only one problem on the card."
    first, rest = parts[0], parts[1:]
    if u.split_target and (tgt := und.things_in(u.split_target)):
        rest = [p for p in parts if und.things_in(p) & tgt] or rest
        first = next((p for p in parts if p not in rest), parts[0])
    _set(card, "issue", first[:200], "you_said")
    card["queued"] = [*rest, *queued][:3]
    if room := extract_location(first):
        _set(card, "location", _tr(room, lang), "you_said")
    _refresh_after_drop(card)
    return (t("split_done", lang, first=first, items="; ".join(card["queued"])),
            "Split: one request per problem; the others wait their turn.")


_RENEWAL_CHIP: dict[Lang, str] = {"en": "Renewal question", "es": "Pregunta de renovación"}
_QUESTIONISH_END = re.compile(r"\?\s*$|^\W*(?:what|when|where|how|who|why|is|are|do|does|did|can|will)\b", re.I)


# J-1: a direct ask for help after a personal-safety alert gets the approved hazard notice again, not a status line.
_CRISIS_HELP = re.compile(
    r"\bwhat (?:should|do|can) i do\b|\b(?:can|could|will) (?:you|someone|somebody|anyone) (?:call|send|come|check)|"
    r"\b(?:call|send) (?:someone|somebody|anyone|help)\b|\bcheck on me\b|\bis (?:someone|anyone|help) coming\b|"
    r"\bhelp me\b|\bqu[eé] (?:hago|debo hacer|puedo hacer)\b|\b(?:pueden|puede) (?:llamar|mandar|enviar|venir)\b|"
    r"\bay[uú]d(?:a|e)me\b", re.I)


_STOP = {"also", "that", "this", "with", "have", "from", "they", "there", "it's", "its", "the", "and", "just",
         "mention", "forgot", "thing", "more", "really", "very", "still", "when", "what", "your", "about", "into",
         "like", "it"}


def _content_words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z']{4,}", text.lower()) if w not in _STOP}


# "oh, also ...", "to add: ...", "forgot to mention ...": more detail, said as an addition
_ADD_DETAIL = re.compile(r"^\W*(?:oh|ah|um|and|ok(?:ay)?)?[\s,.!-]*(?:also|and also|plus|to add|i (?:forgot|meant) to "
                         r"(?:mention|say|add)|forgot to (?:mention|say|add)|one more thing|another thing|btw|by the "
                         r"way|oh and|p\.?s\.?|quick add|adding)\b\W*", re.I)


def plan_turn(*, msg: str, gate: GateDecision, workflow: WorkflowSelection, ctx: SafeContext,
              triage: MaintenanceTriage | None, store: Store | None, session_id: str, persona_id: str | None,
              resident: Resident | None, channel: Channel, lang: Lang, recent: list[str] | None = None,
              hazard: str | None = None, care: str | None = None, memory: dict[str, Any] | None = None,
              understanding_hint: tuple[Any, str] | None = None, person_danger: bool = False,
              full_alert: bool = False, danger_rule: str | None = None, risk: Any = None,
              quickfix_mode: str = "off") -> TurnPlan:
    """`hazard` / `care` come from the safety policy (app/risk); the planner never re-derives safety itself.
    `memory` is what the previous turn's plan left (unproductive-turn streak, whether a tour was already offered);
    it holds flags and counts only, never message text. `understanding_hint` is the optional model pass for this
    message (`app.understanding.model_pass`: (result, status)); the rules pass always runs here."""
    from app.emergency import LABEL as LABEL_EMERGENCY
    from app.emergency import QUEUE_NOTE, emergency_kind
    from app.emergency import notice as emergency_notice

    persona_id = persona_id or None  # "" from the API means not signed in
    pkey = persona_id or "none"
    msg = utt.normalize(msg)  # Sprint 7: "tmrw", "pls", "2morrow" read as words by every step below
    draft = store.get_draft(session_id, pkey, include_declined=True) if store else None
    mem: dict[str, Any] = dict(memory or {})
    streak = int(mem.get("unproductive", 0) or 0)
    # Sprint 8 (D): quick-fix tips offered last turn. The offer lives for exactly one turn (ids only, no text).
    qf_pending = mem.pop(quickfix.MEM_KEY, None)
    qf_intake = False
    normal_q_offer = bool(mem.pop("normal_q", None))  # Sprint 8 C: last turn answered an "is it normal" question
    qf_queue: str | None = None  # the tips' issue, kept on the card of a NEW problem raised while tips were pending
    qf_side = {"on": False}  # a side question while tips are pending: answered normally, the offer is kept
    # 0a. Language (D-6 / B-8 / R-9). An explicit request for English or Spanish switches and sticks ("pinned"). Without
    # a pin, a message that is clearly one language answers in it; an unclear one ("no", "sí", "leak") keeps the
    # language of the conversation so far, so one Spanish word never flips an English conversation (or vice versa).
    asked_lang: Lang | None = "en" if asks_for_english(msg) else "es" if asks_for_spanish(msg) else None
    if asked_lang:
        mem["lang_pin"] = asked_lang
        rest = strip_language_request(msg) if asked_lang == "en" else strip_spanish_request(msg)
        if len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest)) >= 2:
            msg = rest  # "ok english again please. is this sent?" -> the question is still answered
            asked_lang = None  # handled here; step 6 must not answer with a bare "switched" line
    previous = (draft or {}).get("lang") or mem.get("lang")
    clear_es = detect_language(msg) == "es"
    clear_en = len(_ENGLISH_HINT.findall(msg)) >= 2 or (len(msg.split()) >= 3 and _ENGLISH_HINT.search(msg)
                                                        and not clear_es)
    if mem.get("lang_pin"):
        lang = mem["lang_pin"]
    elif clear_es:
        lang = "es"
    elif clear_en:
        lang = "en"
    elif previous in ("en", "es"):
        lang = previous
    if draft and draft.get("lang") != lang:
        draft = {**draft, "lang": lang}
    parked: dict[str, Any] | None = None  # a card declined earlier: its details still go into a note for a person
    if draft and draft.get("declined"):
        act0 = classify_turn(msg, draft, None)
        u0 = und.understand(msg, draft, None, recent, understanding_hint)  # Sprint 6: paraphrased restores too
        tr0 = wf.apply(wf.derive(draft), u0)
        # Sprint 7: a typed "actually yes send it" after Don't send brings the SAME card back (never a new card with
        # the command as a field value); saving still needs Send or a typed send on the restored card
        restore = (act0.has(Act.RESTORE) or tr0.has("restore") or u0.has(und.DialogueAct.RESUME_TASK)) and \
            gate.urgency != "emergency"
        if u0.requests_human:  # D-11: "actually I want a person" asks for a person, not the old card back
            restore = False
            parked = draft
        if draft.get("offered") and is_affirmative(msg) and gate.urgency != "emergency":
            restore = True  # "yes" to "I can pass what you've written to the office"
        if restore and store:
            draft = {k: v for k, v in draft.items() if k != "declined"}
            more: list[str] = []
            if draft["kind"] == "maintenance_request" and draft.get("fields", {}).get("issue"):
                more = [c.strip() for c in re.split(r"[.,;!?]+", msg) if _LATER_SYMPTOM.search(c)
                        and not re.search(r"after all|undo|back|need it|want it", c, re.I)]
                if more:  # "ugh ok i do need it fixed, the kitchen smells. send it after all"
                    iv = draft["fields"]["issue"]["value"]
                    add_txt = "; ".join(m[0].upper() + m[1:] for m in more)
                    _set(draft, "issue", f"{iv} Also: {add_txt}"[:400], "you_said")
            store.save_draft(session_id, pkey, draft["kind"], {**draft, "stale": False, "lang": lang})
            missing0 = _missing(draft["kind"], draft)
            if not missing0 and is_explicit_send(msg) and not u0.requests_human:
                # Sprint 7 fix round: "ok fine actually do send the note" after Don't send is consent for THAT card
                # (one consent vocabulary; a bare "ok" alone still never sends)
                result0 = confirm(store, session_id, persona_id, draft["kind"], ctx, lang)
                new0 = result0.record if result0.record and result0.error_code != "ALREADY_SAVED" else None
                return TurnPlan(template=result0.message, functions=[KIND_FN[draft["kind"]]], action=result0.action,
                                skip_model=True, records=[new0] if new0 else [], consumed_by_draft=True, memory=mem,
                                lang=lang, workflow=_sel(KIND_WF[draft["kind"]], "Typed send for the declined card."))
            ask, chips0 = _next_step(draft, lang)  # W-7: an incomplete card asks its missing question
            restored_txt = t("restored_missing", lang, ask=ask) if missing0 else t("restored", lang)
            if draft["kind"] == "maintenance_request" and "Also:" in (draft["fields"].get("issue", {}).get("value") or
                                                                     "") and more:
                restored_txt = restored_txt.replace(", unchanged", "", 1).replace(", sin cambios", "", 1) + " " + \
                    t("note_added", lang, value="; ".join(more))
            return TurnPlan(template=restored_txt,
                            functions=[KIND_FN[draft["kind"]]], chips=chips0 if missing0 else [],
                            action=_proposed(draft["kind"], draft, lang), skip_model=True, consumed_by_draft=True,
                            memory=mem, lang=lang,
                            workflow=_sel(KIND_WF[draft["kind"]], "Person restored a card they had declined."))
        if draft.get("parked") and store and not parked:
            # W-4: a note that was skipped hands back the card it had parked; this message then works on that card
            back = {**draft["parked"], "stale": False, "lang": lang}
            back.pop("declined", None)
            store.save_draft(session_id, pkey, back["kind"], back)
            draft = back
        elif draft["kind"] in ("maintenance_request", "tour_request") and gate.urgency != "emergency" and (
                act0.question in ("card_status", "timing") or is_status_request(msg) or is_meta_question(msg)) \
                and not parked:
            # D-3: "wait what happened? is someone coming for my window" right after Don't send: say so plainly, and
            # keep the declined card restorable
            return TurnPlan(template=t("declined_status", lang, what=WHAT[draft["kind"]][lang]), functions=["F8"],
                            skip_model=True, consumed_by_draft=True, chips=CHIPS["after_decline"][lang][:1],
                            memory=mem, lang=lang,
                            workflow=_sel("status_lookup", "Asked about a card they had declined."))
        else:
            if store:
                store.clear_draft(session_id, pkey)
            draft = None
    flags = set(gate.risk_flags)
    verified = _verified(ctx)
    is_resident = ctx.audience == "resident"
    handoff = build_handoff(gate, workflow, ctx, False, "", triage, None)
    fns: list[FunctionId] = ["F3"] + (["F2"] if channel in ("sms", "email") else [])
    mine = [r for r in (store.records(session_id=session_id, limit=50) if store else [])
            if (r.get("persona_id") or None) == persona_id]
    touched = {"draft": False}
    locals_lead: dict[str, str] = {}
    meta_u: dict[str, dict[str, Any]] = {}  # Sprint 6: the understanding / transition summaries for the trace

    def save(kind: str, d: dict[str, Any]) -> None:
        touched["draft"] = True
        if store:
            store.save_draft(session_id, pkey, kind, {**d, "lang": lang, "stale": False})

    def done(plan: TurnPlan) -> TurnPlan:
        plan.functions = list(dict.fromkeys(fns + plan.functions))
        mem["unproductive"] = streak + 1 if "unproductive" in plan.extra_flags else 0
        mem["lang"] = lang
        # Sprint 6 fix round: the offer this reply makes (a kind, never text), so "ok sure" next turn can accept it
        if mem.get("no_tour") and t("faq_offer_tour", lang) in plan.template:
            # Sprint 7 fix round: "no tour, just want to know" is respected: no tour offer until they ask for one
            plan.template = plan.template.replace(t("faq_offer_tour", lang), "").strip()
        mem["offer"] = "tour" if t("faq_offer_tour", lang) in plan.template else "leasing_note" if t(
            "next_leasing_note", lang) in plan.template else None
        plan.memory = mem
        plan.lang = lang
        plan.understanding = plan.understanding or meta_u.get("u", {})
        plan.transition = plan.transition or meta_u.get("tr", {})
        if (inj := locals_lead.get("inj")) and not plan.template.startswith(inj):
            plan.template = inj + plan.template  # E-8: the instruction-like part was dropped; say so once
            plan.skip_model = True
        # Sprint 7: no word-for-word repeat of a note reply. If this reply is the same as the last one and a note for
        # the office is on screen, say the human path once more in other words (memory keeps a checksum, no text).
        crc = zlib.crc32(plan.template.encode("utf-8"))
        if mem.get("last_reply") == crc and plan.action is not None and plan.action.kind == "staff_handoff" and \
                not plan.records and ("frus" in locals_lead or "merged" in locals_lead):
            plan.template = t("frustrated_again" if "frus" in locals_lead else "note_updated", lang)
            crc = zlib.crc32(plan.template.encode("utf-8"))
        mem["last_reply"] = crc
        if qf_side["on"] and plan.action is None and quickfix.MEM_KEY in mem and \
                t("quickfix_side_reminder", lang) not in plan.template:
            # Sprint 8 (D) fix round: a side question during tips is answered and the tips question stays open
            plan.template = plan.template.rstrip() + " " + t("quickfix_side_reminder", lang)
            plan.chips = CHIPS["quickfix"][lang]
        if (rl := locals_lead.get("resume")) and not plan.template.startswith(rl):
            plan.template = rl + plan.template  # Sprint 8 C: the card suspended by an alert is back, still unsent
        lead = locals_lead.get("diy", "")
        if lead and not plan.template.startswith(lead):
            plan.template = lead + plan.template
            plan.skip_model = True  # safety wording stays exactly as written
        # A card the person didn't engage with this turn becomes "stale": a later bare "yes" re-shows it first.
        if store and draft and not touched["draft"]:
            store.mark_stale(session_id, pkey, draft["kind"], {**draft, "stale": True})
        return plan

    def handoff_plan(template_key: str, reason: str, wid: WorkflowId = "human_handoff", *,
                     category: str | None = None, team: str | None = None, topic: str | None = None,
                     card: bool = True, extra: str = "", summary: str | None = None,
                     park: dict[str, Any] | None = None, history: Any = None, requests: str | None = None,
                     **kw: str) -> TurnPlan:
        if not is_resident and mem.get("guest_repair") and team in (None, "leasing") and category not in (
                "leasing_follow_up", "fair_housing_or_legal"):
            team = "maintenance"  # live finding: a guest who reported a repair goes to maintenance, not leasing
        rec = handoff or synthesize_handoff(gate, ctx, category or "other", team or "management", reason)
        upd = {k: v for k, v in (("category", category), ("team", team)) if v}
        if not is_resident and rec.team == "management" and not team and category not in ("fair_housing_or_legal",):
            upd.setdefault("team", "leasing")  # prospects and visitors are leasing's customers
        rec = rec.model_copy(update=upd) if upd else rec
        if summary:
            rec = rec.model_copy(update={"summary": summary})
        hd = _handoff_draft(gate, rec, ctx, msg, lang, draft or parked, topic, recent)
        if summary:
            hd["summary"] = summary  # Sprint 8 C: consistent with the cited record and the repair-only count
        if requests:
            prev_r = (hd["fields"].get("requests") or {}).get("value")
            _set(hd, "requests", f"{prev_r}; {requests}" if prev_r else requests, "you_said")
        if history is None and not (draft or parked) and is_resident and verified and template_key in (
                "handoff_offer", "frustrated", "lost_note") and not any(
                r["kind"] == "maintenance_request" for r in mine):
            # Sprint 8 C: "get me the manager" with no card pending: the history of the resident's most recent OPEN
            # repair (own record or workbook) goes on the note; explicitly none when there is no open repair
            history = _latest_open_history(resident, store, persona_id)
            if history is None:
                hd["repeat_history"] = None
        _carry_history(hd, draft or parked, mine if not (draft or parked) else [], history, lang)
        if (draft or {}).get("kind") == "staff_handoff" and not (draft or {}).get("declined"):
            locals_lead["merged"] = ""  # marker only: this message was merged into the note already on screen
        if not hd["fields"].get("earlier") and not (draft or parked) and not kw.pop("_unlinked", "") and (
                wo0 := next((r for r in mine if r["kind"] == "maintenance_request"
                             and r.get("status") != "urgent_queued"), None)):
            # the repair just saved in this chat is cited, so the office sees which request this is about
            _set(hd, "earlier", f"{wo0['id']} · {wo0.get('title') or WHAT['maintenance_request'][lang]}"[:240],
                 "you_said")
        if not is_resident and mem.get("guest_repair") and not hd["fields"].get("earlier"):
            repair_said = next((r for r in reversed(recent or []) if is_issue_description(r) or _things_in(r)), None)
            if repair_said and repair_said != msg:
                _set(hd, "earlier", redact(repair_said)[:240], "you_said")  # the repair they described, once
        if template_key in ("lost_note", "frustrated") and is_resident and verified and not hd["fields"].get("earlier"):
            # Sprint 7 fix round: a frustrated person's note names their open requests, so nobody has to ask again
            open_items = [i for i in status_items(store, resident, persona_id or "")
                          if "closed" not in i.status.lower()]
            if open_items:
                _set(hd, "earlier", "; ".join(f"{i.reference} {i.title}" for i in open_items[:3])[:240], "on_file")
        if mem.get("questions"):  # P-4: every question the assistant couldn't answer in this chat goes on the note
            _set(hd, "questions", _questions_text(mem["questions"], lang), "you_said")
        template = t(template_key, lang, **kw) + extra
        if template_key == "followup_existing" and _UPSET.search(msg):
            # Sprint 9 (judge: "This is ridiculous, I've reported it three times" got a ticket number first)
            template = t("upset_followup_lead", lang) + " " + template
        if "[phone redacted]" in msg or "[email redacted]" in msg:  # never imply a typed number was stored
            template += t("contact_not_kept", lang)
        if card and draft and draft["kind"] in ("maintenance_request", "tour_request") and not draft.get("declined"):
            what_txt = WHAT[draft["kind"]][lang]
            template += (f" The details of your unsent {what_txt} are included in this note, so nothing is lost."
                         if lang == "en" else f" Los datos de su {what_txt} no enviada van incluidos en esta nota.")
            # W-4: one open card per conversation, so the first card is PARKED inside the note (restorable), never
            # discarded: it comes back after the note is sent (confirm) or skipped (top of plan_turn / decline).
            hd["parked"] = {k: v for k, v in draft.items() if k not in ("parked", "stale")}
            template += t("parked_note", lang, what=what_txt)
        elif card and draft and draft["kind"] == "staff_handoff" and draft.get("parked"):
            hd["parked"] = draft["parked"]
        if not is_resident and (lead_vals := mem.get("lead") or {}).get("budget"):
            _set(hd, "budget", lead_vals["budget"], "you_said")  # C-2: the budget rides on the leasing note
        notes = [r for r in mine if r["kind"] == "staff_handoff" and r.get("status") != "urgent_queued"]
        another = bool(re.search(r"\banother note\b|\bnew note\b|otra nota", msg, re.I))
        if card and notes and not draft and not another and template_key in (
                "handoff_offer", "unclear_offer", "status_unverified", "maint_unverified", "balance", "sensitive",
                "lost_note", "no_promise_note", "account_boundary"):  # j-safe-force-booking: one note, not two
            return done(TurnPlan(template=t("note_exists", lang, ref=notes[0]["id"]), functions=["F9"],
                                 skip_model=True, consumed_by_draft=True, force_handoff=True, handoff=rec,
                                 chips=["Send another note" if lang == "en" else "Enviar otra nota"],
                                 workflow=_sel(wid, "A note is already with the office; no duplicate.")))
        if not card:  # e.g. Fair Housing steering: neutral redirect only; the flag stays staff-side
            return done(TurnPlan(template=template, functions=["F4", "F9"], workflow=_sel(wid, reason),
                                 force_handoff=True, handoff=rec, chips=CHIPS["prospect_next"][lang]))
        if park and not hd.get("parked"):
            hd["parked"] = park  # W-4 mechanism: the other problem's card opens after this note is sent or skipped
        save("staff_handoff", hd)
        return done(TurnPlan(template=template, functions=["F9"], workflow=_sel(wid, reason),
                             action=_proposed("staff_handoff", hd, lang), force_handoff=True, handoff=rec))

    def lost_plan(reason: str) -> TurnPlan:
        """D-12: one apology, the single next step of an open card, and a person, without re-asking anything.
        First time with an open card: restate its next step and offer a person. Otherwise: a note for the office
        that carries the card's details. Nobody is notified (the note is saved only when the person sends it)."""
        live = draft if draft and not draft.get("declined") else None
        if live and live["kind"] == "staff_handoff":
            # Sprint 7: never the same words twice in a row; each repeat alternates and says how the note reaches a
            # person (recorded for staff review; nobody is notified in this prototype)
            live["lost_n"] = int(live.get("lost_n", 0)) + 1
            save("staff_handoff", live)
            key_l = "lost_note_open" if live["lost_n"] % 2 else "frustrated_again"
            return done(TurnPlan(template=t(key_l, lang), functions=["F9"], skip_model=True,
                                 action=_proposed("staff_handoff", live, lang), consumed_by_draft=True,
                                 force_handoff=True, handoff=handoff, workflow=_sel("human_handoff", reason)))
        if live and not live.get("lost_ack"):
            live["lost_ack"] = True
            save(live["kind"], live)
            missing = _missing(live["kind"], live)
            what = WHAT[live["kind"]][lang]
            step = t("next_step_missing", lang, what=what, label=LABEL[missing[0]][lang].lower()) if missing \
                else t("next_step_ready", lang, what=what)
            slot_chips = {"location": CHIPS["locations"][lang], "entry": CHIPS["entry"][lang],
                          "days": CHIPS["tour_days"][lang], "time": CHIPS["tour_time"][lang]}.get(
                missing[0] if missing else "", [])
            return done(TurnPlan(template=t("lost_draft", lang, step=step), functions=[KIND_FN[live["kind"]]],
                                 action=_proposed(live["kind"], live, lang), chips=CHIPS["lost"][lang] + slot_chips,
                                 skip_model=True, consumed_by_draft=True,
                                 workflow=_sel(KIND_WF[live["kind"]], reason)))
        return handoff_plan("lost_note", reason, category="human_requested",
                            topic="The chat wasn't helping; asked for a person",
                            team="leasing" if not is_resident else None)

    def unproductive(plan: TurnPlan, reason: str) -> TurnPlan:
        """A turn that moved nothing forward (fallback reply, or the same question again). The second one in a row
        becomes the D-12 recovery instead of another loop."""
        if streak >= 1:
            return lost_plan("Second unproductive turn in a row: " + reason)
        plan.extra_flags.append("unproductive")
        return done(plan)

    # 0. SMS keywords (F2, I-06 draft) — handled before anything else on the SMS channel.
    if channel == "sms" and is_sms_opt_out(msg):
        if store:
            store.clear_draft(session_id, pkey)
        return done(TurnPlan(template=t("sms_opt_out", lang), functions=["F2"], skip_model=True,
                             workflow=_sel("sms_opt_out", "SMS opt-out keyword (I-06 draft list).")))
    if channel == "sms" and msg.strip().upper() in ("START", "UNSTOP", "YES START"):
        return done(TurnPlan(template=t("sms_opt_in", lang), functions=["F2"], skip_model=True,
                             workflow=_sel("sms_opt_out", "SMS opt-in keyword (I-06 draft list).")))

    # 1. Emergency: deterministic text for every audience, never a model reply; one urgent note per hazard.
    if gate.urgency == "emergency":
        kind = hazard or emergency_kind(msg) or "other"
        people = is_people_hazard(kind)  # one definition, shared with the safety policy
        eh = handoff.model_copy(update={"team": "management"}) if (handoff and people) else handoff
        label = LABEL_EMERGENCY.get(kind, kind).lower()
        topic = f"Possible emergency: {label}" if lang == "en" else "Posible emergencia"
        hd = _handoff_draft(gate, eh, ctx, msg, lang, draft, topic=topic)
        if people:
            hd["team"] = "management"  # a person in danger is not a maintenance job
        if kind in _PRIVATE_HAZARDS:  # minimal record: the words stay out of the queue (policy sign-off needed)
            withheld = ("Details withheld for privacy. Safety guidance was shown in the chat." if lang == "en"
                        else "Detalles reservados por privacidad. Se mostró la guía de seguridad.")
            _set(hd, "message", withheld, "assistant")
            hd["summary"] = "Possible emergency involving a person: check on the resident (prototype)."
        hd["priority"], hd["hazard"] = "urgent", kind
        same = [r for r in mine if r.get("status") == "urgent_queued" and r.get("hazard") == kind]
        records: list[PrototypeRecord] = []
        existed = bool(same)
        rec: PrototypeRecord | None = PrototypeRecord.model_validate(same[0]) if same else None
        if not same and store:
            try:
                raw = store.add_record_once(PREFIX["staff_handoff"], "staff_handoff", session_id, persona_id,
                                            _record_data("staff_handoff", hd, lang), once_key=kind)
                existed = bool(raw.pop("_existing", False))
                rec = PrototypeRecord.model_validate(raw)
            except Exception as e:  # never claim a note that wasn't saved
                log.warning("urgent note write failed: %s", type(e).__name__)
        if rec and not existed:
            records = [rec]
        if store and draft and draft.get("kind") in ("maintenance_request", "tour_request") and \
                not draft.get("declined"):
            # Sprint 8 C last round: an unsent card is SUSPENDED (kept, stale), never lost; it comes back once the
            # safety layer no longer reports an emergency (step 1b-resume)
            store.save_draft(session_id, pkey, draft["kind"], {**draft, "suspended": True, "stale": True})
        elif store and not (draft and draft.get("suspended")):
            store.clear_draft(session_id, pkey)
        touched["draft"] = True
        text = emergency_notice(kind, lang) if kind != "other" else t("emergency_steps", lang)
        # sprint 6 (rule R10): a follow-up during an active incident gets the approved notice FIRST, then the honest
        # line about the note already saved (with its reference), instead of a second "note saved" claim.
        if existed and _EMERGENCY_REFUSE.search(msg):
            from app.emergency import REFUSE_LEAD
            text = REFUSE_LEAD[lang] + text
        action = None
        from app.emergency import NO_LINE, asks_emergency_line
        if rec and existed and asks_emergency_line(msg):  # fix round (P1): no emergency number in this prototype
            text += " " + NO_LINE[lang].format(ref=rec.id)
        elif rec:
            text += (" " + (t("crisis_follow", lang, ref=rec.id) if people else t("emergency_follow", lang, ref=rec.id))
                     if existed else QUEUE_NOTE[lang])
            action = _proposed("staff_handoff", hd, lang).model_copy(update={
                "stage": "submitted", "record": rec, "confirm_label": None,
                "title": "Urgent note for staff" if lang == "en" else "Nota urgente para el personal",
                "note": "Saved as urgent in the prototype staff queue. It does not page or call anyone."})
        per_e = [sg.text for sg in utt.segments(msg, und.requests_human) if sg.workflow == "person"]
        if per_e and rec and kind not in _PRIVATE_HAZARDS:
            # Sprint 7 fix round (UX judge): a second need in the same message ("... and I need someone to call me
            # about my lease") is kept: it is in the urgent note's message, and the reply says so AFTER the fixed text
            mem["queued_person"] = redact(per_e[0])[:160]
            text += t("queued_other_safety", lang, topic=mem["queued_person"])
        return done(TurnPlan(template=text, functions=["F6", "F9"], records=records, action=action,
                             skip_model=True, force_handoff=True, handoff=eh,
                             workflow=_sel("maintenance", f"Emergency ({kind}): fixed safety text, urgent note.")))

    # 1b. Right after an emergency, short follow-ups keep the safety context.
    urgent_mine = [r for r in mine if r.get("status") == "urgent_queued"]
    from app.risk.incident import closed as incident_closed
    if urgent_mine and not asks_privacy(msg) and incident_closed(store, session_id, getattr(store, "persona_key",
                                                                                             pkey)):
        # fix round: the incident was resolved, retracted or brought under control, so short messages are no longer
        # emergency follow-ups (the policy still keeps any remembered calm line, R9); privacy questions still are
        urgent_mine = []
    latest_hz = (urgent_mine[0].get("hazard") or "other") if urgent_mine else None
    if latest_hz in _PRIVATE_HAZARDS and not (draft and not draft.get("stale")) and (
            asks_privacy(msg) or _EMERGENCY_FOLLOW.search(msg) or _SMALL_TALK.match(msg)
            or ("low_confidence" in flags and len(msg) < 80 and not is_status_request(msg))):
        # J-1 (NEEDS McKINLEY REVIEW): a person, not a building, is at risk, so no maintenance-line steps. The approved
        # calm line (988 after self-harm, else 911) is already shown above this reply by the safety policy (rule R9,
        # app/risk/policy.py), so it isn't repeated; the reply says honestly what the urgent note holds and that
        # nobody is notified automatically.
        if asks_privacy(msg):
            tail = t("crisis_privacy", lang, label=LABEL_EMERGENCY.get(latest_hz, latest_hz).capitalize())
        elif _CRISIS_HELP.search(msg):
            # "what do I do / can you call someone / will someone come": no new advice, the approved notice verbatim
            tail = f"{t('crisis_help', lang)} {emergency_notice(latest_hz, lang)}"
        else:
            tail = t("crisis_follow", lang, ref=urgent_mine[0]["id"])
        return done(TurnPlan(template=tail, functions=["F6", "F9"], skip_model=True,
                             consumed_by_draft=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("general_inquiry", "Follow-up after a personal-safety alert: approved "
                                                              "crisis line repeated, no maintenance steps.")))
    if urgent_mine and _EMERGENCY_REFUSE.search(msg):
        from app.emergency import REFUSE_LEAD
        hz = (urgent_mine[-1].get("hazard") or "other")
        steps = emergency_notice(hz, lang) if hz != "other" else t("emergency_steps", lang)
        return done(TurnPlan(template=REFUSE_LEAD[lang] + steps, functions=["F6", "F9"], skip_model=True,
                             consumed_by_draft=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("maintenance", "Resident resisting emergency guidance: repeat it.")))
    proceed = bool(_PROCEED.search(msg)) and gate.urgency != "emergency" and not hazard and not any(
        r.get("hazard") in _PRIVATE_HAZARDS for r in urgent_mine)
    if proceed and urgent_mine and not draft:
        qf_intake = True  # Sprint 8 C: "I'm fine, I just want it fixed": the repair intake for what the alert was about
    if urgent_mine and care != "distress" and not proceed and not (draft and not draft.get("stale")) and (
            _EMERGENCY_FOLLOW.search(msg) or _CRISIS_HELP.search(msg) or (
                "low_confidence" in flags and len(msg) < 60 and not is_status_request(msg)
                and not extract_entry(msg) and not is_affirmative(msg))):
        follow = t("emergency_follow", lang, ref=urgent_mine[0]["id"])
        if _CRISIS_HELP.search(msg):  # E-5: "what do i do": the approved notice verbatim, FIRST (N-4)
            hz0 = urgent_mine[0].get("hazard") or "other"
            notice0 = emergency_notice(hz0, lang) if hz0 != "other" else t("emergency_steps", lang)
            # a person at risk (poisoning, medical): no emergency-maintenance line after the approved notice
            follow = notice0 + " " + (t("crisis_follow", lang, ref=urgent_mine[0]["id"]) if is_people_hazard(hz0)
                                      else follow)
        return done(TurnPlan(template=follow, functions=["F6", "F9"],
                             skip_model=True, consumed_by_draft=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("maintenance", "Follow-up after an emergency report.")))

    # 1b-resume. Sprint 8 C last round: the alert has settled (no emergency this turn, no active-incident follow-up
    # above): the card that was open before the alert comes back, unsent, with its next question
    if draft and draft.get("suspended") and gate.urgency != "emergency" and not hazard and care != "distress" and \
            not _RETRACT.search(msg):  # a retraction is acknowledged first (1b-clear); the card comes back next turn
        back0 = {k: v for k, v in draft.items() if k not in ("suspended", "stale")}
        save(back0["kind"], back0)
        answers_card = bool(extract_entry(msg) or und.entry_value(msg) or is_bare_yes(msg) or is_bare_no(msg) or
                            extract_location(msg) or extract_contact_pref(msg) or (back0["kind"] == "tour_request" and (
                                extract_days(msg) or extract_time_of_day(msg))))
        if answers_card:
            # "yes you can enter": the answer goes onto the resumed card (steps below); the reply says it is back
            draft = back0
            locals_lead["resume"] = t("resume_card_note", lang, what=WHAT[back0["kind"]][lang]) + " "
        else:
            ask0, chips0 = _next_step(back0, lang)
            return done(TurnPlan(template=t("resume_after_alert", lang, what=WHAT[back0["kind"]][lang], ask=ask0),
                                 functions=[KIND_FN[back0["kind"]]], chips=chips0, skip_model=True,
                                 consumed_by_draft=True, action=_proposed(back0["kind"], back0, lang),
                                 workflow=_sel(KIND_WF[back0["kind"]], "Alert settled: the earlier card is back.")))
    # 1b'. Distress that isn't a clear emergency: no forms; the care line (988) is added above the reply.
    if care == "distress" and not draft:
        return done(TurnPlan(template=t("distress_ack", lang), functions=["F9"], skip_model=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Possible distress: care line, no form.")))
    # 1b''. A hazard named as a question / hypothetical / past event: the steps are shown calmly; no form, no alarm.
    if care == "info" and not draft and danger_rule != "R5p":  # R5p: a small event that already happened
        return done(TurnPlan(template=t("safety_info_ack", lang), functions=["F6"], skip_model=True,
                             chips=CHIPS["safety_info"][lang],
                             workflow=_sel("general_inquiry", "Safety question (no active danger reported).")))

    # 1b-clear. Sprint 7 fix round (with Agent A): "never mind, false alarm, it was a candle" right after an urgent note
    # is the safety retraction the safety layer cleared. Acknowledge it and continue; it never cancels or changes a
    # request sent earlier, and the urgent note stays in the staff queue for a person to close.
    if gate.urgency != "emergency" and _RETRACT.search(msg) and any(
            r.get("status") == "urgent_queued" for r in mine) and not und.requests_human(msg):
        return done(TurnPlan(template=t("all_clear_ack", lang), functions=["F9"], skip_model=True,
                             consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Safety retraction acknowledged; nothing else changed.")))
    # 1b-qf. Sprint 8 (D): the answer to the quick-fix tips offered last turn. Every safety step above runs first;
    # a safety signal this turn ends the flow (quickfix.follow_up). "Fixed" closes it with no record. "No", "not sure"
    # or "just send maintenance" continue as the repair request with the ORIGINAL issue, word for word (from the
    # conversation history, never from planner memory), plus whole clauses that add a room / entry / visit time. An
    # unclear short answer is asked once. A side question is answered normally and the offer is kept (at most 2 turns);
    # a NEW problem gets its own card and the tips' issue is kept on it as the next request (never dropped).
    if qf_pending and is_resident and verified and not draft:
        qstep, qkeep = quickfix.follow_up(qf_pending, msg, risk)
        if (uq := quickfix.unsafe_question(msg)) and not unsafe_diy_kind(msg):
            locals_lead["diy"] = t(f"quickfix_unsafe_{uq}", lang) + " "
        if qkeep:
            mem[quickfix.MEM_KEY] = qkeep
        issue0 = quickfix.issue_from_recent(recent, qstep.entry_id) if qstep.entry_id else None
        if qstep.action == "close_resolved":
            return done(TurnPlan(template=t("quickfix_resolved", lang), functions=["F6"], skip_model=True,
                                 consumed_by_draft=True, chips=CHIPS["resident_next"][lang],
                                 workflow=_sel("maintenance", "Quick-fix tips fixed it: no repair request.")))
        if qstep.action == "ask_again":
            return done(TurnPlan(template=t("quickfix_ask_again", lang), functions=["F6"], skip_model=True,
                                 consumed_by_draft=True, chips=CHIPS["quickfix"][lang],
                                 workflow=_sel("maintenance", "Quick-fix: asked once whether it is fixed.")))
        if qstep.action == "other":
            # not an answer: a side question (answered below, the tips question stays open) or a NEW problem (if step
            # 8 opens a card for it, the tips' issue is queued on that card and the offer ends; never dropped)
            qf_queue = issue0 if quickfix.match_entry(msg) != qstep.entry_id else None
            qf_side["on"] = bool(qkeep)
        if qstep.action == "intake":
            msg = utt.normalize(quickfix.intake_message(issue0, msg))
            qf_intake = True
        if (qstep.action == "intake" or qf_queue) and resident is not None:
            # the context of a "no" turn was built for "no": add the on-file maintenance fields a direct request gets
            # (entry window, open requests, staff-noted contact clause), from this verified resident only
            have = {f.name for f in ctx.fields}
            # (" - maintenance request" only steers the topic gate of the context builder to the repair fields)
            extra = [f for f in build_resident_context(resident, f"{issue0 or msg} - maintenance request",
                                                       persona_id or "").fields
                     if f.name in ("preferred_entry_window", "open_maintenance_requests",
                                   "staff_noted_contact_preference") and f.name not in have]
            if extra:
                ctx = ctx.model_copy(update={"fields": [*ctx.fields, *extra]})
    # 1c. Questions about something already sent: answer plainly, never start a new draft.
    sent = [r for r in mine if r.get("status") != "urgent_queued"]
    if not is_resident and gate.urgency != "emergency" and (says_resident(msg) or (
            gate.intent == "maintenance" and (is_issue_description(msg) or _things_in(msg)))):
        mem["guest_repair"] = True  # flag only: a visitor who says they live here / reports a repair
    if not verified and gate.urgency != "emergency" and claims_account_access(msg):
        # j-safe-impersonation: a name typed in chat unlocks nothing; never a tour card from it
        if draft and not draft.get("declined") and draft["kind"] == "tour_request" and store and not draft.get(
                "fields", {}).get("days"):
            store.clear_draft(session_id, pkey)
            touched["draft"] = True
        mem["boundary_said"] = mem.get("boundary_said", 0) + 1  # Sprint 9: the full refusal once, then shorter
        return done(TurnPlan(template=t("account_boundary" if mem["boundary_said"] == 1 else "account_boundary_again",
                                        lang), functions=["F3"], skip_model=True,
                             consumed_by_draft=True,
                             chips=["Send a note to the office" if lang == "en" else "Enviar nota a la oficina"],
                             workflow=_sel("general_inquiry", "Account details asked for without that account "
                                                              "signed in: nothing shared.")))
    if is_resident and not_account_holder(msg) and gate.urgency != "emergency":
        if draft and store:  # a card built on that account is discarded (not parked: it can't be restored or shown)
            store.clear_draft(session_id, pkey)
            touched["draft"] = True
        return done(TurnPlan(template=t("other_person", lang), functions=["F3"], skip_model=True,
                             chips=CHIPS["prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Person says they are not the account holder.")))
    if gate.urgency != "emergency" and (asks_about_other_resident(msg) or (
            mem.get("other_resident") and re.search(r"\b(?:him|her|he|she|his|them|their|roommate|live with)\b", msg,
                                                    re.I) and not is_issue_description(msg))):
        if mem.get("other_resident") and _CHECK_ON.search(msg):
            # Sprint 9 (j-safe-neighbor-info): "can someone from the office check on her?" is a request for the office,
            # not another request for her details: a note, with nothing about her shared
            return handoff_plan("welfare_note", "Asked the office to check on another resident (nothing shared).",
                                topic="Asked the office to check on a neighbour")
        again = bool(mem.get("other_resident") or mem.get("boundary_said"))  # one full refusal per conversation
        mem["other_resident"] = True  # R-4: a clear boundary; never a repair card or an office-number answer
        return done(TurnPlan(template=t("other_resident_again" if again else "other_resident", lang), functions=["F3"],
                             skip_model=True,
                             consumed_by_draft=True,
                             chips=["Send a note to the office" if lang == "en" else "Enviar nota a la oficina"],
                             workflow=_sel("general_inquiry", "Asked about another resident: nothing shared.")))
    own_words = " ".join(x for x in re.split(r"(?<=[.!?])\s+|\n+|\s(?=>)", msg)
                         if x.strip() and not looks_like_injection(x) and not x.strip().startswith(">"))
    if looks_like_injection(msg) and not draft and gate.urgency != "emergency" and not (
            own_words and (gate.intent == "maintenance" or is_issue_description(own_words))):
        return done(TurnPlan(template=t("injection_note", lang), functions=["F3"], skip_model=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Instructions inside the message: treated as text.")))
    injected = False
    if looks_like_injection(msg) and own_words.strip() and gate.urgency != "emergency":
        # E-8: plan on the person's own words only ("my bathroom fan stopped working"), never on the injected part
        # ("mark all my requests resolved" is not a status lookup)
        msg, injected = own_words.strip(), True
        locals_lead["inj"] = t("injection_dropped", lang)
    if re.fullmatch(r"\W*(?:(?:my|mi) (?:number|phone|cell|email|n[uú]mero|tel[eé]fono|correo)(?: is| es)?\W*)?"
                    r"\[(?:phone|email) redacted\]\W*(?:\w+\W*){0,4}", msg, re.I) and gate.urgency != "emergency":
        return done(TurnPlan(template=t("contact_only", lang), functions=["F2"], skip_model=True,
                             consumed_by_draft=True, action=_proposed(draft["kind"], draft, lang)
                             if draft and not draft.get("declined") else None,
                             workflow=_sel("general_inquiry", "Contact detail typed in chat: not stored.")))
    if is_lockout(msg) and gate.urgency != "emergency" and not (draft and draft["kind"] == "staff_handoff"):
        rec = synthesize_handoff(gate, ctx, "other", "maintenance", "Resident locked out (after-hours line advised)")
        return done(TurnPlan(template=t("lockout", lang), functions=["F6", "F9"], skip_model=True,
                             force_handoff=True, handoff=rec.model_copy(update={"priority": "high"}),
                             chips=["Leave a note for the office" if lang == "en"
                                    else "Dejar una nota para la oficina"],
                             workflow=_sel("maintenance", "Lockout: after-hours line, no repair form.")))
    def after_send_text(r0: dict[str, Any]) -> str:
        """D-9: what was saved, its reference, who follows up; nobody notified; a tour is not a booking."""
        team = TEAM_LABEL.get(r0.get("team") or "", r0.get("team") or "the team")
        team_es = _TEAM_ES.get(team.lower(), team.lower())
        team_txt = (f"the {team.lower()} team" if lang == "en" else f"el equipo de {team_es}") \
            if r0.get("team") else ("the team" if lang == "en" else "el equipo")
        if r0["kind"] == "staff_handoff":  # Sprint 9: a note is for "the office" everywhere (card, chat, follow-up)
            team_txt = "the office" if lang == "en" else "la oficina"
        what_txt = ("Your " if lang == "en" else "Su ") + WHAT[r0["kind"]][lang]
        saved = _saved_summary(r0)
        if _ASKS_CONTACT.search(msg):  # Sprint 9: "will someone call me?" gets a direct no, not the whole record
            urgent_kind = r0["kind"] == "maintenance_request" or r0.get("priority") == "urgent"
            return t("after_send_contact_tour" if r0["kind"] == "tour_request" else "after_send_contact_urgent"
                     if urgent_kind else "after_send_contact", lang, ref=r0["id"],
                     what=WHAT[r0["kind"]][lang], team=team_txt if r0["kind"] != "tour_request" else (
                         "the leasing team" if lang == "en" else "el equipo de arrendamiento"))
        if r0["kind"] == "tour_request":
            return t("after_send_tour", lang, ref=r0["id"])
        if r0["kind"] == "staff_handoff" and r0.get("priority") != "urgent":
            return t("after_send_note", lang, what=what_txt, ref=r0["id"])  # Sprint 9: no urgency line on a status
        if saved:
            return t("after_send_saved", lang, what=what_txt, ref=r0["id"], team=team_txt, saved=saved)
        return t("after_send", lang, what=what_txt, ref=r0["id"], team=team_txt)

    if asks_saved_contact(msg) and gate.urgency != "emergency":  # P-6: a direct no, then how follow-up works here
        live_card = draft if draft and not draft.get("declined") else None
        if live_card:
            save(live_card["kind"], live_card)
        route = "contact_route_account" if verified else (
            "contact_route_profile" if _ctx_value(ctx, "preferred_contact_channel") else "contact_followup_none")
        return done(TurnPlan(template=t("contact_not_saved", lang) + " " + t(route, lang), functions=["F2"],
                             skip_model=True, consumed_by_draft=True,
                             action=_proposed(live_card["kind"], live_card, lang) if live_card else None,
                             workflow=_sel("general_inquiry", "Asked whether a typed phone or email was saved.")))

    # 1b-normal-q. Sprint 8 C: after "I can't tell whether that's normal ... say 'report it'", a "yes" / "report it"
    # starts the repair request with the question the person asked as the problem (never "nothing waiting")
    if normal_q_offer and not draft and is_resident and verified and gate.urgency != "emergency" and not hazard and \
            (is_affirmative(msg) or _REPORT_IT.search(msg)) and recent and len(recent) >= 2 and \
            _is_normal_question(recent[-2], live_ok=True):
        msg = _normal_q_issue(utt.normalize(recent[-2]))
        qf_intake = True  # the existing "start the intake with this issue" switch (no tips, straight to the card)
    elif not draft and is_resident and verified and gate.urgency != "emergency" and not hazard and \
            _is_normal_question(msg, live_ok=True) and _live_symptom(msg):
        # "is it normal for the water heater to have a puddle under it?": a present fault of their own thing is a
        # repair: the intake starts (never an FAQ or policy answer)
        qf_intake = True
    # 1c-acts. Sprint 5.1 TYPED DIALOGUE ACTS (app/dialogue.py). Runs here: after the safety, identity, injection and
    # contact-privacy steps above (they always win), and BEFORE anything below that can change or replace the open card
    # (meta answers, the lost/frustrated recovery, step 2 consent/decline, routing in step 6, intake in steps 8-9).
    # Only ANSWER / CORRECTION / NEW_DETAIL change fields; a QUESTION is answered and the card stays, unchanged.
    live = draft if draft and not draft.get("declined") else None
    pending = (_missing(live["kind"], live) or [None])[0] if live else None
    # 1c-understand (Sprint 6, app/understanding.py + app/workflow_state.py). The message is understood ONCE here, in
    # one typed object (rules, plus the optional model pass the engine ran), and the open card's state machine says
    # which transition it causes. Every later step reads these instead of its own keyword check:
    #   wants_person (was is_staff_request), status_q (was is_status_request), chat_frustrated (was
    #   is_lost_or_frustrated_with_chat), act (classify_turn widened with paraphrased cancels / restores),
    #   tr / tr2 (consent: only an explicit confirmation proposes a save; a bare yes proposes "tap Send").
    # It runs after the safety, identity, injection and contact-privacy steps above (they always win).
    u = und.understand(msg, live, pending, recent, understanding_hint)
    queued_note: dict[str, Any] | None = None
    if u.segments and is_resident and verified and not live and gate.urgency != "emergency":
        # Sprint 7: two DIFFERENT workflows in one message ("my sink is leaking and can someone call me about my
        # renewal"). The repair card comes first; the request for a person is kept as a prepared note that opens
        # after the repair is sent or skipped. Neither is lost, and one card is on screen at a time.
        rep_c = [c for c, w in u.segments if w == "repair"]
        per_c = [c for c, w in u.segments if w == "person"]
        if rep_c and per_c:
            per_txt = redact(" ".join(per_c))[:200]
            team_q = "leasing" if re.search(r"\b(?:leas\w*|renew\w*|rent|contrato|renovaci\w*|arrend\w*)\b", per_txt,
                                            re.I) else "management"
            rec_q = synthesize_handoff(gate, ctx, "human_requested", team_q, "Asked for a person in the same message "
                                                                             "as a repair")
            queued_note = _handoff_draft(gate, rec_q, ctx, per_txt, lang, None, "Asked to be contacted", recent)
            queued_note["queued_topic"] = per_txt
            msg = " ".join(rep_c)
            flags -= {"explicit_human_request", "human_requested"}
            workflow = _sel("maintenance", "Repair first; the request for a person is queued as a note.")
            u = und.understand(msg, live, pending, recent, None)
    act = und.with_acts(u)
    tr = wf.apply(wf.derive(live, mine), u)
    meta_u["u"], meta_u["tr"] = u.summary(), tr.summary()
    wants_person = u.requests_human
    status_q = u.has(und.DialogueAct.CHECK_STATUS)
    if status_q and _new_request_ask(msg):
        status_q = False  # Sprint 8 C: "can I put in a request to fix the stove burner?" asks for a NEW repair
    if u.frustration_target == "assistant" or u.confused:
        locals_lead["frus"] = ""  # marker only (never shown): this turn repeats frustration, so no verbatim repeat
    # Sprint 7: a problem schema (an object or the person's own space + a symptom: "a weird noise in my unit", "add
    # that the light inside is also out") is a repair even when the gate's keyword intent missed it
    problem_shape = bool(is_resident and not draft and u.utterance is not None and (u.utterance.problem or (
        u.utterance.objects and re.match(r"^\W*(?:(?:and|also|oh and|plus|y)\W+)*(?:add|include|agrega|a[ñn]ade)\b",
                                         msg, re.I))) and not u.utterance.asks and not wants_person and not status_q and
                         not match_faq(msg)) or (qf_intake and is_resident and not draft)  # Sprint 8 (D)
    chat_frustrated = und.frustration(msg) == "assistant"
    kinds = question_kinds(msg) + (["phone"] if is_phone_question(msg) else [])
    # Sprint 7 fix round: a short answer to the card's own question ("guest bathroom" to "which room?") is the answer,
    # never an FAQ about guests
    slot_answer = bool(live and live["kind"] == "maintenance_request" and utt.room_in(msg) and len(msg.split()) <= 4
                       and "?" not in msg and not (u.utterance is not None and u.utterance.asks))
    if slot_answer:
        kinds = []
    if u.question_topic == "history" and "history" not in kinds:
        kinds.append("history")  # Sprint 6 fix round: "did someone already look at this?" with or without a card
    if u.utterance is not None and u.utterance.asks_timing and "timing" not in kinds and live and \
            live["kind"] == "maintenance_request":
        kinds.append("timing")  # Sprint 7: "how long will it take" while the entry question waits: answered first
    sent_wo_now = [r for r in sent if r["kind"] == "maintenance_request"]
    if u.report_possible_emergency and gate.urgency != "emergency":
        # pass-through only (Sprint 6): the safety layer (2b) already decided and nothing here lowers it; the engine
        # adds a staff-review recommendation (chat_engine step 9) when safety found nothing
        log.info("understanding: possible emergency flagged for the safety layer (no message text logged)")

    def apply_answer(card: dict[str, Any]) -> None:
        if not act.has(Act.ANSWER) or not act.slot:
            return
        value = act.value
        if value == "same_as_before":  # "same as before": the entry permission given for the last request
            value = next((f.get("value") for r in sent_wo_now for f in r.get("fields", [])
                          if f.get("key") == "entry" and f.get("value")), None)
        elif value == "flexible":
            value = _FLEXIBLE[act.slot][lang]
        if value:
            _set(card, act.slot, _tr(value, lang), "you_said")
        for k, v in act.extra.items():
            if not card.get("fields", {}).get(k, {}).get("value"):
                _set(card, k, _tr(v, lang), "you_said")

    def card_reply(card: dict[str, Any], lead: str, reason: str, chips: list[str] | None = None,
                   fns: list[FunctionId] | None = None) -> TurnPlan:
        step, step_chips = _next_step(card, lang)
        # Sprint 9: after a second side question in a row the same step isn't asked again (the card still shows it)
        repeat_step = bool(lead) and card.get("last_side_step") == step
        card["last_side_step"] = step if lead else None
        save(card["kind"], card)
        if repeat_step:  # the step itself is not asked again, but there is still a gentle way forward
            lead = f"{lead} {t('side_resume', lang, what=WHAT[card['kind']][lang])}"
        return done(TurnPlan(template=lead if repeat_step else f"{lead} {step}".strip(),
                             functions=fns or [KIND_FN[card["kind"]]],
                             action=_proposed(card["kind"], card, lang), chips=chips if chips is not None
                             else step_chips, skip_model=True, consumed_by_draft=True,
                             workflow=_sel(KIND_WF[card["kind"]], reason)))

    def history_text(card: dict[str, Any] | None) -> str:
        """Earlier repairs about the same thing: the verified resident's own history and this chat's saved requests.
        Only reference, subject, status and date (the same allowlist as the status list). Never someone else's."""
        if not (is_resident and verified):
            return t("q_history_unverified", lang)
        about = " ".join(x for x in ((card or {}).get("fields", {}).get("issue", {}).get("value"), msg) if x)
        if not _things_in(about) and (wo_h := next((r for r in sent if r["kind"] == "maintenance_request"), None)):
            about = f"{about} {wo_h.get('title') or ''} {wo_h.get('summary') or ''}"  # "this" = the request just sent
        things = _things_in(about) - {"drain"} or _things_in(about)
        items = []
        # Sprint 6 final (judge P1): "what's the history on my place" names nothing: list the resident's own repair
        # history (same allowlist), never "nothing found" while requests exist
        everything = not things
        if resident:
            for i in reversed(resident.interactions):
                if i.category == "maintenance" and (everything or _things_in(i.subject) & things):
                    subj = sanitize_field(i.subject, 80) or "Maintenance request"
                    when = i.timestamp.strftime("%Y-%m-%d") if i.timestamp else ""
                    items.append(f"{i.interaction_id} \"{subj}\" ({i.status}{', ' + when if when else ''})")
        for r in sent:
            if r["kind"] == "maintenance_request" and (everything or things & _things_in(r.get("title") or "")):
                items.append(f"{r['id']} \"{r.get('title')}\" ({r.get('status_label', 'Submitted')})")
        if not items:
            return t("q_history_none_all" if everything else "q_history_none", lang)
        key = "q_history_all" if everything else ("q_history_card" if card else "q_history")
        return t(key, lang, items="; ".join(items[:4]))

    def answer_text(q: str, card: dict[str, Any] | None) -> str | None:
        """An honest answer to a side question, or None when a later step owns it."""
        what = WHAT[card["kind"]][lang] if card else ""
        if q == "who_sees":  # N-4: the neighbour line only when neighbours were mentioned
            return t("q_who_sees" if mentions_neighbor(msg) else "q_who_sees_plain", lang)
        if q == "confirm_visit":
            return t("q_no_visit", lang)
        if q == "count":
            listed = [f"{WHAT[r['kind']][lang]} {r['id']}" for r in sent[:6]]
            out = t("q_count", lang, n=str(len(listed)), items="; ".join(listed)) if listed else t("q_count_none", lang)
            return out + (t("q_count_open", lang) if card else "")
        if q == "what_send":
            return t("q_what_send", lang, what=what) if card else t("q_what_send_none", lang)
        if q == "cost":
            # Sprint 7: a prospect asking what it costs to LIVE here is a price question (step 11's honest price line
            # and the leasing next step), not "does pressing Send cost anything"
            return t("q_cost", lang) if (is_resident or card) else None
        if q == "priority":
            if card:
                note = card.get("fields", {}).get("priority_note", {}).get("value")
                return t("q_priority", lang, flag=t("q_priority_flag", lang, note=note) if note else "")
            return t("q_priority_sent", lang, ref=sent[0]["id"]) if sent else None
        if q == "timing" and card and is_resident:  # prospects: the contact-route answer (1c-route) owns this
            return t("q_timing", lang)
        if q == "phone" or (q is None and is_phone_question(msg) and card):
            return t("q_phone", lang)
        if q == "gate_code" and (card or is_resident):
            return t("q_gate_code", lang)
        if q == "name":
            return t("q_name", lang)
        if q == "history":  # Sprint 6: "has anyone fixed this before?" from the person's own record only
            return history_text(card)
        if q == "budget":
            val = (card or {}).get("fields", {}).get("budget", {}).get("value") or (mem.get("lead") or {}).get("budget")
            return t("q_budget", lang, value=val) if val else t("q_budget_none", lang)
        if q == "card_status" and card:
            if card["kind"] == "tour_request" and "area" in _missing("tour_request", card) and (
                    pu := _unknown_place(msg)):  # "i meant kalamazoo": say which areas the demo has (holdout)
                return t("unknown_city", lang, area=pu)
            if card["kind"] == "staff_handoff" and card.get("parked"):
                return t("q_parked", lang, what=WHAT[card["parked"]["kind"]][lang])
            missing = _missing(card["kind"], card)
            return t("next_step_missing", lang, what=what, label=LABEL[missing[0]][lang].lower()) if missing else ""
        if q == "renewal" and card and card["kind"] != "staff_handoff":
            return t("q_renewal_card", lang, what=what)
        if q in ("policy", "faq") and card and card["kind"] != "staff_handoff":
            faq = match_faq(msg)
            unanswered = [tp.label for tp in faq if tp.status != "approved"]
            if unanswered:  # P-4: remembered (topic labels only) for a later leasing note
                mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), *unanswered]))
            if faq:
                return _faq_text(faq, lang)
            return t("policy_unknown", lang, topic=_tr_topic(policy_topic(msg) or "that", lang))
        return None

    if live and tr.event is wf.Event.SWITCH_TOPIC and gate.urgency != "emergency" and not wants_person:
        # Sprint 6 (P1 "Forget it, what are the pool hours?"): a cancel word followed by a new question answers the
        # question and keeps the card on screen, NOT sent; it is never discarded on an ambiguous "forget it".
        faq_s = match_faq(msg)
        if unanswered_s := [tp.label for tp in faq_s if tp.status != "approved"]:
            mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), *unanswered_s]))
        ans_s = [a for a in (answer_text(q, live) for q in kinds or ([act.question] if act.question else [])) if a]
        text_s = " ".join(dict.fromkeys(ans_s)) or (_faq_text(faq_s, lang) if faq_s else t("q_unknown_card", lang))
        save(live["kind"], live)
        return done(TurnPlan(template=f"{text_s} {t('switch_keep', lang, what=WHAT[live['kind']][lang])}",
                             functions=[KIND_FN[live["kind"]]] + (["F4"] if faq_s else []), skip_model=True,
                             action=_proposed(live["kind"], live, lang), consumed_by_draft=True,
                             workflow=_sel(KIND_WF[live["kind"]], "Topic switch: question answered; the card is kept, "
                                                                  "not sent.")))

    # 1c-target (Sprint 7 fix round). A cancel that NAMES one of two queued workflows cancels only that one: "cancel the
    # callback" drops the queued note and keeps the repair; "no, I meant keep the faucet" after the note was opened
    # brings the repair back. The target is resolved against what is on the card (its issue words) and the queued
    # item (a call / note / the office / its own topic words), never by position.
    wo_first = next((r for r in reversed(sent) if r["kind"] == "maintenance_request"), None)
    if gate.urgency != "emergency" and wo_first and _NO_NEW_TICKET.search(msg) and not (
            live and live["kind"] == "staff_handoff"):
        # Sprint 7 last round: "i said dont open another ticket, the first one is not done": no field changes; the
        # new card (if any) is dropped and a follow-up note cites the EARLIER request
        if live and store:
            store.clear_draft(session_id, pkey)
            touched["draft"] = True
            draft = live = None
        return handoff_plan("followup_existing", f"Follow-up on {wo_first['id']}; no second request.",
                            wid="maintenance", topic=f"Follow-up on {wo_first['id']}", ref=wo_first["id"],
                            title=wo_first.get("title") or WHAT["maintenance_request"][lang])
    if live and gate.urgency != "emergency":
        rep_card = live if live["kind"] == "maintenance_request" else live.get("restorable")
        target = _cancel_target(msg, _fval(rep_card, "issue")) if rep_card and (
            live.get("queued_note") or live["kind"] == "staff_handoff") else None
        if live["kind"] == "maintenance_request" and live.get("queued_note") and target == "call":
            live.pop("queued_note", None)
            return card_reply(live, t("queued_dropped", lang, what=WHAT["maintenance_request"][lang]),
                              "Cancel named the queued callback: only that is dropped.")
        if live["kind"] == "maintenance_request" and (qn_t := live.get("queued_note")) and target == "repair" and \
                store:
            # Sprint 7 last round: "cancel the oven repair, I just want the call": the repair is set aside
            # (restorable) and the call note opens now
            note_t = {**qn_t, "stale": False, "lang": lang,
                      "restorable": {k: v for k, v in live.items() if k not in ("queued_note", "declined")}}
            save("staff_handoff", note_t)
            return done(TurnPlan(template=t("repair_dropped_call_kept", lang, topic=qn_t.get("queued_topic") or ""),
                                 functions=["F9"], skip_model=True, consumed_by_draft=True,
                                 action=_proposed("staff_handoff", note_t, lang),
                                 workflow=_sel("human_handoff", "Cancel named the repair: the call note opens.")))
        if live["kind"] == "staff_handoff" and rep_card and target == "call":
            back_r = {k: v for k, v in rep_card.items() if k not in ("declined", "queued_note")}
            save("maintenance_request", back_r)
            draft = back_r
            return card_reply(back_r, t("queued_dropped", lang, what=WHAT["maintenance_request"][lang]),
                              "The repair the person meant to keep is back; the note is dropped.")
    # 1c-edit (Sprint 6 fix round). Field-targeted edits to the open card, a request to split or drop one of its
    # problems, and "don't send it yet". Runs after the safety / identity / privacy steps and the topic switch, and
    # BEFORE the older per-step correction code below, so a correction that names (or implies) a field REPLACES that
    # field ("call me instead of email" -> Contact preference; "let me rephrase: X" -> What's wrong), is never appended
    # to "What's wrong", and the reply names the change. After Send, the same edit becomes a change note citing the
    # sent reference (staff edit sent requests).
    if gate.urgency != "emergency" and not wants_person:
        if live and tr.event is wf.Event.HOLD:
            save(live["kind"], live)
            step_h, chips_h = _next_step(live, lang) if _missing(live["kind"], live) else ("", [])
            return done(TurnPlan(template=f"{t('hold_kept', lang, what=WHAT[live['kind']][lang])} {step_h}".strip(),
                                 functions=[KIND_FN[live["kind"]]], action=_proposed(live["kind"], live, lang),
                                 chips=chips_h, skip_model=True, consumed_by_draft=True,
                                 workflow=_sel(KIND_WF[live["kind"]], "Hold: the card stays, unsent.")))
        # a queued card nobody has touched yet: "actually, call me before entering" is about the request just sent (a
        # change note below), not the next card
        to_sent = bool(live and live.get("stale") and sent and u.edits)
        if live and live["kind"] == "maintenance_request" and tr.event in (wf.Event.DROP_ISSUE, wf.Event.SPLIT_ISSUE):
            plan_e = _drop_or_split(live, u, lang)
            if plan_e is not None:
                lead_e, why = plan_e
                return card_reply(live, lead_e, why)
        if live and u.edits and not to_sent and not act.has(Act.CANCEL) and not (
                live["kind"] == "tour_request" and act.has(Act.META)):
            return card_reply(live, _apply_edits(live, u.edits, msg, lang), "Field-targeted correction: the named "
                                                                              "field is replaced, nothing appended.")
        chg_ref = re.search(r"\bDEMO-(?:WO|TOUR)-\d+\b", str((live or {}).get("topic") or "")) if live and \
            live["kind"] == "staff_handoff" else None
        rec_c = next((r for r in sent if chg_ref and r["id"] == chg_ref.group(0)), None)
        if rec_c is not None and not is_explicit_send(msg) and not act.has(Act.CANCEL):
            # Sprint 7 fix round: a further correction while the change note is open ("it's the hall closet
            # actually") is resolved against the SENT request's fields and added to the same note
            card_c = {"kind": rec_c["kind"], "fields": {f.get("key"): {"value": f.get("value")}
                                                        for f in rec_c.get("fields", []) if f.get("key")}}
            edits_c = und.field_edits(msg, card_c, rec_c["kind"])
            if edits_c:
                chg_txt = "; ".join(f"{LABEL[c.field][lang]} → {_edit_value(c, lang)}" for c in edits_c)
                old_c = live["fields"].get("message", {}).get("value", "")
                _set(live, "message", (f"{old_c} | {chg_txt}" if old_c else chg_txt)[:480], "you_said")
                save("staff_handoff", live)
                return done(TurnPlan(template=t("note_updated", lang) + " " + t("change_requested", lang,
                                                                               detail=chg_txt).strip(),
                                     functions=["F9"], skip_model=True, consumed_by_draft=True,
                                     action=_proposed("staff_handoff", live, lang),
                                     workflow=_sel("human_handoff", "Another change added to the open change note.")))
        ut_n = u.utterance
        note_text = " ".join(str((v or {}).get("value") or "") for v in (live or {}).get("fields", {}).values())
        about_note = bool(live and live["kind"] == "staff_handoff" and ut_n is not None and not ut_n.asks and
                          not (ut_n.problem and ut_n.objects - utt.things(note_text)) and not is_explicit_send(msg) and
                          not is_affirmative(msg) and not act.has(Act.CANCEL) and not wants_person and
                          not ut_n.names_tour and not extract_days(msg) and not extract_time_of_day(msg) and
                          (re.search(r"\b(?:don'?t|do not|dont) want (?:to (?:start|open|make|file) )?(?:a )?new "
                                     r"(?:request|ticket|one)\b|\bthe (?:old|first|last|other) one\b|"
                                     r"\bno quiero (?:una )?"
                                     r"nueva\b", msg, re.I) or ut_n.addition))
        if live and live["kind"] == "staff_handoff" and len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", msg)) >= 3 and (re.search(
                r"^\W*(?:(?:please|pls|ok|and|also|no|not just \S+)\W+)*(?:add|include|mention|put|write|say|tell them)"
                r"\b|\b(?:to|in|on) the note\b", msg, re.I) or about_note) and not u.edits:
            # Sprint 7 fix round: "no I don't want a new request, the old one wasn't fixed" is more for the open note
            # (it cites the earlier request), never a new repair card
            # "add that i'm interested in the 2 bed, moving dec 1", "write that someone parks in my spot": more detail
            # for the note that is open (never a new tour or repair card)
            old_m = live["fields"].get("message", {}).get("value", "")
            add_m = redact(re.sub(r"^\W*(?:(?:please|pls|ok|and|also|no|not just \S+)\W+)*(?:add|include|mention|put|"
                                  r"write|say|tell them)\s+(?:this |that |it )?(?:to|in|on)?\s*(?:the note)?\s*:?\s*",
                                  "", msg, flags=re.I) or msg)
            _set(live, "message", (f"{old_m} | {add_m}" if old_m else add_m)[:480], "you_said")
            save("staff_handoff", live)
            return done(TurnPlan(template=t("note_updated", lang), functions=["F9"], skip_model=True,
                                 consumed_by_draft=True, action=_proposed("staff_handoff", live, lang),
                                 workflow=_sel("human_handoff", "More detail added to the open note.")))
        if live and live["kind"] == "tour_request" and (pets_t := extract_pets(msg)) and re.search(
                r"\b(?:make sure|let them know|tell them|know|note|add|mention|fyi|btw|heads up)\b", msg, re.I):
            _set(live, "pets", pets_t, "you_said")  # "make sure they know i have a dog": on the card, not a question
            return card_reply(live, t("note_added", lang, value=pets_t), "Pet noted on the tour card.")
        if u.accepts_offer and (offer := (memory or {}).get("offer")) and (
                not live or (offer == "leasing_note" and live["kind"] == "tour_request")):
            # Sprint 6 fix round: "ok sure" / "yeah send them my questions" accepts what the last reply offered. It
            # opens that card (a tour request, a note for leasing); saving still needs Send or an explicit "send it".
            if offer == "leasing_note":
                if mem.get("questions"):
                    return handoff_plan("questions_note", "Accepted the offered note with their questions.",
                                        category="leasing_follow_up", team="leasing",
                                        topic="Questions for the leasing team",
                                        value=_questions_text(mem["questions"], lang))
                return handoff_plan("handoff_offer", "Accepted the offered note for the leasing team.",
                                    category="leasing_follow_up", team="leasing",
                                    topic="Questions for the leasing team")
            if offer == "tour" and not is_resident:
                msg = "I'd like to request a tour"  # replayed as the request that was offered (step 9 starts the card)
        # Sprint 7 last round: a change targets the ORIGINAL request, never the latest change note
        rec_e = next((r for r in sent if r["kind"] in ("maintenance_request", "tour_request")), None)
        sent_txt_e = (f"{rec_e.get('title') or ''} {rec_e.get('summary') or ''} " + " ".join(
            str(f.get("value") or "") for f in rec_e.get("fields", []))) if rec_e else ""
        if rec_e and rec_e["kind"] == "maintenance_request" and not live and _WAITING.search(msg):
            # Sprint 7 final round: "been waiting since monday for someone to fix my sink" right after Send is a
            # follow-up on THAT request, never a change or a new request
            return handoff_plan("followup_existing", f"Follow-up on {rec_e['id']}; no second request.",
                                wid="maintenance", topic=f"Follow-up on {rec_e['id']}", ref=rec_e["id"],
                                title=rec_e.get("title") or WHAT["maintenance_request"][lang])
        # Sprint 7: an addition is recognised by its STRUCTURE (an addition marker, or a descriptive statement whose
        # problem objects are already on the sent request; landmarks like "next to the fridge" are not new problems)
        adds_e = bool(_ADD_DETAIL.match(msg)) or (rec_e is not None and utt.adds_to(u.utterance or utt.analyze(msg),
                                                                                   sent_txt_e))
        if (not live or to_sent) and rec_e and rec_e["kind"] == "maintenance_request" and adds_e and \
                len(msg.split()) <= 30 and not act.has(Act.QUESTION) and "?" not in msg and not u.edits and \
                not wants_person:
            # Sprint 6 final (verifier P1): "oh, also it's the upper cabinet by the fridge" right after Send is more
            # detail for THAT request (a change note citing it), never a second request for the same repair. A
            # different thing named ("also the bathroom fan is loud") is a new problem and goes on below.
            sent_things = _things_in(f"{rec_e.get('title') or ''} {rec_e.get('summary') or ''} " + " ".join(
                str(f.get("value") or "") for f in rec_e.get("fields", [])))
            new_things = _things_in(msg)
            sent_text = f"{rec_e.get('title') or ''} " + " ".join(str(f.get("value") or "") for f in rec_e.get(
                "fields", []) if f.get("key") in ("issue", "location"))
            shared = _content_words(msg) & _content_words(sent_text)
            if shared or new_things & sent_things or not (new_things or is_issue_description(msg)) or (
                    not _ADD_DETAIL.match(msg) and adds_e) or utt.adds_to(u.utterance or utt.analyze(msg), sent_txt_e):
                detail = redact(_ADD_DETAIL.sub("", msg, count=1).strip(" ,.;:-") or msg)[:200]
                ref_a = rec_e["id"]
                return handoff_plan("maint_change", f"More detail for {ref_a} after Send (staff add it).",
                                    topic=f"Change {ref_a}", ref=f"{WHAT['maintenance_request'][lang]} {ref_a}",
                                    extra=t("change_requested", lang, detail=f"{LABEL['notes'][lang]}: {detail}"))
        tour_r = next((r for r in sent if r["kind"] == "tour_request"), None)
        ut_t = u.utterance
        if not is_resident and not live and tour_r and ut_t is not None and not ut_t.asks and \
                len(msg.split()) <= 30 and not (extract_days(msg) or extract_time_of_day(msg) or community_in(msg) or
                                                city_in(msg) or und.ordinal_date(msg)) and \
                not is_explicit_send(msg) and not is_affirmative(msg) and not is_accommodation(msg) and \
                "fair_housing_or_legal" not in flags and (
                    ut_t.addition or ut_t.correction or extract_beds(msg) or extract_pets(msg) or re.search(
                        r"\b(?:we|i)(?:'d| would)? (?:need|want|have|like|prefer|will|are)\b|\bnote\b|\bcoming too\b|"
                        r"\bwill (?:come|be coming|join)\b|\b(?:somos|tenemos|necesito|necesitamos|queremos|"
                        r"prefiero)\b",
                        msg, re.I)):
            # Sprint 7: more detail or a correction for the tour request already saved ("oh also my roommate will
            # come", "oops I need 3 bedrooms not 2"): a change note citing that tour, never a generic welcome, a
            # policy answer that drops the detail, or a second tour
            detail_t = redact(_ADD_DETAIL.sub("", msg, count=1).strip(" ,.;:-") or msg)[:200]
            ref_t = tour_r["id"]
            return handoff_plan("maint_change", f"More detail for {ref_t} after Send (leasing adds it).",
                                topic=f"Change {ref_t}", team="leasing", ref=f"{WHAT['tour_request'][lang]} {ref_t}",
                                extra=t("change_requested", lang, detail=detail_t))
        new_problem_e = bool(u.utterance.problem and (u.utterance.objects - utt.things(sent_txt_e)) and
                             not u.utterance.correction) if u.utterance is not None else is_issue_description(msg)
        if (not live or to_sent) and rec_e and not new_problem_e and len(msg.split()) <= 25:
            card_e = {"kind": rec_e["kind"], "fields": {f.get("key"): {"value": f.get("value")}
                                                        for f in rec_e.get("fields", []) if f.get("key")}}
            edits_e = und.field_edits(msg, card_e, rec_e["kind"])
            if not edits_e and rec_e["kind"] == "maintenance_request" and (
                    loc_e := extract_location_change(msg, _fval(card_e, "location"))):
                edits_e = [und.Correction(field="location", value=loc_e)]
            if edits_e:
                changes = "; ".join(f"{LABEL[c.field][lang]} → {_edit_value(c, lang)}" for c in edits_e)
                ref_e = rec_e["id"]
                return handoff_plan("maint_change", f"Change to {ref_e} after Send (staff handle it).",
                                    topic=f"Change {ref_e}",
                                    team="leasing" if rec_e["kind"] == "tour_request" else None,
                                    ref=f"{WHAT[rec_e['kind']][lang]} {ref_e}",
                                    extra=t("change_requested", lang, detail=changes))

    if gate.urgency != "emergency":
        # C-2: a stated budget is recorded (never answered as a price question, never quoted back as a price)
        budget = u.entities.budget if not is_resident else None
        if not is_resident:  # C-6: tour preferences said before any card exists are remembered (values, not text)
            said = {k: v for k, v in (("area", community_in(msg) or city_in(msg)), ("beds", extract_beds(msg)),
                                      ("pets", extract_pets(msg)), ("budget", budget)) if v}
            if said:
                mem["lead"] = {**(mem.get("lead") or {}), **said}
        if budget:
            if live and live["kind"] == "tour_request":
                _set(live, "budget", budget, "you_said")
        if live and live["kind"] == "staff_handoff" and (pk := live.get("parked")) and pk["kind"] == \
                "maintenance_request" and (fix := und.issue_rewrite(msg) or extract_issue_swap(msg)):
            # A-2: a correction to the repair parked inside the note goes to that repair, never into a new card
            _set(pk, "issue", fix[:200], "you_said")
            save("staff_handoff", live)
            return done(TurnPlan(template=t("issue_updated", lang, issue=fix) + " " + t(
                "q_parked", lang, what=WHAT["maintenance_request"][lang]), functions=["F7", "F9"], skip_model=True,
                consumed_by_draft=True, action=_proposed("staff_handoff", live, lang),
                workflow=_sel("human_handoff", "Correction applied to the repair parked in the note.")))
        if live and not u.saved_question:
            snapshot = repr(sorted((k, v.get("value")) for k, v in live.get("fields", {}).items()))
            pure_q = utt.ends_as_question(msg) and len(re.split(r"[.!;,]\s+", msg.strip())) == 1
            if act.has(Act.ANSWER) and not act.has(Act.CANCEL) and not pure_q and (
                    act.has(Act.QUESTION) or act.has(Act.META)
                                                                     or act.has(Act.NEW_ISSUE) or budget):
                apply_answer(live)  # A-2 / C-3: the answer in the same message is saved first
                save(live["kind"], live)
            said_place = community_in(msg) or city_in(msg)
            cur_place = live.get("fields", {}).get("area", {}).get("value") or ""
            if live["kind"] == "tour_request" and said_place and not cur_place.lower().startswith(said_place.lower()) \
                    and (act.has(Act.META) or act.has(Act.QUESTION) or re.search(r"\b(?:i said|i meant|not|no)\b", msg,
                                                                                  re.I)):
                _set(live, "area", said_place, "you_said")  # N-2: "no, I said Fernhill Apartments" updates the card
                save(live["kind"], live)
            changed_now = repr(sorted((k, v.get("value")) for k, v in live.get("fields", {}).items())) != snapshot
            sorry = t("meta_sorry" if changed_now else "meta_sorry_nochange", lang)  # N-2: "got it" only if changed
            answers = [a for a in (answer_text(q, live) for q in kinds or ([act.question] if act.question else []))
                       if a is not None]
            if act.question == "renewal" and live["kind"] != "staff_handoff" and mem.get("renewal_asked"):
                answers = []  # asked again (or tapped the chip): the renewal note is prepared below, the card parked
            if answers and not act.has(Act.CANCEL) and not act.has(Act.NEW_ISSUE):
                if act.question == "renewal":
                    mem["renewal_asked"] = True
                lead = (sorry + " " if act.has(Act.META) and act.has(Act.ANSWER) else "") + \
                    " ".join(a for a in dict.fromkeys(answers) if a)
                chips_q = [_RENEWAL_CHIP[lang]] if act.question == "renewal" else None
                if act.question == "card_status" and not lead.strip():
                    lead = t("next_step_ready", lang, what=WHAT[live["kind"]][lang])
                    return done(TurnPlan(template=lead, functions=[KIND_FN[live["kind"]]], skip_model=True,
                                         action=_proposed(live["kind"], live, lang), consumed_by_draft=True,
                                         workflow=_sel(KIND_WF[live["kind"]], "Asked whether the card is sent.")))
                if act.question == "card_status" and live["kind"] == "staff_handoff":
                    save("staff_handoff", live)
                    return done(TurnPlan(template=lead, functions=["F9"], skip_model=True, consumed_by_draft=True,
                                         action=_proposed("staff_handoff", live, lang),
                                         workflow=_sel("human_handoff", "Asked about the parked card.")))
                return card_reply(live, lead, f"Side question ({act.question or kinds[0]}) answered; the open card "
                                  "stays.",
                                  chips=chips_q)
            if act.has(Act.META) and not act.has(Act.CANCEL) and not act.has(Act.NEW_ISSUE) and not (
                    live["kind"] == "staff_handoff" and not is_resident and (extract_days(msg) or extract_time_of_day(
                        msg) or und.ordinal_date(msg))) and (
                    act.has(Act.ANSWER) or (not pending and not live.get("lost_ack"))):
                live["lost_ack"] = True
                return card_reply(live, sorry, "Answer plus 'I already told you': answer saved first.")
            if budget and live["kind"] == "tour_request" and not (extract_days(msg) or extract_time_of_day(msg)
                                                                   or community_in(msg) or city_in(msg)):
                noted_c = t("budget_noted", lang, value=budget[0].lower() + budget[1:] if lang == "en" else budget)
                return card_reply(live, noted_c + " " + t("budget_no_quote", lang), "Budget noted on the tour card.")
            if act.correction and act.correction[0] == "contact" and not appliance_in(msg) and not wants_person and \
                    not _LATER_SYMPTOM.search(msg) and len(msg.split()) <= 14:  # A-3: "change the contact pref to call"
                pref = _prefers(act.correction[1], lang) or act.correction[1]
                _set(live, "contact", pref, "you_said")
                return card_reply(live, t("contact_updated", lang, value=pref),
                                  "Contact preference changed on the card.")
            if live["kind"] == "maintenance_request" and (note := visit_note(msg)) and not act.has(Act.QUESTION) \
                    and not (is_issue_description(msg) and not re.search(r"\b(?:add|note|mention)\b", msg, re.I)):
                # W-12 / B-3: "add that there's a dog inside" is a note for the visit, not a pet-policy question
                prev = live.get("fields", {}).get("notes", {}).get("value")
                _set(live, "notes", (f"{prev}; {note}" if prev and note.lower() not in prev.lower() else
                                     prev or note)[:240], "you_said")
                if (e := extract_entry(msg)) and not live.get("fields", {}).get("entry"):
                    _set(live, "entry", _tr(e, lang), "you_said")
                return card_reply(live, t("note_added", lang, value=note), "A note for the visit added to the card.")
        else:
            answers = [a for a in (answer_text(q, None) for q in kinds) if a]
            if answers and (act.question in ("who_sees", "what_send", "cost", "gate_code", "name", "budget", "count",
                                             "history")
                            or (act.question == "confirm_visit" and not sent)) or (
                    act.question == "priority" and sent and not asks_for_priority(msg) and answers):
                return done(TurnPlan(template=" ".join(dict.fromkeys(answers)), functions=["F8"], skip_model=True,
                                     consumed_by_draft=True,
                                     chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                                     workflow=_sel("general_inquiry", f"Side question ({act.question}) answered.")))
            if budget and not (is_tour_request(msg) or extract_days(msg) or community_in(msg) or city_in(msg)
                               or extract_beds(msg) or extract_move_in(msg)):
                tail = t("next_leasing_note", lang) if mem.get("tour_pitched") else t("faq_offer_tour", lang)
                mem["tour_pitched"] = True
                price_line = _faq_text([tp for tp in match_faq(msg) if tp.status != "approved"], lang) \
                    if _QUESTIONISH_END.search(msg) else ""  # "anything under $1400?" also gets the honest price line
                noted = t("budget_noted", lang, value=budget[0].lower() + budget[1:] if lang == "en" else budget)
                if not price_line:
                    noted += " " + t("budget_no_quote", lang)  # Sprint 9: the no-quote line once, not twice
                return done(TurnPlan(template=(price_line + " " if price_line else "") + noted + " " + tail,
                                     functions=["F4"],
                                     skip_model=True, consumed_by_draft=True, chips=CHIPS["prospect_next"][lang],
                                     workflow=_sel("leasing", "Budget noted for the leasing team (no prices).")))
        if not is_resident and mem.get("questions") and accepts_question_note(msg):
            # C-7: "ok send those questions to the leasing team pls" accepts the offered note
            return handoff_plan("questions_note", "Prospect accepted the offered note with their questions.",
                                category="leasing_follow_up", team="leasing", topic="Questions for the leasing team",
                                value=_questions_text(mem["questions"], lang))
        if live and act.question == "renewal" and live["kind"] != "staff_handoff" and mem.get("renewal_asked") \
                and is_resident:
            # W-4: a second need while a card is open: the card is parked (restorable) inside the renewal note
            contact = _ctx_value(ctx, "preferred_contact_channel")
            suffix = (f" and noted that you prefer {contact}" if lang == "en"
                      else f" y anoté que prefiere {_ES_CHANNEL.get(contact.lower(), contact)}") if contact else ""
            return handoff_plan("renewal", "Renewal asked while another card was open.", wid="renewal",
                                contact=suffix, topic="Renewal question", team="leasing")
        typed_ref = re.search(r"\bDEMO-(?:WO|TOUR|TASK)-\d+\b", msg, re.I)
        if typed_ref and is_resident and verified and not (is_cancel_submitted(msg) or is_change_request(msg)) and \
                not (live and live["kind"] == "maintenance_request"):  # c20: "is DEMO-WO-1007 fixed": a status answer
            ref_t = typed_ref.group(0).upper()
            rec_t = next((r for r in mine if r["id"].upper() == ref_t), None) or (
                store.own_record(ref_t) if store and hasattr(store, "own_record") else None)
            if rec_t:
                return done(TurnPlan(template=after_send_text(rec_t), functions=["F8"], skip_model=True,
                                     consumed_by_draft=True, workflow=_sel("status_lookup", "Status of a typed "
                                                                                           "reference.")))
            items_t = status_items(store, resident, persona_id or "")
            return done(TurnPlan(template=t("ref_not_found", lang, ref=ref_t), functions=["F8"], skip_model=True,
                                 status_items=items_t, consumed_by_draft=True,
                                 workflow=_sel("status_lookup", "Typed reference not found in this chat.")))
        # A-6 / B-1 / C-5: a request that is already open (sent in this chat, or open on the record) gets a follow-up
        # note citing its reference, never a duplicate work order
        # Sprint 8 C fix round: a status QUESTION about an open item ("what's the status of my AC rattling request?")
        # is answered by the status step below, not turned into a follow-up note
        status_only = (status_q or is_status_request(msg)) and not asks_for_priority(msg) and not re.search(
            r"\burgent\b|\burgente\b", msg, re.I)
        no_card_issue = not (live and live["kind"] == "maintenance_request" and live.get("fields", {}).get("issue"))
        # Sprint 8 C fix round: an OPEN request this resident saved in an EARLIER session about the same thing gets a
        # follow-up note citing it, never a second record ("it's a different problem" still starts a new one)
        # Sprint 8 C last round: several problems in one message: the one about an open request is matched; the others
        # each start their own request (queued behind the follow-up note), never absorbed into it
        fu_parts = split_issues(msg) if no_card_issue else [msg]
        fu_part = msg
        other_open = None
        wb_hit = False
        if is_resident and verified and no_card_issue and not status_only and not _DIFFERENT.search(msg) and (
                is_issue_description(msg) or states_repeat(msg) or (u.utterance is not None and u.utterance.problem)):
            wb_open = [(i, i.subject) for i in (resident.interactions if resident else [])
                       if i.category == "maintenance" and i.status != "closed" and mh.is_repair_request(i.subject)]
            for part in fu_parts:
                if (other_open := _own_open_elsewhere(store, persona_id, sent, part)) is not None:
                    fu_part = part
                    break
                wb_item = _best_open(part, wb_open)
                if wb_item is not None and (mh.match_score(part, wb_item.subject) >= 3 or (
                        not mh.symptoms(part) and _STILL.search(part))):
                    # an OPEN workbook request: the same symptom, or "still not working" about the same thing. A
                    # generic "my AC is out again" is a new repair flagged as a repeat (Sprint 5.1 D-5)
                    fu_part, wb_hit = part, True
                    break
        about_open = is_resident and verified and no_card_issue and not status_only and (
            refers_to_existing(msg) or asks_for_priority(msg) or (states_repeat(msg) and _sent_match(sent, msg))
            or _repeat_of_open(resident, msg) or other_open is not None or wb_hit or bool(re.search(
                r"\bmark (?:my|the) [\w/ ]{1,25}? (?:request )?(?:as )?urgent\b", msg, re.I)))
        if about_open:
            if other_open is None and len(fu_parts) > 1:  # which part is about an open item
                fu_part = next((p for p in fu_parts if _sent_match(sent, p) or _repeat_of_open(resident, p)
                                or _history_match(resident, p, open_only=True)), msg)
            rec0 = _sent_match(sent, fu_part)
            hist0 = _repeat_of_open(resident, fu_part) or _history_match(resident, fu_part, open_only=True)
            open_items = [i for i in (resident.interactions if resident else [])
                          if i.category == "maintenance" and i.status != "closed"]
            # one choice over every open candidate: the best object + symptom match (a symptom-matched workbook item
            # beats an older saved request about another symptom of the same thing)
            pick = _best_open(fu_part, [(rec0, _rec_issue(rec0) if rec0 else ""),
                                        (other_open, _rec_issue(other_open) if other_open else ""),
                                        *[(i, i.subject) for i in open_items]])
            # Sprint 8 C: no fallback. A different room, fixture, pest or a specific new symptom is a NEW request
            # (match_score 0), never merged into an open one
            is_rec = isinstance(pick, dict)
            rec0, hist0 = (pick, None) if is_rec else (None, pick)
            ref = rec0["id"] if rec0 else (hist0.interaction_id if hist0 else None)
            if ref:
                # cite a saved request by what it is about, never by the resident's raw words; a workbook item by its
                # staff-written subject
                title = mh.request_label(_rec_issue(rec0), lang) if rec0 else (
                    sanitize_field(hist0.subject, 80) or "that request")
                fu_hist = mh.related_history(fu_part, resident=resident, persona_id=persona_id,
                                             records=store.records(persona_id=persona_id, kind="maintenance_request",
                                                                   limit=200) if store and persona_id else [])
                others = [p for p in fu_parts if p is not fu_part and p != fu_part]
                park = None
                if others:
                    park = {"kind": "maintenance_request", "fields": {}, "lang": lang, "stale": False,
                            "queued": [_cap(strip_greeting(redact(o)))[:200] for o in others[1:3]]}
                    _set(park, "issue", _cap(_issue_text(strip_greeting(redact(others[0]))) or others[0])[:200],
                         "you_said")
                    if room0 := extract_location(others[0]):
                        _set(park, "location", _tr(room0, lang), "you_said")
                extras = [c.strip() for c in re.split(r"(?<=[.!?;])\s+|,\s+|\s+and\s+(?=(?:i|someone|somebody|"
                                                       r"have|please)\b)", msg)
                          if c.strip() and (asks_for_promise(c) or _CALLBACK_ASK.search(c))]
                if queued_note and queued_note.get("queued_topic"):
                    # the request for a person / refund said in the same message is kept ON this note (one note,
                    # nothing dropped); nothing is promised
                    extras = [*extras, str(queued_note["queued_topic"])]
                    queued_note = None
                summary0 = (f"Follow-up on open request {ref} ({mh.request_label(_rec_issue(rec0)) if rec0 else title}"
                            f"); no new request was created. " + (
                                f"{fu_hist.count} earlier related repair request(s) "
                                f"{fu_hist.window('en', singular=fu_hist.count == 1) or 'on record'}"
                                f" ({', '.join(fu_hist.references)})." if fu_hist.count else ""))
                if live and store:  # a card started for the same problem is dropped: it would be a duplicate
                    store.clear_draft(session_id, pkey)
                    touched["draft"] = True
                key = "priority_offer" if (asks_for_priority(msg) or re.search(r"\burgent\b", msg, re.I)) \
                    else "followup_existing"
                extra = ""
                if extras:
                    extra += t("followup_extra_asks", lang)
                if park:
                    extra += t("followup_other_problem", lang, issue=park["fields"]["issue"]["value"])
                return handoff_plan(key, f"Follow-up on open request {ref}; no duplicate.", wid="maintenance",
                                    topic=f"Follow-up on {ref}", ref=ref, title=title, extra=extra,
                                    summary=summary0, park=park,
                                    history=fu_hist if fu_hist.count else None,
                                    requests="; ".join(redact(e) for e in extras)[:240] if extras else None)
        if not live and (bt := back_to_topic(msg)) and (rec_b := _sent_match(sent, bt)):
            # "ok back to the fan" after the fan request was sent: that request, not a new card
            return done(TurnPlan(template=after_send_text(rec_b), functions=["F7", "F8"], skip_model=True,
                                 consumed_by_draft=True, workflow=_sel("status_lookup", "Back to a request already "
                                                                                       "sent in this chat.")))
        # A-6 / B-6: changing an entry or contact detail after Send: a change note with the reference
        if sent_wo_now and not live and (extract_entry(msg) or contact_change(msg)) and len(msg.split()) <= 16 \
                and not is_issue_description(msg) and re.search(r"\b(?:actually|instead|change|wait|now|rather)\b",
                                                                 msg, re.I):
            r0 = sent_wo_now[0]
            return handoff_plan("maint_change", f"Change to {r0['id']} after Send (staff handle it).",
                                topic=f"Change {r0['id']}", ref=f"{WHAT['maintenance_request'][lang]} {r0['id']}")

    # Sprint 6 fix round: the "what have you saved?" family is understood once (u.saved_question) and answered from
    # this conversation's real records and open card, even with a draft open
    meta_q = is_meta_question(msg) or u.saved_question
    status_from_record = bool(meta_q and not sent and not draft and is_resident and verified)
    # "did that go in?", "is it in or just notes?"
    if meta_q and gate.urgency != "emergency" and not status_from_record:
        listed = [f"{WHAT[r['kind']][lang]} {r['id']} {'saved' if lang == 'en' else 'guardada'}" for r in sent[:4]]
        pending = ""
        if draft and not draft.get("declined"):  # D-10: "press Send" only when there is a Send button
            still = _missing(draft["kind"], draft)
            pending = t("pending_missing", lang, what=WHAT[draft["kind"]][lang],
                        missing=", ".join(LABEL[m][lang].lower() for m in still)) if still else \
                t("pending_ready", lang, what=WHAT[draft["kind"]][lang])
        live = bool(draft and not draft.get("declined"))
        text = after_send_text(sent[0]) if len(sent) == 1 and not live else \
            (t("sent_summary", lang, sent="; ".join(listed), pending=pending) if listed else
             (t("q_count_none", lang) + pending).strip())
        return done(TurnPlan(template=text,
                             functions=["F8"], skip_model=True, consumed_by_draft=True,
                             action=_proposed(draft["kind"], draft, lang) if draft and not draft.get("declined")
                             else None,
                             workflow=_sel("status_lookup", "Question about what this chat has actually sent.")))
    no_live = not (draft and not draft.get("stale"))
    if sent and no_live and asks_for_priority(msg) and gate.urgency != "emergency":  # P-5: staff set priority
        r0 = sent[0]
        return handoff_plan("priority_offer", f"Asks for priority on {r0['id']}.", topic=f"Asks for priority on "
                            f"{r0['id']}", team="leasing" if r0["kind"] == "tour_request" else None, ref=r0["id"])
    sent_wo0 = [r for r in sent if r["kind"] == "maintenance_request"]
    if sent_wo0 and no_live and (add := detail_to_add(msg)) and gate.urgency != "emergency":
        r0 = sent_wo0[0]  # P-2: a detail for the request already sent goes to the office with its reference
        return handoff_plan("maint_add_detail", f"Add a detail to {r0['id']} (staff update sent requests).",
                            topic=f"Add to {r0['id']}", ref=r0["id"], detail=redact(add)[:160])
    if sent and (is_after_send_question(msg) or (u.asks_visit and not wants_person)) and \
            not (draft and not draft.get("stale")):
        r0 = sent[0]  # D-9: the request just sent (records come newest first)
        return done(TurnPlan(template=after_send_text(r0), functions=[KIND_FN[r0["kind"]], "F8"], skip_model=True,
                             consumed_by_draft=True,
                             workflow=_sel("status_lookup", "Question about a request already sent in this chat.")))
    # Sprint 7 (judge H-8): a confused person ("I don't understand", "huh?", "no entiendo") gets the current step said
    # plainly, the card kept; never "didn't follow" or an early note for the office. A second confused turn in a row
    # is the D-12 recovery (a person offered).
    if u.confused and not wants_person and gate.urgency != "emergency" and streak < 1:
        live_c = draft if draft and not draft.get("declined") else None
        if live_c:
            step_c, chips_c = _next_step(live_c, lang)
            save(live_c["kind"], live_c)
            return done(TurnPlan(template=t("confused_card", lang, step=step_c), functions=[KIND_FN[live_c["kind"]]],
                                 action=_proposed(live_c["kind"], live_c, lang), chips=chips_c, skip_model=True,
                                 consumed_by_draft=True, extra_flags=["unproductive"],
                                 workflow=_sel(KIND_WF[live_c["kind"]], "Confused: the step explained, card kept.")))
        return done(TurnPlan(template=t("confused_none", lang), functions=[], skip_model=True, consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             extra_flags=["unproductive"],
                             workflow=_sel("general_inquiry", "Confused: what the assistant can do, in plain words.")))
    # 1c-lost. D-12: lost, or says the chat isn't helping: one apology, the next step, and a person.
    if chat_frustrated and gate.urgency != "emergency" and not wants_person:
        return lost_plan("Person is lost or says the chat isn't helping.")
    # 1c-route. B1: how a prospect will be reached. Contact details typed in chat are never stored.
    if not is_resident and (asks_how_reached(msg) or (not sent and is_after_send_question(msg) and draft)) and \
            gate.urgency != "emergency" and not wants_person:
        live_tour = draft if draft and not draft.get("declined") else None
        if live_tour:
            save(live_tour["kind"], live_tour)
        key = "contact_route_profile" if _ctx_value(ctx, "preferred_contact_channel") else "contact_route_none"
        return done(TurnPlan(template=t(key, lang), functions=["F2", "F5"], skip_model=True, consumed_by_draft=True,
                             action=_proposed(live_tour["kind"], live_tour, lang) if live_tour else None,
                             chips=[] if live_tour else CHIPS["prospect_next"][lang],
                             workflow=_sel("tour_request" if live_tour else "general_inquiry",
                                           "How the leasing team reaches a prospect: contact not collected in chat.")))

    # 1c''. "yes" after "you also mentioned X": start the queued request now.
    if draft and draft.get("stale") and "queued" in draft and draft["kind"] == "maintenance_request" and \
            is_affirmative(msg) and len(msg.split()) <= 4:
        draft = {**draft, "stale": False}
        if not draft["fields"].get("location") and (guess := infer_location(draft["fields"]["issue"]["value"]) or
                                                     extract_location(draft["fields"]["issue"]["value"])):
            _set(draft, "location", _tr(guess, lang), "you_said")
        if not draft["fields"].get("contact"):
            _set(draft, "contact", _prefers(_ctx_value(ctx, "preferred_contact_channel"), lang), "on_file")
        save("maintenance_request", draft)
        missing = _missing("maintenance_request", draft)
        key = {"location": "maint_ask_location", "entry": "maint_ask_entry"}.get(missing[0], "maint_ready") \
            if missing else "maint_ready"
        chips = {"location": CHIPS["locations"][lang], "entry": CHIPS["entry"][lang]}.get(
            missing[0] if missing else "", [])
        return done(TurnPlan(template=t(key, lang), functions=["F6", "F7"], chips=chips, consumed_by_draft=True,
                             action=_proposed("maintenance_request", draft, lang),
                             workflow=_sel("maintenance", "Next problem from the same message.")))

    # 1c'. "send it" / a follow-up on something already sent in this chat: point to it, don't start over.
    sent_wo = [r for r in sent if r["kind"] == "maintenance_request"]
    send_again = bool(re.search(r"\b(just |please |pls )?(send|submit) (it|that)\b", msg, re.I)) or is_affirmative(msg)
    insist = bool(re.search(r"\b(fix(ed)?|know|still|already|troubleshoot\w*|hurry|asap)\b", msg, re.I)) \
        and not is_issue_description(msg) and not appliance_in(msg)
    new_object = (a := appliance_in(msg)) and sent_wo and a.lower() not in sent_wo[0].get("summary", "").lower() \
        and not any(a.lower() in str(f.get("value", "")).lower() for f in sent_wo[0].get("fields", []))
    cancel_like = is_cancel_submitted(msg) or is_decline(msg) or is_change_request(msg) or wants_person
    if sent and (not draft or draft.get("stale")) and not new_object and not cancel_like and (
            send_again or (sent_wo and (frustration_only(msg) or insist))):
        r0 = sent[0]
        team = TEAM_LABEL.get(r0.get("team") or "", r0.get("team") or "")
        team_es = _TEAM_ES.get(team.lower(), team.lower())
        team_txt = (f"the {team.lower()} team" if lang == "en" else f"el equipo de {team_es}") if team \
            else ("the team" if lang == "en" else "el equipo")
        lead = t("listening", lang).split(". ")[0] + ". " if not send_again else ""
        what_txt = ("Your " if lang == "en" else "Su ") + WHAT[r0["kind"]][lang]
        return done(TurnPlan(template=lead + t("after_send", lang, what=what_txt, ref=r0["id"],
                                               team=team_txt),
                             functions=[KIND_FN[r0["kind"]], "F8"], skip_model=True, consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("status_lookup", "Follow-up on a request already sent in this chat.")))

    # Sprint 7: the person says the open repair is a DIFFERENT problem from one already saved: it may be saved as its
    # own request (the only way past the near-duplicate check in confirm)
    if draft and not draft.get("declined") and draft["kind"] == "maintenance_request" and gate.urgency != "emergency" \
            and _DIFFERENT.search(msg) and any(r["kind"] == "maintenance_request" for r in sent):
        draft["dup_ok"] = True
        save("maintenance_request", draft)
        return done(TurnPlan(template=t("dup_ok", lang), functions=["F7"], skip_model=True, consumed_by_draft=True,
                             action=_proposed("maintenance_request", draft, lang),
                             workflow=_sel("maintenance", "Person says this is a different problem: may be saved.")))
    # 1d. Unsafe do-it-yourself steps get a plain "please don't" first; a repair request follows if relevant.
    diy = unsafe_diy_kind(msg)
    if diy:
        locals_lead["diy"] = DIY_ADVICE[diy][lang] + " "
    elif (uq := quickfix.unsafe_question(msg)) and "diy" not in locals_lead:
        # Sprint 8 (D) fix round: "disposal jammed, can I reach in and grab it?" gets a direct "no" first (never tips)
        locals_lead["diy"] = t(f"quickfix_unsafe_{uq}", lang) + " "

    # 2. The open card: consent, decline, correction, or a stale card being re-shown.
    effective = msg
    if draft:
        missing_now = _missing(draft["kind"], draft)
        # Sprint 6: consent is the state machine's transition. Only CONFIRM_EXPLICIT (a typed "send it"; the Send
        # button goes through confirm() directly) proposes `save`; a bare yes proposes `prompt_send`; a yes that also
        # corrects, cancels or asks for a person is that act instead, never consent.
        tr2 = wf.apply(wf.derive(draft, mine), u)
        meta_u["tr"] = tr2.summary()
        if missing_now and tr2.event is wf.Event.CONFIRM_EXPLICIT and not draft.get("declined"):
            # Sprint 7 final round: "send it" on an incomplete card says exactly what is still missing
            save(draft["kind"], draft)
            step_m, chips_m = _next_step(draft, lang)
            return done(TurnPlan(template=t("send_missing", lang, missing=", ".join(
                LABEL[m][lang].lower() for m in missing_now)) + " " + step_m, functions=[KIND_FN[draft["kind"]]],
                action=_proposed(draft["kind"], draft, lang), chips=chips_m, skip_model=True, consumed_by_draft=True,
                workflow=_sel(KIND_WF[draft["kind"]], "Typed send on an incomplete card: what is missing.")))
        if not missing_now and tr2.event in (wf.Event.CONFIRM_EXPLICIT, wf.Event.CONFIRM_BARE):
            if draft.get("stale"):
                save(draft["kind"], draft)
                return done(TurnPlan(template=t("reshow", lang, title=WHAT[draft["kind"]][lang]),
                                     functions=[KIND_FN[draft["kind"]]], action=_proposed(draft["kind"], draft, lang),
                                     skip_model=True, consumed_by_draft=True,
                                     workflow=_sel(KIND_WF[draft["kind"]], "Card was set aside; shown again first.")))
            if not tr2.has("save"):
                # W-3: only Send (the button) or an explicit "send it" saves. A bare "yes" / "ok" / "sure" / "sí" on a
                # ready card gets this one line and the card stays (explicit consent before anything is saved).
                save(draft["kind"], draft)
                return done(TurnPlan(template=t("tap_send", lang, what=WHAT[draft["kind"]][lang]),
                                     functions=[KIND_FN[draft["kind"]]], action=_proposed(draft["kind"], draft, lang),
                                     skip_model=True, consumed_by_draft=True,
                                     workflow=_sel(KIND_WF[draft["kind"]], "Bare yes on a ready card: tap Send.")))
            result = confirm(store, session_id, persona_id, draft["kind"], ctx, lang)
            touched["draft"] = True
            new_rec = result.record if result.record and result.error_code != "ALREADY_SAVED" else None
            return done(TurnPlan(template=result.message, functions=[KIND_FN[draft["kind"]]], action=result.action,
                                 skip_model=True, records=[new_rec] if new_rec else [],
                                 consumed_by_draft=True,
                                 workflow=_sel(KIND_WF[draft["kind"]], "Person confirmed the read-back.")))
        # W-7 (documented reorder): the cancel test is the dialogue act, which already treats a bare "no" to the
        # ENTRY question as the answer "contact me first" (handled just below), so "no" never cancels the request.
        cancel = act.has(Act.CANCEL) and draft is live
        if cancel and wants_person and draft["kind"] != "staff_handoff":
            # "no tour, I want someone to call me": park the card, then handle the request for a person below
            if store:
                store.save_draft(session_id, pkey, draft["kind"], {**draft, "declined": True})
            touched["draft"] = True
            parked = draft  # Sprint 8 C: the note for a person carries the pending card's details and history
            draft = None
        elif cancel:
            if store:  # kept (marked declined) so "send it after all" can bring it back once
                store.save_draft(session_id, pkey, draft["kind"], {**draft, "declined": True})
            touched["draft"] = True
            if draft["kind"] == "staff_handoff" and draft.get("parked") and store:
                back = {**draft["parked"], "stale": False, "lang": lang}  # W-4: the parked card comes back
                store.save_draft(session_id, pkey, back["kind"], back)
                step, step_chips = _next_step(back, lang)
                return done(TurnPlan(template=t("declined", lang).split(". ")[0] + "." +
                                     t("parked_back", lang, what=WHAT[back["kind"]][lang]) + " " + step,
                                     functions=[KIND_FN[back["kind"]]], skip_model=True, consumed_by_draft=True,
                                     action=_proposed(back["kind"], back, lang), chips=step_chips,
                                     workflow=_sel(KIND_WF[back["kind"]], "Note skipped; parked card restored.")))
            if (qn0 := draft.get("queued_note")) and store:
                # Sprint 7: the repair is skipped, the request for a person from the same message is not lost
                note0 = {**qn0, "stale": False, "lang": lang,
                         "restorable": {k: v for k, v in draft.items() if k not in ("queued_note", "declined")}}
                store.save_draft(session_id, pkey, "staff_handoff", note0)
                return done(TurnPlan(template=t("declined", lang).split(". ")[0] + "." + t(
                    "queued_other_next", lang, topic=qn0.get("queued_topic") or ""), functions=["F9"],
                    skip_model=True, consumed_by_draft=True, action=_proposed("staff_handoff", note0, lang),
                    workflow=_sel("human_handoff", "Repair skipped; the queued note for a person opens.")))
            faq = match_faq(msg)  # "no tour yet, just prices": the question still gets its answer
            answer = (" " + _faq_text(faq, lang)) if faq else ""
            stands = sent and (is_cancel_submitted(msg) or re.search(r"\brequest\b|solicitud", msg, re.I))
            lead = t("declined_sent_stands", lang, what=WHAT[sent[0]["kind"]][lang], ref=sent[0]["id"]) \
                if stands else t("declined", lang)
            return done(TurnPlan(template=lead + answer, functions=["F4"] if faq else [],
                                 skip_model=True, consumed_by_draft=True,
                                 chips=CHIPS["after_decline"][lang],
                                 extra_flags=[f"declined:{draft['kind']}"],
                                 workflow=_sel("general_inquiry", "Person declined the pending action.")))
        effective = strip_correction_lead(msg)
        if draft and draft["kind"] == "maintenance_request" and missing_now[:1] == ["entry"] and is_bare_ok(msg):
            if not draft.get("entry_checked"):  # D-17: a bare "ok" is not permission to enter someone's home
                draft["entry_checked"] = True
                save("maintenance_request", draft)
                return done(TurnPlan(template=t("maint_entry_confirm", lang), functions=["F7"],
                                     action=_proposed("maintenance_request", draft, lang), chips=CHIPS["entry"][lang],
                                     skip_model=True, consumed_by_draft=True,
                                     workflow=_sel("maintenance", "Bare 'ok' to the entry question: confirm first.")))
            effective = "Contact me first"  # asked twice, still no clear yes: the conservative choice, editable
        elif draft and draft["kind"] == "maintenance_request" and missing_now[:1] == ["entry"]:
            if (ev0_ := und.entry_value(msg)) and _ENTRY_FRAMED.search(msg) and not act.has(Act.QUESTION):
                # Sprint 7 last round: the shared entry grammar decides first ("ok to enter without me" is permission,
                # "you can let yourself in", "come on in", "enter ok")
                effective = "Contact me first" if ev0_.startswith("Contact") else "Yes, you can enter"
            elif is_bare_yes(msg) or is_entry_plain_yes(msg):
                effective = "Yes, you can enter"
            elif is_bare_no(msg):
                effective = "Contact me first"
            elif not extract_entry(msg) and (ev_ := und.entry_value(msg)) and not act.has(Act.QUESTION):
                # Sprint 6 fix round: "knock first", "come in whenever", "go ahead and enter" answer the entry question
                effective = "Contact me first" if ev_.startswith("Contact") else "Yes, you can enter"
            elif act.slot == "entry" and act.value and not extract_entry(msg):
                # "just go in", "whatever works", "yes for both", "yes same as before" (W-12)
                same = act.value == "same_as_before"
                prev = next((f.get("value") for r in sent_wo_now for f in r.get("fields", [])
                             if f.get("key") == "entry" and f.get("value")), "") if same else act.value
                effective = "Contact me first" if (prev or "").startswith(("Contact", "Contactar")) else \
                    "Yes, you can enter" if prev else effective
    elif (is_decline(msg) or is_affirmative(msg)) and not mine and not (rest := _after_lead_decline(msg)):
        # Sprint 9 (live review): "nvm" after a cancel is an acknowledgment, not "nothing waiting to be sent"
        return done(TurnPlan(template=t("nvm_ack" if is_decline(msg) else "nothing_pending", lang), functions=[],
                             skip_model=True,
                             consumed_by_draft=True, chips=CHIPS["resident_next" if is_resident else "prospect_next"]
                             [lang], workflow=_sel("general_inquiry", "Nothing pending to confirm or cancel.")))

    if not draft and (rest := _after_lead_decline(msg)):
        msg = rest  # "nvm. whats your phone number": answer the question, not the "nvm" (Sprint 9 live review)
    if not draft and gate.urgency != "emergency" and _WANTS_NOTE.search(msg):
        # holdout2: "fine, just leave them a note then" after "I can also start a note for the office"
        return handoff_plan("handoff_offer", "Asked for a note to the office.", topic="Note for the office")

    # 3. Languages without approved templates → universal 911 line + staff.
    if non_latin_script(msg):
        return handoff_plan("other_language", "Language without approved templates: offer a person.",
                            topic="Language support needed")

    # 4. Small talk never counts as "unsure" and never escalates.
    sm = _SMALL_TALK.match(msg)
    if sm and not draft:
        key = "small_hi" if sm.group("hi") else "small_bye" if sm.group("bye") else "small_thanks"
        return done(TurnPlan(template=t(key, lang), functions=[], skip_model=True, consumed_by_draft=True,
                             chips=(CHIPS["resident_next"] if is_resident else CHIPS["prospect_next"])[lang]
                             if key != "small_bye" else [],
                             workflow=_sel("general_inquiry", "Greeting or thanks.")))

    # 5. Something already sent in this conversation: change or cancel goes to staff with the reference.
    bare_no = is_bare_no(msg) or bool(re.fullmatch(r"\s*(no|nope|nah)[\s,.!]*(that'?s (all|it)|thanks?)?[\s.!]*",
                                                    msg, re.I))
    if mine and bare_no and not draft:
        return done(TurnPlan(template=t("small_bye", lang), functions=[], skip_model=True, consumed_by_draft=True,
                             workflow=_sel("general_inquiry", "Nothing else needed.")))
    if mine and (is_cancel_submitted(msg) or is_change_request(msg) or
                 (is_decline(msg) and not draft) or
                 (re.search(r"\b(change|move|switch|reschedule|make (it|that)|actually|instead|no wait)\b", msg,
                            re.I) and any(r["kind"] == "tour_request" for r in mine) and not draft
                  and not is_resident and (extract_move_in(msg) or extract_days(msg) or extract_time_of_day(msg)
                                           or extract_clock_preference(msg) or re.search(r"\b(change|move|switch|"
                                                                                         r"reschedule)\b", msg,
                                                                                         re.I)))):
        typed = re.search(r"\bDEMO-(?:WO|TOUR|TASK)-\d+\b", msg, re.I)
        ref_rec = next((r for r in mine if typed and r["id"].lower() == typed.group(0).lower()), None) or next(
            (r for r in mine if r["kind"] != "staff_handoff"), mine[0])
        unknown = bool(typed) and typed.group(0).upper() != ref_rec["id"]
        own_t = bool(typed and store and hasattr(store, "own_record") and store.own_record(typed.group(0).upper()))
        if unknown and typed and not own_t:
            # Sprint 7 (security review): a typed reference that is not this caller's own record is never cited
            typed = None
            ref_txt = "a reference I couldn't match" if lang == "en" else "una referencia que no pude encontrar"
        else:
            ref_txt = None
        ref = ref_txt or (typed.group(0).upper() if unknown and typed else
                          f"{WHAT[ref_rec['kind']][lang]} {ref_rec['id']}")
        verb = "cancel" if re.search(r"cancel|never ?mind|don'?t need|anular|cancelar", msg, re.I) else "change"
        if ref_txt:
            # Sprint 7 final round (security review): an unmatched reference links to NO record, not even the
            # person's own latest one
            return handoff_plan("maint_change", f"{verb.capitalize()} request for a reference that wasn't matched.",
                                topic=f"{verb.capitalize()} {ref_txt}", ref=ref_txt, _unlinked="1",
                                extra=t("still_stands", lang, what=WHAT[ref_rec["kind"]][lang], ref=ref_rec["id"])
                                if verb == "cancel" and ref_rec["kind"] != "staff_handoff" else "")
        return handoff_plan("maint_change", f"{verb.capitalize()} request for {ref_rec['id']} (I-24 rules not "
                            "approved, staff handle it).",
                            topic=f"{verb.capitalize()} "
                                  f"{(ref_txt or typed.group(0).upper()) if unknown else ref_rec['id']}",
                            team="leasing" if ref_rec["kind"] == "tour_request" else None, ref=ref,
                            extra=(t("unknown_ref", lang, ref=ref) if unknown and not ref_txt else "") + (
                                t("still_stands", lang, what=WHAT[ref_rec["kind"]][lang], ref=ref_rec["id"])
                                if verb == "cancel" and not unknown and ref_rec["kind"] != "staff_handoff" else ""))

    # 6. Deterministic routing that must reach staff.
    recognized = bool(status_q or is_tour_request(msg) or match_faq(msg) or wants_person
                      or gate.intent == "maintenance" or draft)
    if is_vendor_contact(msg) and not verified:
        return handoff_plan("vendor", "Vendor contact (D-06): no resident or access data; route to management.",
                            category="other", team="management", topic="Vendor contact")
    if asks_for_english(msg):
        if draft and store:  # the open card (and so the conversation) continues in English
            store.save_draft(session_id, pkey, draft["kind"], {**draft, "lang": "en"})
            touched["draft"] = True
        keep = draft if draft and not draft.get("declined") else None  # D-6: the open card stays on screen
        lead_en = t("english_switch", "en")
        if keep:
            lead_en = lead_en.split(". ")[0] + ". " + _next_step({**keep, "lang": "en"}, "en")[0]
            save(keep["kind"], {**keep, "lang": "en"})
        return done(TurnPlan(template=lead_en, functions=[], skip_model=True, consumed_by_draft=True,
                             action=_proposed(keep["kind"], {**keep, "lang": "en"}, "en") if keep else None,
                             chips=[] if keep else CHIPS["resident_next" if is_resident else "prospect_next"]["en"],
                             workflow=_sel("general_inquiry", "Person asked for English.")))
    live_card = draft if draft and not draft.get("declined") else None
    if asks_for_spanish(msg) and live_card:  # R-2: the card stays; the rest of the message is still an answer
        lang = "es"
        live_card["lang"] = "es"
        draft = live_card
        rest = strip_spanish_request(msg)
        if len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest)) >= 2:
            msg = effective = rest
        else:
            save(live_card["kind"], live_card)
            return done(TurnPlan(template=t("spanish_card", "es"), functions=[KIND_FN[live_card["kind"]]],
                                 action=_proposed(live_card["kind"], live_card, "es"), skip_model=True,
                                 consumed_by_draft=True,
                                 workflow=_sel(KIND_WF[live_card["kind"]], "Switched to Spanish; card kept.")))
    elif asks_for_spanish(msg):
        key = "spanish_switch_resident" if is_resident else "spanish_switch"
        return done(TurnPlan(template=t(key, "es"), functions=[], skip_model=True, consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"]["es"],
                             workflow=_sel("general_inquiry", "Person asked for Spanish.")))
    if is_steering_question(msg):
        faq_extra = " " + _faq_text([tp for tp in match_faq(msg) if tp.status == "approved"], lang)
        return handoff_plan(steering_kind(msg), "Fair Housing steering question (I-13 draft neutral redirect).",
                            wid="faq", category="fair_housing_or_legal", team="management", card=False,
                            extra=faq_extra.rstrip())
    if "sensitive_data_request" in flags:
        return handoff_plan("sensitive", "Sensitive identifiers in chat: redacted; office handles payments.")
    if is_rent_withholding(msg) or ("fair_housing_or_legal" in flags and not is_eviction_worry(msg)
                                    and not is_accommodation(msg) and is_resident):
        return handoff_plan("legal_note", "Rent withholding / legal statement: a manager responds; nothing decided.",
                            category="fair_housing_or_legal", team="management", topic="Legal or rent question")
    if "fair_housing_or_legal" in flags and not is_eviction_worry(msg):
        return handoff_plan("accommodation", "Accommodation / fair-housing / legal topic: trained staff.",
                            topic="Accommodation or legal question")
    if status_q and is_resident and not verified:
        return handoff_plan("status_unverified", "Status lookup needs a verified resident (I-10/I-11 draft).")
    if status_q and persona_id is None and store is not None and gate.urgency != "emergency" and not hazard \
            and not care:
        # Not signed in (the public demo): only records THIS conversation sent, never an account listing. Without
        # this the model answered "nothing on file" right after a tour request was saved.
        mine = [r for r in store.records(session_id=session_id, limit=20) if not r.get("persona_id")]
        if mine:
            items = ", ".join(f"{WHAT.get(r['kind'], WHAT['staff_handoff'])[lang]} {r['id']}" for r in mine[:5])
            return done(TurnPlan(template=t("guest_session_status", lang, items=items), functions=["F8"],
                                 skip_model=True, chips=CHIPS["prospect_next"][lang],
                                 workflow=_sel("status_lookup", "Guest asked about what this conversation sent.")))
    if is_resident and verified and _PAYMENT_PLAN.search(msg) and gate.urgency != "emergency" and \
            (not draft or draft["kind"] == "staff_handoff"):
        # Sprint 8 C last round: a payment-plan request is a billing note, never "Follow-up still owed"
        return handoff_plan("payment_plan", "Payment plan request: accounting decides.", topic="Payment plan request",
                            category="financial_or_lease", team="accounting")
    if is_resident and (thing_q := _is_normal_question(msg)) and not draft and gate.urgency != "emergency" and \
            not hazard and not care and not qf_intake:
        mem["normal_q"] = 1  # flag only: a "yes" / "report it" next turn starts the request
        # Sprint 8 C last round: "is it normal for the water heater to pop?" is a QUESTION: an honest answer and an
        # offer, never a repair card filed on the person's behalf
        return done(TurnPlan(template=t("q_is_normal", lang, thing=thing_q), functions=["F4", "F6"], skip_model=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Question about whether something is normal: answered, "
                                                              "repair request offered.")))
    if _praise_only(msg) and not draft and gate.urgency != "emergency" and not hazard and not care:
        # Sprint 8 C fix round: "the pool party was fire, this place is killer" is a compliment, not a noise complaint
        return done(TurnPlan(template=t("praise_ack", lang), functions=[], skip_model=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Compliment or small talk: no workflow.")))
    if is_resident and verified and is_noise_complaint(msg) and (not draft or draft["kind"] == "staff_handoff"):
        return handoff_plan("noise", "Noise complaint between neighbors: community team.", topic="Noise complaint",
                            team="management")
    if is_resident and verified and re.search(r"\bbalance\b|what do i owe|cu[aá]nto debo", msg, re.I):
        return handoff_plan("balance", "Balance or payment question: accounting.", topic="Balance or payment question",
                            team="accounting")
    if asks_for_promise(msg) and not (draft and draft["kind"] == "maintenance_request"):
        return handoff_plan("no_promise_note", "Request for a promise, date or credit: staff decide.",
                            topic="Credit, date or other commitment requested",
                            team="accounting" if re.search(r"credit|refund|reimburs|compensat|money", msg, re.I)
                            else None)
    if is_resident and verified and not mine and (is_cancel_submitted(msg) or re.search(
            r"\b(cancel|change|reschedule|move)\b.{0,25}\b(my |the )?(repair|request|work order|visit|appointment)\b|"
            r"\bcome (in the )?(mornings?|afternoons?|evenings?|later|earlier) instead\b", msg, re.I)):
        return handoff_plan("maint_change", "Change or cancel an earlier request: staff handle it.",
                            topic="Change or cancel an earlier request",
                            ref="your earlier request" if lang == "en" else "su solicitud anterior")
    hurry = re.search(r"been waiting|waiting since|waiting (?:for|on) (?:someone|somebody|them|a tech\w*|maintenance)|"
                      r"llevo esperando|been forever|taking (?:so long|forever|ages)|ask them to hurry|hurry (?:up|"
                      r"them)|still waiting|"
                      r"\bpush (?:them|it|this|that|things)\b|\bexpedite\b|speed (?:it|this|them|things) up|"
                      r"\bapur\w+|\bnudge (?:them|it)\b|"
                      r"been (?:weeks|days|a month)|nobody (?:has )?(?:come|came|called|fixed)|why is(?:n'?t)? it "
                      r"(?:taking|fixed)", msg, re.I)
    if hurry and is_resident and verified and not (draft and draft["kind"] == "maintenance_request"):
        items = sorted(status_items(store, resident, persona_id or ""), key=lambda i: 0 if "owed" in i.status else 1)
        refs = ", ".join(i.reference for i in items[:3])
        return handoff_plan("frustrated", "Resident says a request is taking too long: office follow-up.",
                            topic="Waiting too long on a request" + (f" ({refs})" if refs else ""),
                            category="unresolved_commitment")
    if re.search(r"what (?:communities|properties|places|buildings|locations|apartments) do you have|which "
                 r"communities|list (?:your |the )?communities|where are your (?:communities|properties|apartments)|"
                 r"que comunidades tienen", msg, re.I) and not is_resident:
        return done(TurnPlan(template=t("communities", lang), functions=["F4"], skip_model=True,
                             chips=CHIPS["prospect_next"][lang],
                             workflow=_sel("faq", "Communities in the demo data (names only; no prices or units).")))
    if is_lease_break(msg) and not claims_prior_decision(msg):  # D-14: its own topic, never "renewal"
        return handoff_plan("lease_break", "Early move-out or lease break: the leasing office explains the options and "
                            "costs; the assistant decides nothing.", category="financial_or_lease", team="leasing",
                            topic="Early move-out or lease break")
    ptopic = policy_topic(msg)
    if ptopic and not match_faq(msg) and not slot_answer and not qf_intake and not (  # Sprint 8 C: a forced intake
            draft and draft["kind"] == "maintenance_request" and _missing("maintenance_request", draft)[:1] == ["entry"]
            and extract_entry(msg)):
        return done(TurnPlan(template=t("policy_unknown", lang, topic=_tr_topic(ptopic, lang)), functions=["F4"],
                             skip_model=True, chips=CHIPS["ask_office"][lang],
                             workflow=_sel("faq", f"Policy question ({ptopic}): no approved answer (D-07).")))
    if not is_resident and states_price_claim(msg):
        return done(TurnPlan(template=t("price_claim", lang), functions=["F4"], skip_model=True,
                             chips=CHIPS["prospect_next"][lang],
                             workflow=_sel("faq", "Person stated a price or special: never confirmed (D-08).")))
    if is_phone_question(msg):
        return done(TurnPlan(template=t("phone_number", lang), functions=["F9"], skip_model=True,
                             chips=["Send a note to the office" if lang == "en" else "Enviar nota a la oficina"],
                             workflow=_sel("faq", "Phone number question: none in the prototype (D-02).")))
    pref_only = not (u.utterance is not None and u.utterance.problem) and not is_issue_description(msg)
    cpref = extract_contact_pref(msg) or (_prefers(und.contact_pref(msg), lang) if pref_only else None)
    if cpref and is_resident and not (draft and draft["kind"] == "maintenance_request"):
        mem["contact_pref"] = und.contact_pref(msg) or mem.get("contact_pref")  # a channel name only, never a number
        return handoff_plan("contact_note_offer", "Contact preference change: the office updates the account.",
                            topic="Contact preference change", pref=cpref)
    if claims_prior_decision(msg):  # never agree with a decision the assistant can't see or make
        return handoff_plan("premise_check", "Person says something was already decided; staff must check.",
                            category="financial_or_lease" if re.search(r"fee|rent|lease|credit|refund|deposit|"
                                                                       r"discount|penalty", msg, re.I) else "other",
                            topic="Says something was already agreed")
    if u.staff_complaint and is_resident and verified and gate.urgency != "emergency" and not (
            draft and draft["kind"] == "staff_handoff" and not draft.get("declined")):
        # Sprint 6 fix round: "the tech was rude", "missed Tuesday visit, I want an explanation": a note for a manager,
        # never a repair card asking "which room?". An answer in the same message is kept on the parked card first.
        if draft and draft["kind"] == "maintenance_request" and not draft.get("declined") and act.has(Act.ANSWER):
            apply_answer(draft)
        return handoff_plan("staff_complaint_note", "Complaint about a visit or a staff member: a manager reads it.",
                            category="other", team="management", topic="Complaint about a visit or staff member")
    if wants_person or "explicit_human_request" in flags or "human_requested" in flags:
        manager = asks_for_manager(msg)  # D-11: a manager is the management team, for residents and prospects
        return handoff_plan("handoff_offer", "Person asked for a manager." if manager else
                            "Person asked to reach a person or the office.", category="human_requested",
                            team="management" if manager else ("leasing" if not is_resident else None),
                            topic="Asked for a manager" if manager else None)
    if is_eviction_worry(msg) or (draft and draft["kind"] == "staff_handoff" and "financial_or_lease" in flags):
        return handoff_plan("eviction" if is_eviction_worry(msg) else "handoff_offer",
                            "Lease or eviction worry: office explains, assistant decides nothing.",
                            topic="Lease or payment question")
    hard_human = flags & {"explicit_human_request", "unverified_private_request"}
    if workflow.id == "human_handoff" and not problem_shape and not (
            "repeated_low_confidence" in flags and recognized and not hard_human):
        if "repeated_low_confidence" in flags and not hard_human:  # offer, don't file a note nobody asked for
            if store and is_resident and not draft:
                rec_ = handoff or synthesize_handoff(gate, ctx, "other", "management", "Not understood twice")
                hd_ = _handoff_draft(gate, rec_, ctx, msg, lang, None, "Couldn't understand the request", recent)
                store.save_draft(session_id, pkey, "staff_handoff", {**hd_, "lang": lang, "declined": True,
                                                                      "offered": True})
                touched["draft"] = True
            # this offer already is the D-12 "offer a person" step, so it is not converted into a note card
            return done(TurnPlan(template=t("unclear_offer", lang), functions=["F9"], skip_model=True,
                                 chips=CHIPS["unclear"][lang] if is_resident else CHIPS["prospect_next"][lang],
                                 workflow=_sel("general_inquiry", "Not understood twice: offer the office, no card.")))
        return handoff_plan("handoff_offer", workflow.reason)

    # 7a. D-15: "the one for the sink leak", "the AC one": an existing request, not a new repair. Checked before the
    # generic status list (step 7), so "status of the one for the sink leak" gets that one request.
    ref_words = existing_request_words(msg) if (is_resident and verified and gate.urgency != "emergency" and not (
        draft and draft["kind"] == "maintenance_request" and not draft.get("stale"))) else []
    if ref_words:
        items = status_items(store, resident, persona_id or "")
        hit = next((i for i in items if matches_words(ref_words, i.title)), None)
        if hit:
            return done(TurnPlan(template=t("existing_request", lang, ref=hit.reference, title=hit.title,
                                            status=hit.status), functions=["F8"], status_items=[hit], skip_model=True,
                                 consumed_by_draft=True,
                                 chips=(["Send a note to the office", "Report a new repair"] if lang == "en"
                                        else ["Enviar nota a la oficina", "Reportar una reparación"]),
                                 workflow=_sel("status_lookup", "Person referred to a request already open.")))
        effective = " ".join(ref_words)  # no match: a new repair, described in their words ("sink leak")

    # 7. Status lookup (F8) for a verified resident.
    if is_resident and verified and (status_q or status_from_record):
        items = sorted(status_items(store, resident, persona_id or ""),
                       key=lambda i: 0 if "owed" in i.status else 1)
        frustrated = "complaint_or_frustration" in flags
        none_key = "status_none_history" if _ctx_value(ctx, "repeat_issue_flag") else "status_none"  # J-4
        open_card = draft if draft and draft["kind"] == "maintenance_request" and not draft.get("declined") else None
        draft_txt = t("status_draft_open", lang, what=WHAT["maintenance_request"][lang]) if open_card else ""
        plan = TurnPlan(template=t("status_some" if items else none_key, lang) + draft_txt, functions=["F8"],
                        action=_proposed("maintenance_request", open_card, lang) if open_card else None,
                        status_items=items, skip_model=not frustrated,
                        workflow=_sel("status_lookup", "Verified resident asked about request status."),
                        chips=(["Send a note to the office", "Report a new repair"] if lang == "en"
                               else ["Enviar nota a la oficina", "Reportar una reparación"]))
        if frustrated:
            hd = _handoff_draft(gate, handoff, ctx, msg, lang, draft, topic="Waiting too long on a request")
            save("staff_handoff", hd)
            plan.action, plan.force_handoff, plan.handoff = _proposed("staff_handoff", hd, lang), True, handoff
            plan.template = t("frustrated", lang) + " " + t("status_some_short" if items else none_key, lang)
            plan.chips = []
            plan.functions.append("F9")
        return done(plan)

    # 8. Maintenance intake (F6) and the work-order draft (F7).
    in_maint_draft = bool(draft and draft["kind"] == "maintenance_request")
    first_window: str | None = None
    exposure_urgent = False
    if care == "unwell" and gate.urgency != "emergency" and not full_alert and not person_danger:
        from app.risk.frame import analyse as risk_frame  # read-only: the safety layer's own frame (Agent A)

        exposure_urgent = "exposure" in risk_frame(msg, recent).hazards
    scan = _NEG_SEGMENT.sub(" ", effective)  # "bathroom, not kitchen" -> bathroom
    location = utt.room_in(scan)  # Sprint 7: garage, closet... are places too
    entry = (und.entry_value(effective) if _ENTRY_FRAMED.search(effective) else None) or extract_entry(effective)
    adds_detail = bool(re.search(r"\b(also note|add (that|this)|note that|mention that|tell them)\b", msg, re.I))
    question_only = msg.strip().endswith("?") and not is_issue_description(msg) and not location and not entry \
        and not adds_detail
    off_topic = bool(match_faq(msg) or is_tour_request(msg) or question_only) and not entry and not location
    answers_draft = in_maint_draft and not off_topic and (location or entry or gate.intent in ("general", "maintenance")
                                                          or len(effective.split()) >= 3)
    # follow-ups during a PROPERTY incident (R10 / R10q after a sparking outlet) and remembered lines (R9) are not a
    # person in danger THIS turn; the repair may continue (Sprint 2 / 3 behaviour)
    danger_now = person_danger and (full_alert and is_people_hazard(hazard or "") or (
        care is not None and (danger_rule or "") not in ("R9", "R9e", "R10", "R10q")))
    if danger_now and gate.urgency != "emergency" and (
            workflow.id == "maintenance" or gate.intent == "maintenance" or answers_draft or problem_shape):
        # (THIS turn's danger signal only: a remembered line from earlier (R9) passes care=None, so "the bathroom sink
        # is leaking" after an earlier disclosure still gets a repair card, as Sprint 3 requires)
        # Sprint 7 (with Agent A): while a person may be in danger (a full alert, or a care line from a person sign,
        # distress or a follow-up), no ordinary repair card is opened or extended; the safety text above stays as is
        return done(TurnPlan(template=t("danger_no_form", lang), functions=["F9"], skip_model=True,
                             consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "A person may be in danger: no repair intake now.")))
    tour_open = bool(draft and draft["kind"] == "tour_request" and not draft.get("declined"))
    tour_detail = tour_open and not appliance_in(msg) and not hazard and bool(
        extract_days(msg) or extract_clock_preference(msg))  # "saturday is fine if thursday doesnt work" (holdout)
    if not tour_detail and (workflow.id == "maintenance" or gate.intent == "maintenance" and is_resident or
                            answers_draft or problem_shape or (exposure_urgent and is_resident) or (
            injected and is_resident and is_issue_description(msg)) or (
            is_resident and (qf_intake or quickfix.match_entry(msg) is not None))):  # Sprint 8 (D): see report
        if not is_resident:
            return done(TurnPlan(template=t("maint_guest", lang), functions=["F6"], chips=CHIPS["who"][lang],
                                 workflow=_sel("maintenance", "Maintenance from someone not signed in.")))
        if not verified:
            return handoff_plan("maint_unverified", "Maintenance from an unmatched resident: office takes it.",
                                wid="maintenance", topic="Repair report (account not matched)")
        # 8-qf. Sprint 8 (D): up to 3 quick-fix tips BEFORE a new repair request, only for an eligible low-risk issue
        # with a negative safety finding (app/quickfix.py decides; content gate QUICKFIX_CONTENT_MODE). One round
        # per issue; never on an open card, a repeat issue, several problems at once, or the turn that follows tips.
        if not in_maint_draft and not draft and not qf_intake and quickfix_mode != "off" and \
                len(split_issues(effective)) == 1:
            qres = quickfix.check_eligibility(
                msg, risk, mode=quickfix_mode, lang=lang, urgency=gate.urgency,  # type: ignore[arg-type]
                repeat=bool(triage and triage.level == "repeat") or bool(
                    {"context_repeat_issue", "repeat_with_history"} & flags) or bool(_repeat_of_open(resident, msg)),
                used=mem.get(quickfix.USED_KEY) or [])
            if qres.eligible:
                quickfix.offered_memory(mem, qres)
                tips = "\n".join(f"{i}. {s}" for i, s in enumerate(qres.tips, 1))
                label = t("quickfix_draft_label", lang) + "\n\n" if qres.draft else ""
                return done(TurnPlan(template=label + t("quickfix_offer", lang, items=tips), functions=["F6"],
                                     skip_model=True, chips=CHIPS["quickfix"][lang],
                                     workflow=_sel("maintenance", f"Quick-fix tips offered ({qres.entry_id}) "
                                                   "before a repair request.")))
        d = draft if in_maint_draft else {"fields": {}}
        assert d is not None
        fields_before = repr(sorted((k, v.get("value")) for k, v in d.get("fields", {}).items()))
        effective = re.sub(r"^\W*(?:ok(?:ay)?|so|and|anyway)?[\s,]*(?:back to|about|regarding|re:?) (?:the |my )?",
                           "", effective, flags=re.I) or effective  # "ok, back to the oven" resumes; it isn't a problem
        if not in_maint_draft and (restated := extract_issue_restate(effective)):
            effective = restated  # "it should say the kitchen sink is leaking" -> that is the problem
        if not in_maint_draft:
            # Sprint 7: entry permission said in the FIRST message ("toilet keeps running, come in any time") goes to
            # the entry field and out of "What's wrong". A clause is an entry answer when it has an entry value and no
            # problem of its own.
            cl_e = [c for c in re.split(r"(?<=[.;!?,])\s+|\s+[-–—]\s+|\s+(?:and|but|y|pero)\s+(?=(?:maintenance|they|"
                                        r"you|the tech\w*|someone|please|feel|use|ok|come|llamen|pueden|que)\b)",
                                        effective) if c.strip()]
            ent_c = [c for c in cl_e if und.entry_value(c) and not utt.analyze(c).problem]
            if ent_c and len(ent_c) < len(cl_e):
                entry = entry or und.entry_value(ent_c[0])
                effective = " ".join(c for c in cl_e if c not in ent_c).strip(" ,;-–—")
            # Sprint 7 final round: a visit-time clause in the first message ("only mornings work for visits. the
            # bedroom closet door is off the track") sets the visit window and stays out of "What's wrong"
            win_c = [(c, w) for c in cl_e if not utt.analyze(c).problem
                     for w in [und._TIME_VALUE.search(c)] if w and und._VISIT_TIME_WORDS.search(c)]
            if win_c and len(win_c) < len(cl_e):
                first_window = _cap(win_c[0][1].group("v").strip())
                effective = " ".join(c for c in cl_e if c not in [x for x, _ in win_c] and c not in ent_c).strip(
                    " ,;-–—") or effective
        if not in_maint_draft and asks_for_plain_ticket(msg) and recent:
            # E-7: "just put in a normal repair ticket" after describing the problem: the ticket keeps that description
            # (the safety decision is not touched here; only the repair text is not overwritten by the request)
            earlier_issue = next((r for r in reversed((recent or [])[:-1]) if is_issue_description(r) or _things_in(r)
                                  or _LATER_SYMPTOM.search(r) or re.search(r"\bsmok|spark|burn", r, re.I)), None)
            if earlier_issue:
                effective = re.sub(r"^.*?\b(?:not in danger|i'?m fine|it'?s fine|its fine)\b[^,]*,?\s*(?:but\s+)?",
                                   "", earlier_issue, flags=re.I) or earlier_issue
        if not in_maint_draft and not d["fields"].get("issue") and not utt.things(effective) and \
                not utt.has_symptom(effective) and (u_rec := next(
                    (r for r in mine if r.get("status") == "urgent_queued" and r.get("hazard") not in _PRIVATE_HAZARDS),
                    None)):
            # Sprint 8 C: "I'm fine, I just want it fixed" right after an alert: the repair is the problem the alert
            # was about (the words the person typed then, kept on the urgent note), not this sentence
            said0 = next((str(f.get("value") or "") for f in u_rec.get("fields") or [] if f.get("key") == "message"),
                         "")
            if said0 and (utt.things(said0) or utt.has_symptom(said0)):
                effective = said0
        clean = strip_greeting(redact(effective))
        injection_lead = ""
        if looks_like_injection(clean):  # keep the person's own words, drop the instruction-like part
            kept = [x for x in re.split(r"(?<=[.!?])\s+|\n+|\s(?=>)", clean)
                    if x.strip() and not looks_like_injection(x) and not x.strip().startswith(">")]
            clean = " ".join(kept).strip()
            effective = clean or effective
            injection_lead = t("injection_dropped", lang)
        multi_note = ""
        parts = split_issues(effective) if not in_maint_draft and not d["fields"].get("issue") else [effective]
        if len(parts) > 1:  # one request per problem; the rest wait and are offered after this one is sent
            effective = parts[0]
            clean = strip_greeting(redact(parts[0]))
            location = extract_location(_NEG_SEGMENT.sub(" ", parts[0]))
            d["queued"] = [strip_greeting(redact(p))[:200] for p in parts[1:3]]
            multi_note = t("multi_issue_named", lang, n=str(len(parts)), first=clean[0].lower() + clean[1:],
                           items="; ".join(q[0].lower() + q[1:] for q in d["queued"] if q))
        if qf_queue and not in_maint_draft:  # Sprint 8 (D): the problem the tips were for waits on this card
            kept = strip_greeting(redact(qf_queue))[:200]
            d["queued"] = [*(d.get("queued") or []), kept][:3]
            mem.pop(quickfix.MEM_KEY, None)
            qf_side["on"] = False
            multi_note = (multi_note + " " if multi_note else "") + t(
                "quickfix_kept_first", lang, issue=kept[0].lower() + kept[1:])
        promise = in_maint_draft and (asks_for_promise(msg) or bool(_TIMING_Q.search(msg)) or asks_for_priority(msg))
        venting = in_maint_draft and frustration_only(msg)
        issue = d["fields"].get("issue", {}).get("value")
        swap = (extract_issue_swap(msg) or und.issue_rewrite(msg)) if in_maint_draft and issue and \
            not utt.ends_as_question(msg) and not utt.UNRELATED.search(msg) else None  # R-1; Sprint 7
        loc_change = extract_location_change(msg, d["fields"].get("location", {}).get("value")) \
            if in_maint_draft else None
        cpref = extract_contact_pref(msg)
        updated_note = ""
        if swap:  # replace, never append; flags from the old problem no longer apply
            _set(d, "issue", swap[:200], "you_said")
            for k in ("repeat", "repeat_acknowledged", "stated_repeat", "vague_issue", "repeat_history",
                      "manager_review"):
                d.pop(k, None)
            d["fields"].pop("priority_note", None)
            d["fields"].pop("related_history", None)
            d["priority"], d["team"] = "normal", "maintenance"
            triage = None
            updated_note = t("issue_updated", lang, issue=swap)
            effective = swap
        if loc_change:
            prev_loc = d["fields"].get("location", {}).get("value")
            detailed = len(loc_change.split()) == 2 and extract_location(loc_change)  # "Hall bathroom" stays as is
            _set(d, "location", loc_change if (detailed or loc_change == "Hallway") else
                 _tr(extract_location(loc_change) or loc_change, lang), "you_said")
            new_room = extract_location(d["fields"]["location"]["value"])
            if prev_loc and new_room and (iv := d["fields"].get("issue", {}).get("value")) and \
                    extract_location(prev_loc) != new_room:  # "my bathroom faucet" -> "my kitchen faucet"
                d["fields"]["issue"]["value"] = re.sub(
                    rf"\b{re.escape(extract_location(prev_loc) or prev_loc)}\b",
                    lambda m_: new_room if m_.start() == 0 else new_room.lower(), iv, flags=re.I)
            updated_note = (updated_note + " " if updated_note else "") + t(
                "location_updated", lang, loc=d["fields"]["location"]["value"])
        if cpref:
            _set(d, "contact", cpref, "you_said")
            updated_note = (updated_note + " " if updated_note else "") + t("contact_noted", lang, pref=cpref)
        if swap or loc_change or (cpref and in_maint_draft and len(msg) - len(cpref) < 25):
            pass  # nothing else in this message is a new repair detail
        elif issue and (app_word := appliance_in(effective)) and not appliance_in(issue) and in_maint_draft:
            _set(d, "issue", f"{app_word[0].upper() + app_word[1:]}: {issue}"[:200], "you_said")
            d.pop("vague_issue", None)
        elif issue and in_maint_draft and d.get("vague_issue") and (not _slot_only(effective) or is_issue_description(
                effective)) and _issue_text(clean):
            _set(d, "issue", f"{issue}: {_issue_text(clean)}"[:200], "you_said")  # their own words, once
            d.pop("vague_issue", None)
        elif promise:  # never written into the repair text; shown separately for the office to decide
            prev = d["fields"].get("requests", {}).get("value")
            _set(d, "requests", ((prev + "; ") if prev else "") + clean[:120], "you_said")
        elif venting:
            pass
        elif cpref and not issue and len(msg) - len(cpref) < 25:
            pass
        elif not issue and no_issue_content(effective):
            d["vague_issue"] = True  # D-4: "can you fix it" / "the thing again" says nothing about the problem: ask
        elif not issue and describes_issue(effective) and (not (_slot_only(effective) and in_maint_draft)
                                                           or is_issue_description(effective)):
            text = _issue_text(clean) or clean  # B-3 / A-10: entry and contact wording stay out of "What's wrong"
            thing = appliance_in(text)
            if thing and not is_issue_description(text) and not _LATER_SYMPTOM.search(text) and \
                    not states_repeat(text) and re.search(  # "the fridge", "i called about the fridge last wk"
                        rf"^\W*(?:the |my )?{re.escape(thing)}\W*$|\b(?:about|regarding|re|for|with) (?:the |my )?"
                        rf"{re.escape(thing)}\b", text, re.I):
                _set(d, "issue", thing[0].upper() + thing[1:], "you_said")  # B-2: "the fridge" alone: ask what's wrong
                d["vague_issue"] = True
            else:
                _set(d, "issue", text[:200], "you_said")
                d.pop("vague_issue", None)  # D-4: asked "what's wrong?" and now told
                if _vague_issue(text):
                    d["vague_issue"] = True
        elif issue and in_maint_draft and not _slot_only(effective) and (is_issue_description(effective)
                                                                         or utt.analyze(effective).problem
                                                                         or adds_detail
                                                                         or _LATER_SYMPTOM.search(effective)) \
                and clean.lower() not in issue.lower():
            more = re.sub(r"^\W*(?:(?:oh|ok|okay|and|also|plus|y|tambi[eé]n)\W+)+", "", clean, flags=re.I) or clean
            more = _issue_text(more)  # "Text me first. and it's blowing warm air" -> only the symptom is added
            # Sprint 7 fix round: a meta-complaint ("I already said ...") never goes into the problem text; and a
            # restatement that adds no new words is not a new detail
            more = re.sub(r"^\W*(?:i (?:already |just )?(?:said|told you)(?: (?:it|that|this))?|like i said|as i said|"
                          r"ya (?:le |te )?dije)\W*", "", more or "", flags=re.I).strip()
            if more and (is_meta_complaint(msg) or not (_content_words(more) - _content_words(issue))):
                more = ""
                updated_note = updated_note or t("meta_sorry_nochange", lang)
            unrelated = bool(utt.UNRELATED.search(clean))
            more_ut = utt.analyze(more) if more else None
            if more and more_ut is not None and (unrelated or (more_ut.problem and more_ut.objects and not (
                    more_ut.objects & utt.things(issue)))) and not adds_detail:
                # Sprint 7 last round: a DIFFERENT problem said while a card is open ("unrelated - the hallway carpet
                # has a stain") waits as its own request, never "Also:" on this one
                more = utt.UNRELATED.sub("", more).strip(" :-–—,")
                d["queued"] = [*(d.get("queued") or []), _cap(more)[:200]][:3]
                updated_note = (updated_note + " " if updated_note else "") + t("queued_note", lang,
                                                                                 items="; ".join(d["queued"]))
                more = ""
            if more and more.lower() not in issue.lower():
                more = more[0].upper() + more[1:]  # "also its…" never becomes "Also: Also its…"
                _set(d, "issue", (issue + " Also: " + more)[:400], "you_said")  # new repair details are kept
        if loc_change:
            location = None
        elif swap and not re.search(r"\b(?:kitchen|bath ?room|bedroom|living room|laundry|balcony|patio|hallway|cocina|"
                                    r"baño|dormitorio|sala)\b", swap, re.I):
            location = None  # R-1: "toilet" in a restated problem isn't a new room; the corrected room stays
        old_loc = d["fields"].get("location", {}).get("value")
        correction = effective != msg or bool(_NEG_SEGMENT.search(msg)) or bool(re.search(r"\binstead\b", msg, re.I))
        if location and old_loc and old_loc != _tr(location, lang) and not correction:
            location = None  # a second room goes into the issue text ("Also: ..."), never replaces the first
        if location and old_loc and old_loc != _tr(location, lang) and d["fields"].get("issue"):
            iv = d["fields"]["issue"]["value"]
            d["fields"]["issue"]["value"] = re.sub(rf"\b{re.escape(old_loc)}\b", _tr(location, lang) or old_loc, iv,
                                                   flags=re.I)
        _set(d, "location", _tr(location, lang), "you_said")
        new_loc = d["fields"].get("location", {}).get("value")
        if in_maint_draft and old_loc and new_loc and new_loc != old_loc and not loc_change:
            # Sprint 6: "Actually, it is the bedroom AC": say what changed; the intake continues, nothing restarts
            updated_note = (updated_note + " " if updated_note else "") + t("location_updated", lang, loc=new_loc)
        elif in_maint_draft and location and new_loc == old_loc and not updated_note and repr(sorted(
                (k, v.get("value")) for k, v in d.get("fields", {}).items())) == fields_before:
            updated_note = t("location_confirmed", lang, loc=new_loc)  # honest: nothing changed, not "Got it"
        if not d["fields"].get("location") and (guess := infer_location(effective)):
            _set(d, "location", _tr(guess, lang), "assistant")
        if not d["fields"].get("location") and triage and triage.category == "hvac" and \
                not ({"water heater", "hot water"} & utt.things(  # Sprint 8 C: a water heater is plumbing
                    d["fields"].get("issue", {}).get("value") or effective)):
            _set(d, "location", _tr("Heating / cooling system", lang), "assistant")
        issue_now = d["fields"].get("issue", {}).get("value") or ""
        hist = _history_match(resident, issue_now or effective) if verified else None
        if not d["fields"].get("location") and hist and (room := extract_location(hist.subject)):
            _set(d, "location", _tr(room, lang), "assistant")  # W-12: the room is on the matching history item
        common = is_common_area(f"{issue_now} {effective}") and not re.search(r"\b(?:my|our) (?:gate|pool)\b",
                                                                             issue_now, re.I)
        if common and (not d["fields"].get("location") or extract_location(effective) == "Outside or common area"
                       or re.search(r"\boutside\b|common area|not in my", effective, re.I)):
            _set(d, "location", _tr("Outside or common area", lang), "assistant" if not loc_change else "you_said")
        if common and d["fields"].get("location", {}).get("value") == _tr("Outside or common area", lang) and \
                not entry and not d["fields"].get("entry"):
            _set(d, "entry", _tr("Not needed (common area)", lang), "assistant")  # B-5: no one enters a home
        _set(d, "entry", _tr(entry, lang), "you_said")
        if not d["fields"].get("contact") and mem.get("contact_pref"):
            # Sprint 7 fix round: a preference said earlier in this chat ("I'd rather get a phone call") is applied to
            # every later card, labelled as the person's own words
            _set(d, "contact", _prefers(mem["contact_pref"], lang), "you_said")
        if not d["fields"].get("contact"):
            contact = _ctx_value(ctx, "preferred_contact_channel")
            _set(d, "contact", _prefers(contact, lang), "on_file")
        said_channel = channel_said(msg)  # D-20: "text me first" in chat wins over the profile's channel on the card
        if said_channel and not cpref and d["fields"].get("contact", {}).get("source") != "you_said":
            _set(d, "contact", _prefers(said_channel, lang), "you_said")
        if first_window and not in_maint_draft:
            _set(d, "entry_window", first_window, "you_said")
        window = _ctx_value(ctx, "preferred_entry_window")
        if window and not d["fields"].get("entry_window"):
            _set(d, "entry_window", _window_es(window) if lang == "es" else window, "on_file")
        # D-5 / F-4: a repeat from the record needs a history item about the SAME thing (a toilet is not the kitchen
        # sink); without resident history to check, the triage decision stands.
        # Sprint 8 C: the related history is computed from AUTHORIZED data only (this verified resident's own workbook
        # interactions and this principal's own prototype records; app/maintenance_history.py). The draft being written
        # is not a record, so it is never counted. A repeat "from the record" needs at least one related request.
        history = mh.related_history(
            issue_now or effective, resident=resident if verified else None,
            persona_id=persona_id if verified else None,
            records=store.records(persona_id=persona_id, kind="maintenance_request", limit=200)
            if (store and verified and persona_id) else [])
        triage_repeat = bool(triage and triage.level == "repeat") and history.count >= 1
        repeat = triage_repeat or (history.count >= 2 and not swap) or d.get("repeat", False)
        if triage_repeat and hist is not None:
            d["history_ref"] = f"{hist.interaction_id} \"{sanitize_field(hist.subject, 80) or 'maintenance'}\""
        frustrated = ("complaint_or_frustration" in flags and not swap) or d.get("frustrated", False)
        # Sprint 8 C: after quick-fix tips, "still not working" means the tips didn't help, not a repeat or urgent case
        urgent_wording = (gate.urgency == "high" and not swap and not (
            qf_intake and set(gate.risk_flags) <= {"repeat_language", "low_confidence"})) or bool(re.search(
            r"(?:through|from) the ceiling|ceiling (?:is )?(?:leak|drip)|from upstairs", effective, re.I))
        priority = _max_priority(d.get("priority"), handoff.priority if handoff and not swap else None)
        security = is_security_repair(d["fields"].get("issue", {}).get("value", "") or effective)  # D-13
        if security:
            d["security"] = True
        elif swap:
            d.pop("security", None)
        es_repeat = says_repeat_es(msg) and not swap  # D-19: "otra vez", "ya pasó antes"
        if states_repeat(msg) and not swap and not repeat and not no_issue_content(msg) and (
                states_named_repeat(msg) or (issue_now and not d.get("vague_issue"))):
            d["stated_repeat"] = True  # J-6 / R-3: the person says a NAMED problem came back ("the thing again" isn't)
        if not repeat and (d.get("stated_repeat") or es_repeat) and history.count >= 1:
            repeat = True  # Sprint 8 C: what the person says is confirmed by their own record
        if repeat and history.count >= 1:
            d["repeat_history"] = history.to_record()
            _set(d, "related_history", mh.summary_line(history, lang), "on_file")
        elif not d.get("repeat"):
            d.pop("repeat_history", None)
            d["fields"].pop("related_history", None)
        if repeat or d.get("stated_repeat"):
            d["manager_review"] = True  # the existing repeat-issue manager-review flag, carried on the saved request
        vulnerable = bool(_VULNERABLE.search(msg))  # R-7: a baby at home, 85 or 50 degrees inside
        if vulnerable:
            d["vulnerable"] = True
        if repeat or frustrated or urgent_wording or d.get("security") or es_repeat or d.get("stated_repeat") or \
                d.get("vulnerable"):
            priority = _max_priority(priority, "high")
        if exposure_urgent or d.get("exposure"):
            # Sprint 7 (with Agent A): no heat / no AC with a vulnerable person at home and no symptom described is an
            # URGENT heating or cooling repair; the calm "unwell" care line from the safety layer is still shown
            d["exposure"] = d["vulnerable"] = True
            priority = "urgent"
            if not d["fields"].get("location"):
                _set(d, "location", _tr("Heating / cooling system", lang), "assistant")
        team = "management" if d.get("team") == "management" or (handoff and handoff.team == "management"
                                                                  and repeat) else "maintenance"
        if repeat and frustrated:
            team = "management"
        flags_txt = "repeat issue (history on record)" if repeat else \
            "repeat issue (resident says)" if d.get("stated_repeat") else ""
        summary = " · ".join(x for x in (d["fields"].get("issue", {}).get("value"),
                                         d["fields"].get("location", {}).get("value"), flags_txt,
                                         "high priority" if priority in ("high", "urgent") else "") if x)
        d.update(repeat=repeat, frustrated=frustrated, team=team, priority=priority,
                 category=triage.category if triage else d.get("category", "other"),
                 summary=summary[:300] or "Resident repair request (prototype).")  # R-3/R-8: the real details
        if d.get("exposure"):
            _set(d, "priority_note", t("exposure_note", lang), "assistant")
        elif repeat or frustrated or priority == "high":
            stated = d.get("stated_repeat") and not repeat
            note_txt = ("Repeat issue: manager review" if repeat else "Repeat issue (you said): manager review"
                        if stated else "High priority: home security (lock)" if d.get("security") else
                        "High priority") if lang == "en" else (
                "Problema repetido: revisión de gerente" if repeat else "Problema repetido (según usted): revisión "
                "de gerente" if stated else "Prioridad alta: seguridad (cerradura)" if d.get("security") else
                "Prioridad alta")
            _set(d, "priority_note", note_txt, "assistant")
        missing = _missing("maintenance_request", d)
        first_turn = not in_maint_draft
        if not missing:
            key = "maint_ready_repeat" if repeat and not d.get("repeat_acknowledged") else "maint_ready"
            if key == "maint_ready_repeat" and d.get("repeat_history"):
                key = "repeat_history_ready"
            chips: list[str] = []
        else:
            door = bool(d.get("security"))  # D-13: a lock repair offers the front (entry) door first
            key = {"issue": "maint_ask_what" if d.get("vague_issue") else "maint_ask_issue",
                   "location": "maint_ask_location_door" if door else "maint_ask_location", "entry": "maint_ask_entry"}[
                missing[0]]
            chips = {"location": CHIPS["door_locations" if door else "locations"][lang],
                     "entry": CHIPS["entry"][lang]}.get(missing[0], [])
        template = t(key, lang)
        hist_line = _history_line(history, lang) if repeat and d.get("repeat_history") else ""
        if key == "repeat_history_ready":
            template = f"{t('repeat_history_lead', lang)} {hist_line} {template}"
        if d.get("exposure") and not d.get("exposure_said"):
            template = t("exposure_lead", lang) + " " + template
            d["exposure_said"] = True
        if updated_note:  # J-8: after "Updated: …" no extra "Got it." opener
            follow = t("maint_ask_entry_plain", lang) if key == "maint_ask_entry" else template
            template = updated_note + (" " + t("maint_ready_plain", lang) if not missing else " " + follow)
        elif promise:
            template = t("no_promise", lang) + (" " + template if missing else "")
        elif venting:
            template = t("listening", lang) + (" " + template if missing else "")
        if repeat and missing and not d.get("repeat_acknowledged"):
            template = (f"{t('repeat_history_lead', lang)} {hist_line}" if hist_line else t("maint_repeat_ack", lang)) \
                + " " + template
            d["repeat_acknowledged"] = d["frustration_acknowledged"] = True  # one apology, not two
        elif frustrated and not d.get("frustration_acknowledged"):
            template = t("frustrated_repair", lang) + " " + template
            d["frustration_acknowledged"] = True
        elif d.get("stated_repeat") and not repeat and not d.get("repeat_acknowledged"):
            template = t("maint_repeat_stated", lang) + " " + template  # J-6: said once, acknowledged once
            d["repeat_acknowledged"] = True
        hazard_words = re.search(r"smell|gas|smok|burn|spark|odor|olor|humo", msg, re.I)
        already_tried = re.search(r"\bagain\b|\bstill\b|\d+(st|nd|rd|th) time|(second|third|fourth|fifth) time|"
                                  r"tech (came|was here)|already (tried|checked|did)|otra vez|de nuevo|"
                                  r"ya pas[oó] antes", msg, re.I)
        if repeat and already_tried and not d.get("repeat_heard") and missing:
            template = t(_heard_key(history.count), lang) + " " + template.replace(
                "I'm sorry this is happening again. ", "").replace("Lamento que vuelva a pasar. ", "")
            d["repeat_heard"] = True
        if key == "maint_ask_entry" and (in_maint_draft or not template.startswith(t(key, lang))):
            # Sprint 9: after an apology or a repeat line, the question alone (no second "Got it" opener)
            template = template.replace(t(key, lang), t("maint_ask_entry_plain", lang))
        legacy = quickfix.legacy_checks(
            msg, risk, mode=quickfix_mode, category=triage.category, steps=legacy_draft_steps(triage.category),
            approved=legacy_checks_approved(), urgency=gate.urgency, repeat=repeat, lang=lang,  # type: ignore[arg-type]
        ) if first_turn and triage and triage.level == "routine" and not repeat and not hazard_words and \
            not already_tried and not diy and lang == "en" and not d.get("stated_repeat") and not multi_note and \
            not qf_intake and "diy" not in locals_lead else None  # R-9: the legacy checks exist in English only
        # (Sprint 6: not after a split: the triage read the WHOLE message, so its tips may be for the other problem)
        # Sprint 8 fix round: the legacy checks are DRAFTS (not McKinley-approved): the same safety checks and content
        # gate as the quick-fix tips; shown only in demo_drafts, labelled, or once McKinley approves them
        if legacy and legacy.eligible:
            template += " " + t("legacy_checks_draft" if legacy.draft else "legacy_checks", lang,
                                items=" ".join(legacy.tips))
        if multi_note:
            template = multi_note + " " + template
        template = injection_lead + template
        if queued_note and not in_maint_draft:
            d["queued_note"] = queued_note
            template += t("queued_other", lang, topic=queued_note["queued_topic"])
        save("maintenance_request", d)
        mplan = TurnPlan(template=template, functions=["F6", "F7"] + (["F9"] if gate.requires_human else []),
                         action=_proposed("maintenance_request", d, lang), chips=chips,
                         consumed_by_draft=in_maint_draft and workflow.id != "maintenance",
                         workflow=_sel("maintenance", "Maintenance intake for a verified resident."),
                         force_handoff=repeat or frustrated, handoff=handoff)
        mplan.facts.append(  # F-4: the model may state a repeat or history fact only when the planner established it
            ("Repeat issue: YES" + (f", it matches history item {d['history_ref']}" if d.get("history_ref") else "")
             + f". The resident's own record shows exactly {history.count} earlier related maintenance request(s) "
             f"{history.window('en', singular=history.count == 1) or 'on record'}; state only that count and window, "
             "do not count this request, and do not say anyone was notified.") if repeat and history.count else
            f"Repeat issue: YES, it matches history item {d['history_ref']}." if repeat and d.get("history_ref") else
            "Repeat issue: YES, history on record shows related repairs." if repeat else
            "Repeat issue: the person says it happened before (not confirmed by the record)." if d.get("stated_repeat")
            else "Repeat issue: NO. Do not say this is a repeat and do not mention earlier requests on the record.")
        stuck = in_maint_draft and missing and not updated_note and not promise and \
            repr(sorted((k, v.get("value")) for k, v in d.get("fields", {}).items())) == fields_before
        return unproductive(mplan, "Repair card: nothing new, same question again.") if stuck else done(mplan)

    # 9. Tour request (F5) for prospects and visitors.
    in_tour_draft = bool(draft and draft["kind"] == "tour_request")
    if not is_resident and (_FLOOR_Q.search(msg) or (u.utterance is not None and u.utterance.question and
                                                      extract_beds(msg) and not extract_days(msg) and re.search(
                r"\b(?:do you have|are there|any|available|availability|tienen|hay)\b", msg, re.I))) and \
            not is_tour_request(msg) and \
            not match_faq(msg) and \
            gate.urgency != "emergency":  # D-21: "how big are the 2 beds": no verified plans; answer, don't fill a form
        live_tour = draft if in_tour_draft else None
        if live_tour:
            save("tour_request", live_tour)
        tail = t("next_leasing_note", lang) if (mem.get("tour_pitched") or live_tour or any(
            r["kind"] == "tour_request" for r in mine)) else t("faq_offer_tour", lang)
        mem["tour_pitched"] = True
        mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), "floor plans"]))
        return done(TurnPlan(template=t("floor_plans_none", lang) + " " + tail, functions=["F4"], skip_model=True,
                             action=_proposed("tour_request", live_tour, lang) if live_tour else None,
                             chips=CHIPS["ask_leasing" if "leasing team" in tail.lower() else "prospect_next"][lang],
                             workflow=_sel("faq", "Floor plan or size question: no verified floor plans.")))
    tour_mine = [r for r in mine if r["kind"] == "tour_request"]
    if not is_resident and in_tour_draft and draft and u.utterance is not None and u.utterance.question and \
            re.search(r"\b(?:office|leasing office|front desk|oficina)\b.{0,30}\b(?:open|hours|closed|abierta|"
                      r"horario|abre|abren|cierra|cierran)\b|"
                      r"\b(?:hours|horario)\b", msg, re.I):
        # Sprint 7 final round: "is the leasing office open on sundays" is a question, not a tour day; the draft stays
        save("tour_request", draft)
        mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), "office hours"]))
        return done(TurnPlan(template=t("q_unknown_office", lang) + " " + _next_step(draft, lang)[0],
                             functions=["F4", "F5"], skip_model=True, consumed_by_draft=True,
                             action=_proposed("tour_request", draft, lang),
                             workflow=_sel("tour_request", "Office-hours question: answered; the tour card stays.")))
    if not is_resident and is_booking_question(msg) and (in_tour_draft or tour_mine):
        pref = extract_clock_preference(msg)
        pref_txt = (f"I've noted {pref[1]} as your preference. " if lang == "en"
                    else f"Anoté {pref[1]} como su preferencia. ") if pref else ""
        if in_tour_draft and draft and pref:
            _set(draft, "time", f"{pref[0]} ({pref[1]})", "you_said")
            save("tour_request", draft)
        ref = t("booking_saved_ref", lang, ref=tour_mine[0]["id"]) if tour_mine and not in_tour_draft else ""
        return done(TurnPlan(template=t("booking_q", lang, pref=pref_txt, ref=ref).strip(), functions=["F5"],
                             skip_model=True, consumed_by_draft=True,
                             action=_proposed("tour_request", draft, lang) if in_tour_draft and draft else None,
                             workflow=_sel("tour_request", "Booking or exact-time question: not a booking.")))
    clock = extract_clock_preference(effective)
    # Sprint 6: each date goes to ONE field by its own clause (tour visit vs move-in); "could we do December 14th
    # instead?" on an open tour card is the tour day and never also the move-in (P1)
    tour_date, move_date = und.dates(effective, in_tour_draft, (
        _missing("tour_request", draft) or [None])[0] if in_tour_draft and draft else None,
        draft if in_tour_draft else None)
    if refuses_tour(msg) and not is_resident and gate.urgency != "emergency" and not match_faq(msg) and \
            not (u.utterance is not None and u.utterance.question) and not draft:
        # Sprint 7 last round: "nope, still no tour, thanks" is answered, not met with the generic welcome
        mem["no_tour"] = True
        return done(TurnPlan(template=t("no_tour_ack", lang), functions=["F4"], skip_model=True,
                             consumed_by_draft=True, chips=CHIPS["ask_office"][lang],
                             workflow=_sel("leasing", "No tour wanted: questions welcome.")))
    tour_slots = {"area": community_in(effective) or extract_area_correction(effective) or city_in(effective),
                  "days": extract_days(effective) or (tour_date if (
                      in_tour_draft or is_tour_request(msg)) else None),  # C-4: "can the tour be on dec 6"
                  "time": f"{_tr(clock[0], lang)} ({clock[1]})" if clock else _tr(extract_time_of_day(effective), lang),
                  "beds": extract_beds(effective), "move_in": move_date}
    if not tour_slots["days"] and (wd := re.search(r"\b(?:any ?(?:week)?day|(?:any )?weekdays?|(?:any )?weekends?|"
                                                   r"entre semana|fin(?:es)? de semana)\b", effective, re.I)):
        tour_slots["days"] = _cap(wd.group(0).lower())  # "any weekday evening" answers the days question
    if in_tour_draft and draft and not tour_slots["area"] and _missing("tour_request", draft)[:1] == ["area"]:
        tour_slots["area"] = bare_area_answer(effective)
    unlisted_area = None  # Sprint 9 (holdout2): "something in Flint" is not a demo area: never saved as the area
    if tour_slots["area"] and not (community_in(tour_slots["area"]) or city_in(tour_slots["area"])) and \
            _unknown_place(f"in {tour_slots['area']}"):
        unlisted_area, tour_slots["area"] = _unknown_place(f"in {tour_slots['area']}"), None
    tour_mine0 = [r for r in mine if r["kind"] == "tour_request"]
    if tour_slots["days"] and tour_date and tour_date.lower() not in tour_slots["days"].lower() and \
            extract_days(effective) and (in_tour_draft or is_tour_request(msg) or tour_mine0):
        tour_slots["days"] = f"{tour_slots['days']}, {tour_date}"  # "friday nov 20" keeps both
    # Sprint 7: a date that can be misread ("3/4": March 4 or April 3; "tmrw") is written as a date the person can
    # check, and the reply reads it back. It is the tour day unless the clause is about moving.
    readback = ""
    if not is_resident and gate.urgency != "emergency" and (in_tour_draft or is_tour_request(msg)) and not \
            re.search(r"\bmov(?:e|ing)\b|move-?in|mudanza|mudar", effective, re.I) and \
            (rb := utt.date_readback(effective, lang)):
        rb_val, rb_shown = rb
        if "|" in rb_shown:
            us_d, alt_d = rb_shown.split("|", 1)
            readback = t("date_readback_alt", lang, value=us_d, detail=alt_d)
        else:
            readback = t("date_readback", lang, value=rb_shown)
        tour_slots["days"] = rb_val if not tour_slots["days"] or re.search(
            r"tomorrow|today|tonight|ma[ñn]ana|hoy|\d/\d", tour_slots["days"], re.I) else \
            f"{tour_slots['days']} ({rb_val})"
    # Sprint 6 fix round: a day of the month with no month ("push it to the 20th") goes to the field the card holds;
    # with both a tour day and a move-in on the card (or the saved tour), ask which one, and apply the answer next turn
    if not is_resident and gate.urgency != "emergency":
        card_d = draft if in_tour_draft else ({"fields": {f.get("key"): {"value": f.get("value")}
                                                         for f in tour_mine0[0].get("fields", [])}}
                                              if tour_mine0 else None)
        pend = (draft or {}).get("pending_date") if in_tour_draft else mem.get("pending_date")
        if card_d is not None and pend and (not und.ordinal_date(effective) or und.ordinal_date(effective) == pend):
            which = "days" if re.search(r"\btour\b|\bvisit\b|\bvisita\b|\bsee\b", effective, re.I) else \
                "move_in" if re.search(r"\bmove[- ]?in\b|\bmoving\b|mudanza", effective, re.I) else None
            if which and not tour_slots[which]:
                tour_slots[which] = pend
                if in_tour_draft and draft:
                    draft.pop("pending_date", None)
                mem.pop("pending_date", None)
        dval, dfield = und.date_target(effective, card_d) if card_d is not None else (None, None)
        if dval and dfield == "ask":
            if in_tour_draft and draft:
                draft["pending_date"] = dval
                save("tour_request", draft)
            else:
                mem["pending_date"] = dval
            return done(TurnPlan(template=t("date_which", lang, value=dval), functions=["F5"], skip_model=True,
                                 consumed_by_draft=True,
                                 action=_proposed("tour_request", draft, lang) if in_tour_draft and draft else None,
                                 chips=["The tour", "The move-in"] if lang == "en" else ["La visita", "La mudanza"],
                                 workflow=_sel("tour_request", "Date with no month: tour day or move-in?")))
        if dval and dfield in ("days", "move_in"):
            tour_slots[dfield] = dval
    budget_said = u.entities.budget  # C-2: "my max is $1,600" is a budget for the note, not a price question
    tour_slots["budget"] = budget_said
    price_q = any(tp.status != "approved" for tp in match_faq(msg)) and not budget_said
    if price_q:
        tour_slots["days"] = None  # "sign today" is not a tour day
    voucher_q = any(tp.id == "vouchers" for tp in match_faq(msg))  # P-12: a voucher question isn't a tour request
    leasing_hint = not is_resident and not price_q and not voucher_q and (workflow.id in ("leasing",
                                                                                         "general_inquiry") and any(
        tour_slots[k] for k in ("area", "beds", "move_in", "days")) and gate.intent == "leasing" or
        (gate.audience == "unknown" and tour_slots["move_in"]))
    keeps_tour_card = in_tour_draft and (any(tour_slots.values()) or len(effective.strip()) <= 40) and not \
        (match_faq(msg) and not budget_said)
    guest_place = not is_resident and not draft and not mine and bool(bare_area_answer(effective)) and \
        gate.audience != "resident" and not match_faq(msg) and not voucher_q  # "floor plans?" isn't a place
    if guest_place and not tour_slots["area"]:
        tour_slots["area"] = bare_area_answer(effective)
    open_note = bool(draft and draft["kind"] == "staff_handoff" and not draft.get("declined"))
    asks_t = bool(u.utterance is not None and u.utterance.asks and not re.search(
        r"\b(?:change|switch|move|reschedule|instead|can we do|could we do|how about)\b", msg, re.I) and not (
        extract_days(msg) or extract_time_of_day(msg) or extract_clock_preference(msg) or und.ordinal_date(msg)))
    if not is_resident and (not draft or open_note) and tour_mine and gate.urgency != "emergency" and not asks_t and (
            is_tour_request(msg) or leasing_hint or any(tour_slots.values())):
        sent_vals = {f.get("key"): f.get("value") for f in tour_mine[0].get("fields", [])}
        sent_area = sent_vals.get("area")
        if tour_slots["area"] and sent_area and sent_area.lower().startswith(tour_slots["area"].lower()):
            tour_slots["area"] = sent_area  # "ann arbor" is the "Ann Arbor, Michigan area" already sent
        if (bt := re.search(r"\b(?:but|actually|instead|rather|mejor)\b(?P<rest>.*)$", msg, re.I)) and \
                extract_time_of_day(bt.group("rest")):
            tour_slots["time"] = _tr(extract_time_of_day(bt.group("rest")), lang)  # "I said morning but evenings..."
        new_detail = [k for k in ("days", "time", "move_in") if tour_slots[k] and tour_slots[k] != sent_vals.get(k)]
        switch = bool(re.search(r"\b(?:change|switch|move|swap|instead|make (?:it|that)|reschedule|cambi|i meant|"
                                r"not (?:the |in )?\w+|wrong)", msg, re.I))  # N-3: "i meant Sandpiper Pointe not X"
        if (tour_slots["area"] and tour_slots["area"] != sent_area and switch) or open_note or (
                (not tour_slots["area"] or tour_slots["area"] == sent_area) and new_detail):
            # P-2: a change to the saved tour (or more for the change note already open) attaches to that request
            ref0 = tour_mine[0]["id"]
            chg = [f"{LABEL[k][lang]} → {tour_slots[k]}" for k in ("area", "days", "time", "move_in")
                   if tour_slots[k] and tour_slots[k] != sent_vals.get(k)]
            return handoff_plan("maint_change", f"Change request for {ref0} (staff handle changes).",
                                topic=f"Change {ref0}", team="leasing", ref=f"{WHAT['tour_request'][lang]} {ref0}",
                                extra=t("change_requested", lang, detail="; ".join(chg) if chg else redact(msg)[:160]))
        if not tour_slots["area"] or tour_slots["area"] == sent_area:  # B1: no duplicate of a request already saved
            return done(TurnPlan(template=t("tour_already_sent", lang, ref=tour_mine[0]["id"],
                                            saved=_saved_summary(tour_mine[0]) or "-"),
                                 functions=["F5"], skip_model=True, consumed_by_draft=True,
                                 chips=CHIPS["ask_leasing"][lang][:1],
                                 workflow=_sel("tour_request", "A tour request is already saved in this chat.")))
    if not is_resident and open_note and draft and not tour_mine and gate.urgency != "emergency" and (
            is_tour_request(msg) or any(tour_slots[k] for k in ("days", "time"))) and not wants_person and not (
            _OFFICE_HOURS_Q.search(msg) and not is_tour_request(msg)):  # "do they open on saturdays?" is office hours
        # Sprint 7 (judge H-4): tour details while a note for the leasing team is open never replace that note. They
        # go INTO the note, and the tour card is queued: after the note is sent (confirm), the tour card opens with
        # these values. One card at a time; nothing lost.
        said_t = {k: v for k, v in tour_slots.items() if v and k in ("area", "days", "time", "beds", "move_in")}
        detail_t = ", ".join(f"{LABEL[k][lang]}: {v}" for k, v in said_t.items()) or (
            "tour" if lang == "en" else "visita")
        old_m = draft["fields"].get("message", {}).get("value", "")
        add_m = (f"Tour interest: {detail_t}" if lang == "en" else f"Interés en visita: {detail_t}")
        if add_m.lower() not in old_m.lower():
            _set(draft, "message", (f"{old_m} | {add_m}" if old_m else add_m)[:480], "you_said")
        draft["queued_tour"] = {**(draft.get("queued_tour") or {}), **said_t, "requested": "yes"}
        save("staff_handoff", draft)
        return done(TurnPlan(template=(readback + " " if readback else "") + t("note_tour_added", lang,
                                                                                detail=detail_t),
                             functions=["F9", "F5"], skip_model=True, consumed_by_draft=True,
                             action=_proposed("staff_handoff", draft, lang),
                             workflow=_sel("human_handoff", "Tour details added to the open note; tour card queued.")))
    if refuses_tour(msg):
        mem["no_tour"] = True
    elif is_tour_request(msg) and not refuses_tour(msg):
        mem.pop("no_tour", None)
    if mem.get("no_tour"):
        leasing_hint = guest_place = False  # only an explicit tour request opens a tour card now
    tour_like = bool(not is_resident and gate.urgency != "emergency" and (community_in(msg) or city_in(msg)) and (
        (u.utterance is not None and u.utterance.names_tour) or extract_days(msg) or extract_time_of_day(msg)) and
        not refuses_tour(msg) and not (u.utterance is not None and u.utterance.question and not extract_days(msg)))
    no_tour_now = bool(mem.get("no_tour") and not in_tour_draft and not (is_tour_request(msg) and
                                                                          not refuses_tour(msg)))
    if not is_resident and not no_tour_now and not refuses_tour(msg) and not (
            asks_t and tour_mine and not in_tour_draft and not is_tour_request(msg)) and (
            is_tour_request(msg) or keeps_tour_card or leasing_hint or guest_place or tour_like):
        d = draft if in_tour_draft else {"fields": {}}
        assert d is not None
        if not in_tour_draft and tour_mine and re.search(r"\bsame (?:time|day|days|times|slot)s?\b|\bmisma hora\b|"
                                                         r"\bmismo d[ií]a\b", effective, re.I):
            # a second community: the days and time already given carry over only when the person says so ("same
            # time"); otherwise they are asked (Sprint 7 fix round: never inherited silently)
            for f in tour_mine[0].get("fields", []):
                if (f.get("key") in ("days", "time") or (f.get("key") == "move_in" and f.get("source") == "you_said")) \
                        and f.get("value") and not tour_slots.get(f["key"]):
                    _set(d, f["key"], f["value"], "you_said")  # a second community: what they said carries over
        was_ready = in_tour_draft and not _missing("tour_request", d)
        for k, v in (mem.get("lead") or {}).items() if not in_tour_draft else []:
            # Sprint 6 fix round: what the person said in this chat ("a tour there" after naming Heron Lake) comes
            # before the profile's on-file values
            if k in LABEL and v and not d["fields"].get(k, {}).get("value"):
                _set(d, k, v, "you_said")
        if not d["fields"].get("area") and (area := _ctx_value(ctx, "interest_area")):
            if "no community selected" not in area:
                _set(d, "area", area, "on_file")
        if not d["fields"].get("beds") and (beds := _ctx_value(ctx, "desired_floor_plan")):
            _set(d, "beds", beds.replace("two-bed", "2 beds"), "on_file")
        if not d["fields"].get("move_in") and (mi := _ctx_value(ctx, "move_in_timeframe")):
            _set(d, "move_in", mi, "on_file")
        for k, v in (mem.get("lead") or {}).items() if not in_tour_draft else []:
            # C-6: what a guest said before the card existed carries over to the new card
            if k in LABEL and v and not d["fields"].get(k, {}).get("value"):
                _set(d, k, v, "you_said")
        cur_area = d["fields"].get("area", {}).get("value") or ""
        if tour_slots["area"] and cur_area.lower().startswith(tour_slots["area"].lower()):
            tour_slots["area"] = None  # "ann arbor" again doesn't replace "Ann Arbor, Michigan area"
        if in_tour_draft and is_additive(effective):  # C-4: "sunday afternoon would work too" adds an option
            for k in ("days", "time"):
                cur_k = d["fields"].get(k, {}).get("value")
                if tour_slots[k] and cur_k and tour_slots[k].lower() not in cur_k.lower() and \
                        "flexible" not in cur_k.lower():
                    tour_slots[k] = f"{cur_k}, {tour_slots[k]}"
        # Sprint 7 fix round: two communities in one message ("Heron Lake on Saturday and Sandpiper Pointe on Sunday")
        # are both on the card, each with its own day, so dropping one later removes exactly its community and day
        per_area = [(community_in(c), extract_days(c)) for c in re.split(r"\s+(?:and|or|o|y)\s+|,\s*|;\s*|/",
                                                                          effective)
                    if community_in(c)]
        names_a = list(dict.fromkeys(a for a, _ in per_area))
        if len(names_a) >= 2:
            tour_slots["area"] = ", ".join(names_a)
            d["area_days"] = {a: dd for a, dd in per_area if dd}
        old_area = d["fields"].get("area", {}).get("value")
        before = {k: d["fields"].get(k, {}).get("value") for k in tour_slots}
        waiting = _missing("tour_request", d)[:1]
        if in_tour_draft and waiting and waiting[0] in ("days", "time") and not tour_slots[waiting[0]] and \
                flexible_answer(effective, waiting[0]):  # "whenever" answers the question that was asked
            tour_slots[waiting[0]] = _FLEXIBLE[waiting[0]][lang]
        changed = [k for k, v in tour_slots.items() if _set(d, k, v, "you_said")]
        if (ruled_out := negated_days(effective)) and (cur := d["fields"].get("days", {}).get("value")):
            keep = [x.strip() for x in cur.split(",") if x.strip()[:3].lower() not in ruled_out]
            if keep != [x.strip() for x in cur.split(",")]:
                if keep:
                    _set(d, "days", ", ".join(keep), "you_said")
                else:
                    d["fields"].pop("days", None)
                changed.append("days")
        if pets := extract_pets(effective):
            _set(d, "pets", pets, "you_said")
        on_profile = bool(_ctx_value(ctx, "preferred_contact_channel"))  # B1: the route only, never a typed contact
        _set(d, "contact_route", _ROUTE["profile" if on_profile else "none"][lang],
             "on_file" if on_profile else "assistant")
        d.update(team="leasing", priority="normal", category="leasing_follow_up",
                 summary=f"Tour request from {_who(ctx).lower()}.")
        missing = _missing("tour_request", d)
        asked: dict[str, int] = d.setdefault("asked", {})
        skip_notes: list[str] = []
        while missing and asked.get(missing[0], 0) >= 2:  # D-8: never the same question a third time
            slot = missing[0]
            _set(d, slot, _SKIPPED[lang], "assistant")
            d["skipped"] = [*d.get("skipped", []), slot]
            skip_notes.append(t("tour_skip_slot", lang, label=LABEL[slot][lang].lower()))
            missing = _missing("tour_request", d)
        if missing and (not changed or not asked.get(missing[0])) and not (in_tour_draft and is_tour_request(msg)):
            asked[missing[0]] = asked.get(missing[0], 0) + 1  # P-8: only a question left unanswered counts again
        save("tour_request", d)
        mem["tour_pitched"] = True
        if missing:
            key = {"area": "tour_ask_area", "days": "tour_ask_days", "time": "tour_ask_time"}[missing[0]]
            chips = {"days": CHIPS["tour_days"][lang], "time": CHIPS["tour_time"][lang]}.get(missing[0], [])
        else:
            key, chips = ("tour_updated" if was_ready and changed else "tour_ready"), []
        when = tour_when(d, lang)
        template = t("tour_ready_when", lang, when=when) if key == "tour_ready" and when else t(key, lang)
        if key == "tour_ask_area" and in_tour_draft:
            template = t("ask_plain_area", lang)  # the greeting belongs to the first turn only (holdout)
        notes: list[str] = []  # B1 / D-22: say what changed, in one short line; the card shows every field (Sprint 9)
        if in_tour_draft:
            new_vals = [str(d["fields"].get(k, {}).get("value")) for k in dict.fromkeys(changed)
                        if k in LABEL and d["fields"].get(k, {}).get("value") and before.get(k)]
            first = [k for k in dict.fromkeys(changed) if k in LABEL and d["fields"].get(k, {}).get("value")
                     and not before.get(k)]
            changed_when = {k for k in changed if before.get(k)} <= {"days", "time"} and tour_when(d, lang)
            if new_vals:
                notes.append(t("tour_changed", lang, values=changed_when or ", ".join(
                    v[0].lower() + v[1:] if not _DAY_KEEP.match(v) else v for v in new_vals)))
            elif first and missing:
                notes.append(t("tour_ack", lang))
            elif first and was_ready and lang == "en" and all(k in _FIELD_NAME for k in first):
                # Sprint 9 (review B-4): say WHAT was added, so a misread ("ASAP" as the move-in) is visible
                notes.append(t("field_changed", lang, name=" and ".join(_FIELD_NAME[k] for k in first)))
        if was_ready and changed and notes:
            template = t("tour_recheck", lang) if not missing else template
        elif "area" in changed and old_area and was_ready:
            template = t("tour_area_updated", lang, area=d["fields"]["area"]["value"])
        template = " ".join([*notes, *skip_notes, template])
        if readback:
            template = f"{readback} {template}"
        if "[phone redacted]" in msg or "[email redacted]" in msg:
            template += " " + t("contact_route_profile" if on_profile else "contact_route_none", lang)
        faq = match_faq(msg)
        prefix = _faq_text(faq, lang) + " " if faq else ""
        if faq and in_tour_draft and missing and not changed and not skip_notes and asked.get(missing[0], 0) >= 2:
            # Sprint 9: a side question while the tour card is open gets its answer, not the same tour question
            # again (the card's progress line still shows what's needed); the unasked question isn't counted
            asked[missing[0]] -= 1
            save("tour_request", d)
            template = ""
        if not in_tour_draft and not notes and key in ("tour_ask_days", "tour_ask_time", "tour_ask_area"):
            prefix += t("leasing_capture" if leasing_hint and not is_tour_request(msg) else "tour_start", lang) + " "
        if key == "tour_ask_area" and not notes and not skip_notes:
            template = t("ask_plain_area", lang) if prefix else template
        if missing and missing[0] == "area" and (pu := _unknown_place(effective) or unlisted_area or (
                mem.get("unlisted_area") if is_affirmative(msg) else None)):
            again = mem.get("unlisted_area") is not None  # the full list once; then a shorter line (holdout2)
            mem["unlisted_area"] = pu
            prefix, template = "", t("unknown_city_again" if again else "unknown_city", lang, area=pu)
        tplan = TurnPlan(template=(prefix + template).strip(), functions=["F5"] + (["F4"] if faq else []),
                         action=_proposed("tour_request", d, lang), chips=chips,
                         consumed_by_draft=in_tour_draft and not is_tour_request(msg),
                         workflow=_sel("tour_request", "Tour request from a prospect or visitor."))
        if in_tour_draft and missing and not changed and not skip_notes and not faq:
            return unproductive(tplan, "Tour card: nothing new, same question again.")
        return done(tplan)

    # 10. Renewal (no artifact module; routed through F9 to leasing).
    if workflow.id == "renewal" or (is_resident and re.search(r"renew|renov(?!at)", msg, re.I)):
        contact = _ctx_value(ctx, "preferred_contact_channel")
        suffix = (f" and noted that you prefer {contact}" if lang == "en"
                  else f" y anoté que prefiere {_ES_CHANNEL.get(contact.lower(), contact)}") if contact else ""
        return handoff_plan("renewal", workflow.reason, wid="renewal", contact=suffix, topic="Renewal question",
                            team="leasing")

    # 11. FAQ (F4) — approved answers only.
    faq = match_faq(msg)
    if faq:
        unanswered = [tp.label for tp in faq if tp.status != "approved"]
        if unanswered:  # P-4: remembered (topic labels only, never message text) for the leasing note
            mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), *unanswered]))
        note = draft if draft and draft["kind"] == "staff_handoff" and not draft.get("declined") else None
        if note and mem.get("questions"):
            _set(note, "questions", _questions_text(mem["questions"], lang), "you_said")
            save("staff_handoff", note)
            if re.search(r"\b(?:include|add|put|also|too|as well|tambi[eé]n|agreg\w*|incluy\w*)\b", msg, re.I):
                return done(TurnPlan(template=t("questions_added", lang, value=note["fields"]["questions"]["value"]),
                                     functions=["F4", "F9"], action=_proposed("staff_handoff", note, lang),
                                     skip_model=True, consumed_by_draft=True,
                                     workflow=_sel("human_handoff", "Questions added to the open note.")))
        card = note or (draft if draft and draft["kind"] == "tour_request" and not draft.get("declined") else None)
        if card and not note:
            save(card["kind"], card)  # P-7: the open tour card stays visible while the question is answered
        chips = CHIPS["prospect_next"][lang] if not is_resident else CHIPS["resident_next"][lang]
        floor = any(tp.id == "floor_plans" and tp.status != "approved" for tp in faq)
        answer = _faq_text([tp for tp in faq if not (floor and tp.id == "floor_plans")], lang)
        if floor:  # D-21: no approved floor plans in the data: one honest line, then a real next step
            answer = (t("floor_plans_none", lang) + " " + answer).strip()
        tail = t("faq_offer_tour" if not is_resident else "resident_general", lang).split(". ")[-1]
        toured = any(r["kind"] == "tour_request" for r in mine) or bool(draft and draft["kind"] == "tour_request")
        if not is_resident and (mem.get("tour_pitched") or toured):  # the tour pitch at most once per session
            tail, chips = t("next_leasing_note", lang), CHIPS["ask_leasing"][lang]
            answer = _LEASING_REFERRAL.sub("", answer).strip()  # Sprint 9: one referral, not two in a row
        elif not is_resident:
            mem["tour_pitched"] = True
        return done(TurnPlan(template=answer + " " + tail, functions=["F4"], chips=chips,
                             action=_proposed(card["kind"], card, lang) if card else None,
                             workflow=_sel("faq", "Question matched the FAQ topic list (I-12 draft).")))

    # 12. Any remaining deterministic handoff need (frustration, owed follow-up, voucher, lease/billing).
    if gate.requires_human:
        key = "frustrated" if "complaint_or_frustration" in flags else "handoff_offer"
        return handoff_plan(key, "Backend gate requires a person: " + (gate.handoff_reason or "staff review"),
                            wid=workflow.id)

    if u.utterance is not None and u.utterance.question and not draft and gate.urgency != "emergency" and \
            len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", msg)) >= 3 and is_resident:  # prospects: the leasing reply below
        # Sprint 7 final round: "unrelated question: when is rent due" gets an honest "I don't have that here" and a
        # way to ask the office, never the generic menu
        mem["questions"] = list(dict.fromkeys([*mem.get("questions", []), _cap(policy_topic(msg) or "a question")]))
        return done(TurnPlan(template=t("q_unknown_office", lang), functions=["F4"], skip_model=True,
                             consumed_by_draft=True, chips=CHIPS["ask_office"][lang],
                             workflow=_sel("faq", "Question without an approved answer: ask the office.")))
    # 13. Leasing without slots, resident general help, or unknown visitor. These replies move nothing forward, so
    # each counts as unproductive: the second in a row becomes the D-12 recovery (apology + a person).
    live_note = draft if draft and draft["kind"] == "staff_handoff" and not draft.get("declined") else None
    if live_note and len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", msg)) >= 3 and gate.urgency != "emergency" and re.search(
            r"^\W*(?:it'?s |its |it is |this is |the note is )?(?:about|regarding|concerning|re:)\b|"
            r"^\W*(?:also|and|plus)\b|\b(?:for|to|in) the note\b|\b(?:add|include|mention)\b|"
            r"^\W*(?:es|trata) (?:sobre|de)\b", msg, re.I):
        # only a message that clearly adds to the note; anything else leaves the card to go stale (consent rule)
        old_msg = live_note["fields"].get("message", {}).get("value", "")  # R-6: more detail for the open note
        _set(live_note, "message", (f"{old_msg} | {redact(msg)}" if old_msg else redact(msg))[:480], "you_said")
        save("staff_handoff", live_note)
        return done(TurnPlan(template=t("note_updated", lang), functions=["F9"], skip_model=True,
                             consumed_by_draft=True, action=_proposed("staff_handoff", live_note, lang),
                             workflow=_sel("human_handoff", "More detail added to the open note.")))
    live_n = draft if (draft and draft["kind"] == "staff_handoff" and not draft.get("declined")) else None
    if live_n and gate.urgency != "emergency":  # A-9 / B-1: the open note stays on screen, never the generic menu
        save("staff_handoff", live_n)
        return unproductive(TurnPlan(template=t("lost_note_open", lang), functions=["F9"], workflow=workflow,
                                     skip_model=True, action=_proposed("staff_handoff", live_n, lang)),
                            "Open note; message not about it.")
    live_tour = draft if (not is_resident and draft and draft["kind"] == "tour_request") else None
    if live_tour:  # an open tour card: its single next step, not a welcome and another tour pitch
        save("tour_request", live_tour)
        still = _missing("tour_request", live_tour)
        step = t("next_step_missing", lang, what=WHAT["tour_request"][lang], label=LABEL[still[0]][lang].lower()) \
            if still else t("next_step_ready", lang, what=WHAT["tour_request"][lang])
        if still and still[0] == "area" and (pu := _unknown_place(msg)):
            step = t("unknown_city", lang, area=pu)  # "i meant kalamazoo": the demo's areas, not the same ask (holdout)
        return unproductive(TurnPlan(template=step, functions=["F5"], workflow=workflow, skip_model=True,
                                     action=_proposed("tour_request", live_tour, lang),
                                     chips=CHIPS["lost"][lang]), "Open tour card; message not about it.")
    if workflow.id == "leasing" or (not is_resident and any(r["kind"] == "tour_request" for r in mine)):
        pitch = "" if mem.get("tour_pitched") else " " + t("faq_offer_tour", lang)
        mem["tour_pitched"] = True
        return unproductive(TurnPlan(template=t("leasing_welcome", lang) + pitch, functions=["F4"], workflow=workflow,
                                     chips=CHIPS["prospect_next"][lang]), "Leasing welcome (no details yet).")
    live_m = draft if (draft and draft["kind"] == "maintenance_request" and not draft.get("declined")) else None
    if live_m and is_resident:  # A-4 / D-8: an open repair card never disappears behind the generic menu
        save("maintenance_request", live_m)
        step, step_chips = _next_step(live_m, lang)
        lead = t("q_unknown_card", lang) + " " if _QUESTIONISH_END.search(msg) else ""
        return unproductive(TurnPlan(template=lead + step, functions=["F7"], workflow=workflow, skip_model=True,
                                     action=_proposed("maintenance_request", live_m, lang),
                                     chips=step_chips or CHIPS["lost"][lang]),
                            "Open repair card; message not about it.")
    if is_resident:
        return unproductive(TurnPlan(template=t("resident_general", lang), functions=[], workflow=workflow,
                                     chips=CHIPS["resident_next"][lang] if verified else ["Talk to the office"]),
                            "General resident menu.")
    if says_resident(msg):
        return done(TurnPlan(template=t("guest_resident", lang), functions=[], workflow=workflow,
                             chips=["Ask a general question"] if lang == "en" else []))
    key = "unclear" if "low_confidence" in flags and gate.audience != "unknown" else "who_are_you"
    return unproductive(TurnPlan(template=t(key, lang), functions=[], workflow=workflow,
                                 chips=CHIPS["who"][lang] if key == "who_are_you" else []), f"Fallback ({key}).")


def synthesize_handoff(gate: GateDecision, ctx: SafeContext, category: str, team: str, reason: str
                       ) -> HandoffRecommendation:
    """Handoff record for routes decided by the planner (vendor, steering, language) rather than the gate."""
    from app.handoff import NOT_SENT

    return HandoffRecommendation(team=team, priority="normal", category=category, reasons=[reason],  # type: ignore[arg-type]
                                 summary=f"{gate.audience.capitalize()} · {gate.intent} · {reason}",
                                 included_fields=sorted({f.name for f in ctx.fields}), contact_guidance=None,
                                 delivery_note=NOT_SENT)


_SUMMARY_KEYS = {"maintenance_request": ("issue", "location", "entry"), "tour_request": ("area", "days", "time"),
                 "staff_handoff": ("topic",)}


def _saved_summary(rec: dict[str, Any]) -> str:
    """'Community or city: Heron Lake Apartments; Preferred days: Saturday' from a saved record's own fields."""
    keys = _SUMMARY_KEYS.get(rec.get("kind", ""), ())
    parts = [f"{f.get('label')}: {f.get('value')}" for k in keys for f in rec.get("fields", [])
             if f.get("key") == k and f.get("value")]
    return "; ".join(parts)


_KB_ES = {"housing vouchers": "vales de vivienda", "rent prices": "precios de renta", "availability": "disponibilidad",
          "floor plans": "planos", "the pet policy": "la política de mascotas", "parking": "estacionamiento",
          "amenities": "amenidades", "laundry": "lavandería", "utilities": "servicios",
          "how to apply": "cómo solicitar",
          "office hours": "horario de la oficina", "the neighborhood": "el vecindario",
          "fees and deposits": "cargos y depósitos", "waitlists": "listas de espera"}


def _kb_label(label: str, lang: Lang) -> str:
    return _KB_ES.get(label, label) if lang == "es" else label


def _questions_text(labels: list[str], lang: Lang) -> str:
    return ", ".join(_kb_label(x, lang) for x in labels)[:240]


def _faq_text(topics: list[Any], lang: Lang) -> str:
    approved = [tp for tp in topics if tp.status == "approved"]
    live = [tp for tp in topics if tp.status == "live_data_unavailable"]
    pending = [tp for tp in topics if tp.status == "pending_approval"]
    parts = [(tp.answer_es if lang == "es" and tp.answer_es else tp.answer) for tp in approved]
    if live and pending:  # Sprint 9: one sentence and one referral, not two stacked "I won't guess" paragraphs
        parts.append(t("faq_live_and_pending", lang, live=(" and " if lang == "en" else " y ").join(
            _kb_label(tp.label, lang) for tp in live), pending=(" or " if lang == "en" else " o ").join(
            _kb_label(tp.label, lang) for tp in pending)))
        return " ".join(p for p in parts if p)
    if live:
        parts.append(t("faq_live_unavailable", lang, topics=(" and " if lang == "en" else " y ").join(
            _kb_label(tp.label, lang) for tp in live)))
    if pending:
        parts.append(t("faq_pending", lang, topics=(" or " if lang == "en" else " o ").join(
            _kb_label(tp.label, lang) for tp in pending)))
    return " ".join(p for p in parts if p)


# ---- confirmation ------------------------------------------------------------------------------------------


def confirm(store: Store | None, session_id: str, persona_id: str | None, kind: ActionKind, ctx: SafeContext,
            lang: Lang = "en") -> ActionResult:
    """Write the server-side draft for this session after the person confirmed it (atomic: one record at most)."""
    pkey = persona_id or "none"
    draft = store.get_draft(session_id, pkey) if store else None
    if not draft or draft.get("kind") != kind:
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION",
                            message="There's nothing waiting to be sent. Tell me what you need and I'll set it up.")
    lang = draft.get("lang", lang)  # type: ignore[assignment]
    if kind == "maintenance_request" and not _verified(ctx):
        return ActionResult(ok=False, error_code="NOT_AUTHORIZED",
                            message="Repair requests need a signed-in resident account.")
    missing = _missing(kind, draft)
    if missing:
        return ActionResult(ok=False, error_code="INCOMPLETE", action=_proposed(kind, draft, lang),
                            message=t("send_missing", lang, missing=", ".join(LABEL[m][lang].lower() for m in missing)))
    assert store is not None
    taken = store.take_draft(session_id, pkey, kind)
    if taken is None:  # a concurrent confirm already took it
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION",
                            message="That was already sent. Ask me for its status anytime.")
    if dup := wf.duplicate_of(store.records(session_id=session_id, limit=50), kind, taken, persona_id):
        # Sprint 6: idempotent save (checked after the atomic take, so concurrent confirms still write at most one).
        # The same request is already saved in this chat: show that record, never write it twice.
        rec0 = PrototypeRecord.model_validate(dup)
        action0 = _proposed(kind, taken, lang).model_copy(update={
            "stage": "submitted", "record": rec0, "confirm_label": None, "missing": [],
            "note": CARD_NOTE["saved"][kind][lang]})
        return ActionResult(ok=True, error_code="ALREADY_SAVED", action=action0, record=rec0,
                            message=t("already_saved", lang, what=WHAT[kind][lang].capitalize(), ref=rec0.id))
    own_any = store.records(persona_id=persona_id, kind=kind, limit=200) if (persona_id and _verified(ctx) and
                                                                            kind == "maintenance_request") else []
    if near := wf.near_duplicate_of(store.records(session_id=session_id, limit=50), kind, taken, persona_id) or \
            wf.near_duplicate_of([r for r in own_any if r.get("status") == "submitted_for_review" and mh.match_score(
                str(taken.get("fields", {}).get("issue", {}).get("value") or ""), _rec_issue(r)) > 0], kind, taken,
                                 persona_id):  # Sprint 8 C: an open request from an earlier session counts too
        # Sprint 7 invariant: never a second record for the same repair unless the person says it's a different one
        store.save_draft(session_id, pkey, kind, {**taken, "stale": False})  # put it back, unsent
        return ActionResult(ok=False, error_code="POSSIBLE_DUPLICATE", action=_proposed(kind, taken, lang),
                            message=t("near_duplicate", lang, ref=near["id"]))
    rec = _write(store, kind, session_id, persona_id, taken, lang)
    if rec is None:
        store.save_draft(session_id, pkey, kind, taken)  # put it back: nothing was saved
        return ActionResult(ok=False, error_code="SAVE_FAILED", action=_proposed(kind, draft, lang),
                            message="Sorry, that didn't save, so nothing was sent. Please try again, or contact the "
                                    "office directly.")
    action = _proposed(kind, taken, lang).model_copy(update={
        "stage": "submitted", "record": rec, "confirm_label": None, "missing": [],
        "note": CARD_NOTE["saved"][kind][lang]})
    when = tour_when(taken, lang) if kind == "tour_request" else ""
    message = CONFIRM[kind][lang].format(id=rec.id, when=t("tour_saved_when", lang, when=when) if when else "")
    if kind == "maintenance_request" and (taken.get("repeat_history") or {}).get("count"):
        message += t("repeat_history_saved", lang)  # Sprint 8 C: on the prototype record; nobody is notified
    if kind == "staff_handoff":
        tf = taken.get("fields", {})
        said = str((tf.get("message") or {}).get("value") or "")
        has_details = any((tf.get(k) or {}).get("value") for k in ("earlier", "questions", "budget")) or bool(
            taken.get("parked")) or (len(said.split()) > 8) or (bool(said) and not _is_quick_action(said)
                                                                and not und.requests_human(said))
        if not has_details:  # never claim "with the details" when the note holds none of the person's own
            message = CONFIRM["staff_handoff_plain"][lang].format(id=rec.id)
    if kind == "staff_handoff" and (back := taken.get("parked")):  # W-4: the card the note parked comes back
        store.save_draft(session_id, pkey, back["kind"], {**back, "stale": False, "lang": lang})
        message += t("parked_back", lang, what=WHAT[back["kind"]][lang])
    elif kind == "staff_handoff" and (qt := taken.get("queued_tour")):
        # Sprint 7: the tour the person asked for while the note was open opens now, with what they said
        nxt_t: dict[str, Any] = {"fields": {}, "lang": lang, "stale": False, "team": "leasing", "priority": "normal",
                                 "category": "leasing_follow_up", "summary": "Tour request (prototype)."}
        for k, v in qt.items():
            if k != "requested":
                _set(nxt_t, k, v, "you_said")
        store.save_draft(session_id, pkey, "tour_request", nxt_t)
        message += t("tour_after_note", lang)
    queued = [q for q in (taken.get("queued") or []) if q]
    if kind == "maintenance_request" and (qn := taken.get("queued_note")) and not queued:
        # Sprint 7: the request for a person from the same message opens now, citing the repair just saved
        note = {**qn, "stale": False, "lang": lang}
        _set(note, "earlier", f"{rec.id} · {taken.get('fields', {}).get('issue', {}).get('value') or ''}"[:240],
             "you_said")
        store.save_draft(session_id, pkey, "staff_handoff", note)
        message += t("queued_other_next", lang, topic=qn.get("queued_topic") or "")
    elif kind == "maintenance_request" and queued:  # the next problem waits as a card the person can start with "yes"
        from app.templates import t as tmpl
        nxt = {"fields": {}, "lang": lang, "stale": True, "queued": queued[1:]}
        _set(nxt, "issue", queued[0][0].upper() + queued[0][1:], "you_said")
        if room := extract_location(queued[0]):  # Sprint 6: "the bathroom exhaust fan" already says where
            _set(nxt, "location", _tr(room, lang), "you_said")
        if entry_f := taken.get("fields", {}).get("entry"):  # asked once for this visit; not again
            nxt["fields"]["entry"] = entry_f
        if taken.get("queued_note"):
            nxt["queued_note"] = taken["queued_note"]  # the note waits until the last queued problem
        store.save_draft(session_id, pkey, kind, nxt)
        message += tmpl("multi_next", lang, next=queued[0][0].lower() + queued[0][1:])
    return ActionResult(ok=True, message=message, action=action, record=rec)


def resident_for(persona_id: str | None, wb: Workbook | None) -> Resident | None:
    from app.personas import FIXTURE_RESIDENTS

    if not persona_id:
        return None
    if persona_id in FIXTURE_RESIDENTS:
        return FIXTURE_RESIDENTS[persona_id]
    if wb and persona_id in wb.residents:
        return wb.residents[persona_id]
    return None


__all__ = ["TurnPlan", "plan_turn", "confirm", "status_items", "resident_for", "identity_note", "datetime"]
