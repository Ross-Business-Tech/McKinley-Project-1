"""FastAPI entrypoint. Run: uv run uvicorn app.main:app --reload"""

import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import actions, chat
from app.api.errors import http_error_response
from app.api.protection import BodyLimitMiddleware, CatchAllMiddleware
from app.api.staff_guard import request_is_local, staff_allowed
from app.auth import demo_personas_enabled
from app.chat_engine import prompt_for
from app.config import get_settings
from app.llm import LLMGateway
from app.models import HealthResponse, ModelTarget
from app.state import AppState, get_state

API_VERSION = "0.4.0"
# Sprint 10 (review P1): the deployed commit, so anyone can tell what is live (Render sets RENDER_GIT_COMMIT)
DEPLOYED_COMMIT = (os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "")[:12] or None


class HealthWithAuth(HealthResponse):
    # False = this deployment has no demo personas (APP_ENV=hosted): the website hides the demo sign-in picker and
    # the assistant answers public information only. Never a secret.
    demo_personas_enabled: bool = False
    version: str = API_VERSION
    commit: str | None = None  # short git commit of this deployment, when the host provides it

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_settings = get_settings()
_problems = _settings.hosted_problems()
if _problems:  # refuse to start a shared deployment with unsafe settings (values are never printed)
    raise RuntimeError("Unsafe settings for APP_ENV=hosted: " + "; ".join(_problems))

_ready, _status = LLMGateway(_settings).provider_ready(_settings.llm_provider)
if not _ready:  # visible in the host's logs; the value of any key is never logged
    logging.getLogger("mckinley").warning("default provider %s is not ready (%s): model turns will return errors; "
                                          "set the key or LLM_PROVIDER=mock", _settings.llm_provider, _status)

_hosted = _settings.app_env == "hosted"
app = FastAPI(title="McKinley AI Prototype API", version=API_VERSION,
              description="Synthetic-data prototype. No live Yardi, Databricks, messaging or work-order writes.",
              # Sprint 10: the interactive API docs are a developer tool, not public on a hosted deployment
              docs_url=None if _hosted else "/docs", redoc_url=None if _hosted else "/redoc",
              openapi_url=None if _hosted else "/openapi.json")
# order matters: the last middleware added is the outermost, so CORS headers reach errors and 413s too
app.add_middleware(CatchAllMiddleware)
app.add_middleware(BodyLimitMiddleware, max_bytes=_settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def _invalid(_: Request, exc: RequestValidationError):  # noqa: ANN202 - FastAPI handler signature
    """The standard error shape, naming the fields only: the request is never echoed back (review P1: a 5 MB body
    came back in full, and a typed SSN verbatim)."""
    fields = sorted({".".join(str(x) for x in e.get("loc", ())[1:]) or "body" for e in exc.errors()})[:10]
    return JSONResponse(status_code=422, content={"error": {
        "code": "INVALID_REQUEST", "message": "The request was not valid: " + ", ".join(fields) + ".",
        "retryable": False}})


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException):  # noqa: ANN202 - FastAPI handler signature
    return http_error_response(exc.status_code, exc.detail, getattr(exc, "headers", None))


app.include_router(chat.router)
app.include_router(actions.router)


@app.get("/api/health", response_model=HealthWithAuth)
def health(request: Request, state: AppState = Depends(get_state)) -> HealthWithAuth:
    """Public: liveness, the default provider/model (as /api/models) and whether demo sign-in is offered. Staff
    callers also get the data and database facts (counts, resident source, data error, prompt version)."""
    s = state.deps.settings
    gw = state.deps.llm
    ready, status = gw.provider_ready(gw.default_target.provider)
    public = HealthWithAuth(
        status="ok",
        demo_personas_enabled=demo_personas_enabled(s, request_is_local(request)),
        provider=gw.default_target.provider,
        model=gw.default_target.model,
        provider_ready=ready,
        provider_status="",
        prompt_version="",
        data_loaded=False,
        data_error=None,
        resident_count=0,
        interaction_count=0,
        app_env=s.app_env,
        database="",
        resident_source=None,
        is_mock=gw.default_target.provider == "mock",
        commit=DEPLOYED_COMMIT,
    )
    if not staff_allowed(request, state):
        return public
    wb = state.deps.workbook
    return public.model_copy(update={
        "provider_status": status, "prompt_version": prompt_for("aware", s).version, "data_loaded": wb is not None,
        "data_error": state.data_error, "resident_count": len(wb.residents) if wb else 0,
        "interaction_count": wb.interaction_count if wb else 0, "database": state.store.dialect,
        "resident_source": wb.source if wb else None})


@app.get("/api/models", response_model=list[ModelTarget])
def models(request: Request, state: AppState = Depends(get_state)) -> list[ModelTarget]:
    """Server-configured provider:model targets. Never includes keys or base URLs. Hosted: staff only (an empty
    list otherwise, so the locked staff console still loads)."""
    if state.deps.settings.app_env == "hosted" and not staff_allowed(request, state):
        return []
    gw = state.deps.llm
    out = []
    for t in gw.eval_targets():
        ready, status = gw.provider_ready(t.provider)
        out.append(ModelTarget(key=t.key, provider=t.provider, model=t.model,
                               is_default=t == gw.default_target, ready=ready, status=status,
                               is_mock=t.provider == "mock"))
    return out
