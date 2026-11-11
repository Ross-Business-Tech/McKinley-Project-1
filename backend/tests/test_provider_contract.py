"""Provider contract: the SAME application-level expectations run against every hosted adapter.

OpenRouter is driven through `httpx.MockTransport` (OpenAI-style JSON); Gemini through a fake `google-genai` client
(like tests/test_gemini_provider.py); the Mock provider joins where the expectation is meaningful for it. No network,
no keys. Genuine differences between adapters are asserted explicitly in the "Documented differences" section, never
skipped silently.
"""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import httpx2
import pytest
from google.genai import errors

from app.config import Settings
from app.gates.base import GateContext
from app.gates.llm_gate import GATE_SCHEMA, GATE_SCHEMA_NAME, LLMGate, coerce_decision, parse_gate_json
from app.llm import LLMError, LLMGateway, ModelOutput, Target
from app.llm.base import OUTPUT_SCHEMA, GenerationConfig
from app.llm.contracts import CLASSIFY_RISK, DECIDE_GATE, GENERATE_RESPONSE, MODEL_USES, complete_for
from app.llm.gemini_provider import GeminiProvider
from app.llm.mock import MockProvider
from app.llm.openrouter import OpenRouterProvider
from app.risk import classifier as risk_classifier

CFG = GenerationConfig(max_tokens=800, temperature=0.2, timeout_seconds=12, max_retries=0)
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


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.llm.http.time.sleep", lambda s: None)


# --------------------------------------------------------------------------------------------- adapter harnesses
class ORHarness:
    """OpenRouter over httpx.MockTransport. A 'spec' is a JSON body (200), an httpx.Response, or an exception."""

    name, model = "openrouter", OR_MODEL

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

    name, model = "gemini", GEM_MODEL

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


HARNESSES = {"openrouter": ORHarness, "gemini": GeminiHarness}


@pytest.fixture(params=list(HARNESSES))
def h(request):
    return HARNESSES[request.param]()


def target(h) -> Target:
    return Target(h.name, h.model)


def settings_for(h, tmp_path, **kw) -> Settings:
    key = {"openrouter_api_key": FAKE_KEY} if h.name == "openrouter" else {"gemini_api_key": FAKE_KEY}
    return Settings(_env_file=None, llm_provider=h.name, llm_model=h.model, db_path=tmp_path / "c.sqlite3",  # type: ignore[arg-type]
                    eval_targets=f"{h.name}:{h.model}", **key, **kw)


# ---------------------------------------------------------------------------------------- request contract
def test_system_prompt_is_delivered_once_and_not_as_a_turn(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("SYSTEM PROMPT v9", HISTORY, target(h), CFG)
    assert h.system() == "SYSTEM PROMPT v9"
    assert all(content != "SYSTEM PROMPT v9" for _, content in h.turns())


def test_multi_turn_history_order_and_roles_preserved(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG)
    assert h.turns() == [(m["role"], m["content"]) for m in HISTORY]


def test_requested_model_is_sent_exactly(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG)
    assert h.requests[-1]["model"] == h.model  # one model, no fallback list
    assert "models" not in h.requests[-1]


def test_default_schema_is_the_reply_schema(h):
    h.provider(h.ok(json.dumps(REPLY))).complete("s", HISTORY, target(h), CFG)
    assert h.schema()[1] is OUTPUT_SCHEMA or h.schema()[1] == OUTPUT_SCHEMA


@pytest.mark.parametrize("use", list(MODEL_USES))
def test_each_app_schema_is_passed_as_structured_output(h, use):
    u = MODEL_USES[use]
    h.provider(h.ok(json.dumps(SAMPLES[use]))).complete("s", HISTORY, target(h), CFG, schema=u.schema,
                                                          schema_name=u.schema_name)
    name, schema = h.schema()
    assert schema == u.schema
    if h.name == "openrouter":
        assert name == u.schema_name  # OpenAI json_schema carries a name; Gemini's response_json_schema does not


# ---------------------------------------------------------------------------------------- response contract
WRAPS = [("{}", "json"), ("```json\n{}\n```", "json"), ("Sure! {} Thanks", "json_extracted"),
         ("plain words, no JSON", "text_fallback")]


@pytest.mark.parametrize("wrap,mode", WRAPS)
def test_same_text_parses_to_the_same_model_output(h, wrap, mode):
    text = wrap.replace("{}", json.dumps(REPLY)) if "{}" in wrap else wrap
    r = h.provider(h.ok(text)).complete("s", HISTORY, target(h), CFG)
    expected = ModelOutput.model_validate(REPLY) if mode != "text_fallback" else ModelOutput(reply=text)
    assert (r.output, r.parse_mode, r.provider, r.requested_model) == (expected, mode, h.name, h.model)
    assert r.extra["content"] == text and r.is_mock is False


@pytest.mark.parametrize("use", list(MODEL_USES))
def test_each_schema_round_trips_through_the_callers_parser(h, use):
    u = MODEL_USES[use]
    r = complete_for(u, LLMGateway(Settings(_env_file=None), {h.name: h.provider(h.ok(json.dumps(SAMPLES[use])))}),
                     "s", HISTORY, target(h), CFG)
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


def test_usage_is_normalised_with_thinking_counted_in_output(h):
    r = h.provider(h.ok(json.dumps(REPLY), thinking=12)).complete("s", HISTORY, target(h), CFG)
    assert (r.input_tokens, r.output_tokens) == (120, 42)  # output includes thinking on both
    assert (r.extra["thinking_tokens"], r.extra["answer_tokens"]) == (12, 30)
    assert r.latency_ms >= 0


def test_usage_without_thinking_details(h):
    r = h.provider(h.ok(json.dumps(REPLY), thinking=None)).complete("s", HISTORY, target(h), CFG)
    assert r.input_tokens == 120 and r.extra["thinking_tokens"] is None
    # Documented difference: OpenRouter's completion_tokens is the full output (42); Gemini reports only the visible
    # answer (30) when there is no thoughts count. Either way output_tokens never under-counts what was reported.
    assert r.output_tokens == (42 if h.name == "openrouter" else 30)


# ------------------------------------------------------------------------------------------- error contract
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


@pytest.mark.parametrize("kind,code,retryable,http_status", ERRORS)
def test_failures_map_to_the_same_gateway_error(h, kind, code, retryable, http_status):
    with pytest.raises(LLMError) as ei:
        h.provider(h.failure(kind)).complete("s", HISTORY, target(h), CFG)
    assert (ei.value.code, ei.value.retryable, ei.value.http_status) == (code, retryable, http_status)
    assert FAKE_KEY not in ei.value.message


@pytest.mark.parametrize("kind,code,retryable,http_status", ERRORS)
def test_gateway_passes_provider_errors_through_unchanged(h, tmp_path, kind, code, retryable, http_status):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.failure(kind))})
    with pytest.raises(LLMError) as ei:
        gw.complete("s", HISTORY, cfg=CFG)
    assert ei.value.code == code


def test_no_key_is_needs_api_key_without_any_request(h, tmp_path):
    s = Settings(_env_file=None, llm_provider=h.name, llm_model=h.model, db_path=tmp_path / "n.sqlite3")  # type: ignore[arg-type]
    gw = LLMGateway(s)
    assert gw.provider_ready(h.name) == (False, "NEEDS_API_KEY")
    with pytest.raises(LLMError) as ei:
        gw.complete("s", HISTORY, cfg=CFG)
    assert ei.value.code == "NEEDS_API_KEY" and ei.value.http_status == 503


# ------------------------------------------------------------------------- served model / MODEL_SWITCHED
@pytest.mark.parametrize("served,ok", [(None, True), ("{m}-20261101", True), ("other/vendor-model", False)])
def test_served_model_is_reported_and_switches_are_rejected(h, tmp_path, served, ok):
    served_id = served.format(m=h.model.removesuffix(":free")) if served else None
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(REPLY), served=served_id))})
    if ok:
        r = gw.complete("s", HISTORY, cfg=CFG)
        assert r.model == (served_id or h.model) and r.requested_model == h.model
    else:
        with pytest.raises(LLMError) as ei:
            gw.complete("s", HISTORY, cfg=CFG)
        assert ei.value.code == "MODEL_SWITCHED"
        # strict_model=False (used by the live recorder) still reports the served ID so it can be logged
        assert gw.complete("s", HISTORY, cfg=CFG, strict_model=False).model == served_id


# ------------------------------------------------------------------- the real application callers, per adapter
def test_llm_gate_caller_uses_the_gate_schema_and_decides(h, tmp_path):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(GATE)))})
    ctx = GateContext(audience="resident", identity_verified=True, record_found=True, topics=["maintenance"])
    d = LLMGate(gw, target(h), timeout_seconds=5).classify("My heat is out", ctx, None)  # type: ignore[arg-type]
    assert h.schema()[1] is DECIDE_GATE.schema or h.schema()[1] == DECIDE_GATE.schema
    assert DECIDE_GATE.schema is GATE_SCHEMA and DECIDE_GATE.schema_name == GATE_SCHEMA_NAME  # facade == caller
    assert (d.intent, d.urgency, d.decision_source) == ("maintenance", "high", "llm")
    assert d.gate_usage.input_tokens == 120 and d.gate_usage.output_tokens == 42


def test_risk_classifier_caller_uses_the_risk_schema_and_classifies(h, tmp_path):
    s = settings_for(h, tmp_path, safety_classifier_target=f"{h.name}:{h.model}")
    gw = LLMGateway(s, {h.name: h.provider(h.ok(json.dumps(RISK)))})
    res = risk_classifier.SemanticRiskClassifier(s, gw).classify("I smell something like rotten eggs by the stove")
    assert res.status == "ok" and res.risk.risk_level == "emergency" and res.model == h.model
    assert h.schema()[1] == CLASSIFY_RISK.schema and CLASSIFY_RISK.schema is risk_classifier.SCHEMA
    assert h.temperature() in (0, None)  # classifier pins temperature 0 where the provider takes one


def test_risk_classifier_failure_is_never_safe(h, tmp_path):
    s = settings_for(h, tmp_path, safety_classifier_target=f"{h.name}:{h.model}")
    for kind, status in (("rate_limited", "rate_limited"), ("timeout", "timeout"), ("server", "error")):
        gw = LLMGateway(s, {h.name: h.provider(h.failure(kind))})
        res = risk_classifier.SemanticRiskClassifier(s, gw).classify("help")
        assert res.status == status and res.risk is None


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


# --------------------------------------------------------------------------------------- Mock, where meaningful
def test_mock_reports_requested_model_and_is_labelled(tmp_path):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", db_path=tmp_path / "m.db")
    r = LLMGateway(s).complete("s", HISTORY)
    assert r.is_mock and r.model == r.requested_model == "mock-deterministic-v1" and isinstance(r.output, ModelOutput)
    assert r.estimated_cost_usd == 0.0


def test_mock_gate_content_parses_with_the_gate_parser():
    r = MockProvider().complete("s", [{"role": "user", "content": "my sink leaks"}], Target("mock", "m"), CFG,
                                schema=GATE_SCHEMA, schema_name=GATE_SCHEMA_NAME)
    assert parse_gate_json(r.extra["content"])["intent"] == "maintenance"


def test_mock_is_not_a_risk_classifier(tmp_path):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", db_path=tmp_path / "m.db")
    res = risk_classifier.SemanticRiskClassifier(s, LLMGateway(s)).classify("I smell gas")
    assert res.status == "mock" and res.risk is None  # never inferred, never "safe"


# ------------------------------------------------------------------------------------- Documented differences
def test_difference_temperature_sent_to_openrouter_not_gemini(h, tmp_path):
    gw = LLMGateway(settings_for(h, tmp_path), {h.name: h.provider(h.ok(json.dumps(REPLY)))})
    gw.complete("s", HISTORY)
    assert h.temperature() == (0.2 if h.name == "openrouter" else None)


def test_difference_cost_reported_by_openrouter_only(h):
    spec = h.ok(json.dumps(REPLY))
    if h.name == "openrouter":
        spec["usage"]["cost"] = 0.0
    r = h.provider(spec).complete("s", HISTORY, target(h), CFG)
    assert r.estimated_cost_usd == (0.0 if h.name == "openrouter" else None)  # Gemini: no invented prices


def test_difference_schema_name_only_on_openrouter(h):
    h.provider(h.ok(json.dumps(GATE))).complete("s", HISTORY, target(h), CFG, schema=GATE_SCHEMA,
                                                schema_name=GATE_SCHEMA_NAME)
    name, _ = h.schema()
    assert name == (GATE_SCHEMA_NAME if h.name == "openrouter" else None)


def test_openrouter_only_payment_required_and_error_inside_200():
    o = ORHarness()
    with pytest.raises(LLMError) as ei:
        o.provider(httpx.Response(402, json={"error": {"message": "credits"}})).complete("s", HISTORY, target(o), CFG)
    assert ei.value.code == "MODEL_PAYMENT_REQUIRED"
    for body, code in (({"error": {"code": 429, "message": "upstream rate limited"}}, "MODEL_RATE_LIMITED"),
                       ({"error": {"code": 404, "message": "no endpoints"}}, "MODEL_NOT_FOUND"),
                       ({"error": {"message": "opaque"}}, "MODEL_API_ERROR"),
                       ({"model": OR_MODEL, "choices": []}, "MODEL_EMPTY_RESPONSE")):
        with pytest.raises(LLMError) as ei:
            o.provider(body).complete("s", HISTORY, target(o), CFG)
        assert ei.value.code == code


def test_openrouter_refusal_field_is_a_refusal():
    o = ORHarness()
    body = {"model": OR_MODEL, "choices": [{"message": {"content": None, "refusal": "I can't help with that."},
                                            "finish_reason": "stop"}]}
    with pytest.raises(LLMError) as ei:
        o.provider(body).complete("s", HISTORY, target(o), CFG)
    assert ei.value.code == "MODEL_REFUSAL"


def test_gemini_only_invalid_key_400_is_auth_and_prompt_block_is_refusal():
    g = GeminiHarness()
    bad_key = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid.", "status":
                                                 "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}})
    with pytest.raises(LLMError) as ei:
        g.provider(bad_key).complete("s", HISTORY, target(g), CFG)
    assert ei.value.code == "MODEL_AUTH_ERROR"
    with pytest.raises(LLMError) as ei:
        g.provider(errors.ClientError(400, {"error": {"message": "bad field"}})).complete("s", HISTORY, target(g), CFG)
    assert ei.value.code == "MODEL_BAD_REQUEST"
    with pytest.raises(LLMError) as ei:
        g.provider(g.ok(json.dumps(REPLY), block="PROHIBITED_CONTENT")).complete("s", HISTORY, target(g), CFG)
    assert ei.value.code == "MODEL_REFUSAL"


def test_difference_retries_are_done_by_different_layers(h):
    """OpenRouter: app.llm.http retries 429/5xx/timeouts itself. Gemini: the SDK retries (HttpRetryOptions)."""
    cfg = GenerationConfig(max_tokens=100, temperature=None, timeout_seconds=5, max_retries=2)
    if h.name == "openrouter":
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
