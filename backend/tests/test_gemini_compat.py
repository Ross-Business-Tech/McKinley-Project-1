"""Gemini through an OpenAI-compatible gateway (GEMINI_BASE_URL), driven by httpx.MockTransport (offline)."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import FACTORIES, LLMError, LLMGateway, Target
from app.llm.base import GenerationConfig
from app.llm.gemini_compat import GeminiCompatProvider
from app.llm.gemini_provider import GeminiProvider

REPLY = {"reply": "Hello", "needs_handoff": False}
CFG = GenerationConfig(max_tokens=500, temperature=None, timeout_seconds=5, max_retries=0)
TARGET = Target("gemini", "gemini-3.6-flash")


def _provider(handler, key="k"):
    return GeminiCompatProvider(key, "https://gw.example/v1/", "test",
                                client=httpx.Client(transport=httpx.MockTransport(handler)))


def _ok(model="gemini-3.6-flash"):
    return {"model": model, "choices": [{"finish_reason": "stop",
                                         "message": {"role": "assistant", "content": json.dumps(REPLY)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 30,
                      "completion_tokens_details": {"reasoning_tokens": 20}}}


def test_factory_uses_gateway_only_when_base_url_set():
    with_url = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k", gemini_base_url="https://gw/v1/")
    assert isinstance(FACTORIES["gemini"](with_url), GeminiCompatProvider)
    assert with_url.base_url_for("gemini") == "https://gw/v1"
    without = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k")
    assert isinstance(FACTORIES["gemini"](without), GeminiProvider)


def test_request_shape_and_result():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_ok())

    r = _provider(handler).complete("sys", [{"role": "user", "content": "hi"}], TARGET, CFG)
    assert seen["url"] == "https://gw.example/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    body = seen["body"]
    assert body["model"] == "gemini-3.6-flash" and "temperature" not in body and "reasoning" not in body
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"]["type"] == "json_schema"
    assert r.provider == "gemini" and r.model == "gemini-3.6-flash" and r.output.reply == "Hello"
    assert r.extra["thinking_tokens"] == 20 and r.extra["thinking_level"] == "model default"


def test_no_key_never_calls():
    p = _provider(lambda req: pytest.fail("no request without a key"), key=None)
    with pytest.raises(LLMError) as e:
        p.complete("s", [], TARGET, CFG)
    assert e.value.code == "NEEDS_API_KEY" and "GEMINI_API_KEY" in e.value.message


def test_errors_are_labelled_as_gemini():
    p = _provider(lambda req: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(LLMError) as e:
        p.complete("s", [], TARGET, CFG)
    assert e.value.code == "MODEL_AUTH_ERROR" and "openrouter" not in e.value.message.lower()


def test_gateway_rejects_a_switched_model(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k", gemini_base_url="https://gw/v1",
                 db_path=tmp_path / "t.db")
    gw = LLMGateway(s, providers={"gemini": _provider(lambda req: httpx.Response(200, json=_ok("other-model")))})
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}])
    assert e.value.code == "MODEL_SWITCHED"
