from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.staff_guard import require_staff
from app.gate_evals import evaluate_gates, gate_scenarios
from app.state import AppState, get_state

router = APIRouter(prefix="/api/gates", dependencies=[Depends(require_staff)])


class GateConfig(BaseModel):
    configured_provider: str
    availability: dict[str, str]
    low_confidence_threshold: float


class GateEvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: list[Literal["rules", "llm", "jev"]] = Field(default_factory=lambda: ["rules"], max_length=3)


@router.get("/config", response_model=GateConfig)
def config(state: AppState = Depends(get_state)) -> GateConfig:
    from app.gates.base import LOW_CONFIDENCE_THRESHOLD

    g = state.deps.gates
    assert g is not None
    return GateConfig(configured_provider=g.configured, availability=g.availability(),
                      low_confidence_threshold=LOW_CONFIDENCE_THRESHOLD)


@router.get("/scenarios")
def scenarios() -> list[dict]:
    return gate_scenarios()


@router.post("/evaluate")
def evaluate(req: GateEvalRequest, state: AppState = Depends(get_state)) -> dict:
    """Routing-only comparison. 'llm' costs one model call per scenario; default is rules only (free)."""
    providers = list(dict.fromkeys(req.providers))
    if not state.deps.settings.gate_override_enabled:
        providers = ["rules"]
    return evaluate_gates(state.deps, providers)


@router.get("/log")
def log(limit: int = 50, state: AppState = Depends(get_state)) -> list[dict]:
    """Recent gate decisions (routing metadata only; never message text)."""
    return state.store.gate_log(min(max(limit, 1), 200))
