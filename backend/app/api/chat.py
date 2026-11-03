from fastapi import APIRouter, Depends

from app.api.errors import llm_error_response
from app.chat_engine import resolve_target, run_turn
from app.llm import LLMError
from app.models import ChatRequest, ChatResponse, ContextPreviewRequest, ErrorBody, Persona, SafeContext
from app.personas import build_context, list_personas
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


@router.get("/personas", response_model=list[Persona])
def personas(state: AppState = Depends(get_state)) -> list[Persona]:
    return list_personas(state.deps.workbook)


@router.post("/context/preview", response_model=SafeContext)
def context_preview(req: ContextPreviewRequest, state: AppState = Depends(get_state)) -> SafeContext:
    """Exactly the minimized context the aware mode would send for this persona + message."""
    from app.chat_engine import clean_message

    return build_context(req.persona_id, clean_message(req.message), state.deps.workbook)


@router.post("/chat", response_model=ChatResponse, responses={502: {"model": ErrorBody}, 503: {"model": ErrorBody}})
def chat(req: ChatRequest, state: AppState = Depends(get_state)):
    try:
        target = resolve_target(state.deps, req.target)
        # Interactive chat: a provider-reported model mismatch is surfaced as an error, never hidden.
        return run_turn(state.deps, req.message, req.mode, req.persona_id, req.session_id, target=target)
    except LLMError as e:
        return llm_error_response(e)
