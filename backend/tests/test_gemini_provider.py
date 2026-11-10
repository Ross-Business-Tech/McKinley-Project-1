"""Gemini provider adapter: offline tests with a fake SDK client (no network, no API calls, no key)."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.config import Settings
from app.gates.llm_gate import GATE_SCHEMA, GATE_SCHEMA_NAME
from app.llm import LLMError, LLMGateway, Target
from app.llm.base import GenerationConfig
from app.llm.gemini_provider import GeminiProvider, _to_contents

CFG = GenerationConfig(max_tokens=800, temperature=0.2, timeout_seconds=12, max_retries=2)
TARGET = Target("gemini", "gemini-3.6-flash")
REPLY = {"reply": "Got it.", "audience": "resident", "recommended_handoff": False, "handoff_category": "none",
         "handoff_reason": "", "language": "en"}


REPLY_JSON = json.dumps(REPLY)


def response(text=REPLY_JSON, finish="STOP", model="gemini-3.6-flash", block=None):
    return SimpleNamespace(
        text=text, model_version=model,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
        usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=30, thoughts_token_count=12))


class FakeModels:
    def __init__(self, result):
        self.result, self.calls = result, []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def provider(result):
    models = FakeModels(result)
    return GeminiProvider(api_key=None, client=SimpleNamespace(models=models)), models


def test_request_shape_system_history_schema_and_limits():
    p, models = provider(response())
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "my sink leaks"}]
    r = p.complete("SYSTEM PROMPT", msgs, TARGET, CFG)
    call = models.calls[0]
    cfg = call["config"]
    assert call["model"] == "gemini-3.6-flash"
    assert [c["role"] for c in call["contents"]] == ["user", "model", "user"]
    assert cfg.system_instruction == "SYSTEM PROMPT" and cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema["required"][0] == "reply"
    assert cfg.max_output_tokens == 800 and cfg.temperature == 0.2
    assert cfg.http_options.timeout == 12000 and cfg.http_options.retry_options.attempts == 3
    assert r.output.reply == "Got it." and r.parse_mode == "json" and r.provider == "gemini"
    assert (r.input_tokens, r.output_tokens, r.extra["thinking_tokens"]) == (120, 30, 12)
    assert r.estimated_cost_usd is None  # no invented prices


def test_custom_schema_for_gate_classification():
    gate = {"intent": "maintenance", "urgency": "low", "requires_human": False, "handoff_reason": "",
            "confidence": 0.9, "risk_flags": []}
    p, models = provider(response(text=json.dumps(gate)))
    r = p.complete("gate", [{"role": "user", "content": "x"}], TARGET, CFG, schema=GATE_SCHEMA,
                   schema_name=GATE_SCHEMA_NAME)
    assert models.calls[0]["config"].response_json_schema is GATE_SCHEMA
    assert json.loads(r.extra["content"])["intent"] == "maintenance"


@pytest.mark.parametrize("exc,code", [
    (errors.ClientError(401, {"error": {"message": "bad key"}}), "MODEL_AUTH_ERROR"),
    (errors.ClientError(404, {"error": {"message": "no model"}}), "MODEL_NOT_FOUND"),
    (errors.ClientError(429, {"error": {"message": "quota"}}), "MODEL_RATE_LIMITED"),
    (errors.ClientError(400, {"error": {"message": "bad"}}), "MODEL_BAD_REQUEST"),
    (errors.ServerError(503, {"error": {"message": "overloaded"}}), "MODEL_API_ERROR"),
    (httpx.ReadTimeout("slow"), "MODEL_TIMEOUT"),
    (httpx.ConnectError("down"), "MODEL_CONNECTION_ERROR"),
])
def test_errors_map_to_gateway_codes(exc, code):
    p, _ = provider(exc)
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG)
    assert ei.value.code == code


@pytest.mark.parametrize("resp,code", [
    (response(finish="MAX_TOKENS"), "MODEL_TRUNCATED"),
    (response(finish="SAFETY"), "MODEL_REFUSAL"),
    (response(block="PROHIBITED_CONTENT"), "MODEL_REFUSAL"),
    (response(text=""), "MODEL_EMPTY_RESPONSE"),
])
def test_unusable_responses_are_errors_not_replies(resp, code):
    p, _ = provider(resp)
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG)
    assert ei.value.code == code


def test_non_json_text_is_recorded_as_text_fallback():
    p, _ = provider(response(text="Sure, I can help with that."))
    r = p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG)
    assert r.parse_mode == "text_fallback"


def test_no_key_means_needs_api_key_and_no_client():
    with pytest.raises(LLMError) as ei:
        GeminiProvider(api_key=None).complete("s", [{"role": "user", "content": "x"}], TARGET, CFG)
    assert ei.value.code == "NEEDS_API_KEY"


def test_gateway_rejects_a_different_served_model(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-not-a-real-key",
                 db_path=tmp_path / "g.sqlite3")
    p, _ = provider(response(model="gemini-3.5-flash-lite"))
    gw = LLMGateway(s, {"gemini": p})
    with pytest.raises(LLMError) as ei:
        gw.complete("s", [{"role": "user", "content": "x"}])
    assert ei.value.code == "MODEL_SWITCHED"
    p2, _ = provider(response(model="gemini-3.6-flash-001"))  # a dated/numbered snapshot of the same model is fine
    assert LLMGateway(s, {"gemini": p2}).complete("s", [{"role": "user", "content": "x"}]).provider == "gemini"


def test_settings_default_model_follows_provider(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", db_path=tmp_path / "a.sqlite3")
    assert s.llm_model == s.gemini_model == "gemini-3.6-flash"
    s2 = Settings(_env_file=None, llm_provider="gemini", llm_model="gemini-3.8-flash", db_path=tmp_path / "b.db")
    assert s2.llm_model == "gemini-3.8-flash"  # an explicit LLM_MODEL always wins
    gw = LLMGateway(Settings(_env_file=None, llm_provider="gemini", db_path=tmp_path / "c.db"))
    assert gw.provider_ready("gemini") == (False, "NEEDS_API_KEY")


def test_system_messages_in_history_are_not_sent_as_turns():
    assert _to_contents([{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]) == [
        {"role": "user", "parts": [{"text": "y"}]}]


def test_preflight_checks_gemini_model_without_generating(tmp_path):
    from app.live_eval.preflight import run_preflight

    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-not-a-real-key",
                 eval_targets="mock:mock-deterministic-v1,gemini:gemini-3.6-flash,gemini:gemini-9-made-up",
                 db_path=tmp_path / "p.sqlite3")
    report = run_preflight(s, gemini_lister=lambda key: ["gemini-3.6-flash", "gemini-3.5-flash-lite"])
    info = {r["target"]: r["info"] for r in report["targets"]}
    assert info["gemini:gemini-3.6-flash"]["listed"] is True
    assert info["gemini:gemini-9-made-up"]["listed"] is False
    assert report["keys_present"]["gemini"] is True and "test-not-a-real-key" not in json.dumps(report)
    no_key = Settings(_env_file=None, llm_provider="gemini", db_path=tmp_path / "q.sqlite3")
    r2 = run_preflight(no_key, gemini_lister=lambda key: pytest.fail("must not call without a key"))
    assert any("GEMINI_API_KEY" in b for b in r2["blocked_reasons"])


def test_live_abc_requires_allow_paid_for_gemini(tmp_path):
    from app.live_eval.abc import run_live_eval

    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-not-a-real-key",
                 db_path=tmp_path / "abc.sqlite3")
    p, models = provider(response())
    code, doc = run_live_eval(s, "gemini:gemini-3.6-flash", out_dir=tmp_path / "out", providers={"gemini": p},
                              log=lambda m: None)
    assert doc["status"] == "blocked" and doc["reason_code"] == "MAY_BE_BILLED" and not models.calls
