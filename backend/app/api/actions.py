"""Customer action endpoints (confirm / cancel) and the staff view of the PROTOTYPE system of record."""

from fastapi import APIRouter, Depends, Query

from app.actions import confirm
from app.models import ActionConfirmRequest, ActionResult, PrototypeRecord
from app.personas import build_context
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


@router.post("/actions/confirm", response_model=ActionResult)
def confirm_action(req: ActionConfirmRequest, state: AppState = Depends(get_state)) -> ActionResult:
    """Write the server-side draft for this session. The body names the session and kind only: the saved fields
    always come from the draft the backend built, never from the browser. Identity is re-checked here."""
    ctx = build_context(req.persona_id, "", state.deps.workbook)
    draft = state.store.get_draft(req.session_id, req.persona_id or "none")
    lang = draft.get("lang", "en") if draft else "en"
    return confirm(state.store, req.session_id, req.persona_id, req.kind, ctx, lang)  # type: ignore[arg-type]


@router.post("/actions/cancel", response_model=ActionResult)
def cancel_action(req: ActionConfirmRequest, state: AppState = Depends(get_state)) -> ActionResult:
    draft = state.store.get_draft(req.session_id, req.persona_id or "none")
    if not draft or draft.get("kind") != req.kind:
        return ActionResult(ok=False, error_code="NO_PENDING_ACTION", message="There's nothing waiting to be sent.")
    state.store.clear_draft(req.session_id, req.persona_id or "none")
    return ActionResult(ok=True, message="Okay, I haven't sent anything.")


@router.get("/prototype/records", response_model=list[PrototypeRecord])
def prototype_records(kind: str | None = Query(default=None, pattern=r"^[a-z_]+$"),
                      limit: int = Query(default=50, ge=1, le=200),
                      state: AppState = Depends(get_state)) -> list[PrototypeRecord]:
    """STAFF/DEMO view. Synthetic personas only; session ids are exposed only as a short one-way hash."""
    return [PrototypeRecord.model_validate(r) for r in state.store.records(kind=kind, limit=limit)]
