"""FastAPI entrypoint. Run: uv run uvicorn app.main:app --reload"""

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, chat, evals, gates
from app.chat_engine import prompt_for
from app.config import get_settings
from app.models import HealthResponse, ModelTarget
from app.state import AppState, get_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="McKinley AI Prototype API", version="0.3.0",
              description="Synthetic-data prototype. No live Yardi, Databricks, messaging or work-order writes.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)
app.include_router(chat.router)
app.include_router(evals.router)
app.include_router(gates.router)
app.include_router(actions.router)


@app.get("/api/health", response_model=HealthResponse)
def health(state: AppState = Depends(get_state)) -> HealthResponse:
    s = state.deps.settings
    gw = state.deps.llm
    ready, status = gw.provider_ready(gw.default_target.provider)
    wb = state.deps.workbook
    return HealthResponse(
        status="ok",
        provider=gw.default_target.provider,
        model=gw.default_target.model,
        provider_ready=ready,
        provider_status=status,
        prompt_version=prompt_for("aware", s).version,
        data_loaded=wb is not None,
        data_error=state.data_error,
        resident_count=len(wb.residents) if wb else 0,
        interaction_count=wb.interaction_count if wb else 0,
    )


@app.get("/api/models", response_model=list[ModelTarget])
def models(state: AppState = Depends(get_state)) -> list[ModelTarget]:
    """Server-configured provider:model targets. Never includes keys or base URLs."""
    gw = state.deps.llm
    out = []
    for t in gw.eval_targets():
        ready, status = gw.provider_ready(t.provider)
        out.append(ModelTarget(key=t.key, provider=t.provider, model=t.model,
                               is_default=t == gw.default_target, ready=ready, status=status,
                               is_mock=t.provider == "mock"))
    return out
