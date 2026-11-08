"""Customer action endpoints (confirm / cancel) and the staff view of the PROTOTYPE system of record."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.actions import confirm
from app.api.staff_guard import require_staff
from app.models import ActionConfirmRequest, ActionResult, PrototypeRecord
from app.personas import apply_account_holder_rule, build_context
from app.safety import redact
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


@router.post("/actions/confirm", response_model=ActionResult)
def confirm_action(req: ActionConfirmRequest, state: AppState = Depends(get_state)) -> ActionResult:
    """Write the server-side draft for this session. The body names the session and kind only: the saved fields
    always come from the draft the backend built, never from the browser. Identity is re-checked here."""
    pkey = req.persona_id or "none"
    ctx = apply_account_holder_rule(build_context(req.persona_id, "", state.deps.workbook),
                                    state.store.user_messages(req.session_id, pkey))
    draft = state.store.get_draft(req.session_id, pkey)
    lang = draft.get("lang", "en") if draft else "en"
    return confirm(state.store, req.session_id, req.persona_id, req.kind, ctx, lang)  # type: ignore[arg-type]


@router.post("/actions/cancel", response_model=ActionResult)
def cancel_action(req: ActionConfirmRequest, state: AppState = Depends(get_state)) -> ActionResult:
    draft = state.store.get_draft(req.session_id, req.persona_id or "none")
    if not draft or draft.get("kind") != req.kind:
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION", message="There's nothing waiting to be sent.")
    # kept, marked declined, so "send it after all" in the chat can bring it back once
    state.store.save_draft(req.session_id, req.persona_id or "none", draft["kind"], {**draft, "declined": True})
    return ActionResult(ok=True, message="Okay, I haven't sent it. If you change your mind, say \"send it after "
                                         "all\".")


@router.get("/prototype/records", response_model=list[PrototypeRecord], dependencies=[Depends(require_staff)])
def prototype_records(kind: str | None = Query(default=None, pattern=r"^[a-z_]+$"),
                      limit: int = Query(default=50, ge=1, le=200),
                      state: AppState = Depends(get_state)) -> list[PrototypeRecord]:
    """STAFF/DEMO view. Synthetic personas only; session ids are exposed only as a short one-way hash."""
    return [PrototypeRecord.model_validate(r) for r in state.store.records(kind=kind, limit=limit)]


@router.get("/staff/conversations", dependencies=[Depends(require_staff)])
def staff_conversations(limit: int = Query(default=30, ge=1, le=100),
                        state: AppState = Depends(get_state)) -> list[dict]:
    """STAFF/DEMO: recent live conversations (synthetic personas), each with its saved prototype records."""
    recs = state.store.records(limit=200)
    out = []
    for c in state.store.conversations(limit):
        mine = [r for r in recs if r.get("session_hash") == c["session_hash"]]
        out.append({**c, "records": [{"id": r["id"], "kind": r["kind"], "status_label": r.get("status_label"),
                                      "priority": r.get("priority")} for r in mine]})
    return out


@router.get("/staff/conversations/{session_hash}", dependencies=[Depends(require_staff)])
def staff_conversation(session_hash: str = Path(pattern=r"^[0-9a-f]{10}$"),
                       state: AppState = Depends(get_state)) -> dict:
    turns = [{**t, "content": redact(t["content"])} for t in state.store.conversation(session_hash)]
    if not turns:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "No such conversation.",
                                                     "retryable": False})
    recs = [r for r in state.store.records(limit=200) if r.get("session_hash") == session_hash]
    return {"session_hash": session_hash, "turns": turns,
            "records": [PrototypeRecord.model_validate(r).model_dump(mode="json") for r in recs]}
