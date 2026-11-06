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

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.context import Resident, Workbook
from app.db import Store
from app.handoff import build_handoff
from app.intake import (
    describes_issue,
    extract_area,
    extract_beds,
    extract_days,
    extract_entry,
    extract_location,
    extract_time_of_day,
    infer_location,
    is_affirmative,
    is_change_request,
    is_decline,
    is_sms_opt_out,
    is_staff_request,
    is_status_request,
    is_steering_question,
    is_tour_request,
    is_vendor_contact,
    match_faq,
    non_latin_script,
    says_resident,
    strip_greeting,
)
from app.models import (
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
from app.safety import redact, sanitize_field
from app.templates import CHIPS, CONFIRM, CONFIRM_LABEL, PROTOTYPE_NOTE, Lang, t
from app.workflows import LABELS, WORKFLOW_VERSION

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
    "topic": {"en": "About", "es": "Tema"},
    "message": {"en": "What you said", "es": "Lo que dijo"},
    "who": {"en": "Account", "es": "Cuenta"},
    "earlier": {"en": "Details so far", "es": "Detalles hasta ahora"},
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
    "fair_housing_or_legal": "Accommodation, fair housing or legal question",
    "leasing_follow_up": "Leasing follow-up", "sensitive_data_request": "Account or sensitive information",
    "other": "Needs a team member", "none": "General question",
}
TEAM_LABEL = {"emergency_maintenance": "Emergency maintenance", "maintenance": "Maintenance",
              "leasing": "Leasing", "accounting": "Accounting", "management": "Property management"}


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
    "Outside or common area": "Afuera o área común", "Heating / cooling system": "Calefacción / aire acondicionado",
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


def _field(key: str, value: str | None, source: str, lang: Lang) -> ActionField:
    return ActionField(key=key, label=LABEL[key][lang], value=value, source=source if value else "missing")  # type: ignore[arg-type]


def _draft_fields(draft: dict[str, Any], lang: Lang) -> list[ActionField]:
    return [ActionField(key=k, label=LABEL[k][lang] if k in LABEL else k, value=v["value"], source=v["source"])
            for k, v in draft.get("fields", {}).items()]


def _missing(kind: ActionKind, draft: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED[kind] if not draft.get("fields", {}).get(k, {}).get("value")]


def _proposed(kind: ActionKind, draft: dict[str, Any], lang: Lang) -> ProposedAction:
    missing = _missing(kind, draft)
    stage = "ready" if not missing else "collecting"
    if kind == "maintenance_request":
        note = ("Sending saves it in the prototype for staff review before anything is scheduled. "
                + PROTOTYPE_NOTE[lang])
    elif kind == "tour_request":
        note = "This is a request, not a booking: the leasing team picks the time. " + PROTOTYPE_NOTE[lang]
    else:
        note = "The office sees this note, so you won't have to repeat yourself. " + PROTOTYPE_NOTE[lang]
    if lang == "es":
        note = PROTOTYPE_NOTE["es"]
    return ProposedAction(kind=kind, stage=stage, title=TITLE[kind][lang], fields=_draft_fields(draft, lang),
                          missing=[LABEL[m][lang] for m in missing],
                          confirm_label=CONFIRM_LABEL[kind][lang] if stage == "ready" else None, note=note)


def _set(draft: dict[str, Any], key: str, value: str | None, source: str) -> bool:
    """Set a slot when a value was extracted. Returns True when something changed."""
    if not value:
        return False
    fields = draft.setdefault("fields", {})
    if fields.get(key, {}).get("value") == value:
        return False
    fields[key] = {"value": value, "source": source}
    return True


# ---- status lookup (F8) ---------------------------------------------------------------------------------


def status_items(store: Store | None, resident: Resident | None, persona_id: str) -> list[StatusItem]:
    """Open items for a VERIFIED resident: prototype requests first, then open maintenance history items.
    Only reference, short subject, status and opened date. Entry windows and notes are never included."""
    items: list[StatusItem] = []
    if store:
        for r in store.records(persona_id=persona_id, kind="maintenance_request", limit=10):
            items.append(StatusItem(reference=r["id"], title=r.get("title", "Repair request"),
                                    status=r.get("status_label", "Submitted"), opened=r["created_at"][:10],
                                    source="prototype_store",
                                    note="Submitted through this assistant (prototype)."))
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


def _write(store: Store | None, kind: ActionKind, session_id: str, persona_id: str | None, draft: dict[str, Any],
           lang: Lang) -> PrototypeRecord | None:
    """Write a confirmed draft. Returns None (and logs the error type only) when the write fails."""
    if store is None:
        return None
    fields = [f.model_dump() for f in _draft_fields(draft, lang)]
    if kind == "maintenance_request":
        status, label = "submitted_for_review", "Submitted, waiting for staff review"
        issue = draft["fields"].get("issue", {}).get("value", "Repair request")
        title = (issue[:57] + "…") if len(issue) > 58 else issue
    elif kind == "tour_request":
        status, label = "requested", "Requested; leasing team to confirm a time"
        title = f"Tour of {draft['fields'].get('area', {}).get('value', 'a community')}"
    else:
        urgent = draft.get("priority") == "urgent"
        status = "urgent_queued" if urgent else "queued"
        label = "Urgent; in the office queue" if urgent else "In the office queue"
        title = draft.get("topic", "Note for the office")
    data = {"status": status, "status_label": label, "title": title, "summary": draft.get("summary", title),
            "fields": fields, "team": draft.get("team"), "priority": draft.get("priority"),
            "category": draft.get("category"), "repeat": draft.get("repeat", False)}
    try:
        return _record(store, kind, session_id, persona_id, data)
    except Exception as e:  # never claim success for a failed write
        log.warning("prototype write failed: %s", type(e).__name__)
        return None


def _handoff_draft(gate: GateDecision, handoff: HandoffRecommendation | None, ctx: SafeContext, msg: str,
                   lang: Lang, earlier: dict[str, Any] | None, topic: str | None = None) -> dict[str, Any]:
    category = handoff.category if handoff else "human_requested"
    team = handoff.team if handoff else "management"
    topic = topic or TOPIC_LABEL.get(category, "Needs a team member")
    draft: dict[str, Any] = {"fields": {}, "team": team, "priority": handoff.priority if handoff else "normal",
                             "category": category, "topic": topic,
                             "summary": handoff.summary if handoff else f"{gate.audience} · {gate.intent}"}
    _set(draft, "topic", f"{topic}, for the {TEAM_LABEL.get(team, team).lower()} team", "assistant")
    snippet = redact(msg)
    _set(draft, "message", (snippet[:157] + "…") if len(snippet) > 160 else snippet, "you_said")
    _set(draft, "who", _who(ctx), "on_file" if _verified(ctx) else "assistant")
    if earlier and earlier.get("kind") == "maintenance_request":
        bits = [v["value"] for k, v in earlier.get("fields", {}).items() if k in ("issue", "location")]
        _set(draft, "earlier", " · ".join(bits) or None, "you_said")
    contact = _ctx_value(ctx, "preferred_contact_channel")
    note = _ctx_value(ctx, "staff_noted_contact_preference")
    pref = "; ".join(x for x in (_prefers(contact, lang), note) if x)
    if pref:
        _set(draft, "contact", pref, "on_file")
    elif not _verified(ctx) and ctx.persona_kind != "prospect":
        _set(draft, "contact", "Not collected in this prototype. Please also contact the office directly.",
             "assistant")
    return draft


# ---- the planner -------------------------------------------------------------------------------------------


def plan_turn(*, msg: str, gate: GateDecision, workflow: WorkflowSelection, ctx: SafeContext,
              triage: MaintenanceTriage | None, store: Store | None, session_id: str, persona_id: str | None,
              resident: Resident | None, channel: Channel, lang: Lang) -> TurnPlan:
    pkey = persona_id or "none"
    draft = store.get_draft(session_id, pkey) if store else None
    flags = set(gate.risk_flags)
    verified = _verified(ctx)
    is_resident = ctx.audience == "resident"
    handoff = build_handoff(gate, workflow, ctx, False, "", triage, None)
    fns: list[FunctionId] = ["F3"] + (["F2"] if channel in ("sms", "email") else [])

    def done(plan: TurnPlan) -> TurnPlan:
        plan.functions = list(dict.fromkeys(fns + plan.functions))
        return plan

    def handoff_plan(template_key: str, reason: str, wid: WorkflowId = "human_handoff", *,
                     category: str | None = None, team: str | None = None, topic: str | None = None,
                     **kw: str) -> TurnPlan:
        rec = handoff or synthesize_handoff(gate, ctx, category or "other", team or "management", reason)
        if category or team:
            rec = rec.model_copy(update={k: v for k, v in (("category", category), ("team", team)) if v})
        hd = _handoff_draft(gate, rec, ctx, msg, lang, draft, topic)
        if store:
            store.save_draft(session_id, pkey, "staff_handoff", {**hd, "lang": lang})
        return done(TurnPlan(template=t(template_key, lang, **kw), functions=["F9"], workflow=_sel(wid, reason),
                             action=_proposed("staff_handoff", hd, lang), force_handoff=True, handoff=rec))

    # 0. SMS opt-out keyword (F2, I-06 draft) — handled before anything else on the SMS channel.
    if channel == "sms" and is_sms_opt_out(msg):
        if store:
            store.clear_draft(session_id, pkey)
        return done(TurnPlan(template=t("sms_opt_out", lang), functions=["F2"], skip_model=True,
                             workflow=_sel("sms_opt_out", "SMS opt-out keyword (I-06 draft list).")))

    # 1. Emergency: deterministic, for every audience, before any draft logic (F6 + F9).
    if gate.urgency == "emergency":
        hd = _handoff_draft(gate, handoff, ctx, msg, lang, draft)
        hd["priority"] = "urgent"
        existing = [r for r in (store.records(session_id=session_id, kind="staff_handoff", limit=20) if store
                                else []) if r.get("status") == "urgent_queued"]
        records = []
        if existing:
            rec = PrototypeRecord.model_validate(existing[0])
        else:
            rec = _write(store, "staff_handoff", session_id, persona_id, hd, lang)
            records = [rec] if rec else []
        if store:
            store.clear_draft(session_id, pkey)
        action = _proposed("staff_handoff", hd, lang)
        template = t("emergency", lang)
        if rec:
            action = action.model_copy(update={
                "stage": "submitted", "record": rec, "confirm_label": None, "title": "Urgent note for staff",
                "note": "Saved as urgent in the prototype staff queue. It does not page or call anyone."})
        else:  # write failed: never say a note was added
            template = re.split(r"(?<=\.) (?=I've added|Dejé)", template)[0] + (
                " Then call your community's emergency maintenance line." if lang == "en" else "")
            action = None
        return done(TurnPlan(template=template, functions=["F6", "F9"], records=records, action=action,
                             workflow=_sel("maintenance", "Emergency indicators: safety first, urgent staff note."),
                             force_handoff=True, handoff=handoff))

    # 2. A ready draft + an unambiguous yes/no from the person.
    if draft and not _missing(draft["kind"], draft) and is_affirmative(msg):
        result = confirm(store, session_id, persona_id, draft["kind"], ctx, lang)
        fn: FunctionId = {"maintenance_request": "F7", "tour_request": "F5", "staff_handoff": "F9"}[draft["kind"]]
        return done(TurnPlan(template=result.message, functions=[fn], action=result.action, skip_model=True,
                             records=[result.record] if result.record else [], consumed_by_draft=True,
                             workflow=_sel({"maintenance_request": "maintenance", "tour_request": "tour_request",
                                            "staff_handoff": "human_handoff"}[draft["kind"]],  # type: ignore[arg-type]
                                           "Person confirmed the read-back.")))
    if draft and is_decline(msg):
        if store:
            store.clear_draft(session_id, pkey)
        return done(TurnPlan(template=t("declined", lang), functions=[], skip_model=True, consumed_by_draft=True,
                             workflow=_sel("general_inquiry", "Person declined the pending action.")))

    # 3. Languages without approved templates → staff.
    if non_latin_script(msg):
        return handoff_plan("other_language", "Language without approved templates: offer a person.",
                            topic="Language support needed")

    # 4. Deterministic routing that must reach staff (vendor, steering, accommodation, sensitive, human, ...).
    if is_vendor_contact(msg) and not verified:
        return handoff_plan("vendor", "Vendor contact (D-06): no resident or access data; route to management.",
                            category="other", team="management", topic="Vendor contact")
    if is_steering_question(msg):
        return handoff_plan("steering", "Fair Housing steering question (I-13 draft neutral redirect).",
                            wid="faq", category="fair_housing_or_legal", team="management",
                            topic="Fair Housing-sensitive question")
    if "sensitive_data_request" in flags:
        return handoff_plan("sensitive", "Sensitive identifiers in chat: redacted; office handles payments.")
    if "fair_housing_or_legal" in flags:
        return handoff_plan("accommodation", "Accommodation / fair-housing / legal topic: trained staff.")
    if is_status_request(msg) and is_resident and not verified:
        return handoff_plan("status_unverified", "Status lookup needs a verified resident (I-10/I-11 draft).")
    if is_staff_request(msg):
        return handoff_plan("handoff_offer", "Person asked to reach the office.", category="human_requested",
                            team="leasing" if not is_resident else None)
    if workflow.id == "human_handoff":
        key = "unclear_twice" if "repeated_low_confidence" in flags else "handoff_offer"
        return handoff_plan(key, workflow.reason)

    # 5. Status lookup (F8) for a verified resident.
    if is_resident and verified and is_status_request(msg):
        items = status_items(store, resident, persona_id or "")
        frustrated = "complaint_or_frustration" in flags
        plan = TurnPlan(template=t("status_some" if items else "status_none", lang), functions=["F8"],
                        status_items=items, skip_model=not frustrated,
                        workflow=_sel("status_lookup", "Verified resident asked about request status."),
                        chips=(["Send a note to the office", "Report a new repair"] if lang == "en"
                               else ["Enviar nota a la oficina", "Reportar una reparación"]))
        if frustrated:
            hd = _handoff_draft(gate, handoff, ctx, msg, lang, draft)
            if store:
                store.save_draft(session_id, pkey, "staff_handoff", {**hd, "lang": lang})
            plan.action, plan.force_handoff, plan.handoff = _proposed("staff_handoff", hd, lang), True, handoff
            plan.template = t("frustrated", lang) + " " + t("status_some_short" if items else "status_none", lang)
            plan.chips = []
            plan.functions.append("F9")
        return done(plan)

    if is_resident and verified and is_change_request(msg):
        return handoff_plan("maint_change", "Change/cancel request: I-24 rules not approved, staff handle it.",
                            topic="Change or cancel an existing request")

    # 6. Maintenance intake (F6) and the work-order draft (F7).
    in_maint_draft = bool(draft and draft["kind"] == "maintenance_request")
    location, entry = extract_location(msg), extract_entry(msg)
    answers_draft = in_maint_draft and (location or entry or gate.intent in ("general", "maintenance"))
    if workflow.id == "maintenance" or answers_draft:
        if not is_resident:
            return done(TurnPlan(template=t("maint_guest", lang), functions=["F6"], chips=CHIPS["who"][lang],
                                 workflow=_sel("maintenance", "Maintenance from someone not signed in.")))
        if not verified:
            return handoff_plan("maint_unverified", "Maintenance from an unmatched resident: office takes it.",
                                wid="maintenance")
        d = draft if in_maint_draft else {"fields": {}}
        assert d is not None
        new_issue = workflow.id == "maintenance" and describes_issue(msg) and not (location and len(msg) < 25)
        if new_issue and (not d["fields"].get("issue") or not in_maint_draft):
            _set(d, "issue", strip_greeting(redact(msg))[:200], "you_said")
        _set(d, "location", _tr(location, lang), "you_said")
        if not d["fields"].get("location") and (guess := infer_location(msg)):
            _set(d, "location", _tr(guess, lang), "assistant")
        if not d["fields"].get("location") and triage and triage.category == "hvac":
            _set(d, "location", _tr("Heating / cooling system", lang), "assistant")
        _set(d, "entry", _tr(entry, lang), "you_said")
        if not d["fields"].get("contact"):
            contact = _ctx_value(ctx, "preferred_contact_channel")
            note = _ctx_value(ctx, "staff_noted_contact_preference")
            _set(d, "contact", "; ".join(x for x in (_prefers(contact, lang), note) if x) or None, "on_file")
        window = _ctx_value(ctx, "preferred_entry_window")
        if window and not d["fields"].get("entry_window"):
            _set(d, "entry_window", window, "on_file")
        repeat = bool(triage and triage.level == "repeat") or d.get("repeat", False)
        d.update(repeat=repeat, team=handoff.team if handoff else "maintenance",
                 priority=handoff.priority if handoff else ("high" if gate.urgency == "high" else "normal"),
                 category=triage.category if triage else d.get("category", "other"),
                 summary=handoff.summary if handoff else "Resident repair request (prototype).")
        if repeat:
            _set(d, "priority_note", "Repeat issue: manager review" if lang == "en"
                 else "Problema repetido: revisión de gerente", "assistant")
        if store:
            store.save_draft(session_id, pkey, "maintenance_request", {**d, "lang": lang})
        missing = _missing("maintenance_request", d)
        if not missing:
            key = "maint_ready_repeat" if repeat else "maint_ready"
            chips: list[str] = []
        else:
            key = {"issue": "maint_ask_issue", "location": "maint_ask_location", "entry": "maint_ask_entry"}[
                missing[0]]
            chips = {"location": CHIPS["locations"][lang], "entry": CHIPS["entry"][lang]}.get(missing[0], [])
        template = t(key, lang)
        if not missing and repeat and d.get("repeat_acknowledged"):
            template = t("maint_ready", lang)
        if repeat and missing and not d.get("repeat_acknowledged"):
            template = t("maint_repeat_ack", lang) + " " + template
            d["repeat_acknowledged"] = True
            if store:
                store.save_draft(session_id, pkey, "maintenance_request", {**d, "lang": lang})
        if "complaint_or_frustration" in flags and not repeat:
            template = t("frustrated", lang) + " " + template
        if triage and triage.approved_troubleshooting and not repeat and missing:
            pass  # approved tips are passed to the model via the workflow section; the template stays short
        return done(TurnPlan(template=template, functions=["F6", "F7"] + (["F9"] if gate.requires_human else []),
                             action=_proposed("maintenance_request", d, lang), chips=chips,
                             consumed_by_draft=answers_draft and workflow.id != "maintenance",
                             workflow=_sel("maintenance", "Maintenance intake for a verified resident."),
                             force_handoff=repeat, handoff=handoff))

    # 7. Tour request (F5) for prospects and visitors.
    in_tour_draft = bool(draft and draft["kind"] == "tour_request")
    tour_slots = {"area": extract_area(msg), "days": extract_days(msg), "time": extract_time_of_day(msg),
                  "beds": extract_beds(msg)}
    answers_area = bool(in_tour_draft and draft and _missing("tour_request", draft)[:1] == ["area"]
                        and len(msg.strip()) <= 40 and not is_staff_request(msg))
    if not is_resident and (is_tour_request(msg) or (in_tour_draft and (any(tour_slots.values()) or answers_area))):
        d = draft if in_tour_draft else {"fields": {}}
        assert d is not None
        was_ready = in_tour_draft and not _missing("tour_request", d)
        if not d["fields"].get("area") and (area := _ctx_value(ctx, "interest_area")):
            _set(d, "area", area, "on_file")
        if not d["fields"].get("beds") and (beds := _ctx_value(ctx, "desired_floor_plan")):
            _set(d, "beds", beds.replace("two-bed", "2 beds"), "on_file")
        if (in_tour_draft and _missing("tour_request", d)[:1] == ["area"] and not any(tour_slots.values())
                and 1 < len(msg.strip()) <= 40 and not is_tour_request(msg)):
            tour_slots["area"] = msg.strip().strip(".!?").title()  # bare answer to "which city or community?"
        changed = [k for k, v in tour_slots.items() if _set(d, k, v, "you_said")]
        d.update(team="leasing", priority="normal", category="leasing_follow_up",
                 summary=f"Tour request from {_who(ctx).lower()}.")
        if store:
            store.save_draft(session_id, pkey, "tour_request", {**d, "lang": lang})
        missing = _missing("tour_request", d)
        if missing:
            key = {"area": "tour_ask_area", "days": "tour_ask_days", "time": "tour_ask_time"}[missing[0]]
            chips = {"days": CHIPS["tour_days"][lang], "time": CHIPS["tour_time"][lang]}.get(missing[0], [])
        else:
            key, chips = ("tour_updated" if was_ready and changed else "tour_ready"), []
        faq = match_faq(msg)
        prefix = _faq_text(faq, lang) + " " if faq else ""
        if not in_tour_draft and key in ("tour_ask_days", "tour_ask_time"):
            prefix += t("tour_start", lang) + " "
        return done(TurnPlan(template=prefix + t(key, lang), functions=["F5"] + (["F4"] if faq else []),
                             action=_proposed("tour_request", d, lang), chips=chips,
                             consumed_by_draft=in_tour_draft and not is_tour_request(msg),
                             workflow=_sel("tour_request", "Tour request from a prospect or visitor.")))

    # 8. Renewal (no artifact module; routed through F9 to leasing).
    if workflow.id == "renewal":
        contact = _ctx_value(ctx, "preferred_contact_channel")
        suffix = (f" and noted that you prefer {contact}" if lang == "en" else f" y anoté que prefiere {contact}"
                  ) if contact else ""
        return handoff_plan("renewal", workflow.reason, wid="renewal", contact=suffix, topic="Renewal question")

    # 9. FAQ (F4) — approved answers only.
    faq = match_faq(msg)
    if faq:
        chips = CHIPS["prospect_next"][lang] if not is_resident else CHIPS["resident_next"][lang]
        return done(TurnPlan(template=_faq_text(faq, lang), functions=["F4"], chips=chips,
                             workflow=_sel("faq", "Question matched the FAQ topic list (I-12 draft).")))

    # 10. Any remaining deterministic handoff need (frustration, owed follow-up, voucher, lease/billing).
    if gate.requires_human:
        key = "frustrated" if "complaint_or_frustration" in flags else "handoff_offer"
        return handoff_plan(key, "Backend gate requires a person: " + (gate.handoff_reason or "staff review"),
                            wid=workflow.id)

    # 11. Leasing without a tour ask, resident general help, or unknown visitor.
    if workflow.id == "leasing":
        return done(TurnPlan(template=t("leasing_welcome", lang), functions=["F4"], workflow=workflow,
                             chips=CHIPS["prospect_next"][lang]))
    if is_resident:
        return done(TurnPlan(template=t("resident_general", lang), functions=[], workflow=workflow,
                             chips=CHIPS["resident_next"][lang] if verified else ["Talk to the office"]))
    if says_resident(msg):
        return done(TurnPlan(template=t("guest_resident", lang), functions=[], workflow=workflow,
                             chips=["Ask a general question"] if lang == "en" else []))
    key = "unclear" if "low_confidence" in flags and gate.audience != "unknown" else "who_are_you"
    return done(TurnPlan(template=t(key, lang), functions=[], workflow=workflow,
                         chips=CHIPS["who"][lang] if key == "who_are_you" else []))


def synthesize_handoff(gate: GateDecision, ctx: SafeContext, category: str, team: str, reason: str
                       ) -> HandoffRecommendation:
    """Handoff record for routes decided by the planner (vendor, steering, language) rather than the gate."""
    from app.handoff import NOT_SENT

    return HandoffRecommendation(team=team, priority="normal", category=category, reasons=[reason],  # type: ignore[arg-type]
                                 summary=f"{gate.audience.capitalize()} · {gate.intent} · {reason}",
                                 included_fields=sorted({f.name for f in ctx.fields}), contact_guidance=None,
                                 delivery_note=NOT_SENT)


def _faq_text(topics: list[Any], lang: Lang) -> str:
    approved = [tp for tp in topics if tp.status == "approved"]
    live = [tp for tp in topics if tp.status == "live_data_unavailable"]
    pending = [tp for tp in topics if tp.status == "pending_approval"]
    parts = [(tp.answer_es if lang == "es" and tp.answer_es else tp.answer) for tp in approved]
    if live:
        parts.append(t("faq_live_unavailable", lang, topics=" and ".join(tp.label for tp in live)))
    if pending:
        parts.append(t("faq_pending", lang, topics=" or ".join(tp.label for tp in pending)))
    return " ".join(p for p in parts if p)


# ---- confirmation ------------------------------------------------------------------------------------------


def confirm(store: Store | None, session_id: str, persona_id: str | None, kind: ActionKind, ctx: SafeContext,
            lang: Lang = "en") -> ActionResult:
    """Write the server-side draft for this session after the person confirmed it."""
    pkey = persona_id or "none"
    draft = store.get_draft(session_id, pkey) if store else None
    if not draft or draft.get("kind") != kind:
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION",
                            message="There's nothing waiting to be sent. Tell me what you need and I'll set it up.")
    if kind == "maintenance_request" and not _verified(ctx):
        return ActionResult(ok=False, error_code="NOT_AUTHORIZED",
                            message="Repair requests need a signed-in resident account.")
    missing = _missing(kind, draft)
    if missing:
        return ActionResult(ok=False, error_code="INCOMPLETE", action=_proposed(kind, draft, lang),
                            message="A few details are still missing: " + ", ".join(LABEL[m][lang] for m in missing))
    rec = _write(store, kind, session_id, persona_id, draft, lang)
    if rec is None:
        return ActionResult(ok=False, error_code="SAVE_FAILED", action=_proposed(kind, draft, lang),
                            message="Sorry, that didn't save, so nothing was sent. Please try again, or contact the "
                                    "office directly.")
    assert store is not None
    store.clear_draft(session_id, pkey)
    action = _proposed(kind, draft, lang).model_copy(update={
        "stage": "submitted", "record": rec, "confirm_label": None, "missing": [],
        "note": PROTOTYPE_NOTE[lang]})
    return ActionResult(ok=True, message=CONFIRM[kind][lang].format(id=rec.id), action=action, record=rec)


def session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()[:10]


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
