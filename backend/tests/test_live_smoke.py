"""Live smoke script, fully offline: fake providers (httpx.MockTransport / fake google-genai client), no key, no net."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.config import Settings
from app.live_eval import smoke
from app.llm.gemini_provider import GeminiProvider
from app.llm.openrouter import OpenRouterProvider

OR_MODEL = "nvidia/nemotron-3.5-super-vl:free"
GEM_MODEL = "gemini-3.6-flash"
FAKE_KEY = "test-key-not-real"
REPLY = {"reply": "Happy to help. Which community are you interested in?", "audience": "unknown",
         "recommended_handoff": False, "handoff_category": "none", "handoff_reason": "", "language": "English"}
GATE = {"intent": "maintenance", "urgency": "high", "requires_human": False, "handoff_reason": "",
        "confidence": 0.9, "risk_flags": []}
RISK = {"risk_level": "emergency", "risk_categories": ["gas"], "immediate_danger": True, "needs_human": True,
        "confidence": 0.9, "framing": "report", "reason": "Possible gas leak."}
BY_SCHEMA = {"mckinley_reply": REPLY, "mckinley_gate": GATE, "mckinley_risk": RISK}


def listing_client() -> httpx.Client:
    def handler(req):
        assert "authorization" not in req.headers
        return httpx.Response(200, json={"data": [{"id": OR_MODEL, "pricing": {"prompt": "0", "completion": "0"},
                                                   "context_length": 1000000,
                                                   "supported_parameters": ["response_format", "structured_outputs"]}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def or_provider(seen: list, *, rate_limit_at: int | None = None, served: str | None = None) -> dict:
    def handler(req):
        body = json.loads(req.content)
        seen.append(body)
        assert req.headers["authorization"] == f"Bearer {FAKE_KEY}"
        if rate_limit_at is not None and len(seen) == rate_limit_at:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        if body["model"] == smoke.BAD_MODEL["openrouter"]:
            return httpx.Response(400, json={"error": {"message": "not a valid model ID"}})
        content = json.dumps(BY_SCHEMA[body["response_format"]["json_schema"]["name"]])
        return httpx.Response(200, json={"model": served or body["model"], "choices": [
            {"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25,
                      "completion_tokens_details": {"reasoning_tokens": 5}}})
    return {"openrouter": OpenRouterProvider(FAKE_KEY, "https://openrouter.test/api/v1", "t",
                                             client=httpx.Client(transport=httpx.MockTransport(handler)))}


def gemini_provider(seen: list) -> dict:
    class Models:
        def generate_content(self, model, contents, config):
            seen.append({"model": model, "contents": contents})
            if model == smoke.BAD_MODEL["gemini"]:
                raise errors.ClientError(404, {"error": {"message": "not found"}})
            schema = config.response_json_schema
            name = ("mckinley_gate" if "intent" in schema["properties"] else
                    "mckinley_risk" if "risk_level" in schema["properties"] else "mckinley_reply")
            return SimpleNamespace(
                text=json.dumps(BY_SCHEMA[name]), model_version=model,
                candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))], prompt_feedback=None,
                usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=20,
                                               thoughts_token_count=5))
    return {"gemini": GeminiProvider(api_key=None, client=SimpleNamespace(models=Models()))}


def settings(tmp_path, provider="openrouter", key=True) -> Settings:
    kw = {}
    if key:
        kw = {"openrouter_api_key": FAKE_KEY} if provider == "openrouter" else {"gemini_api_key": FAKE_KEY}
    return Settings(_env_file=None, llm_provider=provider, db_path=tmp_path / "s.sqlite3", **kw)  # type: ignore[arg-type]


def run(tmp_path, provider="openrouter", **kw):
    logs: list[str] = []
    code, doc = smoke.run_smoke(kw.pop("settings", None) or settings(tmp_path, provider), provider,
                                out_dir=tmp_path / "out", models_client=listing_client(), sleeper=lambda s: None,
                                log=logs.append, label=kw.pop("label", "t"), **kw)
    return code, doc, logs


def steps(doc) -> dict:
    return {s["step"]: s for s in doc["steps"]}


# ------------------------------------------------------------------------------------------------- refusals
@pytest.mark.parametrize("provider,env", [("openrouter", "OPENROUTER_API_KEY"), ("gemini", "GEMINI_API_KEY")])
def test_no_key_is_blocked_and_calls_nothing(tmp_path, provider, env):
    seen: list = []
    prov = or_provider(seen) if provider == "openrouter" else gemini_provider(seen)
    code, doc, logs = run(tmp_path, provider, settings=settings(tmp_path, provider, key=False), providers=prov,
                          allow_paid=True)
    assert code == smoke.EXIT_BLOCKED and doc["status"] == "blocked" and doc["reason_code"] == "NEEDS_API_KEY"
    assert not seen and any(line.startswith("BLOCKED NEEDS_API_KEY") and env in line for line in logs)
    assert json.loads((tmp_path / "out" / "smoke-t.json").read_text())["status"] == "blocked"


def test_gemini_needs_allow_paid(tmp_path):
    seen: list = []
    code, doc, _ = run(tmp_path, "gemini", providers=gemini_provider(seen))
    assert code == smoke.EXIT_BLOCKED and doc["reason_code"] == "MAY_BE_BILLED" and not seen


@pytest.mark.parametrize("n", [0, 9, 60])
def test_budget_is_hard_capped_at_8(tmp_path, n):
    code, doc, _ = run(tmp_path, providers=or_provider([]), max_calls=n)
    assert code == smoke.EXIT_BLOCKED and doc["reason_code"] == "BAD_BUDGET"


def test_unlisted_openrouter_model_is_blocked(tmp_path):
    seen: list = []
    code, doc, _ = run(tmp_path, providers=or_provider(seen), model="made-up/model:free")
    assert code == smoke.EXIT_BLOCKED and doc["reason_code"] == "MODEL_NOT_LISTED" and not seen


def test_main_without_key_prints_blocked_and_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "get_settings", lambda: settings(tmp_path, key=False))
    assert smoke.main(["--provider", "openrouter", "--out-dir", str(tmp_path)]) == smoke.EXIT_BLOCKED
    out = capsys.readouterr().out
    assert "BLOCKED NEEDS_API_KEY" in out and "OPENROUTER_API_KEY" in out


# ---------------------------------------------------------------------------------------------- full runs
@pytest.mark.parametrize("provider", ["openrouter", "gemini"])
def test_full_smoke_passes_through_the_real_app_path(tmp_path, provider):
    seen: list = []
    prov = or_provider(seen) if provider == "openrouter" else gemini_provider(seen)
    code, doc, _ = run(tmp_path, provider, providers=prov, allow_paid=True)
    st = steps(doc)
    assert code == smoke.EXIT_PASS and doc["status"] == "pass", doc["steps"]
    assert len(seen) == doc["budget"]["calls_made"] == 7 <= smoke.HARD_CAP
    model = OR_MODEL if provider == "openrouter" else GEM_MODEL
    for name in ("leasing_inquiry", "resident_maintenance", "follow_up", "gate_decision", "risk_classifier"):
        assert st[name]["status"] == "pass" and st[name]["served_model"] == model
        assert st[name]["input_tokens"] and st[name]["thinking_tokens"] and st[name]["latency_ms"] is not None
    assert st["follow_up"]["model_calls"] == 2 and len(st["follow_up"]["turns"]) == 2
    assert st["resident_maintenance"]["persona"] in ("R001", "U-NOMATCH")  # workbook is git-ignored
    assert st["gate_decision"]["decision"]["intent"] == "maintenance"
    assert st["risk_classifier"]["classifier_status"] == "ok" and st["risk_classifier"]["agrees_with_expected"]
    assert st["bad_model_id"]["error_code"] in smoke.BAD_MODEL_CODES
    assert all(c["schema_name"] for s in doc["steps"] for c in s["calls"])
    text = (tmp_path / "out" / "smoke-t.json").read_text()
    assert FAKE_KEY not in text and json.loads(text)["provider"] == provider
    if provider == "openrouter":  # history really sent on the follow-up turn
        assert [m["role"] for m in seen[3]["messages"]][:1] == ["system"] and len(seen[3]["messages"]) >= 4
    else:
        assert len(seen[3]["contents"]) >= 3


def test_stops_on_the_first_429(tmp_path):
    seen: list = []
    code, doc, _ = run(tmp_path, providers=or_provider(seen, rate_limit_at=1))
    st = steps(doc)
    assert code == smoke.EXIT_STOPPED and doc["status"] == "stopped" and doc["stop_code"] == "RATE_LIMITED"
    assert len(seen) == 1  # no same-model retry, nothing after the 429
    assert all(st[n]["status"] == "not_run" for n in ("resident_maintenance", "follow_up", "bad_model_id"))


def test_small_budget_skips_steps_and_is_not_a_pass(tmp_path):
    seen: list = []
    code, doc, _ = run(tmp_path, providers=or_provider(seen), max_calls=3)
    st = steps(doc)
    assert len(seen) <= 3 and code == smoke.EXIT_FAIL and doc["status"] == "partial"
    assert st["follow_up"]["status"] == "skipped_budget"


def test_served_model_switch_fails_the_step(tmp_path):
    code, doc, _ = run(tmp_path, providers=or_provider([], served="other/model"))
    assert code == smoke.EXIT_FAIL
    assert steps(doc)["leasing_inquiry"]["status"] == "fail"
