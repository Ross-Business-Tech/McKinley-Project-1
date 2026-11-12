"""Customer action endpoints (confirm / cancel) and the staff view of the PROTOTYPE system of record."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.actions import confirm
from app.api.protection import SESSION_LOCKS, rate_limited
from app.api.staff_guard import request_is_local, require_staff, staff_allowed
from app.api.views import customer_record
from app.auth import (
    AuthError,
    Principal,
    check_session_binding,
    continues_session,
    derive_principal,
    with_session_state,
)
from app.db import ScopedStore
from app.models import ActionConfirmRequest, ActionResult, PrototypeRecord
from app.personas import apply_account_holder_rule, build_context, holder_disclaimed
from app.safety import redact
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


def _authorized(req: ActionConfirmRequest, request: Request, state: AppState) -> tuple[Principal, ScopedStore]:
    """Server-side principal + the session binding check, then a store scoped to (session, principal): a draft of
    another session or persona can never be confirmed or cancelled from here."""
    try:
        principal = derive_principal(state.deps.settings, req.persona_id, req.session_id, state.deps.workbook,
                                     local_request=request_is_local(request))
        check_session_binding(state.store, principal)  # read-only: confirm/cancel never bind a session
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail()) from None
    principal = with_session_state(state.store, principal)  # sticky "not the account holder"
    return principal, ScopedStore(state.store, req.session_id, principal.key, principal_kind=principal.kind)


_NOTHING = "There's nothing waiting to be sent."


def _not_issued(req: ActionConfirmRequest, request: Request, state: AppState) -> bool:
    """Hosted / remote: a session id the server did not issue has nothing to confirm or cancel (checked first, so a
    guessed or legacy id never reaches a draft)."""
    return not continues_session(state.store, state.deps.settings, request_is_local(request), req.session_id)


@router.post("/actions/confirm", response_model=ActionResult)
def confirm_action(req: ActionConfirmRequest, request: Request,
                   state: AppState = Depends(get_state)) -> ActionResult:
    """Write the server-side draft for this session. The body names the session and kind only: the saved fields
    always come from the draft the backend built, never from the browser. Identity is re-checked here."""
    _limit(req, request, state)
    principal, store = _authorized(req, request, state)
    if _not_issued(req, request, state):
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION", message=_NOTHING)
    with SESSION_LOCKS.get(req.session_id):
        return _confirm_locked(req, request, state, principal, store)


def _limit(req: ActionConfirmRequest, request: Request, state: AppState) -> None:
    if not staff_allowed(request, state) and rate_limited(request, state.deps.settings, "actions", req.session_id):
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "Please wait a minute and "
                            "try again.", "retryable": True})


def _confirm_locked(req: ActionConfirmRequest, request: Request, state: AppState, principal: Principal,
                    store: ScopedStore) -> ActionResult:
    pkey = principal.key
    record_ctx = build_context(principal.persona_id, "", state.deps.workbook, principal=principal)
    ctx = apply_account_holder_rule(record_ctx, store.user_messages(req.session_id, pkey))
    if holder_disclaimed(record_ctx, ctx):
        store = store.without_account_access()  # the saved note carries no on-file account slots either
    draft = store.get_draft(req.session_id, pkey)
    lang = draft.get("lang", "en") if draft else "en"
    res = confirm(store, req.session_id, principal.persona_id, req.kind, ctx, lang)  # type: ignore[arg-type]
    # Sprint 8: a customer's confirm response carries the customer view of the record (no staff-only review fields)
    if res.record and not staff_allowed(request, state):
        return res.model_copy(update={"record": customer_record(res.record)})
    return res


@router.post("/actions/cancel", response_model=ActionResult)
def cancel_action(req: ActionConfirmRequest, request: Request,
                  state: AppState = Depends(get_state)) -> ActionResult:
    _limit(req, request, state)
    principal, store = _authorized(req, request, state)
    draft = None if _not_issued(req, request, state) else store.get_draft(req.session_id, principal.key)
    if not draft or draft.get("kind") != req.kind:
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION", message=_NOTHING)
    # kept, marked declined, so "send it after all" in the chat can bring it back once
    store.save_draft(req.session_id, principal.key, draft["kind"], {**draft, "declined": True})
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
