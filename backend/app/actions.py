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
    appliance_in,
    asks_for_promise,
    asks_for_spanish,
    bare_area_answer,
    community_in,
    describes_issue,
    extract_area_correction,
    extract_beds,
    extract_clock_preference,
    extract_contact_pref,
    extract_days,
    extract_entry,
    extract_issue_swap,
    extract_location,
    extract_location_change,
    extract_move_in,
    extract_pets,
    extract_time_of_day,
    frustration_only,
    infer_location,
    is_affirmative,
    is_after_send_question,
    is_bare_no,
    is_bare_yes,
    is_booking_question,
    is_cancel_submitted,
    is_change_request,
    is_decline,
    is_eviction_worry,
    is_issue_description,
    is_noise_complaint,
    is_phone_question,
    is_sms_opt_out,
    is_staff_request,
    is_status_request,
    is_steering_question,
    is_tour_request,
    is_vendor_contact,
    match_faq,
    non_latin_script,
    policy_topic,
    says_resident,
    states_price_claim,
    steering_kind,
    strip_correction_lead,
    strip_greeting,
    unsafe_diy_kind,
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
from app.safety import looks_like_injection, redact, sanitize_field
from app.templates import CHIPS, CONFIRM, CONFIRM_LABEL, DIY_ADVICE, PROTOTYPE_NOTE, Lang, t
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
    "move_in": {"en": "Move-in", "es": "Mudanza"},
    "pets": {"en": "Pets", "es": "Mascotas"},
    "requests": {"en": "Also asked for (office decides)", "es": "También pidió (decide la oficina)"},
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
    "fair_housing_or_legal": "Accommodation or legal question",
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
    missing = [k for k in REQUIRED[kind] if not draft.get("fields", {}).get(k, {}).get("value")]
    if kind == "maintenance_request" and draft.get("vague_issue") and "issue" not in missing:
        missing.insert(0, "issue")  # "it's not working": ask what, once, before where
    return missing


_VAGUE = re.compile(r"\b(not working|isn'?t working|doesn'?t work|stopped working|broken|broke|acting up|messed up|"
                    r"no funciona|se descompuso)\b", re.I)


def _vague_issue(text: str) -> bool:
    from app.context import MAINTENANCE_TOPICS, detect_topics
    return bool(_VAGUE.search(text)) and len(text.split()) <= 5 and not appliance_in(text) and not (
        set(detect_topics(text)) & MAINTENANCE_TOPICS)


def _proposed(kind: ActionKind, draft: dict[str, Any], lang: Lang) -> ProposedAction:
    missing = _missing(kind, draft)
    stage = "ready" if not missing else "collecting"
    note = {"maintenance_request": {"en": "Nothing is sent until you press send. Staff review it before scheduling.",
                                    "es": "No se envía nada hasta que pulse enviar. El personal la revisa antes."},
            "tour_request": {"en": "A request, not a booking: the leasing team picks the time.",
                             "es": "Una solicitud, no una cita: el equipo elige la hora."},
            "staff_handoff": {"en": "Nothing is sent until you press send.",
                              "es": "No se envía nada hasta que pulse enviar."}}[kind][lang]
    return ProposedAction(kind=kind, stage=stage, title=TITLE[kind][lang], fields=_draft_fields(draft, lang),
                          missing=[LABEL[m][lang] for m in missing],
                          confirm_label=CONFIRM_LABEL[kind][lang] if stage == "ready" else None, note=note)


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
                                    note="Sent through this assistant (prototype)."))
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
        status, label = "submitted_for_review", "Submitted, waiting for staff review"
        issue = draft["fields"].get("issue", {}).get("value", "Repair request").split(" Also: ")[0]
        title = issue if len(issue) <= 58 else issue[:58].rsplit(" ", 1)[0] + "…"
    elif kind == "tour_request":
        status, label = "requested", "Requested; leasing team to confirm a time"
        title = f"Tour of {draft['fields'].get('area', {}).get('value', 'a community')}"
    else:
        urgent = draft.get("priority") == "urgent"
        status = "urgent_queued" if urgent else "queued"
        label = "Urgent; in the office queue" if urgent else "In the office queue"
        title = draft.get("topic", "Note for the office")
    return {"status": status, "status_label": label, "title": title, "summary": draft.get("summary", title),
            "fields": fields, "team": draft.get("team"), "priority": draft.get("priority"),
            "category": draft.get("category"), "repeat": draft.get("repeat", False), "hazard": draft.get("hazard")}


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
    if recent and _is_quick_action(msg):  # a tapped button says nothing: carry what the person actually wrote
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
            _set(draft, "message", f"{old_msg} | {draft['fields']['message']['value']}"[:480], "you_said")
        if (old_topic := earlier.get("topic")) and old_topic != topic:
            draft["topic"] = f"{old_topic}; {topic}"
            _set(draft, "topic", f"{draft['topic']}, for the {TEAM_LABEL.get(team, team).lower()} team", "assistant")
        draft["priority"] = _max_priority(earlier.get("priority"), draft["priority"])
    contact = _ctx_value(ctx, "preferred_contact_channel")
    pref = _prefers(contact, lang) or ""  # the channel only: internal staff notes never show on the customer card
    if pref:
        _set(draft, "contact", pref, "on_file")
    elif not _verified(ctx) and ctx.persona_kind != "prospect":
        _set(draft, "contact", "Not collected in this prototype. Please also contact the office directly.",
             "assistant")
    return draft


# ---- the planner -------------------------------------------------------------------------------------------


_SMALL_TALK = re.compile(r"^\s*(?:(?P<hi>hi|hello|hey|hola|good (morning|afternoon|evening)|buenos d[ií]as|buenas)"
                         r"|(?P<thanks>thanks|thank you|thx|ty|gracias|ok(ay)?,? thanks|great,? thanks|cool|great|"
                         r"perfect|awesome|got it)|(?P<bye>bye|goodbye|that'?s all|no thanks|nothing else|i'?m good|"
                         r"adi[oó]s|eso es todo))[\s.!,]*(there|so much|a lot)?[\s.!,]*$", re.I)
_EMERGENCY_FOLLOW = re.compile(r"what (now|next|should i do)|(i'?m|we'?re|i am) (outside|out|safe|ok)|anyone coming|"
                               r"someone coming|is help|ya sal[ií]|alguien viene|y ahora", re.I)
_EMERGENCY_REFUSE = re.compile(
    r"(?:not|n'?t|never) (?:going to |gonna )?(?:leav|go(?:ing)? out|evacuat|get out)\w*|(?:won'?t|wont|can'?t|cant|"
    r"refuse to) (?:leave|go out|get out|evacuate)|just send (?:someone|somebody|help|a tech|maintenance)|"
    r"send (?:someone|somebody|help|a tech) (?:now|over|up)|i'?m (?:fine|ok|okay),? (?:i'?m )?staying|"
    r"staying (?:here|inside|put)|no (?:me )?voy a salir|no (?:quiero|puedo) salir|manden a alguien", re.I)
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


def _max_priority(a: str | None, b: str | None) -> str:
    return max([a or "normal", b or "normal"], key=lambda x: PRIORITY_RANK.get(x, 0))


def _slot_only(message: str) -> bool:
    """True when the message only answers a slot question (room, entry, yes/no), not a new description."""
    rest = re.sub(r"\b(yes|no|ok|okay|sure|the|my|it'?s|its|in|is|a|they|can|may|you|please|actually|wait|"
                  r"kitchen|bathroom|bedroom|living room|laundry|balcony|patio|hallway|come in|enter|first|call|text|"
                  r"contact|me|before|home|when|i'?m|only|don'?t|go|without)\b", " ", message, flags=re.I)
    return len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest)) <= 2


def plan_turn(*, msg: str, gate: GateDecision, workflow: WorkflowSelection, ctx: SafeContext,
              triage: MaintenanceTriage | None, store: Store | None, session_id: str, persona_id: str | None,
              resident: Resident | None, channel: Channel, lang: Lang, recent: list[str] | None = None) -> TurnPlan:
    from app.emergency import LABEL as LABEL_EMERGENCY
    from app.emergency import QUEUE_NOTE, emergency_kind
    from app.emergency import notice as emergency_notice
    from app.templates import NO_CONTACT_SUFFIX  # noqa: F401  (used by confirm)

    persona_id = persona_id or None  # "" from the API means not signed in
    pkey = persona_id or "none"
    draft = store.get_draft(session_id, pkey, include_declined=True) if store else None
    if draft and draft.get("lang") == "es":
        lang = "es"  # a conversation that started in Spanish stays in Spanish ("sí" alone isn't detectable)
    if draft and draft.get("declined"):
        restore = bool(_RESTORE.search(msg)) and len(msg.split()) <= 8 and gate.urgency != "emergency" and not \
            re.search(r"\b(don'?t|do not|not|no)\b", _RESTORE.sub(" ", msg), re.I)
        if draft.get("offered") and is_affirmative(msg) and gate.urgency != "emergency":
            restore = True  # "yes" to "I can pass what you've written to the office"
        if restore and store:
            draft = {k: v for k, v in draft.items() if k != "declined"}
            store.save_draft(session_id, pkey, draft["kind"], {**draft, "stale": False})
            return TurnPlan(template=t("restored", lang), functions=[KIND_FN[draft["kind"]]],
                            action=_proposed(draft["kind"], draft, lang), skip_model=True, consumed_by_draft=True,
                            workflow=_sel(KIND_WF[draft["kind"]], "Person restored a card they had declined."))
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

    def save(kind: str, d: dict[str, Any]) -> None:
        touched["draft"] = True
        if store:
            store.save_draft(session_id, pkey, kind, {**d, "lang": lang, "stale": False})

    def done(plan: TurnPlan) -> TurnPlan:
        plan.functions = list(dict.fromkeys(fns + plan.functions))
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
                     card: bool = True, extra: str = "", **kw: str) -> TurnPlan:
        rec = handoff or synthesize_handoff(gate, ctx, category or "other", team or "management", reason)
        upd = {k: v for k, v in (("category", category), ("team", team)) if v}
        if not is_resident and rec.team == "management" and not team and category not in ("fair_housing_or_legal",):
            upd.setdefault("team", "leasing")  # prospects and visitors are leasing's customers
        rec = rec.model_copy(update=upd) if upd else rec
        hd = _handoff_draft(gate, rec, ctx, msg, lang, draft, topic, recent)
        template = t(template_key, lang, **kw) + extra
        notes = [r for r in mine if r["kind"] == "staff_handoff" and r.get("status") != "urgent_queued"]
        another = bool(re.search(r"\banother note\b|\bnew note\b|otra nota", msg, re.I))
        if card and notes and not draft and not another and template_key in (
                "handoff_offer", "unclear_offer", "status_unverified", "maint_unverified", "balance", "sensitive"):
            return done(TurnPlan(template=t("note_exists", lang, ref=notes[0]["id"]), functions=["F9"],
                                 skip_model=True, consumed_by_draft=True, force_handoff=True, handoff=rec,
                                 chips=["Send another note" if lang == "en" else "Enviar otra nota"],
                                 workflow=_sel(wid, "A note is already with the office; no duplicate.")))
        if not card:  # e.g. Fair Housing steering: neutral redirect only; the flag stays staff-side
            return done(TurnPlan(template=template, functions=["F4", "F9"], workflow=_sel(wid, reason),
                                 force_handoff=True, handoff=rec, chips=CHIPS["prospect_next"][lang]))
        save("staff_handoff", hd)
        return done(TurnPlan(template=template, functions=["F9"], workflow=_sel(wid, reason),
                             action=_proposed("staff_handoff", hd, lang), force_handoff=True, handoff=rec))

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
        kind = emergency_kind(msg) or "other"
        people = kind in ("self_harm", "medical", "personal_safety", "poison", "trapped")
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
        if store:
            store.clear_draft(session_id, pkey)
        touched["draft"] = True
        text = emergency_notice(kind, lang) if kind != "other" else t("emergency", lang).split(" An urgent note")[0]
        action = None
        if rec:
            text += QUEUE_NOTE[lang]
            action = _proposed("staff_handoff", hd, lang).model_copy(update={
                "stage": "submitted", "record": rec, "confirm_label": None,
                "title": "Urgent note for staff" if lang == "en" else "Nota urgente para el personal",
                "note": "Saved as urgent in the prototype staff queue. It does not page or call anyone."})
        return done(TurnPlan(template=text, functions=["F6", "F9"], records=records, action=action,
                             skip_model=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("maintenance", f"Emergency ({kind}): fixed safety text, urgent note.")))

    # 1b. Right after an emergency, short follow-ups keep the safety context.
    urgent_mine = [r for r in mine if r.get("status") == "urgent_queued"]
    if urgent_mine and _EMERGENCY_REFUSE.search(msg):
        from app.emergency import REFUSE_LEAD
        hz = (urgent_mine[-1].get("hazard") or "other")
        steps = emergency_notice(hz, lang) if hz != "other" else t("emergency", lang).split(" An urgent note")[0]
        return done(TurnPlan(template=REFUSE_LEAD[lang] + steps, functions=["F6", "F9"], skip_model=True,
                             consumed_by_draft=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("maintenance", "Resident resisting emergency guidance: repeat it.")))
    if urgent_mine and not (draft and not draft.get("stale")) and (
            _EMERGENCY_FOLLOW.search(msg) or ("low_confidence" in flags and len(msg) < 60 and not is_status_request(msg)
                                              and not extract_entry(msg) and not is_affirmative(msg))):
        return done(TurnPlan(template=t("emergency_follow", lang, ref=urgent_mine[0]["id"]), functions=["F6", "F9"],
                             skip_model=True, consumed_by_draft=True, force_handoff=True, handoff=handoff,
                             workflow=_sel("maintenance", "Follow-up after an emergency report.")))

    # 1b'. Distress that isn't a clear emergency: no forms; the care line (988) is added above the reply.
    from app.emergency import possible_risk
    if possible_risk(msg) == "distress" and not draft:
        return done(TurnPlan(template=t("distress_ack", lang), functions=["F9"], skip_model=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("general_inquiry", "Possible distress: care line, no form.")))

    # 1c. Questions about something already sent: answer plainly, never start a new draft.
    sent = [r for r in mine if r.get("status") != "urgent_queued"]
    if sent and is_after_send_question(msg) and not (draft and not draft.get("stale")):
        r0 = sent[0]
        team = TEAM_LABEL.get(r0.get("team") or "", r0.get("team") or "the team")
        team_txt = (f"the {team.lower()} team" if lang == "en" else f"el equipo de {team.lower()}") \
            if r0.get("team") else ("the team" if lang == "en" else "el equipo")
        return done(TurnPlan(template=t("after_send", lang, what=WHAT[r0["kind"]][lang], ref=r0["id"], team=team_txt),
                             functions=[KIND_FN[r0["kind"]], "F8"], skip_model=True, consumed_by_draft=True,
                             workflow=_sel("status_lookup", "Question about a request already sent in this chat.")))

    # 1c'. "send it" / a follow-up on something already sent in this chat: point to it, don't start over.
    sent_wo = [r for r in sent if r["kind"] == "maintenance_request"]
    send_again = bool(re.search(r"\b(just |please |pls )?(send|submit) (it|that)\b", msg, re.I)) or is_affirmative(msg)
    insist = bool(re.search(r"\b(fix(ed)?|know|still|already|troubleshoot\w*|hurry|asap)\b", msg, re.I)) \
        and not is_issue_description(msg) and not appliance_in(msg)
    new_object = (a := appliance_in(msg)) and sent_wo and a.lower() not in sent_wo[0].get("summary", "").lower() \
        and not any(a.lower() in str(f.get("value", "")).lower() for f in sent_wo[0].get("fields", []))
    cancel_like = is_cancel_submitted(msg) or is_decline(msg) or is_change_request(msg) or is_staff_request(msg)
    if sent and (not draft or draft.get("stale")) and not new_object and not cancel_like and (
            send_again or (sent_wo and (frustration_only(msg) or insist))):
        r0 = sent[0]
        team = TEAM_LABEL.get(r0.get("team") or "", r0.get("team") or "")
        team_txt = (f"the {team.lower()} team" if lang == "en" else f"el equipo de {team.lower()}") if team \
            else ("the team" if lang == "en" else "el equipo")
        lead = t("listening", lang).split(". ")[0] + ". " if not send_again else ""
        return done(TurnPlan(template=lead + t("after_send", lang, what=WHAT[r0["kind"]][lang], ref=r0["id"],
                                               team=team_txt),
                             functions=[KIND_FN[r0["kind"]], "F8"], skip_model=True, consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"][lang],
                             workflow=_sel("status_lookup", "Follow-up on a request already sent in this chat.")))

    # 1d. Unsafe do-it-yourself steps get a plain "please don't" first; a repair request follows if relevant.
    diy = unsafe_diy_kind(msg)
    if diy:
        locals_lead["diy"] = DIY_ADVICE[diy][lang] + " "

    # 2. The open card: consent, decline, correction, or a stale card being re-shown.
    effective = msg
    if draft:
        missing_now = _missing(draft["kind"], draft)
        if not missing_now and is_affirmative(msg):
            if draft.get("stale"):
                save(draft["kind"], draft)
                return done(TurnPlan(template=t("reshow", lang, title=WHAT[draft["kind"]][lang]),
                                     functions=[KIND_FN[draft["kind"]]], action=_proposed(draft["kind"], draft, lang),
                                     skip_model=True, consumed_by_draft=True,
                                     workflow=_sel(KIND_WF[draft["kind"]], "Card was set aside; shown again first.")))
            result = confirm(store, session_id, persona_id, draft["kind"], ctx, lang)
            touched["draft"] = True
            return done(TurnPlan(template=result.message, functions=[KIND_FN[draft["kind"]]], action=result.action,
                                 skip_model=True, records=[result.record] if result.record else [],
                                 consumed_by_draft=True,
                                 workflow=_sel(KIND_WF[draft["kind"]], "Person confirmed the read-back.")))
        if is_decline(msg):
            if store:  # kept (marked declined) so "send it after all" can bring it back once
                store.save_draft(session_id, pkey, draft["kind"], {**draft, "declined": True})
            touched["draft"] = True
            return done(TurnPlan(template=t("declined", lang), functions=[], skip_model=True, consumed_by_draft=True,
                                 chips=CHIPS["after_decline"][lang],
                                 extra_flags=[f"declined:{draft['kind']}"],
                                 workflow=_sel("general_inquiry", "Person declined the pending action.")))
        effective = strip_correction_lead(msg)
        if draft["kind"] == "maintenance_request" and missing_now[:1] == ["entry"]:
            if is_bare_yes(msg):
                effective = "Yes, you can enter"
            elif is_bare_no(msg):
                effective = "Contact me first"
    elif (is_decline(msg) or is_affirmative(msg)) and not mine:
        return done(TurnPlan(template=t("nothing_pending", lang), functions=[], skip_model=True,
                             consumed_by_draft=True, chips=CHIPS["resident_next" if is_resident else "prospect_next"]
                             [lang], workflow=_sel("general_inquiry", "Nothing pending to confirm or cancel.")))

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
        ref = typed.group(0).upper() if unknown and typed else f"{WHAT[ref_rec['kind']][lang]} {ref_rec['id']}"
        verb = "cancel" if re.search(r"cancel|never ?mind|don'?t need|anular|cancelar", msg, re.I) else "change"
        return handoff_plan("maint_change", f"{verb.capitalize()} request for {ref_rec['id']} (I-24 rules not "
                            "approved, staff handle it).",
                            topic=f"{verb.capitalize()} "
                                  f"{typed.group(0).upper() if unknown and typed else ref_rec['id']}",
                            team="leasing" if ref_rec["kind"] == "tour_request" else None, ref=ref,
                            extra=t("unknown_ref", lang, ref=ref) if unknown else "")

    # 6. Deterministic routing that must reach staff.
    recognized = bool(is_status_request(msg) or is_tour_request(msg) or match_faq(msg) or is_staff_request(msg)
                      or gate.intent == "maintenance" or draft)
    if is_vendor_contact(msg) and not verified:
        return handoff_plan("vendor", "Vendor contact (D-06): no resident or access data; route to management.",
                            category="other", team="management", topic="Vendor contact")
    if asks_for_spanish(msg):
        return done(TurnPlan(template=t("spanish_switch", "es"), functions=[], skip_model=True, consumed_by_draft=True,
                             chips=CHIPS["resident_next" if is_resident else "prospect_next"]["es"],
                             workflow=_sel("general_inquiry", "Person asked for Spanish.")))
    if is_steering_question(msg):
        faq_extra = " " + _faq_text([tp for tp in match_faq(msg) if tp.status == "approved"], lang)
        return handoff_plan(steering_kind(msg), "Fair Housing steering question (I-13 draft neutral redirect).",
                            wid="faq", category="fair_housing_or_legal", team="management", card=False,
                            extra=faq_extra.rstrip())
    if "sensitive_data_request" in flags:
        return handoff_plan("sensitive", "Sensitive identifiers in chat: redacted; office handles payments.")
    if "fair_housing_or_legal" in flags and not is_eviction_worry(msg):
        return handoff_plan("accommodation", "Accommodation / fair-housing / legal topic: trained staff.",
                            topic="Accommodation or legal question")
    if is_status_request(msg) and is_resident and not verified:
        return handoff_plan("status_unverified", "Status lookup needs a verified resident (I-10/I-11 draft).")
    if is_resident and verified and is_noise_complaint(msg) and not draft:
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
    hurry = re.search(r"been forever|taking (?:so long|forever|ages)|ask them to hurry|hurry (?:up|them)|still waiting|"
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
    ptopic = policy_topic(msg)
    if ptopic and not match_faq(msg) and not (draft and draft["kind"] == "maintenance_request" and
                                              _missing("maintenance_request", draft)[:1] == ["entry"]
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
    cpref = extract_contact_pref(msg)
    if cpref and is_resident and not (draft and draft["kind"] == "maintenance_request"):
        return handoff_plan("contact_note_offer", "Contact preference change: the office updates the account.",
                            topic="Contact preference change", pref=cpref)
    if is_staff_request(msg) or "explicit_human_request" in flags or "human_requested" in flags:
        return handoff_plan("handoff_offer", "Person asked to reach a person or the office.",
                            category="human_requested", team="leasing" if not is_resident else None)
    if is_eviction_worry(msg) or (draft and draft["kind"] == "staff_handoff" and "financial_or_lease" in flags):
        return handoff_plan("eviction" if is_eviction_worry(msg) else "handoff_offer",
                            "Lease or eviction worry: office explains, assistant decides nothing.",
                            topic="Lease or payment question")
    hard_human = flags & {"explicit_human_request", "unverified_private_request"}
    if workflow.id == "human_handoff" and not ("repeated_low_confidence" in flags and recognized and not hard_human):
        if "repeated_low_confidence" in flags and not hard_human:  # offer, don't file a note nobody asked for
            if store and is_resident and not draft:
                rec_ = handoff or synthesize_handoff(gate, ctx, "other", "management", "Not understood twice")
                hd_ = _handoff_draft(gate, rec_, ctx, msg, lang, None, "Couldn't understand the request", recent)
                store.save_draft(session_id, pkey, "staff_handoff", {**hd_, "lang": lang, "declined": True,
                                                                      "offered": True})
                touched["draft"] = True
            return done(TurnPlan(template=t("unclear_offer", lang), functions=["F9"], skip_model=True,
                                 chips=CHIPS["unclear"][lang] if is_resident else CHIPS["prospect_next"][lang],
                                 workflow=_sel("general_inquiry", "Not understood twice: offer the office, no card.")))
        return handoff_plan("handoff_offer", workflow.reason)

    # 7. Status lookup (F8) for a verified resident.
    if is_resident and verified and is_status_request(msg):
        items = sorted(status_items(store, resident, persona_id or ""),
                       key=lambda i: 0 if "owed" in i.status else 1)
        frustrated = "complaint_or_frustration" in flags
        plan = TurnPlan(template=t("status_some" if items else "status_none", lang), functions=["F8"],
                        status_items=items, skip_model=not frustrated,
                        workflow=_sel("status_lookup", "Verified resident asked about request status."),
                        chips=(["Send a note to the office", "Report a new repair"] if lang == "en"
                               else ["Enviar nota a la oficina", "Reportar una reparación"]))
        if frustrated:
            hd = _handoff_draft(gate, handoff, ctx, msg, lang, draft, topic="Waiting too long on a request")
            save("staff_handoff", hd)
            plan.action, plan.force_handoff, plan.handoff = _proposed("staff_handoff", hd, lang), True, handoff
            plan.template = t("frustrated", lang) + " " + t("status_some_short" if items else "status_none", lang)
            plan.chips = []
            plan.functions.append("F9")
        return done(plan)

    # 8. Maintenance intake (F6) and the work-order draft (F7).
    in_maint_draft = bool(draft and draft["kind"] == "maintenance_request")
    scan = _NEG_SEGMENT.sub(" ", effective)  # "bathroom, not kitchen" -> bathroom
    location, entry = extract_location(scan), extract_entry(effective)
    adds_detail = bool(re.search(r"\b(also note|add (that|this)|note that|mention that|tell them)\b", msg, re.I))
    question_only = msg.strip().endswith("?") and not is_issue_description(msg) and not location and not entry \
        and not adds_detail
    off_topic = bool(match_faq(msg) or is_tour_request(msg) or question_only) and not entry and not location
    answers_draft = in_maint_draft and not off_topic and (location or entry or gate.intent in ("general", "maintenance")
                                                          or len(effective.split()) >= 3)
    if workflow.id == "maintenance" or gate.intent == "maintenance" and is_resident or answers_draft:
        if not is_resident:
            return done(TurnPlan(template=t("maint_guest", lang), functions=["F6"], chips=CHIPS["who"][lang],
                                 workflow=_sel("maintenance", "Maintenance from someone not signed in.")))
        if not verified:
            return handoff_plan("maint_unverified", "Maintenance from an unmatched resident: office takes it.",
                                wid="maintenance", topic="Repair report (account not matched)")
        d = draft if in_maint_draft else {"fields": {}}
        assert d is not None
        effective = re.sub(r"^\W*(?:ok(?:ay)?|so|and|anyway)?[\s,]*(?:back to|about|regarding|re:?) (?:the |my )?",
                           "", effective, flags=re.I) or effective  # "ok, back to the oven" resumes; it isn't a problem
        clean = strip_greeting(redact(effective))
        if looks_like_injection(clean):
            clean = "[flagged: message contained instructions; shown as text] " + clean
        promise = in_maint_draft and asks_for_promise(msg)
        venting = in_maint_draft and frustration_only(msg)
        issue = d["fields"].get("issue", {}).get("value")
        swap = extract_issue_swap(msg) if in_maint_draft and issue else None
        loc_change = extract_location_change(msg) if in_maint_draft else None
        cpref = extract_contact_pref(msg)
        updated_note = ""
        if swap:  # replace, never append; flags from the old problem no longer apply
            _set(d, "issue", swap[:200], "you_said")
            for k in ("repeat", "repeat_acknowledged"):
                d.pop(k, None)
            d["fields"].pop("priority_note", None)
            d["priority"], d["team"] = "normal", "maintenance"
            triage = None
            updated_note = t("issue_updated", lang, issue=swap)
            effective = swap
        if loc_change:
            _set(d, "location", _tr(extract_location(loc_change) or loc_change, lang), "you_said")
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
        elif issue and in_maint_draft and d.get("vague_issue") and not _slot_only(effective):
            _set(d, "issue", f"{issue}: {clean}"[:200], "you_said")  # their own words, once
            d.pop("vague_issue", None)
        elif promise:  # never written into the repair text; shown separately for the office to decide
            prev = d["fields"].get("requests", {}).get("value")
            _set(d, "requests", ((prev + "; ") if prev else "") + clean[:120], "you_said")
        elif venting:
            pass
        elif cpref and not issue and len(msg) - len(cpref) < 25:
            pass
        elif not issue and describes_issue(effective) and (not (_slot_only(effective) and in_maint_draft)
                                                           or is_issue_description(effective)):
            _set(d, "issue", clean[:200], "you_said")
            if _vague_issue(clean):
                d["vague_issue"] = True
        elif issue and in_maint_draft and not _slot_only(effective) and (is_issue_description(effective)
                                                                         or adds_detail) \
                and clean.lower() not in issue.lower():
            _set(d, "issue", (issue + " Also: " + clean)[:400], "you_said")  # new repair details are kept
        if loc_change:
            location = None
        old_loc = d["fields"].get("location", {}).get("value")
        correction = effective != msg or bool(_NEG_SEGMENT.search(msg)) or bool(re.search(r"\binstead\b", msg, re.I))
        if location and old_loc and old_loc != _tr(location, lang) and not correction:
            location = None  # a second room goes into the issue text ("Also: ..."), never replaces the first
        if location and old_loc and old_loc != _tr(location, lang) and d["fields"].get("issue"):
            iv = d["fields"]["issue"]["value"]
            d["fields"]["issue"]["value"] = re.sub(rf"\b{re.escape(old_loc)}\b", _tr(location, lang) or old_loc, iv,
                                                   flags=re.I)
        _set(d, "location", _tr(location, lang), "you_said")
        if not d["fields"].get("location") and (guess := infer_location(effective)):
            _set(d, "location", _tr(guess, lang), "assistant")
        if not d["fields"].get("location") and triage and triage.category == "hvac":
            _set(d, "location", _tr("Heating / cooling system", lang), "assistant")
        _set(d, "entry", _tr(entry, lang), "you_said")
        if not d["fields"].get("contact"):
            contact = _ctx_value(ctx, "preferred_contact_channel")
            _set(d, "contact", _prefers(contact, lang), "on_file")
        window = _ctx_value(ctx, "preferred_entry_window")
        if window and not d["fields"].get("entry_window"):
            _set(d, "entry_window", window, "on_file")
        repeat = bool(triage and triage.level == "repeat") or d.get("repeat", False)
        frustrated = ("complaint_or_frustration" in flags and not swap) or d.get("frustrated", False)
        urgent_wording = (gate.urgency == "high" and not swap) or bool(re.search(  # water from above spreads fast
            r"(?:through|from) the ceiling|ceiling (?:is )?(?:leak|drip)|from upstairs", effective, re.I))
        priority = _max_priority(d.get("priority"), handoff.priority if handoff and not swap else None)
        if repeat or frustrated or urgent_wording:
            priority = _max_priority(priority, "high")
        team = "management" if d.get("team") == "management" or (handoff and handoff.team == "management"
                                                                  and repeat) else "maintenance"
        if repeat and frustrated:
            team = "management"
        d.update(repeat=repeat, frustrated=frustrated, team=team, priority=priority,
                 category=triage.category if triage else d.get("category", "other"),
                 summary=(handoff.summary if handoff else d.get("summary") or "Resident repair request (prototype)."))
        if repeat or frustrated or priority == "high":
            note_txt = ("Repeat issue: manager review" if repeat else "High priority") if lang == "en" else (
                "Problema repetido: revisión de gerente" if repeat else "Prioridad alta")
            _set(d, "priority_note", note_txt, "assistant")
        missing = _missing("maintenance_request", d)
        first_turn = not in_maint_draft
        if not missing:
            key = "maint_ready_repeat" if repeat and not d.get("repeat_acknowledged") else "maint_ready"
            chips: list[str] = []
        else:
            key = {"issue": "maint_ask_what" if d.get("vague_issue") else "maint_ask_issue",
                   "location": "maint_ask_location", "entry": "maint_ask_entry"}[
                missing[0]]
            chips = {"location": CHIPS["locations"][lang], "entry": CHIPS["entry"][lang]}.get(missing[0], [])
        template = t(key, lang)
        if updated_note:
            template = updated_note + (" " + t("maint_ready", lang) if not missing else " " + template)
        elif promise:
            template = t("no_promise", lang) + (" " + template if missing else "")
        elif venting:
            template = t("listening", lang) + (" " + template if missing else "")
        if repeat and missing and not d.get("repeat_acknowledged"):
            template = t("maint_repeat_ack", lang) + " " + template
            d["repeat_acknowledged"] = d["frustration_acknowledged"] = True  # one apology, not two
        elif frustrated and not d.get("frustration_acknowledged"):
            template = t("frustrated_repair", lang) + " " + template
            d["frustration_acknowledged"] = True
        hazard_words = re.search(r"smell|gas|smok|burn|spark|odor|olor|humo", msg, re.I)
        already_tried = re.search(r"\bagain\b|\bstill\b|\d+(st|nd|rd|th) time|(second|third|fourth|fifth) time|"
                                  r"tech (came|was here)|already (tried|checked|did)|otra vez|de nuevo", msg, re.I)
        if repeat and already_tried and not d.get("repeat_heard") and missing:
            template = t("repeat_heard", lang) + " " + template.replace("I'm sorry this is happening again. ", "") \
                .replace("Lamento que vuelva a pasar. ", "")
            d["repeat_heard"] = True
        if first_turn and triage and triage.approved_troubleshooting and not repeat and triage.level == "routine" \
                and not hazard_words and not already_tried and not diy:
            tip = " ".join(triage.approved_troubleshooting)
            template += (" Meanwhile, a few safe checks: " if lang == "en" else " Mientras tanto: ") + tip
        save("maintenance_request", d)
        return done(TurnPlan(template=template, functions=["F6", "F7"] + (["F9"] if gate.requires_human else []),
                             action=_proposed("maintenance_request", d, lang), chips=chips,
                             consumed_by_draft=in_maint_draft and workflow.id != "maintenance",
                             workflow=_sel("maintenance", "Maintenance intake for a verified resident."),
                             force_handoff=repeat or frustrated, handoff=handoff))

    # 9. Tour request (F5) for prospects and visitors.
    in_tour_draft = bool(draft and draft["kind"] == "tour_request")
    tour_mine = [r for r in mine if r["kind"] == "tour_request"]
    if not is_resident and is_booking_question(msg) and (in_tour_draft or tour_mine):
        pref = extract_clock_preference(msg)
        pref_txt = (f"I've noted {pref[1]} as your preference. " if lang == "en"
                    else f"Anoté {pref[1]} como su preferencia. ") if pref else ""
        if in_tour_draft and draft and pref:
            _set(draft, "time", f"{pref[0]} ({pref[1]})", "you_said")
            save("tour_request", draft)
        ref = (f" Your request {tour_mine[0]['id']} is waiting for the leasing team." if lang == "en" else
               f" Su solicitud {tour_mine[0]['id']} está pendiente con el equipo.") if tour_mine and not in_tour_draft \
            else ""
        return done(TurnPlan(template=t("booking_q", lang, pref=pref_txt, ref=ref), functions=["F5"],
                             skip_model=True, consumed_by_draft=True,
                             action=_proposed("tour_request", draft, lang) if in_tour_draft and draft else None,
                             workflow=_sel("tour_request", "Booking or exact-time question: not a booking.")))
    clock = extract_clock_preference(effective)
    tour_slots = {"area": community_in(effective) or extract_area_correction(effective),
                  "days": extract_days(effective),
                  "time": f"{clock[0]} ({clock[1]})" if clock else extract_time_of_day(effective),
                  "beds": extract_beds(effective), "move_in": extract_move_in(effective)}
    if in_tour_draft and draft and not tour_slots["area"] and _missing("tour_request", draft)[:1] == ["area"]:
        tour_slots["area"] = bare_area_answer(effective)
    price_q = any(tp.status != "approved" for tp in match_faq(msg))
    if price_q:
        tour_slots["days"] = None  # "sign today" is not a tour day
    leasing_hint = not is_resident and not price_q and (workflow.id in ("leasing", "general_inquiry") and any(
        tour_slots[k] for k in ("area", "beds", "move_in", "days")) and gate.intent == "leasing" or
        (gate.audience == "unknown" and tour_slots["move_in"]))
    keeps_tour_card = in_tour_draft and (any(tour_slots.values()) or len(effective.strip()) <= 40) and not \
        match_faq(msg)
    guest_place = not is_resident and not draft and not mine and bool(bare_area_answer(effective)) and \
        gate.audience != "resident"
    if guest_place and not tour_slots["area"]:
        tour_slots["area"] = bare_area_answer(effective)
    if not is_resident and (is_tour_request(msg) or keeps_tour_card or leasing_hint or guest_place):
        d = draft if in_tour_draft else {"fields": {}}
        assert d is not None
        was_ready = in_tour_draft and not _missing("tour_request", d)
        if not d["fields"].get("area") and (area := _ctx_value(ctx, "interest_area")):
            if "no community selected" not in area:
                _set(d, "area", area, "on_file")
        if not d["fields"].get("beds") and (beds := _ctx_value(ctx, "desired_floor_plan")):
            _set(d, "beds", beds.replace("two-bed", "2 beds"), "on_file")
        if not d["fields"].get("move_in") and (mi := _ctx_value(ctx, "move_in_timeframe")):
            _set(d, "move_in", mi, "on_file")
        old_area = d["fields"].get("area", {}).get("value")
        changed = [k for k, v in tour_slots.items() if _set(d, k, v, "you_said")]
        if pets := extract_pets(effective):
            _set(d, "pets", pets, "you_said")
        d.update(team="leasing", priority="normal", category="leasing_follow_up",
                 summary=f"Tour request from {_who(ctx).lower()}.")
        save("tour_request", d)
        missing = _missing("tour_request", d)
        if missing:
            key = {"area": "tour_ask_area", "days": "tour_ask_days", "time": "tour_ask_time"}[missing[0]]
            chips = {"days": CHIPS["tour_days"][lang], "time": CHIPS["tour_time"][lang]}.get(missing[0], [])
        else:
            key, chips = ("tour_updated" if was_ready and changed else "tour_ready"), []
        template = t(key, lang)
        if "area" in changed and old_area and was_ready:
            template = t("tour_area_updated", lang, area=d["fields"]["area"]["value"])
        faq = match_faq(msg)
        prefix = _faq_text(faq, lang) + " " if faq else ""
        if not in_tour_draft and key in ("tour_ask_days", "tour_ask_time", "tour_ask_area"):
            prefix += t("leasing_capture" if leasing_hint and not is_tour_request(msg) else "tour_start", lang) + " "
        if key == "tour_ask_area":
            template = t("tour_ask_area", lang).split(". ", 1)[-1] if prefix else template
        return done(TurnPlan(template=prefix + template, functions=["F5"] + (["F4"] if faq else []),
                             action=_proposed("tour_request", d, lang), chips=chips,
                             consumed_by_draft=in_tour_draft and not is_tour_request(msg),
                             workflow=_sel("tour_request", "Tour request from a prospect or visitor.")))

    # 10. Renewal (no artifact module; routed through F9 to leasing).
    if workflow.id == "renewal" or (is_resident and re.search(r"renew|renov", msg, re.I)):
        contact = _ctx_value(ctx, "preferred_contact_channel")
        suffix = (f" and noted that you prefer {contact}" if lang == "en"
                  else f" y anoté que prefiere {_ES_CHANNEL.get(contact.lower(), contact)}") if contact else ""
        return handoff_plan("renewal", workflow.reason, wid="renewal", contact=suffix, topic="Renewal question",
                            team="leasing")

    # 11. FAQ (F4) — approved answers only.
    faq = match_faq(msg)
    if faq:
        chips = CHIPS["prospect_next"][lang] if not is_resident else CHIPS["resident_next"][lang]
        return done(TurnPlan(template=_faq_text(faq, lang) + " " + t("faq_offer_tour" if not is_resident else
                                                                    "resident_general", lang).split(". ")[-1],
                             functions=["F4"], chips=chips,
                             workflow=_sel("faq", "Question matched the FAQ topic list (I-12 draft).")))

    # 12. Any remaining deterministic handoff need (frustration, owed follow-up, voucher, lease/billing).
    if gate.requires_human:
        key = "frustrated" if "complaint_or_frustration" in flags else "handoff_offer"
        return handoff_plan(key, "Backend gate requires a person: " + (gate.handoff_reason or "staff review"),
                            wid=workflow.id)

    # 13. Leasing without slots, resident general help, or unknown visitor.
    if workflow.id == "leasing" or (not is_resident and (draft and draft["kind"] == "tour_request")):
        return done(TurnPlan(template=t("leasing_welcome", lang) + " " + t("faq_offer_tour", lang),
                             functions=["F4"], workflow=workflow, chips=CHIPS["prospect_next"][lang]))
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
    """Write the server-side draft for this session after the person confirmed it (atomic: one record at most)."""
    from app.templates import NO_CONTACT_SUFFIX

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
                            message="A few details are still missing: " + ", ".join(LABEL[m][lang] for m in missing))
    assert store is not None
    taken = store.take_draft(session_id, pkey, kind)
    if taken is None:  # a concurrent confirm already took it
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION",
                            message="That was already sent. Ask me for its status anytime.")
    rec = _write(store, kind, session_id, persona_id, taken, lang)
    if rec is None:
        store.save_draft(session_id, pkey, kind, taken)  # put it back: nothing was saved
        return ActionResult(ok=False, error_code="SAVE_FAILED", action=_proposed(kind, draft, lang),
                            message="Sorry, that didn't save, so nothing was sent. Please try again, or contact the "
                                    "office directly.")
    action = _proposed(kind, taken, lang).model_copy(update={
        "stage": "submitted", "record": rec, "confirm_label": None, "missing": [], "note": PROTOTYPE_NOTE[lang]})
    message = CONFIRM[kind][lang].format(id=rec.id)
    if not _verified(ctx) and ctx.persona_kind != "prospect":
        message += NO_CONTACT_SUFFIX[lang]
    return ActionResult(ok=True, message=message, action=action, record=rec)


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
