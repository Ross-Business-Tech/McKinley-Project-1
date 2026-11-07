from fastapi import APIRouter, Depends, HTTPException

from app.api.errors import llm_error_response
from app.api.staff_guard import require_staff
from app.chat_engine import resolve_target
from app.evals import CASES, CASES_BY_ID, export_results, run_evals, summarize
from app.llm import LLMError
from app.models import (
    EvalCase,
    EvalResult,
    EvalReviewPatch,
    EvalRun,
    EvalRunRequest,
    EvalRunResponse,
    EvalSummary,
)
from app.state import AppState, get_state

router = APIRouter(prefix="/api/evals", dependencies=[Depends(require_staff)])


@router.get("/cases", response_model=list[EvalCase])
def cases() -> list[EvalCase]:
    return CASES


@router.get("/runs", response_model=list[EvalRun])
def runs(state: AppState = Depends(get_state)) -> list[dict]:
    return state.store.runs()


@router.post("/run", response_model=EvalRunResponse)
def run(req: EvalRunRequest, state: AppState = Depends(get_state)):
    unknown = [c for c in req.case_ids or [] if c not in CASES_BY_ID]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown case ids: {unknown}")
    try:
        targets = [resolve_target(state.deps, t) for t in (req.targets or [None])]  # type: ignore[list-item]
    except LLMError as e:
        return llm_error_response(e)
    run_id = run_evals(state.deps, state.store, req.case_ids, list(dict.fromkeys(req.modes)), targets)
    export_results(state.store, run_id, state.deps.settings.eval_results_path)
    return EvalRunResponse(run_id=run_id, results=[EvalResult(**r) for r in state.store.results(run_id)])


@router.get("/results", response_model=EvalRunResponse)
def results(run_id: int | None = None, state: AppState = Depends(get_state)):
    rid = run_id or state.store.latest_run_id()
    if rid is None:
        return EvalRunResponse(run_id=0, results=[])
    return EvalRunResponse(run_id=rid, results=[EvalResult(**r) for r in state.store.results(rid)])


@router.patch("/results/{result_id}", response_model=EvalResult)
def review(result_id: int, patch: EvalReviewPatch, state: AppState = Depends(get_state)):
    existing = state.store.get_result(result_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Result not found")
    state.store.review(result_id, patch.human_verdict, patch.human_notes)
    export_results(state.store, existing["run_id"], state.deps.settings.eval_results_path)
    return EvalResult(**state.store.get_result(result_id))  # type: ignore[arg-type]


@router.get("/summary", response_model=EvalSummary)
def summary(run_id: int | None = None, state: AppState = Depends(get_state)):
    rid = run_id or state.store.latest_run_id()
    rs = state.store.results(rid) if rid else []
    s = summarize(rs)
    return EvalSummary(run_id=rid, total=len(rs), **s)
