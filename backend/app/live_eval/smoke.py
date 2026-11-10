"""Bounded live smoke test of one hosted provider through the REAL application path (at most 8 model calls).

    uv run python -m app.live_eval.smoke --provider openrouter --max-calls 8
    uv run python -m app.live_eval.smoke --provider gemini --allow-paid --max-calls 8

Steps (one fixed provider:model, rules gate for chat turns, same-model retries off so the first 429 surfaces):
  1. leasing_inquiry        run_turn, fictional prospect                          (1 reply call)
  2. resident_maintenance   run_turn, synthetic resident R001 (or unmatched)      (1 reply call)
  3. follow_up              run_turn x2 in one session (history sent)             (2 reply calls)
  4. gate_decision          app.gates.llm_gate.LLMGate.classify (gate schema)     (1 call)
  5. risk_classifier        app.risk.classifier.SemanticRiskClassifier (risk schema) (1 call)
  6. bad_model_id           gateway call to a model id that does not exist; checks the error mapping (1 call)

Records provider, served model, latency, tokens (thinking included), parse mode, reply source and error codes to
evals/live/smoke-<label>.json. Stops on the first 429 or any fatal configuration error. Without a key (or for Gemini
without --allow-paid) it prints BLOCKED, calls nothing and exits 3. Exit codes: 0 pass, 1 fail, 2 stopped, 3 blocked.
A pass proves the plumbing works with the live provider; it is NOT a quality or safety evaluation.
"""

import argparse
import json
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.live_eval.preflight import OUT_DIR, fetch_models, model_info
from app.live_eval.recorder import RecordingGateway, RunStopped
from app.llm import LLMError, LLMProvider, Target, same_model

HARD_CAP = 8
EXIT_PASS, EXIT_FAIL, EXIT_STOPPED, EXIT_BLOCKED = 0, 1, 2, 3
PROVIDERS = ("openrouter", "gemini")
BAD_MODEL = {"openrouter": "mckinley-smoke/no-such-model-v0", "gemini": "gemini-0-mckinley-no-such-model"}
BAD_MODEL_CODES = {"MODEL_NOT_FOUND", "MODEL_BAD_REQUEST"}  # OpenRouter answers an unknown id with 400 or 404
GOOD_PARSE = {"json", "json_extracted"}

LEASING = ("P-RELOCATE-AA", "Hi! I'm relocating to Ann Arbor next month and need a 2-bedroom. "
                            "What can you tell me about your floor plans?")
MAINTENANCE = "My bathroom sink has been draining slowly for two days. Can someone take a look?"
FOLLOW_UP = ("P-BROWSE-FL", ["Do you allow pets at your Florida communities?",
                             "And what about parking for a second car?"])
GATE_MESSAGE = "The heat in my unit stopped working last night and it's freezing in here."
RISK_MESSAGE = "There's a strong rotten-egg smell by the stove and I'm feeling dizzy."


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def default_model(settings: Settings, provider: str) -> str:
    if provider == "gemini":
        return settings.llm_model if settings.llm_provider == "gemini" else settings.gemini_model
    if settings.llm_provider == "openrouter":
        return settings.llm_model
    for raw in settings.eval_targets.split(","):
        if raw.strip().startswith("openrouter:"):
            return Target.parse(raw).model
    return settings.llm_model


def _call_summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [c for c in calls if c.get("status") == "ok"]
    last = calls[-1] if calls else {}
    num = lambda k: sum(c[k] for c in ok if isinstance(c.get(k), int)) if ok else None  # noqa: E731
    return {"model_calls": len(calls), "served_model": last.get("served_model"),
            "latency_ms": num("latency_ms"), "input_tokens": num("input_tokens"),
            "output_tokens": num("output_tokens"), "thinking_tokens": num("thinking_tokens"),
            "parse_modes": [c.get("parse_mode") for c in ok], "error_codes": [c["error_code"] for c in calls
                                                                             if c.get("error_code")],
            "calls": calls}


def _calls_ok(calls: list[dict[str, Any]], target: Target, check_parse: bool = True) -> list[str]:
    problems = []
    for c in calls:
        if c.get("status") != "ok":
            problems.append(f"call_error:{c.get('error_code')}")
        elif not same_model(c.get("served_model") or "", target.model):
            problems.append(f"served_model:{c.get('served_model')}")
        elif check_parse and c.get("parse_mode") not in GOOD_PARSE:
            problems.append(f"parse_mode:{c.get('parse_mode')}")
    return problems


def run_smoke(settings: Settings, provider: str, *, model: str | None = None, max_calls: int = HARD_CAP,
              allow_paid: bool = False, label: str | None = None, out_dir: Path = OUT_DIR,
              sleep_seconds: float = 3.0, providers: dict[str, LLMProvider] | None = None,
              models_client: httpx.Client | None = None, sleeper: Callable[[float], None] = time.sleep,
              log: Callable[[str], None] = print) -> tuple[int, dict[str, Any]]:
    """Returns (exit_code, document); the document is always written to smoke-<label>.json."""
    target = Target(provider, model or default_model(settings, provider))
    label = label or f"{provider}-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"smoke-{label}.json"
    keys = {p: bool(settings.api_key_for(p)) for p in PROVIDERS}

    def write(doc: dict[str, Any]) -> None:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    def blocked(code: str, reason: str, **kw: Any) -> tuple[int, dict[str, Any]]:
        doc = {"status": "blocked", "reason_code": code, "reason": reason, "target": target.key,
               "keys_present": keys, "generated_at": _now(), **kw,
               "note": "No model was called. Key presence is reported as booleans only."}
        write(doc)
        log(f"BLOCKED {code}: {reason}")
        log(f"Wrote {path}")
        return EXIT_BLOCKED, doc

    if provider not in PROVIDERS:
        return blocked("UNSUPPORTED_PROVIDER", f"--provider must be one of {PROVIDERS}")
    if not 1 <= max_calls <= HARD_CAP:
        return blocked("BAD_BUDGET", f"--max-calls must be between 1 and {HARD_CAP}")
    if not keys[provider]:
        env = "OPENROUTER_API_KEY" if provider == "openrouter" else "GEMINI_API_KEY"
        return blocked("NEEDS_API_KEY", f"{env} is not set in backend/.env (presence checked only). Add it and "
                                        "re-run `uv run python -m app.live_eval.preflight` first.")
    if provider == "gemini" and not target.model.startswith("gemini"):
        return blocked("BAD_TARGET", f"'{target.model}' is not a Gemini model id")
    if provider == "gemini" and not allow_paid:
        return blocked("MAY_BE_BILLED", f"'{target.key}' may be billed on this key's Google project; pass "
                                        "--allow-paid after checking the project's quota and billing")
    listing: dict[str, Any] | None = None
    if provider == "openrouter":
        models, err = fetch_models(models_client)
        listing = {**model_info(target.model, models), "listing_error": err}
        if listing.get("listed") is False:
            return blocked("MODEL_NOT_LISTED", f"'{target.model}' is not in OpenRouter's public model list",
                           listing=listing)
        if listing.get("listed") and not listing.get("free") and not allow_paid:
            return blocked("MODEL_NOT_FREE", f"'{target.model}' is priced; pass --allow-paid", listing=listing)

    run_settings = settings.model_copy(update={
        "llm_provider": provider, "llm_model": target.model, "decision_gate_provider": "rules",
        "gate_override_enabled": False, "safety_classifier": "off", "safety_classifier_target": None,
        "llm_max_retries": 0,  # the first 429 must surface (and stop the run), not be retried away
        "db_path": Path(tempfile.mkdtemp(prefix="live-smoke-")) / "smoke.sqlite3",
    })
    gw = RecordingGateway(run_settings, providers, max_calls=max_calls, sleep_seconds=sleep_seconds,
                          max_rate_limit_errors=1, sleeper=sleeper)
    if listing and listing.get("listed"):
        gw.pricing[target.model] = (listing["pricing_prompt_usd_per_token"],
                                    listing["pricing_completion_usd_per_token"])

    from app.chat_engine import prompt_for, run_turn
    from app.db import Store
    from app.gates.base import GateContext
    from app.gates.llm_gate import LLMGate
    from app.risk.classifier import PROMPT_VERSION as RISK_PROMPT_VERSION
    from app.risk.classifier import SemanticRiskClassifier
    from app.state import build_state

    deps = build_state(settings=run_settings, gateway=gw, store=Store(run_settings.db_path)).deps
    resident = "R001" if deps.workbook and "R001" in getattr(deps.workbook, "residents", {}) else "U-NOMATCH"

    def chat(step: str, persona: str, messages: list[str]) -> dict[str, Any]:
        n0, sid, turns = len(gw.calls), None, []
        for m in messages:
            resp = run_turn(deps, m, "aware", persona, session_id=sid, use_history=True, target=target)
            sid = resp.session_id
            turns.append({"user": m, "reply": resp.reply, "reply_source": resp.reply_source,
                          "parse_mode": resp.parse_mode, "model": resp.model,
                          "workflow": getattr(resp.workflow, "id", None),
                          "action": getattr(getattr(resp, "action", None), "kind", None),
                          "recommended_handoff": resp.recommended_handoff})
        calls = gw.calls[n0:]
        problems = _calls_ok(calls, target)
        status = "no_model_call" if not calls and not problems else ("fail" if problems else "pass")
        return {"persona": persona, "turns": turns, "problems": problems, "status": status, **_call_summary(calls)}

    def gate() -> dict[str, Any]:
        n0 = len(gw.calls)
        ctx = GateContext(audience="resident", identity_verified=True, record_found=True, topics=["maintenance"])
        d = LLMGate(gw, target, timeout_seconds=run_settings.llm_timeout_seconds).classify(
            GATE_MESSAGE, ctx, None)  # type: ignore[arg-type]  # rules decision is not used by the LLM gate
        calls = gw.calls[n0:]
        problems = _calls_ok(calls, target, check_parse=False)  # gate JSON has no 'reply': parsed by the gate
        return {"decision": {"intent": d.intent, "urgency": d.urgency, "requires_human": d.requires_human,
                             "confidence": d.confidence, "risk_flags": d.risk_flags,
                             "decision_source": d.decision_source},
                "problems": problems, "status": "fail" if problems else "pass", **_call_summary(calls)}

    def risk() -> dict[str, Any]:
        n0 = len(gw.calls)
        cs = run_settings.model_copy(update={"safety_classifier": "auto", "safety_classifier_target": target.key})
        res = SemanticRiskClassifier(cs, gw).classify(RISK_MESSAGE)
        calls = gw.calls[n0:]
        problems = _calls_ok(calls, target, check_parse=False)
        if res.status != "ok":
            problems.append(f"classifier_status:{res.status}:{res.detail}")
        level = res.risk.risk_level if res.risk else None
        return {"prompt_version": RISK_PROMPT_VERSION, "classifier_status": res.status, "risk_level": level,
                "expected_risk_level": "emergency", "agrees_with_expected": level == "emergency",
                "note": "one sample: structured-output plumbing only, not a recall measurement",
                "problems": problems, "status": "fail" if problems else "pass", **_call_summary(calls)}

    def bad_model() -> dict[str, Any]:
        n0 = len(gw.calls)
        code = None
        try:
            gw.complete("Reply with JSON.", [{"role": "user", "content": "ping"}],
                        Target(provider, BAD_MODEL[provider]))
        except LLMError as e:
            code = e.code
        calls = gw.calls[n0:]
        ok = code in BAD_MODEL_CODES
        return {"requested_bad_model": BAD_MODEL[provider], "error_code": code, "expected": sorted(BAD_MODEL_CODES),
                "problems": [] if ok else [f"unexpected:{code}"], "status": "pass" if ok else "fail",
                **_call_summary(calls)}

    steps: list[tuple[str, int, Callable[[], dict[str, Any]]]] = [
        ("leasing_inquiry", 1, lambda: chat("leasing_inquiry", LEASING[0], [LEASING[1]])),
        ("resident_maintenance", 1, lambda: chat("resident_maintenance", resident, [MAINTENANCE])),
        ("follow_up", 2, lambda: chat("follow_up", FOLLOW_UP[0], FOLLOW_UP[1])),
        ("gate_decision", 1, gate),
        ("risk_classifier", 1, risk),
        ("bad_model_id", 1, bad_model),
    ]
    log(f"LIVE smoke on {target.key}: {len(steps)} steps, budget {max_calls} calls, sleep {sleep_seconds}s")
    results: list[dict[str, Any]] = []
    stop: tuple[str, str] | None = None
    for name, need, fn in steps:
        if stop:
            results.append({"step": name, "status": "not_run"})
            continue
        if len(gw.calls) + need > max_calls:
            results.append({"step": name, "status": "skipped_budget", "needs_calls": need})
            continue
        t0 = time.perf_counter()
        try:
            r = fn()
        except RunStopped as e:
            r = {"status": "stopped", "error_code": e.code, "problems": [e.message]}
        except LLMError as e:
            r = {"status": "fail", "error_code": e.code, "problems": [e.message[:300]]}
        except Exception as e:  # report, never crash the run (no content logged)
            r = {"status": "fail", "error_code": type(e).__name__, "problems": [str(e)[:300]]}
        r = {"step": name, "wall_ms": int((time.perf_counter() - t0) * 1000), **r}
        results.append(r)
        log(f"  {name:<22} {r['status']:<14} calls={r.get('model_calls', '?')} served={r.get('served_model')} "
            f"{' '.join(r.get('problems') or [])[:160]}")
        if gw.stop_code and name != "bad_model_id":  # the bad-model step stops the recorder by design
            stop = (gw.stop_code, gw.stop_message or "")

    run = [r for r in results if r["status"] not in ("not_run", "skipped_budget")]
    reply_steps = [r for r in results if r["step"] in ("leasing_inquiry", "resident_maintenance", "follow_up")]
    if stop or any(r["status"] == "stopped" for r in run):
        status, code = "stopped", EXIT_STOPPED
    elif any(r["status"] == "fail" for r in run) or not any(r.get("model_calls") for r in reply_steps):
        status, code = "fail", EXIT_FAIL
    else:
        status, code = ("pass", EXIT_PASS) if len(run) == len(steps) else ("partial", EXIT_FAIL)
    doc = {
        "status": status, "label": label, "generated_at": _now(), "execution": "LIVE",
        "provider": provider, "target": target.key, "requested_model": target.model,
        "served_models": sorted({c["served_model"] for c in gw.calls if c.get("served_model")}),
        "prompt_versions": {"aware": prompt_for("aware", run_settings).version, "risk": RISK_PROMPT_VERSION},
        "generation_settings": {"max_tokens": run_settings.llm_max_tokens, "temperature":
                                gw.generation_config(target).temperature, "max_retries_same_model": 0,
                                "timeout_seconds": run_settings.llm_timeout_seconds},
        "budget": {"max_calls": max_calls, "hard_cap": HARD_CAP, "calls_made": len(gw.calls),
                   "sleep_seconds": sleep_seconds},
        "stop_code": stop[0] if stop else None, "stop_message": stop[1] if stop else None,
        "listing": listing, "keys_present": keys, "steps": results,
        "note": "Smoke test of live plumbing on synthetic data only. Not a quality, safety or A/B/C result.",
    }
    write(doc)
    log(f"Smoke {status.upper()} ({len(gw.calls)}/{max_calls} calls). Wrote {path}")
    return code, doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--model", default=None, help="model id (default: LLM_MODEL / GEMINI_MODEL / first EVAL_TARGET)")
    ap.add_argument("--max-calls", type=int, default=HARD_CAP, help=f"model-call budget, 1..{HARD_CAP}")
    ap.add_argument("--allow-paid", action="store_true", help="required for Gemini and for a priced OpenRouter model")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between model calls (default 3)")
    ap.add_argument("--label", default=None)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    code, _ = run_smoke(get_settings(), a.provider, model=a.model, max_calls=a.max_calls, allow_paid=a.allow_paid,
                        label=a.label, out_dir=a.out_dir, sleep_seconds=a.sleep)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
