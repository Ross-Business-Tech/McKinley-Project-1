from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.errors import llm_error_response
from app.api.staff_guard import require_staff, staff_allowed
from app.auth import AuthError, demo_personas_enabled, derive_principal, staff_principal
from app.chat_engine import resolve_target, run_turn
from app.llm import LLMError
from app.models import ChatRequest, ChatResponse, ContextPreviewRequest, ErrorBody, Persona, SafeContext
from app.personas import build_context, list_personas
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


@router.get("/personas", response_model=list[Persona])
def personas(state: AppState = Depends(get_state)) -> list[Persona]:
    """The demo sign-in list. Empty when this deployment does not allow demo personas (APP_ENV=hosted): the website
    then hides the picker (see also /api/health demo_personas_enabled)."""
    if not demo_personas_enabled(state.deps.settings):
        return []
    return list_personas(state.deps.workbook)


@router.post("/context/preview", response_model=SafeContext, dependencies=[Depends(require_staff)])
def context_preview(req: ContextPreviewRequest, state: AppState = Depends(get_state)) -> SafeContext:
    """Exactly the minimized context the aware mode would send for this persona + message."""
    from app.chat_engine import clean_message

    return build_context(req.persona_id, clean_message(req.message), state.deps.workbook,
                         principal=staff_principal(persona_id=req.persona_id))


@router.post("/chat", response_model=ChatResponse, responses={502: {"model": ErrorBody}, 503: {"model": ErrorBody}})
def chat(req: ChatRequest, request: Request, state: AppState = Depends(get_state)):
    if req.target and not staff_allowed(request, state):  # choosing a (possibly paid) model is a staff tool
        raise HTTPException(status_code=403, detail={"code": "STAFF_ONLY", "message": "Model override is staff-only.",
                                                     "retryable": False})
    try:
        # The principal is derived here, server-side; the persona id is only the demo selector (app/auth.py).
        principal = derive_principal(state.deps.settings, req.persona_id, req.session_id, state.deps.workbook)
        target = resolve_target(state.deps, req.target)
        # Interactive chat: a provider-reported model mismatch is surfaced as an error, never hidden.
        return run_turn(state.deps, req.message, req.mode, principal.persona_id, req.session_id, target=target,
                        gate_provider=req.gate_provider, channel=req.channel, fallback_on_model_error=True,
                        principal=principal)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail()) from None
    except LLMError as e:
        return llm_error_response(e)
