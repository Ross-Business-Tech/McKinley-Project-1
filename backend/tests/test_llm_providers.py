"""LLM providers: gateway, provider contracts (OpenRouter, Gemini, gateway, U-M Toolkit), call budget, and the offline
manual smoke/preflight tools."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
import pytest
from google.genai import errors

from app.config import Settings
from app.gates.base import GateContext
from app.gates.llm_gate import GATE_SCHEMA, GATE_SCHEMA_NAME, LLMGate, coerce_decision, parse_gate_json
from app.live_eval import smoke
from app.live_eval.preflight import fetch_models, model_info, recommend, run_preflight
from app.llm import FACTORIES, SUPPORTED_PROVIDERS, LLMError, LLMGateway, ModelOutput, Target, parse_output, same_model
from app.llm.base import OUTPUT_SCHEMA, GenerationConfig
from app.llm.base import Target as Target_lb
from app.llm.contracts import CLASSIFY_RISK, DECIDE_GATE, GENERATE_RESPONSE, MODEL_USES, complete_for
from app.llm.gemini_provider import GeminiProvider, _to_contents
from app.llm.mock import MockProvider
from app.llm.ollama import OllamaProvider
from app.llm.openrouter import OpenRouterProvider
from app.llm.um_toolkit import UMToolkitProvider
from app.risk import classifier as risk_classifier

# ---- test_llm

CFG = GenerationConfig(max_tokens=500, temperature=0.2, timeout_seconds=5, max_retries=2)


OUT = {"reply": "Hello! Which day works?", "audience": "prospect", "recommended_handoff": False,
       "handoff_category": "none", "handoff_reason": "", "language": "English"}


T = Target("openrouter", "google/gemma-4-31b-it:free")


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.llm.http.time.sleep", lambda s: None)


def or_response(content: str, model: str = "google/gemma-4-31b-it:free", finish: str = "stop") -> dict:
    return {"model": model, "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}}


def router(handler) -> OpenRouterProvider:
    return OpenRouterProvider("sk-test", "https://openrouter.test/api/v1", "test",
                              client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.usefixtures("no_sleep")
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


@pytest.mark.usefixtures("no_sleep")
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


@pytest.mark.usefixtures("no_sleep")
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
@pytest.mark.usefixtures("no_sleep")
def test_openrouter_error_mapping(status, code):
    p = router(lambda req: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(LLMError) as e:
        p.complete("s", [], T, CFG)
    assert e.value.code == code


@pytest.mark.usefixtures("no_sleep")
def test_openrouter_timeout_and_truncation():
    def boom(req):
        raise httpx.ReadTimeout("t")
    with pytest.raises(LLMError) as e:
        router(boom).complete("s", [], T, CFG)
    assert e.value.code == "MODEL_TIMEOUT" and e.value.retryable
    with pytest.raises(LLMError) as e:
        router(lambda r: httpx.Response(200, json=or_response("{", finish="length"))).complete("s", [], T, CFG)
    assert e.value.code == "MODEL_TRUNCATED"


@pytest.mark.usefixtures("no_sleep")
def test_openrouter_requires_key():
    with pytest.raises(LLMError) as e:
        OpenRouterProvider(None, "https://x", "t").complete("s", [], T, CFG)
    assert e.value.code == "NEEDS_API_KEY"


@pytest.mark.usefixtures("no_sleep")
def test_gateway_rejects_silent_model_switch(settings):
    p = router(lambda r: httpx.Response(200, json=or_response(json.dumps(OUT), model="meta/other-model")))
    gw = LLMGateway(settings, providers={"openrouter": p})
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}], T)
    assert e.value.code == "MODEL_SWITCHED"


@pytest.mark.usefixtures("no_sleep")
def test_same_model_normalization():
    assert same_model("google/gemma-4-31b-it", "google/gemma-4-31b-it:free")
    assert same_model("llama3.2:latest", "llama3.2")
    assert same_model("claude-x-20260101", "claude-x")
    assert not same_model("google/gemma-4-31b-it-instruct", "google/gemma-4-31b-it")


@pytest.mark.usefixtures("no_sleep")
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


@pytest.mark.usefixtures("no_sleep")
def test_mock_is_deterministic_and_labeled():
    m = MockProvider()
    msgs = [{"role": "user", "content": "<customer_message>\nMy AC broke\n</customer_message>"}]
    a = m.complete("s", msgs, Target("mock", "mock-v1"), CFG)
    b = m.complete("s", msgs, Target("mock", "mock-v1"), CFG)
    assert a.output == b.output and a.latency_ms == b.latency_ms and a.is_mock


@pytest.mark.usefixtures("no_sleep")
def test_anthropic_without_key(settings):
    gw = LLMGateway(settings)
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}], Target("anthropic", "claude-opus-5-5"))
    assert e.value.code in {"NEEDS_API_KEY", "PROVIDER_NOT_INSTALLED"}


@pytest.mark.usefixtures("no_sleep")
def test_unsupported_provider(settings):
    with pytest.raises(LLMError) as e:
        LLMGateway(settings).complete("s", [], Target("nope", "m"))
    assert e.value.code == "UNSUPPORTED_PROVIDER"


@pytest.mark.usefixtures("no_sleep")
def test_eval_targets_parsing(settings):
    keys = [t.key for t in LLMGateway(settings).eval_targets()]
    assert keys[0] == "mock:mock-deterministic-v1"
    assert "openrouter:google/gemma-4-31b-it:free" in keys  # model ids containing ':' are preserved


@pytest.mark.usefixtures("no_sleep")
def test_providers_are_isolated_from_resident_data():
    """Vendor adapters must not import workbook/persona/context code."""
    from pathlib import Path

    llm_dir = Path(__file__).resolve().parent.parent / "app" / "llm"
    for f in llm_dir.glob("*.py"):
        src = f.read_text()
        for forbidden in ("app.context", "app.personas", "openpyxl", "app.db"):
            assert forbidden not in src, f"{f.name} imports {forbidden}"


# ---- Provider contract: the SAME application-level expectations run against every hosted adapter.

CFG_pc = GenerationConfig(max_tokens=800, temperature=0.2, timeout_seconds=12, max_retries=0)


OR_MODEL = "nvidia/nemotron-3.5-super-vl:free"


GEM_MODEL = "gemini-3.6-flash"


FAKE_KEY = "test-not-a-real-key"


REPLY = {"reply": "Thanks! Which day works for a tour?", "audience": "prospect", "recommended_handoff": True,
         "handoff_category": "leasing_follow_up", "handoff_reason": "Tour request", "language": "English"}


GATE = {"intent": "maintenance", "urgency": "high", "requires_human": False, "handoff_reason": "",
        "confidence": 0.9, "risk_flags": []}


RISK = {"risk_level": "emergency", "risk_categories": ["gas"], "immediate_danger": True, "needs_human": True,
        "confidence": 0.92, "framing": "report", "reason": "Possible gas leak described."}


SAMPLES = {"generate_response": REPLY, "decide_gate": GATE, "classify_risk": RISK}


HISTORY = [{"role": "user", "content": "Hi, I'm looking at 2-bed apartments."},
           {"role": "assistant", "content": "Happy to help. Which city?"},
           {"role": "user", "content": "Ann Arbor. Can I tour this week?"}]


class ORHarness:
    """OpenRouter over httpx.MockTransport. A 'spec' is a JSON body (200), an httpx.Response, or an exception."""

    name, model, wire = "openrouter", OR_MODEL, "openai"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def provider(self, spec: Any) -> OpenRouterProvider:
        def handler(req: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(req.content))
            if isinstance(spec, Exception):
                raise spec
            return spec if isinstance(spec, httpx.Response) else httpx.Response(200, json=spec)
        return OpenRouterProvider(FAKE_KEY, "https://openrouter.test/api/v1", "t",
                                  client=httpx.Client(transport=httpx.MockTransport(handler)))

    def ok(self, content: str, served: str | None = None, finish: str = "stop", thinking: int | None = 12) -> Any:
        usage: dict[str, Any] = {"prompt_tokens": 120, "completion_tokens": 42}
        if thinking is not None:
            usage["completion_tokens_details"] = {"reasoning_tokens": thinking}
        return {"model": served or self.model, "choices": [{"message": {"content": content}, "finish_reason": finish}],
                "usage": usage}

    def failure(self, kind: str) -> Any:
        status = {"auth": 401, "permission": 403, "not_found": 404, "rate_limited": 429, "server": 503}
        if kind in status:
            return httpx.Response(status[kind], json={"error": {"message": kind}})
        return {"timeout": httpx.ReadTimeout("slow"), "connection": httpx.ConnectError("down"),
                "truncated": self.ok(json.dumps(REPLY), finish="length"), "empty": self.ok(""),
                "refusal": self.ok("", finish="content_filter")}[kind]

    # request introspection
    def system(self) -> str:
        msgs = self.requests[-1]["messages"]
        assert msgs[0]["role"] == "system"
        return msgs[0]["content"]

    def turns(self) -> list[tuple[str, str]]:
        return [(m["role"], m["content"]) for m in self.requests[-1]["messages"][1:]]

    def schema(self) -> tuple[str, dict[str, Any]]:
        rf = self.requests[-1]["response_format"]
        assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
        return rf["json_schema"]["name"], rf["json_schema"]["schema"]

    def temperature(self) -> float | None:
        return self.requests[-1].get("temperature")


class GeminiHarness:
    """Gemini with a fake google-genai client. A 'spec' is a response object or an exception."""

    name, model, wire = "gemini", GEM_MODEL, "genai"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def provider(self, spec: Any) -> GeminiProvider:
        harness = self

        class Models:
            def generate_content(self, model, contents, config):
                harness.requests.append({"model": model, "contents": contents, "config": config})
                if isinstance(spec, Exception):
                    raise spec
                return spec
        return GeminiProvider(api_key=None, client=SimpleNamespace(models=Models()))

    def ok(self, content: str, served: str | None = None, finish: str = "STOP", thinking: int | None = 12,
           block: str | None = None) -> Any:
        return SimpleNamespace(
            text=content, model_version=served or self.model,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
            prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=30,
                                           thoughts_token_count=thinking))

    def failure(self, kind: str) -> Any:
        return {"auth": errors.ClientError(401, {"error": {"message": "auth"}}),
                "permission": errors.ClientError(403, {"error": {"message": "permission"}}),
                "not_found": errors.ClientError(404, {"error": {"message": "no model"}}),
                "rate_limited": errors.ClientError(429, {"error": {"message": "quota"}}),
                "server": errors.ServerError(503, {"error": {"message": "overloaded"}}),
                "timeout": httpx2.ReadTimeout("slow"), "connection": httpx2.ConnectError("down"),
                "truncated": self.ok(json.dumps(REPLY), finish="MAX_TOKENS"), "empty": self.ok(""),
                "refusal": self.ok("", finish="SAFETY")}[kind]

    def system(self) -> str:
        return self.requests[-1]["config"].system_instruction

    def turns(self) -> list[tuple[str, str]]:
        role = {"user": "user", "model": "assistant"}  # Gemini's 'model' role is the app's 'assistant'
        return [(role[c["role"]], c["parts"][0]["text"]) for c in self.requests[-1]["contents"]]

    def schema(self) -> tuple[str | None, dict[str, Any]]:
        cfg = self.requests[-1]["config"]
        assert cfg.response_mime_type == "application/json"
        return None, cfg.response_json_schema  # Gemini has no schema name field

    def temperature(self) -> float | None:
        return self.requests[-1]["config"].temperature


class GeminiGatewayHarness(ORHarness):
    """Gemini behind an OpenAI-compatible gateway (GEMINI_BASE_URL), over httpx.MockTransport."""

    name, model, wire = "gemini", GEM_MODEL, "openai"

    def provider(self, spec: Any) -> GeminiProvider:  # type: ignore[override]
        def handler(req: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(req.content))
            if isinstance(spec, Exception):
                raise spec
            return spec if isinstance(spec, httpx.Response) else httpx.Response(200, json=spec)
        return GeminiProvider(FAKE_KEY, base_url="https://gateway.test/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(handler)))


HARNESSES = {"openrouter": ORHarness, "gemini": GeminiHarness, "gemini_gateway": GeminiGatewayHarness}


@pytest.fixture(params=list(HARNESSES))
def h(request):
    return HARNESSES[request.param]()


def target(h) -> Target:
    return Target(h.name, h.model)


def settings_for(h, tmp_path, **kw) -> Settings:
    key = {"openrouter_api_key": FAKE_KEY} if h.name == "openrouter" else {"gemini_api_key": FAKE_KEY}
    return Settings(_env_file=None, llm_provider=h.name, llm_model=h.model, db_path=tmp_path / "c.sqlite3",  # type: ignore[arg-type]  # noqa: E501
                    eval_targets=f"{h.name}:{h.model}", **key, **kw)


@pytest.mark.usefixtures("no_sleep")
def test_system_prompt_is_delivered_once_and_not_as_a_turn(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("SYSTEM PROMPT v9", HISTORY, target(h), CFG_pc)
    assert h.system() == "SYSTEM PROMPT v9"
    assert all(content != "SYSTEM PROMPT v9" for _, content in h.turns())


@pytest.mark.usefixtures("no_sleep")
def test_multi_turn_history_order_and_roles_preserved(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG_pc)
    assert h.turns() == [(m["role"], m["content"]) for m in HISTORY]


@pytest.mark.usefixtures("no_sleep")
def test_requested_model_is_sent_exactly(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG_pc)
    assert h.requests[-1]["model"] == h.model  # one model, no fallback list
    assert "models" not in h.requests[-1]


@pytest.mark.usefixtures("no_sleep")
def test_default_schema_is_the_reply_schema(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG_pc)
    assert h.schema()[1] is OUTPUT_SCHEMA or h.schema()[1] == OUTPUT_SCHEMA


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("use", list(MODEL_USES))
def test_each_app_schema_is_passed_as_structured_output(h, use):
    u = MODEL_USES[use]
    h.provider(h.ok(json.dumps(SAMPLES[use]))).complete("s", HISTORY, target(h), CFG_pc, schema=u.schema,
                                                          schema_name=u.schema_name)
    name, schema = h.schema()
    assert schema == u.schema
    if h.wire == "openai":
        assert name == u.schema_name  # OpenAI json_schema carries a name; Gemini's response_json_schema does not


WRAPS = [("{}", "json"), ("```json\n{}\n```", "json"), ("Sure! {} Thanks", "json_extracted"),
         ("plain words, no JSON", "text_fallback")]


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("wrap,mode", WRAPS)
def test_same_text_parses_to_the_same_model_output(h, wrap, mode):
    text = wrap.replace("{}", json.dumps(REPLY)) if "{}" in wrap else wrap
    r = h.provider(h.ok(text)).complete("s", HISTORY, target(h), CFG_pc)
    expected = ModelOutput.model_validate(REPLY) if mode != "text_fallback" else ModelOutput(reply=text)
    assert (r.output, r.parse_mode, r.provider, r.requested_model) == (expected, mode, h.name, h.model)
    assert r.extra["content"] == text and r.is_mock is False


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("use", list(MODEL_USES))
def test_each_schema_round_trips_through_the_callers_parser(h, use):
    u = MODEL_USES[use]
    r = complete_for(u, LLMGateway(Settings(_env_file=None), {h.name: h.provider(h.ok(json.dumps(SAMPLES[use])))}),
                     "s", HISTORY, target(h), CFG_pc)
    raw = r.extra["content"]
    if use == "generate_response":
        assert r.output == ModelOutput.model_validate(REPLY)
    elif use == "decide_gate":
        ctx = GateContext(audience="resident", identity_verified=True, record_found=True)
        d = coerce_decision(parse_gate_json(raw), ctx, "llm", "llm")
        assert (d.intent, d.urgency, d.confidence) == ("maintenance", "high", 0.9)
    else:
        risk = risk_classifier.parse(raw)
        assert (risk.risk_level, risk.risk_categories, risk.immediate_danger) == ("emergency", ["gas"], True)


@pytest.mark.usefixtures("no_sleep")
def test_usage_is_normalised_with_thinking_counted_in_output(h):
    r = h.provider(h.ok(json.dumps(REPLY), thinking=12)).complete("s", HISTORY, target(h), CFG_pc)
    assert (r.input_tokens, r.output_tokens) == (120, 42)  # output includes thinking on both
    assert (r.extra["thinking_tokens"], r.extra["answer_tokens"]) == (12, 30)
    assert r.latency_ms >= 0


@pytest.mark.usefixtures("no_sleep")
def test_usage_without_thinking_details(h):
    r = h.provider(h.ok(json.dumps(REPLY), thinking=None)).complete("s", HISTORY, target(h), CFG_pc)
    assert r.input_tokens == 120 and r.extra["thinking_tokens"] is None
    # Documented difference: OpenRouter's completion_tokens is the full output (42); Gemini reports only the visible
    # answer (30) when there is no thoughts count. Either way output_tokens never under-counts what was reported.
    assert r.output_tokens == (42 if h.wire == "openai" else 30)


ERRORS = [  # kind, code, retryable, http_status
    ("auth", "MODEL_AUTH_ERROR", False, 502),
    ("permission", "MODEL_PERMISSION_DENIED", False, 502),
    ("not_found", "MODEL_NOT_FOUND", False, 502),
    ("rate_limited", "MODEL_RATE_LIMITED", True, 503),
    ("server", "MODEL_API_ERROR", True, 502),
    ("timeout", "MODEL_TIMEOUT", True, 504),
    ("connection", "MODEL_CONNECTION_ERROR", True, 503),
    ("truncated", "MODEL_TRUNCATED", False, 502),
    ("empty", "MODEL_EMPTY_RESPONSE", False, 502),
    ("refusal", "MODEL_REFUSAL", False, 502),
]


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("kind,code,retryable,http_status", ERRORS)
def test_failures_map_to_the_same_gateway_error(h, kind, code, retryable, http_status):
    with pytest.raises(LLMError) as ei:
        h.provider(h.failure(kind)).complete("s", HISTORY, target(h), CFG_pc)
    assert (ei.value.code, ei.value.retryable, ei.value.http_status) == (code, retryable, http_status)
    assert FAKE_KEY not in ei.value.message


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("kind,code,retryable,http_status", ERRORS)
def test_gateway_passes_provider_errors_through_unchanged(h, tmp_path, kind, code, retryable, http_status):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.failure(kind))})
    with pytest.raises(LLMError) as ei:
        gw.complete("s", HISTORY, cfg=CFG_pc)
    assert ei.value.code == code


@pytest.mark.usefixtures("no_sleep")
def test_no_key_is_needs_api_key_without_any_request(h, tmp_path):
    s = Settings(_env_file=None, llm_provider=h.name, llm_model=h.model, db_path=tmp_path / "n.sqlite3")  # type: ignore[arg-type]  # noqa: E501
    gw = LLMGateway(s)
    assert gw.provider_ready(h.name) == (False, "NEEDS_API_KEY")
    with pytest.raises(LLMError) as ei:
        gw.complete("s", HISTORY, cfg=CFG_pc)
    assert ei.value.code == "NEEDS_API_KEY" and ei.value.http_status == 503


@pytest.mark.usefixtures("no_sleep")
@pytest.mark.parametrize("served,ok", [(None, True), ("{m}-20261101", True), ("other/vendor-model", False)])
def test_served_model_is_reported_and_switches_are_rejected(h, tmp_path, served, ok):
    served_id = served.format(m=h.model.removesuffix(":free")) if served else None
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(REPLY), served=served_id))})
    if ok:
        r = gw.complete("s", HISTORY, cfg=CFG_pc)
        assert r.model == (served_id or h.model) and r.requested_model == h.model
    else:
        with pytest.raises(LLMError) as ei:
            gw.complete("s", HISTORY, cfg=CFG_pc)
        assert ei.value.code == "MODEL_SWITCHED"
        # strict_model=False (used by the live recorder) still reports the served ID so it can be logged
        assert gw.complete("s", HISTORY, cfg=CFG_pc, strict_model=False).model == served_id


@pytest.mark.usefixtures("no_sleep")
def test_llm_gate_caller_uses_the_gate_schema_and_decides(h, tmp_path):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(GATE)))})
    ctx = GateContext(audience="resident", identity_verified=True, record_found=True, topics=["maintenance"])
    d = LLMGate(gw, target(h), timeout_seconds=5).classify("My heat is out", ctx, None)  # type: ignore[arg-type]
    assert h.schema()[1] is DECIDE_GATE.schema or h.schema()[1] == DECIDE_GATE.schema
    assert DECIDE_GATE.schema is GATE_SCHEMA and DECIDE_GATE.schema_name == GATE_SCHEMA_NAME  # facade == caller
    assert (d.intent, d.urgency, d.decision_source) == ("maintenance", "high", "llm")
    assert d.gate_usage.input_tokens == 120 and d.gate_usage.output_tokens == 42


@pytest.mark.usefixtures("no_sleep")
def test_risk_classifier_caller_uses_the_risk_schema_and_classifies(h, tmp_path):
    s = settings_for(h, tmp_path, safety_classifier_target=f"{h.name}:{h.model}")
    gw = LLMGateway(s, {h.name: h.provider(h.ok(json.dumps(RISK)))})
    res = risk_classifier.SemanticRiskClassifier(s, gw).classify("I smell something like rotten eggs by the stove")
    assert res.status == "ok" and res.risk.risk_level == "emergency" and res.model == h.model
    assert h.schema()[1] == CLASSIFY_RISK.schema and CLASSIFY_RISK.schema is risk_classifier.SCHEMA
    assert h.temperature() in (0, None)  # classifier pins temperature 0 where the provider takes one


@pytest.mark.usefixtures("no_sleep")
def test_risk_classifier_failure_is_never_safe(h, tmp_path):
    s = settings_for(h, tmp_path, safety_classifier_target=f"{h.name}:{h.model}")
    for kind, status in (("rate_limited", "rate_limited"), ("timeout", "timeout"), ("server", "error")):
        gw = LLMGateway(s, {h.name: h.provider(h.failure(kind))})
        res = risk_classifier.SemanticRiskClassifier(s, gw).classify("help")
        assert res.status == status and res.risk is None


@pytest.mark.usefixtures("no_sleep")
def test_generate_response_through_run_turn(h, tmp_path):
    from app.chat_engine import run_turn
    from app.db import Store
    from app.state import build_state

    s = settings_for(h, tmp_path, decision_gate_provider="rules", safety_classifier="off")
    gw = LLMGateway(s, {h.name: h.provider(h.ok(json.dumps(REPLY)))})
    deps = build_state(settings=s, gateway=gw, store=Store(s.db_path)).deps
    resp = run_turn(deps, "Do you allow pets at your Florida communities?", "aware", "P-BROWSE-FL", None)
    if h.requests:  # the planner may answer from a template; when the model is called the contract must hold
        assert h.schema()[1] == GENERATE_RESPONSE.schema and h.system()
        assert resp.model == h.model and resp.requested_model == h.model
    else:
        assert resp.reply_source == "template"


@pytest.mark.usefixtures("no_sleep")
def test_mock_reports_requested_model_and_is_labelled(tmp_path):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", db_path=tmp_path / "m.db")
    r = LLMGateway(s).complete("s", HISTORY)
    assert r.is_mock and r.model == r.requested_model == "mock-deterministic-v1" and isinstance(r.output, ModelOutput)
    assert r.estimated_cost_usd == 0.0


@pytest.mark.usefixtures("no_sleep")
def test_mock_gate_content_parses_with_the_gate_parser():
    r = MockProvider().complete("s", [{"role": "user", "content": "my sink leaks"}], Target("mock", "m"), CFG_pc,
                                schema=GATE_SCHEMA, schema_name=GATE_SCHEMA_NAME)
    assert parse_gate_json(r.extra["content"])["intent"] == "maintenance"


@pytest.mark.usefixtures("no_sleep")
def test_mock_is_not_a_risk_classifier(tmp_path):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", db_path=tmp_path / "m.db")
    res = risk_classifier.SemanticRiskClassifier(s, LLMGateway(s)).classify("I smell gas")
    assert res.status == "mock" and res.risk is None  # never inferred, never "safe"


@pytest.mark.usefixtures("no_sleep")
def test_difference_temperature_sent_to_openrouter_not_gemini(h, tmp_path):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(REPLY)))})
    gw.complete("s", HISTORY)
    assert h.temperature() == (0.2 if h.name == "openrouter" else None)


@pytest.mark.usefixtures("no_sleep")
def test_difference_cost_reported_by_openrouter_only(h):
    spec = h.ok(json.dumps(REPLY))
    if h.name == "openrouter":
        spec["usage"]["cost"] = 0.0
    r = h.provider(spec).complete("s", HISTORY, target(h), CFG_pc)
    assert r.estimated_cost_usd == (0.0 if h.name == "openrouter" else None)  # Gemini: no invented prices


@pytest.mark.usefixtures("no_sleep")
def test_difference_schema_name_only_on_openrouter(h):
    h.provider(h.ok(json.dumps(GATE))).complete("s", HISTORY, target(h), CFG_pc, schema=GATE_SCHEMA,
                                                schema_name=GATE_SCHEMA_NAME)
    name, _ = h.schema()
    assert name == (GATE_SCHEMA_NAME if h.wire == "openai" else None)


@pytest.mark.usefixtures("no_sleep")
def test_openrouter_only_payment_required_and_error_inside_200():
    o = ORHarness()
    with pytest.raises(LLMError) as ei:
        o.provider(httpx.Response(402, json={"error": {"message": "credits"}})).complete("s", HISTORY, target(o), CFG_pc)  # noqa: E501
    assert ei.value.code == "MODEL_PAYMENT_REQUIRED"
    for body, code in (({"error": {"code": 429, "message": "upstream rate limited"}}, "MODEL_RATE_LIMITED"),
                       ({"error": {"code": 404, "message": "no endpoints"}}, "MODEL_NOT_FOUND"),
                       ({"error": {"message": "opaque"}}, "MODEL_API_ERROR"),
                       ({"model": OR_MODEL, "choices": []}, "MODEL_EMPTY_RESPONSE")):
        with pytest.raises(LLMError) as ei:
            o.provider(body).complete("s", HISTORY, target(o), CFG_pc)
        assert ei.value.code == code


@pytest.mark.usefixtures("no_sleep")
def test_openrouter_refusal_field_is_a_refusal():
    o = ORHarness()
    body = {"model": OR_MODEL, "choices": [{"message": {"content": None, "refusal": "I can't help with that."},
                                            "finish_reason": "stop"}]}
    with pytest.raises(LLMError) as ei:
        o.provider(body).complete("s", HISTORY, target(o), CFG_pc)
    assert ei.value.code == "MODEL_REFUSAL"


@pytest.mark.usefixtures("no_sleep")
def test_gemini_only_invalid_key_400_is_auth_and_prompt_block_is_refusal():
    g = GeminiHarness()
    bad_key = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid.", "status":
                                                 "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}})
    with pytest.raises(LLMError) as ei:
        g.provider(bad_key).complete("s", HISTORY, target(g), CFG_pc)
    assert ei.value.code == "MODEL_AUTH_ERROR"
    with pytest.raises(LLMError) as ei:
        g.provider(errors.ClientError(400, {"error": {"message": "bad field"}})).complete("s", HISTORY, target(g), CFG_pc)  # noqa: E501
    assert ei.value.code == "MODEL_BAD_REQUEST"
    with pytest.raises(LLMError) as ei:
        g.provider(g.ok(json.dumps(REPLY), block="PROHIBITED_CONTENT")).complete("s", HISTORY, target(g), CFG_pc)
    assert ei.value.code == "MODEL_REFUSAL"


@pytest.mark.usefixtures("no_sleep")
def test_difference_retries_are_done_by_different_layers(h):
    """OpenRouter and the Gemini gateway: app.llm.http retries 429/5xx/timeouts itself. Gemini SDK: the SDK retries
    (HttpRetryOptions)."""
    cfg = GenerationConfig(max_tokens=100, temperature=None, timeout_seconds=5, max_retries=2)
    if h.wire == "openai":
        calls: list[int] = []

        def handler(req):
            calls.append(1)
            return (httpx.Response(429, json={"error": {"message": "slow"}}) if len(calls) < 3
                    else httpx.Response(200, json=h.ok(json.dumps(REPLY))))
        p = OpenRouterProvider(FAKE_KEY, "https://x.test/api/v1", "t",
                               client=httpx.Client(transport=httpx.MockTransport(handler)))
        assert p.complete("s", HISTORY, target(h), cfg).output.reply and len(calls) == 3
    else:
        h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), cfg)
        ro = h.requests[-1]["config"].http_options.retry_options
        assert ro.attempts == 3 and 429 in ro.http_status_codes and 503 in ro.http_status_codes


# ---- Gemini provider adapter: offline tests with a fake SDK client (no network, no API calls, no key).

CFG_gp = GenerationConfig(max_tokens=800, temperature=0.2, timeout_seconds=12, max_retries=2)


TARGET = Target("gemini", "gemini-3.6-flash")


REPLY_gp = {"reply": "Got it.", "audience": "resident", "recommended_handoff": False, "handoff_category": "none",
         "handoff_reason": "", "language": "en"}


REPLY_JSON = json.dumps(REPLY_gp)


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
    r = p.complete("SYSTEM PROMPT", msgs, TARGET, CFG_gp)
    call = models.calls[0]
    cfg = call["config"]
    assert call["model"] == "gemini-3.6-flash"
    assert [c["role"] for c in call["contents"]] == ["user", "model", "user"]
    assert cfg.system_instruction == "SYSTEM PROMPT" and cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema["required"][0] == "reply"
    assert cfg.max_output_tokens == 800 and cfg.temperature == 0.2
    assert cfg.http_options.timeout == 12000 and cfg.http_options.retry_options.attempts == 3
    assert r.output.reply == "Got it." and r.parse_mode == "json" and r.provider == "gemini"
    assert (r.input_tokens, r.output_tokens, r.extra["thinking_tokens"], r.extra["answer_tokens"]) == (120, 42, 12, 30)
    assert r.extra["thinking_level"] == "model default" and cfg.thinking_config is None
    assert r.estimated_cost_usd is None  # no invented prices


def test_custom_schema_for_gate_classification():
    gate = {"intent": "maintenance", "urgency": "low", "requires_human": False, "handoff_reason": "",
            "confidence": 0.9, "risk_flags": []}
    p, models = provider(response(text=json.dumps(gate)))
    r = p.complete("gate", [{"role": "user", "content": "x"}], TARGET, CFG_gp, schema=GATE_SCHEMA,
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
    (httpx2.ReadTimeout("slow"), "MODEL_TIMEOUT"),  # what google-genai 3.x actually raises (httpx2 backend)
    (httpx2.ConnectError("down"), "MODEL_CONNECTION_ERROR"),
    (RuntimeError("unexpected SDK failure"), "MODEL_API_ERROR"),
])
def test_errors_map_to_gateway_codes(exc, code):
    p, _ = provider(exc)
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG_gp)
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
        p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG_gp)
    assert ei.value.code == code


def test_non_json_text_is_recorded_as_text_fallback():
    p, _ = provider(response(text="Sure, I can help with that."))
    r = p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG_gp)
    assert r.parse_mode == "text_fallback"


def test_no_key_means_needs_api_key_and_no_client():
    with pytest.raises(LLMError) as ei:
        GeminiProvider(api_key=None).complete("s", [{"role": "user", "content": "x"}], TARGET, CFG_gp)
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


def test_thinking_level_is_pinned_when_configured():
    models = FakeModels(response())
    p = GeminiProvider(api_key=None, client=SimpleNamespace(models=models), thinking_level="low")
    r = p.complete("s", [{"role": "user", "content": "x"}], TARGET, CFG_gp)
    assert models.calls[0]["config"].thinking_config.thinking_level.name == "LOW"
    assert r.extra["thinking_level"] == "low"


def test_gateway_does_not_send_temperature_to_gemini(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-not-a-real-key",
                 db_path=tmp_path / "t.sqlite3")
    p, models = provider(response())
    LLMGateway(s, {"gemini": p}).complete("s", [{"role": "user", "content": "x"}])
    assert models.calls[0]["config"].temperature is None  # Gemini 3.6 ignores it; future models reject it


def test_a_non_gemini_model_with_the_gemini_provider_is_a_clear_config_error(tmp_path):
    with pytest.raises(ValueError, match="not a Gemini model"):
        Settings(_env_file=None, llm_provider="gemini", llm_model="mock-deterministic-v1",
                 db_path=tmp_path / "v.sqlite3")


def test_preflight_main_prints_a_listed_gemini_model_and_recommends_it(tmp_path, monkeypatch, capsys):
    from app.live_eval import preflight

    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="test-not-a-real-key",
                 eval_targets="mock:mock-deterministic-v1,gemini:gemini-3.6-flash", db_path=tmp_path / "m.db")
    monkeypatch.setattr(preflight, "get_settings", lambda: s)
    monkeypatch.setattr(preflight, "gemini_model_names", lambda key: ["gemini-3.6-flash"])
    code = preflight.main(["--out-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "listed for this key" in out and "Recommended fixed model: gemini:gemini-3.6-flash" in out
    assert "OPENROUTER_API_KEY" not in out and code == preflight.EXIT_READY
    assert "test-not-a-real-key" not in out


# ---- Gemini behind an OpenAI-compatible gateway (GEMINI_BASE_URL): offline tests, httpx.MockTransport, no key.

BASE = "https://gateway.test/v1"


KEY = "test-not-a-real-key"


CFG_gg = GenerationConfig(max_tokens=800, temperature=None, timeout_seconds=12, max_retries=2)


REPLY_gg = {"reply": "Happy to help with a tour.", "audience": "prospect", "recommended_handoff": False,
         "handoff_category": "none", "handoff_reason": "", "language": "en"}


def ok(content=None, finish="stop", model="gemini-3.6-flash", reasoning=0, completion=48):
    return {"model": model, "choices": [{"message": {"content": json.dumps(REPLY_gg) if content is None else content},
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


@pytest.mark.usefixtures("no_sleep")
def test_request_shape_matches_the_verified_gateway_contract():
    p, seen = make([ok()])
    msgs = [{"role": "user", "content": "Can I tour Saturday?"}, {"role": "assistant", "content": "Sure."},
            {"role": "system", "content": "ignored"}, {"role": "user", "content": "2pm"}]
    r = p.complete("SYSTEM", msgs, TARGET, CFG_gg)
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
    assert r.output.reply == REPLY_gg["reply"] and r.provider == "gemini" and r.model == "gemini-3.6-flash"
    assert (r.input_tokens, r.output_tokens) == (900, 48)
    assert (r.extra["thinking_tokens"], r.extra["answer_tokens"]) == (0, 48)
    assert r.extra["transport"] == "gateway" and r.extra["thinking_level"] == "low"


@pytest.mark.usefixtures("no_sleep")
def test_no_thinking_level_sends_no_reasoning_parameter():
    p, seen = make([ok()], thinking_level=None)
    r = p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG_gg)
    assert "reasoning_effort" not in json.loads(seen[0].content)
    assert r.extra["thinking_level"] == "model default"


@pytest.mark.usefixtures("no_sleep")
def test_reasoning_tokens_are_counted_inside_completion_tokens():
    p, _ = make([ok(reasoning=383, completion=396)], thinking_level=None)
    r = p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG_gg)
    assert r.output_tokens == 396 and r.extra["thinking_tokens"] == 383 and r.extra["answer_tokens"] == 13


@pytest.mark.usefixtures("no_sleep")
def test_retries_429_and_5xx_on_the_same_model_then_succeeds():
    p, seen = make([httpx.Response(429, json={"error": {"message": "slow"}}),
                    httpx.Response(503, json={"error": {"message": "busy"}}), ok()])
    assert p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG_gg).output.reply
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
@pytest.mark.usefixtures("no_sleep")
def test_errors_map_to_gateway_codes_without_leaking_key(resp, code):
    p, _ = make([resp])
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET,
                   GenerationConfig(max_tokens=100, temperature=None, timeout_seconds=5, max_retries=0))
    assert ei.value.code == code and KEY not in ei.value.message


@pytest.mark.usefixtures("no_sleep")
def test_connection_error_does_not_reveal_the_gateway_address():
    p, _ = make([httpx.ConnectError("down")])
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG_gg)
    assert ei.value.code == "MODEL_CONNECTION_ERROR" and "gateway.test" not in ei.value.message


@pytest.mark.usefixtures("no_sleep")
def test_no_key_raises_needs_api_key_without_a_request():
    seen: list[httpx.Request] = []
    p = GeminiProvider(None, base_url=BASE,
                       http_client=httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r))))  # type: ignore[arg-type,return-value]  # noqa: E501
    with pytest.raises(LLMError) as ei:
        p.complete("s", [{"role": "user", "content": "hi"}], TARGET, CFG_gg)
    assert ei.value.code == "NEEDS_API_KEY" and not seen


@pytest.mark.usefixtures("no_sleep")
def test_served_model_switch_is_rejected_by_the_gateway_layer(tmp_path):
    p, _ = make([ok(model="gemini-3.5-flash")])
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, db_path=tmp_path / "g.db")  # type: ignore[arg-type]  # noqa: E501
    with pytest.raises(LLMError) as ei:
        LLMGateway(s, {"gemini": p}).complete("s", [{"role": "user", "content": "hi"}])
    assert ei.value.code == "MODEL_SWITCHED"


@pytest.mark.usefixtures("no_sleep")
def test_settings_wire_base_url_and_thinking_level_into_the_provider(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, gemini_base_url=BASE + "/",  # type: ignore[arg-type]  # noqa: E501
                 gemini_thinking_level="low", db_path=tmp_path / "w.db")
    p = LLMGateway(s)._provider("gemini")
    assert isinstance(p, GeminiProvider) and p.transport == "gateway"
    assert p._base_url == BASE and p._thinking_level == "low"
    assert s.llm_model == "gemini-3.6-flash"  # provider default model


@pytest.mark.usefixtures("no_sleep")
def test_without_base_url_the_google_sdk_transport_is_kept(tmp_path):
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, db_path=tmp_path / "s.db")  # type: ignore[arg-type]  # noqa: E501
    assert s.base_url_for("gemini") is None
    assert LLMGateway(s)._provider("gemini").transport == "google-genai"  # type: ignore[attr-defined]


@pytest.mark.usefixtures("no_sleep")
def test_gemini_is_the_default_provider_and_openrouter_stays_selectable(tmp_path):
    d = Settings(_env_file=None, db_path=tmp_path / "d.db")
    assert (d.llm_provider, d.llm_model) == ("gemini", "gemini-3.6-flash")
    o = Settings(_env_file=None, llm_provider="openrouter", db_path=tmp_path / "o.db")  # type: ignore[arg-type]
    assert (o.llm_provider, o.llm_model) == ("openrouter", "nvidia/nemotron-3.5-super-vl:free")
    assert LLMGateway(o)._provider("openrouter").name == "openrouter"


@pytest.mark.usefixtures("no_sleep")
def test_hosted_backend_refuses_a_non_https_gateway(tmp_path):
    kw = dict(_env_file=None, app_env="hosted", llm_provider="gemini", db_path=tmp_path / "h.db",
              cors_origins="https://site.example",
              staff_api_token="x" * 12 + "abcdefghijkl", database_url="postgresql://u:p@db.example/x")
    bad = Settings(**kw, gemini_base_url="http://plain.example/v1")  # type: ignore[arg-type]
    assert any("GEMINI_BASE_URL" in p for p in bad.hosted_problems())
    good = Settings(**kw, gemini_base_url=BASE)  # type: ignore[arg-type]
    assert not any("GEMINI_BASE_URL" in p for p in good.hosted_problems())


@pytest.mark.usefixtures("no_sleep")
def test_preflight_lists_models_from_the_gateway(monkeypatch, tmp_path):
    from app.live_eval import preflight

    calls = []
    monkeypatch.setattr(preflight, "gemini_model_names", lambda key, base=None: calls.append(base) or
                        ["gemini-3.6-flash"])
    s = Settings(_env_file=None, llm_provider="gemini", gemini_api_key=KEY, gemini_base_url=BASE,  # type: ignore[arg-type]  # noqa: E501
                 eval_targets="gemini:gemini-3.6-flash", db_path=tmp_path / "p.db")
    out = preflight.run_preflight(s)
    assert calls == [BASE]
    row = next(t for t in out["targets"] if t["provider"] == "gemini")
    assert row["info"]["listed"] is True


@pytest.mark.usefixtures("no_sleep")
def test_hosted_backend_must_name_its_provider_explicitly(tmp_path):
    """Gemini became the built-in default; a hosted backend relying on the default would switch silently."""
    kw = dict(_env_file=None, app_env="hosted", db_path=tmp_path / "x.db", cors_origins="https://site.example",
              staff_api_token="x" * 12 + "abcdefghijkl", database_url="postgresql://u:p@db.example/x")
    assert any("LLM_PROVIDER must be set" in p for p in Settings(**kw).hosted_problems())  # type: ignore[arg-type]
    for provider in ("openrouter", "gemini"):
        s = Settings(**kw, llm_provider=provider)  # type: ignore[arg-type]
        assert not any("LLM_PROVIDER" in p for p in s.hosted_problems())


# ---- U-M GPT Toolkit provider contract (offline: httpx.MockTransport, synthetic content, no key ever sent anywhere).

REPLY_utp = {"reply": "Happy to help you plan a visit.", "audience": "prospect", "recommended_handoff": False,
         "handoff_category": "none", "handoff_reason": "", "language": "en"}


def _settings(**kw):
    base = dict(llm_provider="um_toolkit", um_toolkit_api_key="test-key-not-real", _env_file=None)
    return Settings(**{**base, **kw})  # type: ignore[arg-type]


def _client(seen, status=200, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {
            "model": "gpt-6.1-sol-2026-09-29",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(REPLY_utp)}}],
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
    assert res.output.reply == REPLY_utp["reply"] and res.provider == "um_toolkit"
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


# ---- Central live-call budget + metadata ledger, and the OpenRouter reasoning setting (all offline).

MODEL = "nvidia/nemotron-3.5-super-vl:free"


BODY = {"model": MODEL, "choices": [{"finish_reason": "stop", "message": {"content": '{"reply": "hi"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 7, "completion_tokens_details": {"reasoning_tokens": 3}}}


def _gw(tmp_path, budget=2, reasoning=None, sent=None):
    def handler(req):
        if sent is not None:
            sent.append(json.loads(req.content))
        return httpx.Response(200, json=BODY)
    s = Settings(_env_file=None, llm_provider="openrouter", llm_model=MODEL, openrouter_api_key="test-not-a-key",
                 llm_call_budget=budget, llm_call_ledger=tmp_path / "ledger.jsonl", db_path=tmp_path / "x.db")
    p = OpenRouterProvider("test-not-a-key", "https://openrouter.test/api/v1", "t",
                           client=httpx.Client(transport=httpx.MockTransport(handler)), reasoning_effort=reasoning)
    return LLMGateway(s, {"openrouter": p}), s


def test_budget_stops_further_live_calls_and_ledger_has_metadata_only(tmp_path):
    gw, s = _gw(tmp_path, budget=2)
    for _ in range(2):
        gw.complete("system secret prompt", [{"role": "user", "content": "private message"}])
    with pytest.raises(LLMError) as e:
        gw.complete("s", [{"role": "user", "content": "x"}])
    assert e.value.code == "LLM_BUDGET_EXHAUSTED"
    lines = s.llm_call_ledger.read_text().strip().splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["execution"] == "LIVE" and row["served_model"] == MODEL and row["thinking_tokens"] == 3
    text = s.llm_call_ledger.read_text()
    assert "private message" not in text and "secret prompt" not in text and "test-not-a-key" not in text


def test_budget_is_shared_across_gateways_through_the_ledger(tmp_path):
    gw1, _ = _gw(tmp_path, budget=1)
    gw1.complete("s", [{"role": "user", "content": "x"}])
    gw2, _ = _gw(tmp_path, budget=1)
    with pytest.raises(LLMError, match="budget"):
        gw2.complete("s", [{"role": "user", "content": "x"}])


def test_mock_calls_are_never_counted(tmp_path):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", llm_call_budget=1,
                 llm_call_ledger=tmp_path / "l.jsonl", db_path=tmp_path / "m.db")
    gw = LLMGateway(s)
    for _ in range(3):
        gw.complete("s", [{"role": "user", "content": "x"}], target=Target_lb("mock", "mock-deterministic-v1"))
    assert not (tmp_path / "l.jsonl").exists()


@pytest.mark.parametrize("effort,expected", [(None, None), ("none", {"enabled": False}), ("low", {"effort": "low"})])
def test_openrouter_reasoning_setting_is_sent_only_when_configured(tmp_path, effort, expected):
    sent: list = []
    gw, _ = _gw(tmp_path, budget=0, reasoning=effort, sent=sent)
    r = gw.complete("s", [{"role": "user", "content": "x"}])
    assert sent[0].get("reasoning") == expected
    assert r.extra["reasoning"] == (effort or "model default")


# ---- Live smoke script, fully offline: fake providers (httpx.MockTransport / fake google-genai client), no key, no...

FAKE_KEY_ls = "test-key-not-real"


REPLY_ls = {"reply": "Happy to help. Which community are you interested in?", "audience": "unknown",
         "recommended_handoff": False, "handoff_category": "none", "handoff_reason": "", "language": "English"}


RISK_ls = {"risk_level": "emergency", "risk_categories": ["gas"], "immediate_danger": True, "needs_human": True,
        "confidence": 0.9, "framing": "report", "reason": "Possible gas leak."}


BY_SCHEMA = {"mckinley_reply": REPLY_ls, "mckinley_gate": GATE, "mckinley_risk": RISK_ls}


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
        assert req.headers["authorization"] == f"Bearer {FAKE_KEY_ls}"
        if rate_limit_at is not None and len(seen) == rate_limit_at:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        if body["model"] == smoke.BAD_MODEL["openrouter"]:
            return httpx.Response(400, json={"error": {"message": "not a valid model ID"}})
        content = json.dumps(BY_SCHEMA[body["response_format"]["json_schema"]["name"]])
        return httpx.Response(200, json={"model": served or body["model"], "choices": [
            {"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 25,
                      "completion_tokens_details": {"reasoning_tokens": 5}}})
    return {"openrouter": OpenRouterProvider(FAKE_KEY_ls, "https://openrouter.test/api/v1", "t",
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
        kw = {"openrouter_api_key": FAKE_KEY_ls} if provider == "openrouter" else {"gemini_api_key": FAKE_KEY_ls}
    return Settings(_env_file=None, llm_provider=provider, db_path=tmp_path / "s.sqlite3", **kw)  # type: ignore[arg-type]  # noqa: E501


def run(tmp_path, provider="openrouter", **kw):
    logs: list[str] = []
    code, doc = smoke.run_smoke(kw.pop("settings", None) or settings(tmp_path, provider), provider,
                                out_dir=tmp_path / "out", models_client=listing_client(), sleeper=lambda s: None,
                                log=logs.append, label=kw.pop("label", "t"), **kw)
    return code, doc, logs


def steps(doc) -> dict:
    return {s["step"]: s for s in doc["steps"]}


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
    assert FAKE_KEY_ls not in text and json.loads(text)["provider"] == provider
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


# ---- Live-model preflight, fully offline (httpx.MockTransport; no network, no real key).

TARGET_le = f"openrouter:{MODEL}"


FAKE_KEY_le = "test-key-not-real"


MODELS_PAYLOAD = {"data": [
    {"id": MODEL, "name": "Nemotron", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 1000000,
     "top_provider": {"max_completion_tokens": 32000},
     "supported_parameters": ["max_tokens", "response_format", "structured_outputs", "temperature"]},
    {"id": "google/gemma-4-31b-it:free", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 262144,
     "supported_parameters": ["response_format", "temperature"]},
    {"id": "paid/model", "pricing": {"prompt": "0.000001", "completion": "0.000002"}, "context_length": 8000,
     "supported_parameters": ["response_format", "structured_outputs"]},
]}


def _models_client(fail: bool = False) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        assert "authorization" not in req.headers  # the public listing never receives a key
        if fail:
            raise httpx.ConnectError("offline")
        if req.url.path.endswith("/api/tags"):
            raise httpx.ConnectError("no ollama")
        return httpx.Response(200, json=MODELS_PAYLOAD)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _reply(model: str, text: str = "Thanks for reaching out. Which community are you interested in?") -> dict:
    content = json.dumps({"reply": text, "audience": "prospect", "recommended_handoff": False,
                          "handoff_category": "none", "handoff_reason": "", "language": "English"})
    return {"model": model, "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def _settings_le(tmp_path: Path, key: str | None = FAKE_KEY_le, **kw) -> Settings:
    kw.setdefault("llm_provider", "openrouter")  # these tests cover the OpenRouter path (Gemini is now the default)
    kw.setdefault("llm_model", "nvidia/nemotron-3.5-super-vl:free")
    return Settings(_env_file=None, openrouter_api_key=key, llm_max_retries=kw.pop("retries", 0),  # type: ignore[call-arg]  # noqa: E501
                    db_path=tmp_path / "t.sqlite3", **kw)


def _provider(handler) -> dict:
    return {"openrouter": OpenRouterProvider(FAKE_KEY_le, "https://openrouter.test/api/v1", "t",
                                             client=httpx.Client(transport=httpx.MockTransport(handler)))}


def test_preflight_parses_listing_and_recommends(tmp_path):
    s = _settings_le(tmp_path, eval_targets=f"mock:mock-deterministic-v1,openrouter:google/gemma-4-31b-it:free,"
                                         f"{TARGET_le},openrouter:missing/model:free,ollama:llama3.2")
    rep = run_preflight(s, client=_models_client())
    rows = {r["target"]: r for r in rep["targets"]}
    info = rows[TARGET_le]["info"]
    assert info["listed"] and info["free"] and info["supports_structured_outputs"]
    assert info["pricing_prompt_usd_per_token"] == 0.0 and info["context_length"] == 1000000
    assert rows["openrouter:google/gemma-4-31b-it:free"]["info"]["supports_structured_outputs"] is False
    assert rows["openrouter:missing/model:free"]["info"]["listed"] is False
    assert rep["ollama_reachable"] is False and rows["ollama:llama3.2"]["provider_ready"] is False
    # gemma comes first in EVAL_TARGETS but lacks structured outputs, so nemotron is recommended
    assert rep["recommended_target"] == TARGET_le
    assert rep["keys_present"] == {"gemini": False, "openrouter": True, "anthropic": False}
    assert rep["live_ready"] is True
    assert FAKE_KEY_le not in json.dumps(rep)


def test_preflight_network_failure_is_graceful(tmp_path):
    rep = run_preflight(_settings_le(tmp_path, key=None), client=_models_client(fail=True))
    assert rep["model_list"]["fetched"] is False and "unreachable" in rep["model_list"]["error"]
    assert rep["recommended_target"] is None and rep["live_ready"] is False
    assert any(r.startswith("NEEDS_API_KEY") for r in rep["blocked_reasons"])
    listing, err = fetch_models(_models_client(fail=True))
    assert listing is None and err


def test_model_info_paid_and_unverified():
    listing, _ = fetch_models(_models_client())
    paid = model_info("paid/model", listing)
    assert paid["free"] is False and paid["pricing_completion_usd_per_token"] == 0.000002
    assert model_info("x/y", None)["listed"] is None
    assert recommend([{"target": "openrouter:paid/model", "provider": "openrouter", "info": paid}])[0] is None
