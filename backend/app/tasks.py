"""Task controller: the ONE owner of task state and the draft lifecycle.

A conversation has at most one ACTIVE task (the card on screen) plus a list of WAITING tasks (set aside, cancelled,
or paused by an emergency). Everything is stored in the session's single draft row, so the store, the card and the
state can't drift apart.

Operations (all validated here; the language model only *proposes* them):
    start     open a new task; an unfinished active task waits (never lost, never sent)
    update    change fields of the active task
    suspend   set the active task aside
    resume    bring a waiting (or cancelled) task back
    cancel    don't send the active task; it stays restorable, the next waiting task opens
    complete  save the active task as a prototype record: ONLY via `confirm` (the Send button or an explicit typed
              send), never from a model proposal

Nothing here reaches McKinley staff, Yardi or anyone else: records are prototype rows labelled "saved in demo".
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Literal

from app.db import Store
from app.models import STATUS_LABEL, ActionField, ActionKind, ActionResult, ProposedAction, PrototypeRecord, StatusItem

log = logging.getLogger("mckinley.tasks")
Lang = Literal["en", "es"]
Op = Literal["none", "start", "update", "suspend", "resume", "cancel"]

# What each task needs before Send is allowed. A guest repair is a note for the office (never a work order): it
# needs to know where the home is. Name, phone, email and entry permission are not collected from guests (no
# approved consent design).
REQUIRED: dict[str, list[str]] = {
    "maintenance_request": ["issue", "location", "entry"],
    "tour_request": ["area", "days", "time"],
    "staff_handoff": ["message"],
    "guest_repair": ["message", "community", "unit"],
}
FIELDS: dict[str, list[str]] = {
    "maintenance_request": ["issue", "location", "entry", "history"],
    "tour_request": ["area", "days", "time", "beds", "move_in"],
    "staff_handoff": ["topic", "message", "community", "unit", "earlier", "history"],
}
LABEL: dict[str, tuple[str, str]] = {
    "issue": ("What's wrong", "Problema"), "location": ("Where", "Dónde"), "entry": ("Entry permission",
                                                                                   "Permiso de entrada"),
    "history": ("Earlier requests", "Solicitudes anteriores"), "area": ("Community or city", "Comunidad o ciudad"),
    "days": ("Preferred days", "Días preferidos"), "time": ("Time of day", "Hora del día"), "beds": ("Beds",
                                                                                                   "Recámaras"),
    "move_in": ("Move-in", "Mudanza"), "topic": ("About", "Tema"), "message": ("What you said", "Lo que dijo"),
    "community": ("Community", "Comunidad"), "unit": ("Unit", "Unidad"), "earlier": ("Details so far",
                                                                                   "Detalles hasta ahora"),
}
TITLE = {"maintenance_request": ("Repair request", "Solicitud de reparación"),
         "tour_request": ("Tour request", "Solicitud de visita"),
         "staff_handoff": ("Note for the office", "Nota para la oficina")}
WHAT = {"maintenance_request": ("repair request", "solicitud de reparación"),
        "tour_request": ("tour request", "solicitud de visita"), "staff_handoff": ("note", "nota")}
SEND_LABEL = {"maintenance_request": ("Send repair request", "Enviar solicitud"),
              "tour_request": ("Send tour request", "Enviar solicitud de visita"),
              "staff_handoff": ("Send note", "Enviar nota")}
NOTE_OPEN = ("Sending saves it in this demo only. It won't notify McKinley staff, create a Yardi work order or book "
             "anything.",
             "Al enviarla se guarda solo en esta demostración. No avisa al personal de McKinley, no crea una orden en "
             "Yardi ni reserva nada.")
NOTE_SAVED = ("Saved in this demo only. Nobody at McKinley has been notified.",
              "Guardada solo en esta demostración. No se avisó a nadie de McKinley.")
PREFIX = {"maintenance_request": "DEMO-WO", "tour_request": "DEMO-TOUR", "staff_handoff": "DEMO-TASK"}
TEAM = {"maintenance": "maintenance", "leasing": "leasing", "accounting": "accounting", "management": "management",
        "emergency_maintenance": "emergency maintenance"}


def _l(pair: tuple[str, str], lang: Lang) -> str:
    return pair[1] if lang == "es" else pair[0]


# ---- state -----------------------------------------------------------------------------------------------------

def load(store: Store | None, session_id: str, key: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(active task or None, waiting tasks). A cancelled card is stored as a waiting task marked `declined`."""
    row = store.get_draft(session_id, key, include_declined=True) if store else None
    if not row:
        return None, []
    waiting = list(row.get("waiting") or [])
    task = {k: v for k, v in row.items() if k != "waiting"}
    if task.get("declined"):
        return None, [task, *waiting]
    return task, waiting


def save(store: Store | None, session_id: str, key: str, active: dict[str, Any] | None,
         waiting: list[dict[str, Any]]) -> None:
    if store is None:
        return
    if active is None and not waiting:
        store.clear_draft(session_id, key)
        return
    if active is None:  # nothing on screen: the first waiting task is the row, kept hidden (declined) until resumed
        head, *rest = waiting
        store.save_draft(session_id, key, head["kind"], {**head, "declined": True, "waiting": rest})
        return
    store.save_draft(session_id, key, active["kind"], {**active, "waiting": waiting})


def requirement(task: dict[str, Any]) -> str:
    return "guest_repair" if task.get("guest_repair") else task["kind"]


def missing(task: dict[str, Any]) -> list[str]:
    return [f for f in REQUIRED[requirement(task)] if not (task.get("fields", {}).get(f) or {}).get("value")]


def new_task(kind: str, lang: Lang, *, guest_repair: bool = False, team: str | None = None,
             topic: str | None = None, priority: str = "normal") -> dict[str, Any]:
    task: dict[str, Any] = {"kind": kind, "fields": {}, "lang": lang}
    if kind == "staff_handoff":
        task.update(team=team or ("maintenance" if guest_repair else "management"), priority=priority,
                    topic=topic or ("Repair reported by a visitor" if guest_repair else "Needs a team member"))
        if guest_repair:
            task["guest_repair"] = True
    return task


_RESIDENT_ID = re.compile(r"(?:resident\s+)?R\d{3}", re.I)


def set_fields(task: dict[str, Any], values: dict[str, str], source: str = "you_said") -> list[str]:
    """Apply proposed field values the task type allows. Returns the keys that changed."""
    allowed = FIELDS[task["kind"]]
    changed = []
    for k, v in values.items():
        v = (v or "").strip()[:600 if k == "history" else 240]
        if k == "unit" and _RESIDENT_ID.fullmatch(v):
            continue  # a resident ID ("R003") is an account, never an apartment number
        if k in allowed and v and (task["fields"].get(k) or {}).get("value") != v:
            task["fields"][k] = {"value": v, "source": source}
            changed.append(k)
    return changed


def apply(op: Op, active: dict[str, Any] | None, waiting: list[dict[str, Any]], *, kind: str | None = None,
          values: dict[str, str] | None = None, new: dict[str, Any] | None = None
          ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """The transition table. Returns (active, waiting, what happened)."""
    values = values or {}
    if op == "start" and new is not None:
        if active is not None and active["kind"] == new["kind"] and not new.get("guest_repair"):
            set_fields(active, values)  # the same kind of task again: it is the one already open
            return active, waiting, "continued"
        set_fields(new, values)
        return new, ([active, *waiting] if active is not None else waiting), "started"
    if op == "update" and active is not None:
        return active, waiting, "updated" if set_fields(active, values) else "unchanged"
    if op == "suspend" and active is not None:
        return None, [active, *waiting], "suspended"
    if op == "resume":
        pick = next((w for w in waiting if not kind or w["kind"] == kind), None)
        # remediation P2: details given in the same message ("you can let yourselves in") are applied to the card that
        # comes back, as an update would; only values the person said (the model's proposal), never inferred ones
        if pick is None:
            if active is not None and (not kind or active["kind"] == kind):
                set_fields(active, values)
            return active, waiting, "continued" if active is not None else "nothing_to_resume"
        rest = [w for w in waiting if w is not pick]
        pick = {k: v for k, v in pick.items() if k not in ("declined", "paused")}
        set_fields(pick, values)
        return pick, ([active, *rest] if active is not None else rest), "resumed"
    if op == "cancel" and active is not None:
        nxt, rest = (waiting[0], waiting[1:]) if waiting and not waiting[0].get("declined") else (None, waiting)
        cancelled = {**active, "declined": True}
        if nxt is not None:
            return {k: v for k, v in nxt.items() if k != "paused"}, [*rest, cancelled], "cancelled_next_opened"
        return None, [cancelled, *rest], "cancelled"
    return active, waiting, "unchanged"


def pause_for_emergency(active: dict[str, Any] | None, waiting: list[dict[str, Any]]
                        ) -> tuple[None, list[dict[str, Any]]]:
    """An emergency interrupts the active task: it waits, unsent and unchanged, until it is safe to continue."""
    if active is None:
        return None, waiting
    return None, [{**active, "paused": True}, *waiting]


def paused(waiting: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((w for w in waiting if w.get("paused")), None)


# ---- what the person sees --------------------------------------------------------------------------------------

def card(task: dict[str, Any], lang: Lang, *, record: PrototypeRecord | None = None) -> ProposedAction:
    kind = task["kind"]
    miss = missing(task)
    keys = list(dict.fromkeys([*REQUIRED[requirement(task)], *task.get("fields", {})]))
    fields = [ActionField(key=k, label=_l(LABEL[k], lang), value=(task["fields"].get(k) or {}).get("value"),
                          source=(task["fields"].get(k) or {}).get("source", "missing"))  # type: ignore[arg-type]
              for k in keys if k in LABEL]
    if record is not None:
        return ProposedAction(kind=kind, stage="submitted", title=_l(TITLE[kind], lang), fields=fields, missing=[],
                              confirm_label=None, note=_l(NOTE_SAVED, lang), record=record)
    return ProposedAction(kind=kind, stage="collecting" if miss else "ready", title=_l(TITLE[kind], lang),
                          fields=fields, missing=[_l(LABEL[m], lang) for m in miss],
                          confirm_label=None if miss else _l(SEND_LABEL[kind], lang), note=_l(NOTE_OPEN, lang))


def describe(active: dict[str, Any] | None, waiting: list[dict[str, Any]], lang: Lang = "en") -> str:
    """Task state for the model's context (field values the person gave; no other resident's data)."""
    def one(t: dict[str, Any]) -> str:
        vals = ", ".join(f"{k}={v['value']!r}" for k, v in t.get("fields", {}).items() if v.get("value"))
        state = "cancelled" if t.get("declined") else "paused by an emergency" if t.get("paused") else "waiting"
        return f"{t['kind']}{' (guest repair note)' if t.get('guest_repair') else ''}: {vals or 'no details yet'}" \
               + (f" [missing: {', '.join(missing(t))}]" if missing(t) else " [ready to send]") + f" ({state})"
    lines = [f"ACTIVE: {one(active).rsplit(' (', 1)[0]}" if active else "ACTIVE: none"]
    lines += [f"WAITING: {one(w)}" for w in waiting]
    return "\n".join(lines)


# ---- complete: the only path that writes a request ---------------------------------------------------------------

def _fingerprint(kind: str, task: dict[str, Any]) -> str:
    vals = {k: str(v.get("value", "")).strip().lower() for k, v in task.get("fields", {}).items()}
    return hashlib.sha256(json.dumps([kind, vals], sort_keys=True).encode()).hexdigest()[:16]


def _record_data(task: dict[str, Any], lang: Lang) -> dict[str, Any]:
    kind = task["kind"]
    fields = [f.model_dump() for f in card(task, lang).fields]
    if kind == "maintenance_request":
        status, title = "submitted_for_review", (task["fields"].get("issue") or {}).get("value", "Repair request")
    elif kind == "tour_request":
        status = "requested"
        title = f"Tour of {(task['fields'].get('area') or {}).get('value', 'a community')}"
    else:
        status = "urgent_queued" if task.get("priority") == "urgent" else "queued"
        title = task.get("topic") or "Note for the office"
    title = title if len(title) <= 60 else title[:58].rsplit(" ", 1)[0] + "…"
    return {"status": status, "status_label": STATUS_LABEL[status], "title": title, "summary": title,
            "fields": fields, "team": task.get("team") or ("maintenance" if kind == "maintenance_request" else
                                                           "leasing" if kind == "tour_request" else "management"),
            "priority": task.get("priority", "normal"), "hazard": task.get("hazard"),
            "fingerprint": _fingerprint(kind, task)}


CONFIRMED = {"maintenance_request": ("Your repair request {ref} is saved in this demo. Nobody at McKinley has been "
                                     "notified and no visit is scheduled.",
                                     "Su solicitud {ref} quedó guardada en esta demostración. No se avisó a nadie de "
                                     "McKinley ni se programó una visita."),
             "tour_request": ("Your tour request {ref} is saved in this demo. Nothing is booked; the leasing team "
                              "hasn't been notified.",
                              "Su solicitud de visita {ref} quedó guardada en esta demostración. No se reservó nada."),
             "staff_handoff": ("Your note {ref} is saved in this demo. It hasn't been sent to anyone at McKinley.",
                               "Su nota {ref} quedó guardada en esta demostración. No se envió a nadie de McKinley.")}


def confirm(store: Store | None, session_id: str, persona_id: str | None, kind: ActionKind, verified: bool,
            lang: Lang = "en") -> ActionResult:
    """COMPLETE: save the active task after an explicit confirmation. Atomic and idempotent (one record at most)."""
    key = persona_id or "none"
    active, waiting = load(store, session_id, key)
    if store is None or active is None or active["kind"] != kind:
        mine = store.records(session_id=session_id, limit=20) if store else []
        if store is not None and getattr(store, "account_access", True) and (
                prev := next((r for r in mine if r["kind"] == kind and r.get("status") != "urgent_queued"), None)):
            rec0 = PrototypeRecord.model_validate(prev)  # a retried Send gets the record it already saved
            return ActionResult(ok=False, error_code="ALREADY_SAVED", record=rec0,
                                action=ProposedAction(kind=kind, stage="submitted", title=_l(TITLE[kind], lang),
                                                      fields=rec0.fields, note=_l(NOTE_SAVED, lang), record=rec0),
                                message=_l(CONFIRMED[kind], lang).format(ref=rec0.id))
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION",
                            message="There's nothing waiting to be sent. Tell me what you need and I'll set it up.")
    lang = active.get("lang", lang)
    if kind == "maintenance_request" and not verified:
        return ActionResult(ok=False, error_code="NOT_AUTHORIZED", message="Repair requests need a signed-in "
                                                                           "resident account.")
    if miss := missing(active):
        return ActionResult(ok=False, error_code="INCOMPLETE", action=card(active, lang),
                            message="Still needed before sending: " + ", ".join(_l(LABEL[m], lang).lower()
                                                                                for m in miss) + ".")
    if kind == "maintenance_request" and not active.get("separate") and (
            same := _same_repair(active, store.records(session_id=session_id, limit=50))):
        # never a second record for the same repair unless the person says it's a different problem
        active["possible_duplicate"] = same["id"]
        save(store, session_id, key, active, waiting)
        return ActionResult(ok=False, error_code="POSSIBLE_DUPLICATE", action=card(active, lang),
                            message=_l(DUPLICATE, lang).format(ref=same["id"]))
    taken = store.take_draft(session_id, key, kind)
    if taken is None:  # a concurrent confirm already took it
        return confirm(store, session_id, persona_id, kind, verified, lang)
    data = _record_data(active, lang)
    dup = next((r for r in store.records(session_id=session_id, limit=50)
                if r["kind"] == kind and r.get("fingerprint") == data["fingerprint"]), None)
    try:
        raw = dup or store.add_record(PREFIX[kind], kind, session_id, persona_id, data)
        rec = PrototypeRecord.model_validate(raw)
    except Exception as e:  # never claim success for a failed write
        log.warning("prototype write failed: %s", type(e).__name__)
        save(store, session_id, key, active, waiting)
        return ActionResult(ok=False, error_code="SAVE_FAILED", action=card(active, lang),
                            message="Sorry, that didn't save, so nothing was sent. Please try again.")
    nxt_task, rest, _ = apply("resume", None, [w for w in waiting if not w.get("declined")])
    save(store, session_id, key, nxt_task, [*rest, *[w for w in waiting if w.get("declined")]])
    message = _l(CONFIRMED[kind], lang).format(ref=rec.id)
    if nxt_task is not None:
        message += " " + (f"Your {_l(WHAT[nxt_task['kind']], lang)} is back on screen, not sent yet."
                          if lang == "en" else f"Su {_l(WHAT[nxt_task['kind']], lang)} vuelve a la pantalla, sin "
                                               "enviar.")
    return ActionResult(ok=dup is None, error_code="ALREADY_SAVED" if dup else None,
                        action=card(active, lang, record=rec), record=rec, message=message)


DUPLICATE = ("This looks like the same problem as {ref}, which is already saved, so I haven't saved it again. If it's "
             "a different problem, tell me and I'll keep it as a separate request.",
             "Parece el mismo problema que {ref}, que ya está guardado, así que no lo guardé de nuevo. Si es otro "
             "problema, dígamelo y lo dejo como una solicitud aparte.")


def _same_repair(task: dict[str, Any], saved: list[dict[str, Any]]) -> dict[str, Any] | None:
    """An already-saved repair in this conversation about the same object in the same room."""
    from app.utterance import things
    f = task.get("fields", {})
    objs, room = things((f.get("issue") or {}).get("value", "")), (f.get("location") or {}).get("value", "").lower()
    for r in saved:
        if r["kind"] != "maintenance_request":
            continue
        rf = {x["key"]: str(x.get("value") or "") for x in r.get("fields", [])}
        if objs & things(rf.get("issue", "")) and (not room or room == rf.get("location", "").lower()):
            return r
    return None


def save_urgent_note(store: Store | None, session_id: str, persona_id: str | None, hazard: str, message: str,
                     lang: Lang, team: str = "emergency_maintenance", incident: str = ""
                     ) -> tuple[PrototypeRecord | None, bool]:
    """One urgent prototype note per incident (a hazard reported again after it was resolved is a new incident and a
    new note; follow-ups in the same incident never add one). The safety step writes it; nobody is paged."""
    if store is None:
        return None, False
    task = new_task("staff_handoff", lang, team=team, priority="urgent",
                    topic=f"Possible emergency: {hazard.replace('_', ' ')}")
    task["hazard"] = hazard
    set_fields(task, {"topic": task["topic"], "message": message})
    try:
        raw = store.add_record_once(PREFIX["staff_handoff"], "staff_handoff", session_id, persona_id,
                                    _record_data(task, lang), once_key=f"{hazard}:{incident}"[:60])
        existed = bool(raw.pop("_existing", False))
        return PrototypeRecord.model_validate(raw), existed
    except Exception as e:
        log.warning("urgent note write failed: %s", type(e).__name__)
        return None, False


# ---- read tool: the person's OWN maintenance history, as short grounded lines (for notes) ----------------

def history_lines(wb: Any, persona_id: str | None, verified: bool, about: str | None = None) -> list[str]:
    """A verified resident's maintenance requests from their own record, newest first, as 'I046 Subject (status,
    date)'. With `about`, only the requests about the same thing (the object vocabulary the repair card uses)."""
    from app.personas import FIXTURE_RESIDENTS
    from app.safety import sanitize_field
    from app.utterance import things
    resident = FIXTURE_RESIDENTS.get(persona_id or "") or (getattr(wb, "residents", {}) or {}).get(persona_id)
    if not verified or resident is None:
        return []
    want = things(about) if about else None
    out = []
    for i in sorted((i for i in resident.interactions if i.category == "maintenance"),
                    key=lambda i: str(i.timestamp or ""), reverse=True):
        subject = sanitize_field(i.subject, 80) or "Maintenance request"
        if want is not None and not want & things(subject):
            continue
        when = i.timestamp.strftime("%Y-%m-%d") if i.timestamp else "date unknown"
        out.append(f"{i.interaction_id} {subject} ({i.status}{', follow-up owed' if i.follow_up_needed else ''}, "
                   f"{when})")
    return out


def history_text(lines: list[str], limit: int = 480) -> str:
    """Whole items only (never cut mid-item), with a count of what didn't fit."""
    kept: list[str] = []
    for line in lines:
        if len("; ".join([*kept, line])) > limit:
            break
        kept.append(line)
    rest = len(lines) - len(kept)
    return "; ".join(kept) + (f"; +{rest} more on record" if rest else "")


# ---- read tool: the person's OWN requests (authorized data only) -------------------------------------------------

PRIVATE_HAZARDS = {"self_harm", "medical", "personal_safety", "poisoning", "violence"}  # never listed back


def my_requests(store: Store | None, wb: Any, persona_id: str | None, verified: bool) -> list[StatusItem]:
    """Prototype requests this principal may see (the scoped store decides), then a verified resident's open
    maintenance items from their own record. Only reference, short subject, status and date."""
    from app.personas import FIXTURE_RESIDENTS
    from app.safety import sanitize_field
    items: list[StatusItem] = []
    recs = (store.records(persona_id=persona_id, limit=20) if persona_id else store.records(limit=20)) if store else []
    for r in recs:
        if r["kind"] == "tour_request" or r.get("hazard") in PRIVATE_HAZARDS:
            continue
        items.append(StatusItem(reference=r["id"], title=r.get("title", "Request"), status=r.get("status_label",
                                "Saved in demo"), opened=str(r.get("created_at", ""))[:10], source="prototype_store",
                                note="Saved through this assistant (demo)."))
    resident = FIXTURE_RESIDENTS.get(persona_id or "") or (getattr(wb, "residents", {}) or {}).get(persona_id)
    if verified and resident is not None:
        for i in resident.interactions:
            if i.category == "maintenance" and i.status != "closed":
                items.append(StatusItem(reference=i.interaction_id, title=sanitize_field(i.subject, 80) or
                                        "Maintenance request", status=i.status.capitalize() + (
                                            "; a follow-up is owed to you" if i.follow_up_needed else ""),
                                        opened=i.timestamp.strftime("%Y-%m-%d") if i.timestamp else None,
                                        source="resident_history"))
    return items
