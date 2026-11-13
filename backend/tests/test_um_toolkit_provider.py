"""U-M GPT Toolkit provider contract (offline: httpx.MockTransport, synthetic content, no key ever sent anywhere)."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import FACTORIES, SUPPORTED_PROVIDERS, LLMError, LLMGateway, Target
from app.llm.um_toolkit import UMToolkitProvider

REPLY = {"reply": "Happy to help you plan a visit.", "audience": "prospect", "recommended_handoff": False,
         "handoff_category": "none", "handoff_reason": "", "language": "en"}


def _settings(**kw):
    base = dict(llm_provider="um_toolkit", um_toolkit_api_key="test-key-not-real", _env_file=None)
    return Settings(**{**base, **kw})  # type: ignore[arg-type]


def _client(seen, status=200, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {
            "model": "gpt-6.1-sol-2026-09-29",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(REPLY)}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 150,
                      "completion_tokens_details": {"reasoning_tokens": 60}}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_registered_without_removing_other_providers():
    assert "um_toolkit" in FACTORIES
    assert {"gemini", "openrouter", "ollama", "mock", "anthropic", "um_toolkit"} <= set(SUPPORTED_PROVIDERS)


def test_settings_default_model_and_base_url():
    s = _settings()
    assert s.llm_model == "gpt-6.1-sol"
    assert s.base_url_for("um_toolkit") == "https://api.toolkit.umgpt.umich.edu/v1"
    assert s.api_key_for("um_toolkit") == "test-key-not-real"
    assert _settings(um_toolkit_model="gpt-5.6-terra").llm_model == "gpt-5.6-terra"
    assert _settings(llm_model="gpt-6-luna").llm_model == "gpt-6-luna"


def test_request_shape_and_parsed_result():
    seen: list[httpx.Request] = []
    s = _settings()
    gw = LLMGateway(s, providers={"um_toolkit": UMToolkitProvider("test-key-not-real", s.base_url_for("um_toolkit"),
                                                                    client=_client(seen))})
    target = Target("um_toolkit", "gpt-6.1-sol")
    cfg = gw.generation_config(target)
    assert cfg.temperature is None  # reasoning models accept only the default
    res = gw._provider("um_toolkit").complete("system text", [{"role": "user", "content": "hi"},
                                                             {"role": "assistant", "content": "hello"},
                                                             {"role": "user", "content": "tour?"}], target, cfg)
    req = seen[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.toolkit.umgpt.umich.edu/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer test-key-not-real" and "x-title" not in req.headers
    assert "max_completion_tokens" in body and "max_tokens" not in body
    assert "temperature" not in body and "reasoning" not in body
    assert body["messages"][0] == {"role": "system", "content": "system text"} and len(body["messages"]) == 4
    assert body["response_format"]["json_schema"]["strict"] is True
    assert res.output.reply == REPLY["reply"] and res.provider == "um_toolkit"
    assert res.input_tokens == 200 and res.extra["thinking_tokens"] == 60 and res.estimated_cost_usd is None


def test_dated_snapshot_counts_as_the_requested_model():
    from app.llm import same_model
    assert same_model("gpt-6.1-sol-2026-09-29", "gpt-6.1-sol")
    assert not same_model("gpt-6-sol", "gpt-6.1-sol")


@pytest.mark.parametrize("status,code", [(400, "MODEL_BAD_REQUEST"), (401, "MODEL_AUTH_ERROR"),
                                         (404, "MODEL_NOT_FOUND")])
def test_gateway_errors_map_without_leaking_the_key(status, code):
    seen: list[httpx.Request] = []
    p = UMToolkitProvider("test-key-not-real", "https://api.toolkit.umgpt.umich.edu/v1",
                          client=_client(seen, status, {"error": {"message": "unsupported_parameter"}}))
    with pytest.raises(LLMError) as e:
        p.complete("s", [{"role": "user", "content": "hi"}], Target("um_toolkit", "gpt-6.1-sol"),
                   LLMGateway(_settings()).generation_config(Target("um_toolkit", "gpt-6.1-sol")))
    assert e.value.code == code and "test-key-not-real" not in str(e.value)


def test_missing_key_is_reported_not_sent():
    p = UMToolkitProvider(None, "https://api.toolkit.umgpt.umich.edu/v1")
    with pytest.raises(LLMError) as e:
        p.complete("s", [], Target("um_toolkit", "gpt-6.1-sol"),
                   LLMGateway(_settings()).generation_config(Target("um_toolkit", "gpt-6.1-sol")))
    assert e.value.code == "NEEDS_API_KEY" and "UM_TOOLKIT_API_KEY" in str(e.value)
    assert LLMGateway(_settings(um_toolkit_api_key=None)).provider_ready("um_toolkit") == (False, "NEEDS_API_KEY")


def test_refused_on_a_hosted_backend_until_use_is_approved():
    hosted = dict(app_env="hosted", staff_api_token="x" * 32, cors_origins="https://example.org",
                  database_url="postgresql://u:p@db.example.org/x")
    assert any("um_toolkit" in p for p in _settings(**hosted).hosted_problems())
    assert not any("um_toolkit" in p for p in _settings(**hosted, um_toolkit_hosted_approved=True).hosted_problems())
