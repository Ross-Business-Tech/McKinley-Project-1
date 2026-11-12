from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.errors import customer_llm_error_response, llm_error_response
from app.api.staff_guard import request_is_local, require_staff, staff_allowed
from app.api.views import customer_view
from app.auth import (
    AuthError,
    continues_session,
    demo_personas_enabled,
    derive_principal,
    new_session_id,
    staff_principal,
    with_session_state,
)
from app.chat_engine import resolve_target, run_turn
from app.llm import LLMError
from app.models import ChatRequest, ChatResponse, ContextPreviewRequest, ErrorBody, Persona, SafeContext
from app.personas import build_context, list_personas
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


@router.get("/personas", response_model=list[Persona])
def personas(request: Request, state: AppState = Depends(get_state)) -> list[Persona]:
    """The demo sign-in list. Empty when this request may not use demo personas (APP_ENV=hosted, switched off, or a
    non-local request without DEMO_PERSONAS_ENABLED=true): the website then hides the picker (see also /api/health
    demo_personas_enabled)."""
    if not demo_personas_enabled(state.deps.settings, request_is_local(request)):
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
    staff = staff_allowed(request, state)
    # Choosing a (possibly paid) model or gate, or an evaluation mode without the aware safety pipeline, is a staff
    # tool. The customer website always sends mode "aware" and neither override.
    if (req.target or req.gate_provider or req.mode != "aware") and not staff:
        raise HTTPException(status_code=403, detail={"code": "STAFF_ONLY", "message": "Model, gate and mode "
                                                     "overrides are staff-only.", "retryable": False})
    local = request_is_local(request)
    session_id = req.session_id
    if not session_id or not continues_session(state.store, state.deps.settings, local, session_id):
        # hosted / remote: only a session the server issued (bound by an earlier turn) is continued; a client-chosen
        # or guessed id starts a new conversation under a fresh server-issued id (the website adopts it)
        session_id = new_session_id()
    try:
        # The principal is derived here, server-side; the persona id is only the demo selector (app/auth.py).
        principal = derive_principal(state.deps.settings, req.persona_id, session_id, state.deps.workbook,
                                     local_request=local)
        principal = with_session_state(state.store, principal)  # sticky "not the account holder"
        target = resolve_target(state.deps, req.target)
        # Interactive chat: a provider-reported model mismatch is surfaced as an error, never hidden.
        resp = run_turn(state.deps, req.message, req.mode, principal.persona_id, session_id, target=target,
                        gate_provider=req.gate_provider, channel=req.channel, fallback_on_model_error=True,
                        principal=principal, local_request=local)
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail()) from None
    except LLMError as e:
        # staff see the provider's code and message (diagnostics); customers a fixed, safe one (app/api/errors.py)
        return llm_error_response(e) if staff else customer_llm_error_response(e)
    # Staff diagnostics (risk, gate, pipeline, context provenance, rule ids) only for staff callers (app/api/views).
    return resp if staff else customer_view(resp)
