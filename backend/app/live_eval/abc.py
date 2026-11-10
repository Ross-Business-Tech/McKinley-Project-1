"""Controlled multi-turn A/B/C evaluation against ONE fixed provider:model.

    uv run python -m app.live_eval.abc --target recommended --label live-v1     # after preflight is ready
    uv run python -m app.live_eval.abc --target mock:mock-deterministic-v1 --allow-mock --label mock-dryrun

Modes: baseline (A, generic prompt), prompt_only (B, McKinley prompt, no resident context), aware (C, full
context). Same target, same generation settings, rules decision gate (no extra model calls), temp database.
Items: the five core cases (single turn, graded with app.evals.grade) and persona conversations (adaptive simulator
from app.usability over an in-process client, graded by the independent usability evaluator).

Every chat turn is recorded with the model call(s) it made. A record is ``comparable`` only if it is LIVE, the reply
came from the model and its single model call succeeded on the requested model; everything else (mock, templates,
model errors, fallbacks, MODEL_SWITCHED, validation replacements) is kept but excluded from A/B/C comparisons.
No provider ready -> BLOCKED (exit 3), evals/live/status.json written, nothing falls back to mock.
"""

import argparse
import json
import re
import statistics
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.evals import CASES_BY_ID, CORE_CASE_IDS, grade, routed_id
from app.live_eval.preflight import OUT_DIR, fetch_models, model_info
from app.live_eval.recorder import RecordingGateway, RunStopped
from app.llm import LLMError, LLMProvider, Target
from app.models import ChatResponse

MODES = ("baseline", "prompt_only", "aware")
MODE_LABEL = {"baseline": "A baseline", "prompt_only": "B prompt_only", "aware": "C aware"}
DEFAULT_SCENARIOS = ("r-ac-4th-time", "p-tour-this-week", "a-injected-history")  # fits the default budget
EXIT_OK, EXIT_STOPPED, EXIT_BLOCKED = 0, 2, 3
_SAFETY_KEY = re.compile(r"safety|emergency|care_|crisis|risk", re.I)


# ----------------------------------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_status(out_dir: Path, status: str, **kw: Any) -> Path:
    """status.json describes the LIVE evaluation; a mock dry run writes status-mock-dryrun.json instead, so it can
    never replace a 'blocked' or live status."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("status-mock-dryrun.json" if status == "mock_dry_run" else "status.json")
    path.write_text(json.dumps({"status": status, "updated_at": _now(), **kw}, indent=2) + "\n", encoding="utf-8")
    return path


def _ollama_up(settings: Settings) -> bool:
    try:
        r = httpx.get(f"{(settings.base_url_for('ollama') or 'http://localhost:11434').rstrip('/')}/api/tags",
                      timeout=2)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def safety_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Every top-level response field about safety, captured generically (new safety fields are included as-is)."""
    return {k: v for k, v in d.items() if _SAFETY_KEY.search(k) or k == "safety"}


def _turn_record(*, kind: str, item_id: str, mode: str, turn_index: int, user_message: str, execution: str,
                 target: Target, calls: list[dict[str, Any]], resp: dict[str, Any] | None,
                 error: tuple[str, str] | None, case_grade: dict[str, Any] | None) -> dict[str, Any]:
    ok_calls = [c for c in calls if c.get("status") == "ok"]
    last = calls[-1] if calls else {}
    rec: dict[str, Any] = {
        "kind": kind, "item_id": item_id, "mode": mode, "mode_label": MODE_LABEL[mode], "turn_index": turn_index,
        "execution": execution, "user_message": user_message, "target": target.key,
        "requested_model": target.model, "served_model": last.get("served_model"),
        "model_calls": calls, "human_review_status": "pending",
    }
    if resp is None:
        rec.update(status="error", error_code=error[0] if error else "UNKNOWN",
                   error_message=error[1] if error else "", reply_source=None, reply=None,
                   raw_model_text=last.get("response_text"))
    else:
        wf, routed, gate = resp.get("workflow") or {}, resp.get("routed_workflow") or {}, resp.get("gate") or {}
        action, handoff = resp.get("action") or {}, resp.get("handoff") or {}
        usage = resp.get("usage") or {}
        rec.update(
            status="ok", reply=resp.get("reply"), raw_model_text=last.get("response_text"),
            reply_source=resp.get("reply_source"), parse_mode=resp.get("parse_mode"),
            prompt_version=resp.get("prompt_version"), temperature=resp.get("temperature"),
            response_model=resp.get("model"), is_mock=resp.get("is_mock"),
            source_context_fields=resp.get("source_context_fields") or [],
            input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
            latency_ms=resp.get("latency_ms"),
            estimated_cost_usd=sum(c.get("estimated_cost_usd") or 0 for c in ok_calls) if ok_calls else
            usage.get("estimated_cost_usd"),
            cost_source=",".join(sorted({c.get("cost_source", "unknown") for c in ok_calls})) or None,
            workflow={"routed": routed.get("id"), "active": wf.get("id"), "gate_intent": gate.get("intent"),
                      "gate_urgency": gate.get("urgency"), "gate_source": gate.get("decision_source"),
                      "action_kind": action.get("kind"), "action_stage": action.get("stage"),
                      "functions": resp.get("functions") or [],
                      "records": [{"id": r.get("id"), "kind": r.get("kind"), "status": r.get("status")}
                                  for r in resp.get("records_created") or []]},
            handoff={"recommended": resp.get("recommended_handoff"), "category": resp.get("handoff_category"),
                     "reason": resp.get("handoff_reason"), "model_handoff": resp.get("model_handoff"),
                     "team": handoff.get("team"), "priority": handoff.get("priority")},
            safety=safety_fields(resp),
            output_checks=resp.get("output_checks") or [],
            failed_checks=[c["code"] for c in resp.get("output_checks") or [] if not c.get("passed")],
        )
        if error:  # the turn produced a reply but a model call failed (template fallback)
            rec.update(error_code=error[0], error_message=error[1])
    rec["automated_grade"] = case_grade
    reasons: list[str] = []
    if execution != "LIVE":
        reasons.append("MOCK")
    if rec["status"] != "ok":
        reasons.append(f"error:{rec.get('error_code')}")
    elif rec.get("reply_source") != "model":
        reasons.append(f"reply_source={rec.get('reply_source')}")
    bad = [c for c in calls if c.get("status") != "ok"]
    reasons += [f"model_call_error:{c.get('error_code')}" for c in bad]
    if rec["status"] == "ok" and rec.get("reply_source") == "model" and len(ok_calls) != 1:
        reasons.append(f"model_calls_ok={len(ok_calls)}")
    rec["comparable"] = not reasons
    rec["non_comparable_reasons"] = sorted(set(reasons))
    # Dry-run plumbing only: what WOULD be comparable on a live run. Never used for LIVE comparisons.
    rec["comparable_if_live"] = not [r for r in reasons if r != "MOCK"]
    return rec


def _call_errors(calls: list[dict[str, Any]]) -> tuple[str, str] | None:
    bad = [c for c in calls if c.get("status") != "ok"]
    return (bad[-1]["error_code"], bad[-1].get("error_message", "")) if bad else None


# ------------------------------------------------------------------------------------------ in-process transport
class ModeTransport:
    """Simulator transport: real API routes in-process (TestClient), with the mode forced per run and every chat
    turn recorded together with the model calls it made."""

    def __init__(self, client: Any, gw: RecordingGateway, mode: str, target: Target, execution: str,
                 scenario_id: str, sink: list[dict[str, Any]]):
        self.c, self.gw, self.mode, self.target, self.execution = client, gw, mode, target, execution
        self.scenario_id, self.sink = scenario_id, sink
        self.turn = 0

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.gw.stop_code:
            raise RunStopped(self.gw.stop_code, self.gw.stop_message or "")
        if path != "/api/chat":
            r = self.c.post(path, json=body)
            return r.status_code, r.json()
        self.turn += 1
        n0 = len(self.gw.calls)
        r = self.c.post(path, json={**body, "mode": self.mode})
        calls = self.gw.calls[n0:]
        d = r.json()
        err = _call_errors(calls)
        if r.status_code != 200:
            e = d.get("error") or {}
            err = (e.get("code") or f"HTTP_{r.status_code}", e.get("message") or "")
        self.sink.append(_turn_record(
            kind="conversation_turn", item_id=self.scenario_id, mode=self.mode, turn_index=self.turn,
            user_message=body.get("message", ""), execution=self.execution, target=self.target, calls=calls,
            resp=d if r.status_code == 200 else None, error=err, case_grade=None))
        return r.status_code, d


# --------------------------------------------------------------------------------------------------- runner
def _resolve(settings: Settings, raw: str | None, out_dir: Path) -> Target:
    if raw in (None, "", "default"):
        return Target(settings.llm_provider, settings.llm_model)
    if raw == "recommended":
        pf = out_dir / "preflight.json"
        if not pf.exists():
            raise ValueError("--target recommended needs evals/live/preflight.json; run the preflight first")
        rec = json.loads(pf.read_text()).get("recommended_target")
        if not rec:
            raise ValueError("preflight.json has no recommended_target (see its recommendation_reason)")
        return Target.parse(rec)
    return Target.parse(raw)


def run_live_eval(
    settings: Settings, target_raw: str | None, *, allow_mock: bool = False, allow_paid: bool = False,
    label: str | None = None, max_calls: int = 60, sleep_seconds: float = 3.0, max_rate_limit_errors: int = 1,
    case_ids: list[str] | None = None, scenario_ids: list[str] | None = None, modes: list[str] | None = None,
    out_dir: Path = OUT_DIR, providers: dict[str, LLMProvider] | None = None,
    models_client: httpx.Client | None = None, sleeper: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print, with_safety_classifier: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Returns (exit_code, document). Writes status.json always; results/report only when the run started."""
    modes = list(modes or MODES)
    case_ids = CORE_CASE_IDS if case_ids is None else case_ids
    scenario_ids = list(DEFAULT_SCENARIOS) if scenario_ids is None else scenario_ids

    def blocked(code: str, reason: str, **kw: Any) -> tuple[int, dict[str, Any]]:
        doc = {"status": "blocked", "reason_code": code, "reason": reason, "target": target_raw, **kw,
               "keys_present": {p: bool(settings.api_key_for(p)) for p in ("gemini", "openrouter", "anthropic")},
               "note": "No model was called and nothing fell back to mock."}
        write_status(out_dir, **doc)
        log(f"BLOCKED {code}: {reason}")
        return EXIT_BLOCKED, doc

    try:
        target = _resolve(settings, target_raw, out_dir)
    except ValueError as e:
        return blocked("BAD_TARGET", str(e))
    is_mock = target.provider == "mock"
    if is_mock and not allow_mock:
        return blocked("MOCK_NOT_ALLOWED", "The mock is deterministic templates, not a language model. Use "
                                           "--allow-mock for a labelled MOCK dry run (never comparable).")
    if case_ids and any(c not in CASES_BY_ID for c in case_ids):
        return blocked("BAD_CASE", f"unknown case ids: {[c for c in case_ids if c not in CASES_BY_ID]}")
    from app.usability.personas import PERSONAS
    from app.usability.scenarios import SCENARIOS
    by_sc = {s.id: s for s in SCENARIOS}
    if scenario_ids == ["all"]:
        scenario_ids = list(by_sc)
    if any(s not in by_sc for s in scenario_ids):
        return blocked("BAD_SCENARIO", f"unknown scenario ids: {[s for s in scenario_ids if s not in by_sc]}")

    # Pin the run: the fixed target becomes the default target, rules gate only (no extra model calls).
    run_settings = settings.model_copy(update={
        "llm_provider": target.provider, "llm_model": target.model,
        "decision_gate_provider": "rules", "gate_override_enabled": False,
        # The semantic safety classifier is an extra model call per turn: off unless asked for, and then on the SAME
        # fixed target. Deterministic safety (rules + policy) is recorded on every turn either way.
        "safety_classifier": "auto" if with_safety_classifier else "off", "safety_classifier_target": None,
        "db_path": Path(tempfile.mkdtemp(prefix="live-eval-")) / "live_eval.sqlite3",
    })
    gw = RecordingGateway(run_settings, providers, max_calls=max_calls, sleep_seconds=0 if is_mock else sleep_seconds,
                          max_rate_limit_errors=max_rate_limit_errors, sleeper=sleeper)
    configured = {t.key for t in gw.eval_targets()}
    if target.key not in configured and target != Target(settings.llm_provider, settings.llm_model):
        return blocked("UNKNOWN_TARGET", f"'{target.key}' is not in EVAL_TARGETS or the default target",
                       configured_targets=sorted(configured))
    ready, status = gw.provider_ready(target.provider)
    if target.provider == "ollama" and not (providers and "ollama" in providers):
        ready, status = (True, status) if _ollama_up(settings) else (False, "OLLAMA_NOT_REACHABLE")
    if not ready:
        return blocked(status if status.isupper() else "PROVIDER_NOT_READY",
                       f"{target.provider} is not ready ({status}). Add OPENROUTER_API_KEY to backend/.env (or "
                       "start Ollama) and re-run preflight." if target.provider != "mock" else status,
                       resolved_target=target.key)

    listing_info: dict[str, Any] | None = None
    if target.provider == "openrouter":
        listing, err = fetch_models(models_client)
        listing_info = model_info(target.model, listing)
        listing_info["listing_error"] = err
        if listing_info.get("listed") is False:
            return blocked("MODEL_NOT_LISTED", f"'{target.model}' is not in OpenRouter's public model list",
                           resolved_target=target.key, listing=listing_info)
        if listing_info.get("listed") and not listing_info.get("free") and not allow_paid:
            return blocked("MODEL_NOT_FREE", f"'{target.model}' is priced; pass --allow-paid to spend credits",
                           resolved_target=target.key, listing=listing_info)
        if listing_info.get("listed"):
            gw.pricing[target.model] = (listing_info["pricing_prompt_usd_per_token"],
                                        listing_info["pricing_completion_usd_per_token"])

    if target.provider == "gemini" and not allow_paid:  # free tier or billed depends on the key's project
        return blocked("MAY_BE_BILLED", f"'{target.key}' may be billed on this key's Google project; pass "
                       "--allow-paid after checking the project's quota and billing", resolved_target=target.key)

    execution = "MOCK" if is_mock else "LIVE"
    label = label or ("mock-dryrun" if is_mock else "live-" + datetime.now(UTC).strftime("%Y%m%d-%H%M"))
    cfg = gw.generation_config(target)
    from app.chat_engine import prompt_for
    meta = {
        "label": label, "execution": execution, "started_at": _now(), "target": target.key,
        "target_arg": target_raw, "provider": target.provider, "requested_model": target.model,
        "generation_settings": {"temperature": cfg.temperature, "max_tokens": cfg.max_tokens,
                                "timeout_seconds": cfg.timeout_seconds, "max_retries_same_model": cfg.max_retries},
        "decision_gate": "rules (deterministic; no gate model calls)",
        "prompt_versions": {m: prompt_for(m, run_settings).version for m in modes},  # type: ignore[arg-type]
        "modes": modes, "cases": case_ids, "scenarios": scenario_ids,
        "budget": {"max_calls": max_calls, "sleep_seconds": gw.sleep_seconds,
                   "max_rate_limit_errors": max_rate_limit_errors},
        "listing": listing_info,
        "note": ("MOCK DRY RUN: deterministic templates exercise the pipeline only. NOT model quality evidence; "
                 "every record is comparable:false." if is_mock else
                 "LIVE run on one fixed provider:model. Automated grades are PROVISIONAL; human review pending."),
    }
    from app.db import Store
    from app.state import build_state
    state = build_state(settings=run_settings, gateway=gw, store=Store(run_settings.db_path))
    deps = state.deps
    records: list[dict[str, Any]] = []
    conversations: list[dict[str, Any]] = []
    stop: tuple[str, str] | None = None
    log(f"{execution} A/B/C on {target.key}: {len(case_ids)} cases + {len(scenario_ids)} conversations x "
        f"{len(modes)} modes, budget {max_calls} calls, sleep {gw.sleep_seconds}s")

    from app.chat_engine import run_turn
    def budget_left() -> int:
        return gw.max_calls - len(gw.calls)

    for cid in case_ids:
        case = CASES_BY_ID[cid]
        if budget_left() < len(modes):  # never start an item that cannot get all its modes (unbalanced A/B/C)
            gw._stop("BUDGET_EXHAUSTED", f"Not enough call budget left ({budget_left()}) for a balanced A/B/C set "
                                         f"of case {cid}; raise --max-calls.")
            stop = (gw.stop_code or "", gw.stop_message or "")
            break
        for mode in modes:
            n0 = len(gw.calls)
            resp: ChatResponse | None = None
            err: tuple[str, str] | None = None
            try:
                resp = run_turn(deps, case.message, mode, case.persona_id or None, session_id=None,  # type: ignore[arg-type]
                                use_history=False, target=target)
            except RunStopped as e:
                stop = (e.code, e.message)
                break
            except LLMError as e:
                err = (e.code, e.message)
            calls = gw.calls[n0:]
            g = None
            if resp is not None:
                crit, verdict, why = grade(case, mode, resp)  # type: ignore[arg-type]
                g = {"criteria": [c.model_dump() for c in crit], "provisional_verdict": verdict,
                     "rationale": why, "routed_workflow": routed_id(resp)}
            rec = _turn_record(kind="case", item_id=cid, mode=mode, turn_index=1, user_message=case.message,
                               execution=execution, target=target, calls=calls,
                               resp=resp.model_dump(mode="json") if resp else None, error=err or _call_errors(calls),
                               case_grade=g)
            records.append(rec)
            log(f"  case {cid:<30} {mode:<11} {rec.get('reply_source') or rec.get('error_code')}"
                f"{'' if rec['comparable'] else ' [not comparable]'}")
            if gw.stop_code:
                stop = (gw.stop_code, gw.stop_message or "")
                break
        if stop:
            break

    if not stop and scenario_ids:
        from fastapi.testclient import TestClient

        import app.state as app_state
        from app.main import app
        from app.usability.evaluator import evaluate
        from app.usability.simulator import run_scenario
        previous = app_state._state
        app_state.set_state(state)
        try:
            client = TestClient(app)
            for sid in scenario_ids:
                sc = by_sc[sid]
                need = len(modes) * (len(sc.moves) + 2)  # rough upper estimate of chat turns needing the model
                if budget_left() < need:
                    gw._stop("BUDGET_EXHAUSTED", f"Not enough call budget left ({budget_left()}, need ~{need}) for a "
                                                 f"balanced A/B/C set of conversation {sid}; raise --max-calls.")
                    stop = (gw.stop_code or "", gw.stop_message or "")
                    break
                for mode in modes:
                    sink: list[dict[str, Any]] = []
                    t = ModeTransport(client, gw, mode, target, execution, sid, sink)
                    convo_doc: dict[str, Any] = {"scenario": sid, "persona": sc.persona, "mode": mode,
                                                 "identity": PERSONAS[sc.persona].identity}
                    try:
                        convo = run_scenario(t, sc, f"{label}-{mode}")
                        ev = evaluate(sc, convo)
                        convo_doc.update(complete=True, evaluation=ev, transcript=convo["turns"])
                    except RunStopped as e:
                        stop = (e.code, e.message)
                        convo_doc.update(complete=False, evaluation=None, transcript=None,
                                         stopped=f"{e.code}: {e.message}")
                    records.extend(sink)
                    clean_if_live = bool(convo_doc["complete"] and not any(
                        r.get("error_code") or r["status"] != "ok"
                        or r.get("reply_source") == "template_after_model_error" for r in sink))
                    clean = clean_if_live and execution == "LIVE"
                    convo_doc.update(turn_records=len(sink), comparable=clean, comparable_if_live=clean_if_live,
                                     comparable_turns=sum(r["comparable"] for r in sink),
                                     human_review_status="pending")
                    conversations.append(convo_doc)
                    ev = convo_doc.get("evaluation") or {}
                    log(f"  convo {sid:<29} {mode:<11} {ev.get('outcome', 'STOPPED')}"
                        f"{'' if clean else ' [not comparable]'}")
                    if stop or gw.stop_code:
                        stop = stop or (gw.stop_code or "", gw.stop_message or "")
                        break
                if stop:
                    break
        finally:
            app_state._state = previous

    if not stop and gw.stop_code:
        stop = (gw.stop_code, gw.stop_message or "")
    run_status = "stopped" if stop else "completed"
    meta.update(finished_at=_now(), run_status=run_status, stop_code=stop[0] if stop else None,
                stop_message=stop[1] if stop else None, model_calls_made=len(gw.calls),
                served_models=sorted({c["served_model"] for c in gw.calls if c.get("served_model")}))
    basis = "comparable_if_live" if is_mock else "comparable"
    doc = {"meta": meta, "summary": summarize(records, conversations, basis), "records": records,
           "conversations": conversations}
    out_dir.mkdir(parents=True, exist_ok=True)
    rpath, mpath = out_dir / f"results-{label}.json", out_dir / f"report-{label}.md"
    rpath.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    mpath.write_text(render_md(doc), encoding="utf-8")
    write_status(out_dir, "mock_dry_run" if is_mock else run_status, execution=execution, label=label,
                 target=target.key, stop_code=meta["stop_code"], stop_message=meta["stop_message"],
                 model_calls_made=len(gw.calls), results=rpath.name, report=mpath.name,
                 note=("Dry run only; live evaluation not yet run." if is_mock else meta["note"]))
    if stop:
        log(f"STOPPED {stop[0]}: {stop[1]} (partial results written)")
    log(f"Wrote {rpath} and {mpath}")
    return (EXIT_STOPPED if stop else EXIT_OK), doc


# -------------------------------------------------------------------------------------------------- summary
def _agg(rs: list[dict[str, Any]], key: str = "comparable") -> dict[str, Any]:
    comp = [r for r in rs if r[key]]
    lat = [r["latency_ms"] for r in comp if r.get("latency_ms") is not None]
    tin = [r["input_tokens"] for r in comp if r.get("input_tokens") is not None]
    tout = [r["output_tokens"] for r in comp if r.get("output_tokens") is not None]
    cost = [r["estimated_cost_usd"] for r in comp if r.get("estimated_cost_usd") is not None]
    graded = [r for r in comp if r.get("automated_grade")]
    return {
        "records": len(rs), key: len(comp), "excluded": len(rs) - len(comp),
        "errors": sum(1 for r in rs if r.get("error_code")),
        "template_replies": sum(1 for r in rs if r.get("reply_source") == "template"),
        "validation_replacements": sum(1 for r in rs if r.get("reply_source") == "template_after_validation"),
        "model_error_fallbacks": sum(1 for r in rs if r.get("reply_source") == "template_after_model_error"),
        "graded": len(graded),
        "good": sum(1 for r in graded if r["automated_grade"]["provisional_verdict"] == "GOOD"),
        "handoffs": sum(1 for r in comp if (r.get("handoff") or {}).get("recommended")),
        "false_action_claims": sum(1 for r in comp if "no_false_action_claim" in r.get("failed_checks", [])),
        "json_contract_failures": sum(1 for r in comp if r.get("parse_mode") == "text_fallback"),
        "input_tokens": sum(tin) if tin else None, "output_tokens": sum(tout) if tout else None,
        "latency_ms_avg": round(statistics.mean(lat)) if lat else None,
        "latency_ms_p50": int(statistics.median(lat)) if lat else None,
        "estimated_cost_usd": round(sum(cost), 6) if cost else None,
    }


def summarize(records: list[dict[str, Any]], conversations: list[dict[str, Any]],
              key: str = "comparable") -> dict[str, Any]:
    """`key="comparable"` for LIVE; a MOCK dry run aggregates `comparable_if_live` (plumbing check, not evidence)."""
    out: dict[str, Any] = {"basis": key, "turns_by_mode": {}, "cases_by_mode": {}, "conversations_by_mode": {}}
    modes = [m for m in MODES if any(r["mode"] == m for r in records) or any(c["mode"] == m for c in conversations)]
    for m in modes:
        out["turns_by_mode"][m] = _agg([r for r in records if r["mode"] == m], key)
        out["cases_by_mode"][m] = _agg([r for r in records if r["mode"] == m and r["kind"] == "case"], key)
        cs = [c for c in conversations if c["mode"] == m]
        comp = [c for c in cs if c[key]]
        evs = [c["evaluation"] for c in comp]
        out["conversations_by_mode"][m] = {
            "conversations": len(cs), "complete": sum(1 for c in cs if c["complete"]), key: len(comp),
            "success": sum(1 for e in evs if e["outcome"] in ("success", "simulated_success")),
            "partial": sum(1 for e in evs if e["outcome"] == "partial"),
            "blocked": sum(1 for e in evs if e["outcome"] == "blocked"),
            "failure": sum(1 for e in evs if e["outcome"] == "failure"),
            "handoff_ok": sum(1 for e in evs if e["handoff_ok"]),
            "false_claims": sum(len(e["false_claims"]) for e in evs),
            "safety_violations": sum(len(e["safety_violations"]) for e in evs),
        }
    return out


def _fmt(v: Any) -> str:
    return "–" if v is None else str(v)


def render_md(doc: dict[str, Any]) -> str:
    meta, s = doc["meta"], doc["summary"]
    live = meta["execution"] == "LIVE"
    k = s["basis"]
    comp_col = "Comparable" if live else "Would-be comparable (MOCK)"
    head = (f"# LIVE A/B/C evaluation: `{meta['target']}`" if live else
            "# MOCK DRY RUN — not model evidence")
    lines = [head, "",
             ("> " + meta["note"]) if live else
             "> **MOCK DRY RUN.** Every reply came from deterministic templates. This proves the pipeline and "
             "recording only; it says nothing about language-model quality. All records are `comparable: false`.",
             "",
             f"- Label `{meta['label']}`, {meta['started_at']} → {meta.get('finished_at')}; run status "
             f"**{meta['run_status']}**" + (f" ({meta['stop_code']}: {meta['stop_message']})" if meta.get('stop_code')
                                            else ""),
             f"- Requested `{meta['target']}`; served models seen: {meta.get('served_models') or 'none'}",
             f"- Generation: {meta['generation_settings']}; gate: {meta['decision_gate']}",
             f"- Prompt versions: {meta['prompt_versions']}",
             f"- Budget: {meta['model_calls_made']}/{meta['budget']['max_calls']} model calls, "
             f"{meta['budget']['sleep_seconds']}s between calls",
             "- Comparable = LIVE, reply written by the model, its single model call succeeded on the requested "
             "model. Templates, validation replacements, model errors/fallbacks, MODEL_SWITCHED and MOCK are "
             "recorded but excluded from the comparison columns (tokens, latency, cost, handoffs, false claims).",
             "- All automated grades are PROVISIONAL; `human_review_status` is `pending` on every record.", ""]
    for title, key in (("All chat turns (cases + conversation turns)", "turns_by_mode"),
                       ("Five core cases (single turn)", "cases_by_mode")):
        lines += [f"## {title}", "",
                  f"| Mode | Records | {comp_col} | Excluded | Errors | Templates | Validation replacements | "
                  "Model-error fallbacks | Auto GOOD / graded | Handoffs | False action claims | JSON failures | "
                  "Tokens in | Tokens out | Latency avg ms | Cost USD |",
                  "| --- |" + " ---: |" * 15]
        for m, a in s[key].items():
            lines.append(f"| {MODE_LABEL[m]} | {a['records']} | {a[k]} | {a['excluded']} | {a['errors']} | "
                         f"{a['template_replies']} | {a['validation_replacements']} | {a['model_error_fallbacks']} | "
                         f"{a['good']}/{a['graded']} | {a['handoffs']} | {a['false_action_claims']} | "
                         f"{a['json_contract_failures']} | {_fmt(a['input_tokens'])} | {_fmt(a['output_tokens'])} | "
                         f"{_fmt(a['latency_ms_avg'])} | {_fmt(a['estimated_cost_usd'])} |")
        lines.append("")
    lines += ["## Conversations (adaptive persona simulator, independent evaluator)", "",
              f"| Mode | Run | Complete | {comp_col} | Success | Partial | Blocked | Failure | Handoff ok | "
              "False claims | Safety violations |", "| --- |" + " ---: |" * 10]
    for m, a in s["conversations_by_mode"].items():
        lines.append(f"| {MODE_LABEL[m]} | {a['conversations']} | {a['complete']} | {a[k]} | "
                     f"{a['success']} | {a['partial']} | {a['blocked']} | {a['failure']} | {a['handoff_ok']} | "
                     f"{a['false_claims']} | {a['safety_violations']} |")
    lines += ["", "Outcome columns count comparable conversations only (LIVE, complete, no model error or fallback)."
              + ("" if live else " MOCK DRY RUN: columns use would-be-comparable records to exercise the "
                 "aggregation; the numbers describe templates, not a model."),
              "", "## Per conversation", "", "| Scenario | Mode | Outcome | Turns | Comparable | Notes |",
              "| --- | --- | --- | ---: | --- | --- |"]
    for c in doc["conversations"]:
        ev = c.get("evaluation") or {}
        notes = "; ".join((ev.get("safety_violations") or []) + (ev.get("notes") or []))[:200] or c.get("stopped", "")
        lines.append(f"| {c['scenario']} | {c['mode']} | {ev.get('outcome', 'STOPPED')} | {c['turn_records']} | "
                     f"{c['comparable']} | {notes.replace('|', '/')} |")
    lines += ["", "## Per case", "", "| Case | Mode | Reply source | Auto verdict | Comparable | Excluded because |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in doc["records"]:
        if r["kind"] != "case":
            continue
        g = r.get("automated_grade") or {}
        lines.append(f"| {r['item_id']} | {r['mode']} | {r.get('reply_source') or r.get('error_code')} | "
                     f"{g.get('provisional_verdict', '–')} | {r['comparable']} | "
                     f"{', '.join(r['non_comparable_reasons']) or '–'} |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=None, help="provider:model from EVAL_TARGETS, 'recommended' (from "
                    "preflight.json) or 'default' (LLM_PROVIDER/LLM_MODEL)")
    ap.add_argument("--allow-mock", action="store_true", help="allow the mock target (labelled MOCK DRY RUN)")
    ap.add_argument("--allow-paid", action="store_true", help="allow a model whose listing price is not zero")
    ap.add_argument("--label", default=None)
    ap.add_argument("--max-calls", type=int, default=60, help="global model-call budget (default 60)")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between model calls (default 3, free tiers)")
    ap.add_argument("--max-rate-limit-errors", type=int, default=1,
                    help="stop after this many 429s that survived the bounded retries (default 1)")
    ap.add_argument("--cases", nargs="*", default=None, help="case ids (default: the five core cases; none: skip)")
    ap.add_argument("--scenarios", nargs="*", default=None,
                    help=f"usability scenario ids, 'all', or nothing to skip (default: {' '.join(DEFAULT_SCENARIOS)})")
    ap.add_argument("--modes", nargs="*", default=None, choices=MODES)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--with-safety-classifier", action="store_true",
                    help="also run the semantic safety classifier (one extra call per turn, same fixed model)")
    a = ap.parse_args(argv)
    code, _ = run_live_eval(get_settings(), a.target, allow_mock=a.allow_mock, allow_paid=a.allow_paid,
                            label=a.label, max_calls=a.max_calls, sleep_seconds=a.sleep,
                            max_rate_limit_errors=a.max_rate_limit_errors, case_ids=a.cases,
                            scenario_ids=a.scenarios, modes=a.modes, out_dir=a.out_dir,
                            with_safety_classifier=a.with_safety_classifier)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
