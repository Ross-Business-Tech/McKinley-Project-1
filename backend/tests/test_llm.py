import json

import httpx
import pytest

from app.llm import LLMError, LLMGateway, Target, parse_output, same_model
from app.llm.base import GenerationConfig
from app.llm.mock import MockProvider
from app.llm.ollama import OllamaProvider
from app.llm.openrouter import OpenRouterProvider

CFG = GenerationConfig(max_tokens=500, temperature=0.2, timeout_seconds=5, max_retries=2)
OUT = {"reply": "Hello! Which day works?", "audience": "prospect", "recommended_handoff": False,
       "handoff_category": "none", "handoff_reason": "", "language": "English"}
T = Target("openrouter", "google/gemma-4-31b-it:free")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.llm.http.time.sleep", lambda s: None)


def or_response(content: str, model: str = "google/gemma-4-31b-it:free", finish: str = "stop") -> dict:
    return {"model": model, "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}}


def router(handler) -> OpenRouterProvider:
    return OpenRouterProvider("sk-test", "https://openrouter.test/api/v1", "test",
                              client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_output_modes():
    assert parse_output(json.dumps(OUT))[1] == "json"
    assert parse_output("```json\n" + json.dumps(OUT) + "\n```")[1] == "json"
    out, mode = parse_output("Sure! " + json.dumps(OUT) + " Thanks")
    assert mode == "json_extracted" and out.reply.startswith("Hello")
    out, mode = parse_output("Just plain text reply")
    assert mode == "text_fallback" and out.reply == "Just plain text reply" and not out.recommended_handoff
    out, _ = parse_output(json.dumps({**OUT, "handoff_category": "made_up", "recommended_handoff": True}))
    assert out.handoff_category == "other"
    with pytest.raises(LLMError) as e:
        parse_output("  ")
    assert e.value.code == "MODEL_EMPTY_RESPONSE"


def test_openrouter_success_and_payload():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json=or_response(json.dumps(OUT)))

    r = router(handler).complete("SYS", [{"role": "user", "content": "hi"}], T, CFG)
    assert r.output.reply.startswith("Hello") and r.input_tokens == 120 and r.output_tokens == 30
    body = seen["body"]
    assert body["model"] == T.model and "models" not in body  # no model fallback list
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["temperature"] == 0.2 and body["response_format"]["type"] == "json_schema"
    assert seen["auth"] == "Bearer sk-test"


def test_openrouter_retries_429_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=or_response(json.dumps(OUT)))

    assert router(handler).complete("s", [], T, CFG).output.reply
    assert len(calls) == 2


@pytest.mark.parametrize("status,code", [(401, "MODEL_AUTH_ERROR"), (402, "MODEL_PAYMENT_REQUIRED"),
                                         (404, "MODEL_NOT_FOUND"), (429, "MODEL_RATE_LIMITED"),
                                         (400, "MODEL_BAD_REQUEST"), (503, "MODEL_API_ERROR")])
def test_openrouter_error_mapping(status, code):
    p = router(lambda req: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(LLMError) as e:
        p.complete("s", [], T, CFG)
    assert e.value.code == code


def test_openrouter_timeout_and_truncation():
    def boom(req):
        raise httpx.ReadTimeout("t")
    with pytest.raises(LLMError) as e:
        router(boom).complete("s", [], T, CFG)
    assert e.value.code == "MODEL_TIMEOUT" and e.value.retryable
    with pytest.raises(LLMError) as e:
        router(lambda r: httpx.Response(200, json=or_response("{", finish="length"))).complete("s", [], T, CFG)
    assert e.value.code == "MODEL_TRUNCATED"


def test_openrouter_requires_key():
    with pytest.raises(LLMError) as e:
        OpenRouterProvider(None, "https://x", "t").complete("s", [], T, CFG)
    assert e.value.code == "NEEDS_API_KEY"


def test_gateway_rejects_silent_model_switch(settings):
    p = router(lambda r: httpx.Response(200, json=or_response(json.dumps(OUT), model="meta/other-model")))
    gw = LLMGateway(settings, providers={"openrouter": p})
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}], T)
    assert e.value.code == "MODEL_SWITCHED"


def test_same_model_normalization():
    assert same_model("google/gemma-4-31b-it", "google/gemma-4-31b-it:free")
    assert same_model("llama3.2:latest", "llama3.2")
    assert same_model("claude-x-20260101", "claude-x")
    assert not same_model("google/gemma-4-31b-it-instruct", "google/gemma-4-31b-it")


def test_ollama_success_and_errors():
    def ok(req):
        body = json.loads(req.content)
        assert body["format"]["type"] == "object" and body["stream"] is False
        return httpx.Response(200, json={"model": "llama3.2", "message": {"content": json.dumps(OUT)},
                                         "done_reason": "stop", "prompt_eval_count": 50, "eval_count": 20})
    p = OllamaProvider("http://ollama.test", client=httpx.Client(transport=httpx.MockTransport(ok)))
    r = p.complete("s", [], Target("ollama", "llama3.2"), CFG)
    assert r.input_tokens == 50 and r.estimated_cost_usd == 0.0

    p = OllamaProvider("http://ollama.test", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "model not found"}))))
    with pytest.raises(LLMError) as e:
        p.complete("s", [], Target("ollama", "llama3.2"), CFG)
    assert "ollama pull llama3.2" in e.value.message

    def refuse(req):
        raise httpx.ConnectError("refused")
    p = OllamaProvider("http://ollama.test", client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(LLMError) as e:
        p.complete("s", [], Target("ollama", "llama3.2"), CFG)
    assert e.value.code == "MODEL_CONNECTION_ERROR" and "ollama serve" in e.value.message


def test_mock_is_deterministic_and_labeled():
    m = MockProvider()
    msgs = [{"role": "user", "content": "<customer_message>\nMy AC broke\n</customer_message>"}]
    a = m.complete("s", msgs, Target("mock", "mock-v1"), CFG)
    b = m.complete("s", msgs, Target("mock", "mock-v1"), CFG)
    assert a.output == b.output and a.latency_ms == b.latency_ms and a.is_mock


def test_anthropic_without_key(settings):
    gw = LLMGateway(settings)
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}], Target("anthropic", "claude-opus-5-5"))
    assert e.value.code in {"NEEDS_API_KEY", "PROVIDER_NOT_INSTALLED"}


def test_unsupported_provider(settings):
    with pytest.raises(LLMError) as e:
        LLMGateway(settings).complete("s", [], Target("nope", "m"))
    assert e.value.code == "UNSUPPORTED_PROVIDER"


def test_eval_targets_parsing(settings):
    keys = [t.key for t in LLMGateway(settings).eval_targets()]
    assert keys[0] == "mock:mock-deterministic-v1"
    assert "openrouter:google/gemma-4-31b-it:free" in keys  # model ids containing ':' are preserved


def test_providers_are_isolated_from_resident_data():
    """Vendor adapters must not import workbook/persona/context code."""
    from pathlib import Path

    llm_dir = Path(__file__).resolve().parent.parent / "app" / "llm"
    for f in llm_dir.glob("*.py"):
        src = f.read_text()
        for forbidden in ("app.context", "app.personas", "openpyxl", "app.db"):
            assert forbidden not in src, f"{f.name} imports {forbidden}"
