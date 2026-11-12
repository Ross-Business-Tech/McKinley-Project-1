"""Gemini behind an OpenAI-compatible gateway (GEMINI_BASE_URL): offline tests, httpx.MockTransport, no key.

The request/response shapes here mirror what the real gateway accepted in live probes on 2026-11-11 (see the
module docstring of app/llm/gemini_provider.py). No real address or key appears in this file.
"""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import LLMError, LLMGateway, Target
from app.llm.base import GenerationConfig
from app.llm.gemini_provider import GeminiProvider

BASE = "https://gateway.test/v1"
KEY = "test-not-a-real-key"
CFG = GenerationConfig(max_tokens=800, temperature=None, timeout_seconds=12, max_retries=2)
TARGET = Target("gemini", "gemini-3.6-flash")
REPLY = {"reply": "Happy to help with a tour.", "audience": "prospect", "recommended_handoff": False,
         "handoff_category": "none", "handoff_reason": "", "language": "en"}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.llm.http.time.sleep", lambda s: None)


def ok(content=None, finish="stop", model="gemini-3.6-flash", reasoning=0, completion=48):
    return {"model": model, "choices": [{"message": {"content": json.dumps(REPLY) if content is None else content},
                                         "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": completion,
                      "completion_tokens_details": {"reasoning_tokens": reasoning}}}


def make(responses, thinking_level="low"):
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        r = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, httpx.Response) else httpx.Response(200, json=r)

    p = GeminiProvider(KEY, thinking_level=thinking_level, base_url=BASE + "/",
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return p, seen


def test_request_shape_matches_the_verified_gateway_contract():
    p, seen = make([ok()])
    msgs = [{"role": "user", "content": "Can I tour Saturday?"}, {"role": "assistant", "content": "Sure."},
            {"role": "system", "content": "ignored"}, {"role": "user", "content": "2pm"}]
    r = p.complete("SYSTEM", msgs, TARGET, CFG)
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == BASE + "/chat/completions"  # trailing slash normalised
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "gemini-3.6-flash" and body["max_tokens"] == 800
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert body["messages"][0]["content"] == "SYSTEM"
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["strict"]
    assert body["reasoning_effort"] == "low"  # forwarded by the gateway to Gemini's thinking_level
    assert "temperature" not in body and "reasoning" not in body and "thinking" not in body
    assert r.output.reply == REPLY["reply"] and r.provider == "gemini" and r.model == "gemini-3.6-flash"
    assert (r.input_tokens, r.output_tokens) == (900, 48)
    assert (r.extra["thinking_tokens"], r.extra["answer_tokens"]) == (0, 48)
    assert r.extra["transport"] == "gateway" and r.extra["thinking_level"] == "low"


def test_no_thinking_level_sends_no_reasoning_parameter():
    p, seen = make([ok()], thinking_level=None)
    r = p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG)
    assert "reasoning_effort" not in json.loads(seen[0].content)
    assert r.extra["thinking_level"] == "model default"


def test_reasoning_tokens_are_counted_inside_completion_tokens():
    p, _ = make([ok(reasoning=383, completion=396)], thinking_level=None)
    r = p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG)
    assert r.output_tokens == 396 and r.extra["thinking_tokens"] == 383 and r.extra["answer_tokens"] == 13


def test_retries_429_and_5xx_on_the_same_model_then_succeeds():
    p, seen = make([httpx.Response(429, json={"error": {"message": "slow"}}),
                    httpx.Response(503, json={"error": {"message": "busy"}}), ok()])
    assert p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG).output.reply
    assert len(seen) == 3 and {json.loads(r.content)["model"] for r in seen} == {"gemini-3.6-flash"}


@pytest.mark.parametrize("resp,code", [
    (httpx.Response(401, json={"error": {"message": "Portkey Error: Invalid API Key.", "code": "03"}}),
     "MODEL_AUTH_ERROR"),
    (httpx.Response(404, json={"error": {"message": "models/x is not found", "code": 404}}), "MODEL_NOT_FOUND"),
    (httpx.Response(400, json={"error": {"message": "Invalid value at thinking_level"}}), "MODEL_BAD_REQUEST"),
    ({"error": {"code": 429, "message": "quota"}}, "MODEL_RATE_LIMITED"),
    ({"error": {"message": "opaque"}}, "MODEL_API_ERROR"),
    (ok(finish="length"), "MODEL_TRUNCATED"),
    (ok(content=""), "MODEL_EMPTY_RESPONSE"),
    (ok(finish="content_filter"), "MODEL_REFUSAL"),
    ({"model": "gemini-3.6-flash", "choices": []}, "MODEL_EMPTY_RESPONSE"),
])
def test_errors_map_to_gateway_codes_without_leaking_key(resp, code):
    p, _ = make([resp])
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET,
                   GenerationConfig(max_tokens=100, temperature=None, timeout_seconds=5, max_retries=0))
    assert ei.value.code == code and KEY not in ei.value.message


def test_connection_error_does_not_reveal_the_gateway_address():
    p, _ = make([httpx.ConnectError("down")])
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG)
    assert ei.value.code == "MODEL_CONNECTION_ERROR" and "gateway.test" not in ei.value.message


def test_no_key_raises_needs_api_key_without_a_request():
    seen: list[httpx.Request] = []
    p = GeminiProvider(None, base_url=BASE,
                       http_client=httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r))))  # type: ignore[arg-type,return-value]
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG)
    assert ei.value.code == "NEEDS_API_KEY" and not seen


def test_served_model_switch_is_rejected_by_the_gateway_layer(tmp_path):
    p, _ = make([ok(model="gemini-3.5-flash")])
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, db_path=tmp_path / "g.db")  # type: ignore[arg-type]
    with pytest.raises(LLMError) as ei:
        LLMGateway(s, {"gemini": p}).complete("s", [{"role": "user", "content": "hi"}])
    assert ei.value.code == "MODEL_SWITCHED"


# ---------------------------------------------------------------------------------------- settings wiring
def test_settings_wire_base_url_and_thinking_level_into_the_provider(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, gemini_base_url=BASE + "/",  # type: ignore[arg-type]
                 gemini_thinking_level="low", db_path=tmp_path / "w.db")
    p = LLMGateway(s)._provider("gemini")
    assert isinstance(p, GeminiProvider) and p.transport == "gateway"
    assert p._base_url == BASE and p._thinking_level == "low"
    assert s.llm_model == "gemini-3.6-flash"  # provider default model


def test_without_base_url_the_google_sdk_transport_is_kept(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, db_path=tmp_path / "s.db")  # type: ignore[arg-type]
    assert s.base_url_for("gemini") is None
    assert LLMGateway(s)._provider("gemini").transport == "google-genai"  # type: ignore[attr-defined]


def test_gemini_is_the_default_provider_and_openrouter_stays_selectable(tmp_path):
    d = Settings(_env_file=None, db_path=tmp_path / "d.db")
    assert (d.llm_provider, d.llm_model) == ("gemini", "gemini-3.6-flash")
    o = Settings(_env_file=None, llm_provider="openrouter", db_path=tmp_path / "o.db")  # type: ignore[arg-type]
    assert (o.llm_provider, o.llm_model) == ("openrouter", "nvidia/nemotron-3.5-super-vl:free")
    assert LLMGateway(o)._provider("openrouter").name == "openrouter"


def test_hosted_backend_refuses_a_non_https_gateway(tmp_path):
    kw = dict(_env_file=None, app_env="hosted", llm_provider="gemini", db_path=tmp_path / "h.db",
              cors_origins="https://site.example",
              staff_api_token="x" * 12 + "abcdefghijkl", database_url="postgresql://u:p@db.example/x")
    bad = Settings(**kw, gemini_base_url="http://plain.example/v1")  # type: ignore[arg-type]
    assert any("GEMINI_BASE_URL" in p for p in bad.hosted_problems())
    good = Settings(**kw, gemini_base_url=BASE)  # type: ignore[arg-type]
    assert not any("GEMINI_BASE_URL" in p for p in good.hosted_problems())


def test_preflight_lists_models_from_the_gateway(monkeypatch, tmp_path):
    from app.live_eval import preflight

    calls = []
    monkeypatch.setattr(preflight, "gemini_model_names", lambda key, base=None: calls.append(base) or
                        ["gemini-3.6-flash"])
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, gemini_base_url=BASE,  # type: ignore[arg-type]
                 eval_targets="gemini:gemini-3.6-flash", db_path=tmp_path / "p.db")
    out = preflight.run_preflight(s)
    assert calls == [BASE]
    row = next(t for t in out["targets"] if t["provider"] == "gemini")
    assert row["info"]["listed"] is True


def test_hosted_backend_must_name_its_provider_explicitly(tmp_path):
    """Gemini became the built-in default; a hosted backend relying on the default would switch silently."""
    kw = dict(_env_file=None, app_env="hosted", db_path=tmp_path / "x.db", cors_origins="https://site.example",
              staff_api_token="x" * 12 + "abcdefghijkl", database_url="postgresql://u:p@db.example/x")
    assert any("LLM_PROVIDER must be set" in p for p in Settings(**kw).hosted_problems())  # type: ignore[arg-type]
    for provider in ("openrouter", "gemini"):
        s = Settings(**kw, llm_provider=provider)  # type: ignore[arg-type]
        assert not any("LLM_PROVIDER" in p for p in s.hosted_problems())
