"""Preflight for the controlled live evaluation. Spends nothing and never reads or prints a key's value.

    uv run python -m app.live_eval.preflight            # writes evals/live/preflight.json

Checks: provider keys present (booleans only), provider readiness, Ollama reachability, and each configured
OpenRouter model ID against the PUBLIC model list (GET https://openrouter.ai/api/v1/models, no key sent): listed,
free, per-token pricing, context length, structured-output support. Recommends one fixed model for the A/B/C
comparison from EVAL_TARGETS. Exit code 0 = a live run can start, 3 = blocked (reasons printed and saved).
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import REPO_DIR, Settings, get_settings
from app.llm import LLMGateway, Target

MODELS_URL = "https://openrouter.ai/api/v1/models"
OUT_DIR = REPO_DIR / "evals" / "live"
EXIT_READY, EXIT_BLOCKED = 0, 3


def fetch_models(client: httpx.Client | None = None, timeout: float = 10.0,
                 url: str = MODELS_URL) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """Public listing keyed by model id, or (None, error). No Authorization header is ever sent."""
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None, f"model list returned HTTP {resp.status_code}"
        data = resp.json().get("data")
        if not isinstance(data, list):
            return None, "model list had no 'data' array"
        return {m["id"]: m for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)}, None
    except httpx.TimeoutException:
        return None, f"model list timed out after {timeout:.0f}s"
    except httpx.HTTPError as e:
        return None, f"model list unreachable ({type(e).__name__})"
    except ValueError:
        return None, "model list was not valid JSON"
    finally:
        if own:
            client.close()


def _price(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def model_info(model_id: str, listing: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """What the public listing says about one model ID (exact ID match only: no fuzzy substitution)."""
    if listing is None:
        return {"model": model_id, "listed": None, "note": "model list unavailable; could not verify"}
    m = listing.get(model_id)
    if m is None:
        base = model_id.removesuffix(":free")
        near = sorted(i for i in listing if i.removesuffix(":free") == base and i != model_id)
        return {"model": model_id, "listed": False, "similar_ids_listed": near}
    pricing = m.get("pricing") or {}
    p_in, p_out = _price(pricing.get("prompt")), _price(pricing.get("completion"))
    params = m.get("supported_parameters") or []
    top = m.get("top_provider") or {}
    return {
        "model": model_id,
        "listed": True,
        "name": m.get("name"),
        "free": p_in == 0 and p_out == 0,
        "pricing_prompt_usd_per_token": p_in,
        "pricing_completion_usd_per_token": p_out,
        "context_length": m.get("context_length"),
        "max_completion_tokens": top.get("max_completion_tokens"),
        "supports_response_format": "response_format" in params,
        "supports_structured_outputs": "structured_outputs" in params,
        "reasoning_mandatory": bool((m.get("reasoning") or {}).get("mandatory")),
        "expiration_date": m.get("expiration_date"),
        "may_retain_prompts": "retain" in str(m.get("description") or "").lower()
                              or model_id.endswith(":free"),
    }


def _ollama_reachable(base_url: str, client: httpx.Client | None, timeout: float = 2.0) -> bool:
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        return client.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        if own:
            client.close()


def recommend(targets: list[dict[str, Any]]) -> tuple[str | None, str]:
    """First configured OpenRouter target (EVAL_TARGETS order) that is listed, free and supports structured
    outputs; then listed+free; never a model that is not in the listing."""
    orr = [t for t in targets if t["provider"] == "openrouter" and t["info"].get("listed")]
    for want, why in ((lambda i: i.get("free") and i.get("supports_structured_outputs"),
                       "listed, free, supports structured outputs (strict JSON schema)"),
                      (lambda i: i.get("free"), "listed and free, but NO structured-output support listed: "
                                                "expect more JSON-contract failures")):
        for t in orr:
            if want(t["info"]):
                return t["target"], f"{why}; first such model in EVAL_TARGETS order"
    if any(t["provider"] == "openrouter" and t["info"].get("listed") is None for t in targets):
        return None, "could not verify models (public model list unavailable)"
    return None, "no configured OpenRouter model is listed and free"


def run_preflight(settings: Settings, client: httpx.Client | None = None, timeout: float = 10.0) -> dict[str, Any]:
    gw = LLMGateway(settings)
    targets = gw.eval_targets()
    need_listing = any(t.provider == "openrouter" for t in targets)
    listing, list_error = fetch_models(client, timeout) if need_listing else (None, "not needed")
    keys = {p: bool(settings.api_key_for(p)) for p in ("openrouter", "anthropic")}
    ollama_ok = (_ollama_reachable(settings.base_url_for("ollama") or "http://localhost:11434", client)
                 if any(t.provider == "ollama" for t in targets) else None)
    rows = []
    for t in targets:
        ready, status = gw.provider_ready(t.provider)
        if t.provider == "ollama":
            ready, status = bool(ollama_ok), "local server reachable" if ollama_ok else "OLLAMA_NOT_REACHABLE"
        info = model_info(t.model, listing) if t.provider == "openrouter" else {"model": t.model, "listed": None,
                                                                                  "note": "not an OpenRouter model"}
        rows.append({"target": t.key, "provider": t.provider, "is_default": t == gw.default_target,
                     "is_mock": t.provider == "mock", "provider_ready": ready, "provider_status": status,
                     "info": info})
    rec, why = recommend(rows)
    blocked: list[str] = []
    if rec is None:
        blocked.append(f"NO_RECOMMENDED_MODEL: {why}")
    if not keys["openrouter"]:
        blocked.append("NEEDS_API_KEY: OPENROUTER_API_KEY is not set in backend/.env (presence checked only)")
    cfg = gw.generation_config(Target.parse(rec)) if rec else gw.generation_config(gw.default_target)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": "No secrets: key presence is reported as booleans only. No model was called.",
        "keys_present": keys,
        "ollama_reachable": ollama_ok,
        "default_target": gw.default_target.key,
        "generation_settings": {"temperature": cfg.temperature, "max_tokens": cfg.max_tokens,
                                "timeout_seconds": cfg.timeout_seconds, "max_retries": cfg.max_retries},
        "model_list": {"url": MODELS_URL, "fetched": listing is not None, "error": list_error if listing is None
                       else None, "models_listed": len(listing) if listing else 0},
        "targets": rows,
        "recommended_target": rec,
        "recommendation_reason": why,
        "live_ready": not blocked,
        "blocked_reasons": blocked,
    }


def write_preflight(report: dict[str, Any], out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "preflight.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    report = run_preflight(get_settings(), timeout=a.timeout)
    path = write_preflight(report, a.out_dir)
    ml = report["model_list"]
    print(f"Keys present: {report['keys_present']}  Ollama reachable: {report['ollama_reachable']}")
    print(f"Public model list: {'ok, ' + str(ml['models_listed']) + ' models' if ml['fetched'] else ml['error']}")
    for t in report["targets"]:
        i = t["info"]
        facts = ("not listed" if i.get("listed") is False else "unverified" if i.get("listed") is None else
                 f"free={i['free']} structured={i['supports_structured_outputs']} ctx={i['context_length']}")
        print(f"  {t['target']:<55} ready={t['provider_ready']!s:<5} {facts}")
    print(f"Recommended fixed model: {report['recommended_target']} ({report['recommendation_reason']})")
    if report["blocked_reasons"]:
        print("BLOCKED for a live run:")
        for r in report["blocked_reasons"]:
            print(f"  - {r}")
    print(f"Wrote {path}")
    return EXIT_READY if report["live_ready"] else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
