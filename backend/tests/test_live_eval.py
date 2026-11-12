"""Live A/B/C runner and preflight, fully offline (httpx.MockTransport; no network, no real key)."""

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.live_eval import abc as live_abc
from app.live_eval.preflight import fetch_models, model_info, recommend, run_preflight
from app.llm.mock import MockProvider
from app.llm.openrouter import OpenRouterProvider

MODEL = "nvidia/nemotron-3.5-super-vl:free"
TARGET = f"openrouter:{MODEL}"
FAKE_KEY = "test-key-not-real"

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


def _settings(tmp_path: Path, key: str | None = FAKE_KEY, **kw) -> Settings:
    kw.setdefault("llm_provider", "openrouter")  # these tests cover the OpenRouter path (Gemini is now the default)
    kw.setdefault("llm_model", "nvidia/nemotron-3.5-super-vl:free")
    return Settings(_env_file=None, openrouter_api_key=key, llm_max_retries=kw.pop("retries", 0),  # type: ignore[call-arg]
                    db_path=tmp_path / "t.sqlite3", **kw)


def _provider(handler) -> dict:
    return {"openrouter": OpenRouterProvider(FAKE_KEY, "https://openrouter.test/api/v1", "t",
                                             client=httpx.Client(transport=httpx.MockTransport(handler)))}


def _run(tmp_path: Path, handler=None, **kw):
    kw.setdefault("case_ids", ["case2_price_shopper"])
    kw.setdefault("scenario_ids", [])
    return live_abc.run_live_eval(
        kw.pop("settings", None) or _settings(tmp_path), kw.pop("target", TARGET), out_dir=tmp_path / "out",
        providers=_provider(handler) if handler else None, models_client=_models_client(),
        sleeper=kw.pop("sleeper", lambda s: None), log=lambda m: None, **kw)


def _ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_reply(json.loads(req.content)["model"]))


# ---------------------------------------------------------------------------------------------- preflight
def test_preflight_parses_listing_and_recommends(tmp_path):
    s = _settings(tmp_path, eval_targets=f"mock:mock-deterministic-v1,openrouter:google/gemma-4-31b-it:free,"
                                         f"{TARGET},openrouter:missing/model:free,ollama:llama3.2")
    rep = run_preflight(s, client=_models_client())
    rows = {r["target"]: r for r in rep["targets"]}
    info = rows[TARGET]["info"]
    assert info["listed"] and info["free"] and info["supports_structured_outputs"]
    assert info["pricing_prompt_usd_per_token"] == 0.0 and info["context_length"] == 1000000
    assert rows["openrouter:google/gemma-4-31b-it:free"]["info"]["supports_structured_outputs"] is False
    assert rows["openrouter:missing/model:free"]["info"]["listed"] is False
    assert rep["ollama_reachable"] is False and rows["ollama:llama3.2"]["provider_ready"] is False
    # gemma comes first in EVAL_TARGETS but lacks structured outputs, so nemotron is recommended
    assert rep["recommended_target"] == TARGET
    assert rep["keys_present"] == {"gemini": False, "openrouter": True, "anthropic": False}
    assert rep["live_ready"] is True
    assert FAKE_KEY not in json.dumps(rep)


def test_preflight_network_failure_is_graceful(tmp_path):
    rep = run_preflight(_settings(tmp_path, key=None), client=_models_client(fail=True))
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


# ------------------------------------------------------------------------------------------------ runner
def test_blocked_without_key_never_falls_back_to_mock(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("mock must not be called")
    monkeypatch.setattr(MockProvider, "complete", boom)
    code, doc = live_abc.run_live_eval(_settings(tmp_path, key=None), TARGET, out_dir=tmp_path / "out",
                                       log=lambda m: None)
    assert code == live_abc.EXIT_BLOCKED and doc["reason_code"] == "NEEDS_API_KEY"
    status = json.loads((tmp_path / "out" / "status.json").read_text())
    assert status["status"] == "blocked" and status["keys_present"]["openrouter"] is False
    assert not list((tmp_path / "out").glob("results-*.json"))


def test_mock_requires_allow_flag(tmp_path):
    code, doc = live_abc.run_live_eval(_settings(tmp_path), "mock:mock-deterministic-v1", out_dir=tmp_path / "out",
                                       log=lambda m: None)
    assert code == live_abc.EXIT_BLOCKED and doc["reason_code"] == "MOCK_NOT_ALLOWED"


def test_mock_dry_run_labelled_and_never_comparable(tmp_path):
    code, doc = _run(tmp_path, target="mock:mock-deterministic-v1", allow_mock=True,
                     scenario_ids=["a-injected-history"], label="dry")
    assert code == live_abc.EXIT_OK
    assert doc["meta"]["execution"] == "MOCK" and doc["summary"]["basis"] == "comparable_if_live"
    assert doc["records"] and all(r["execution"] == "MOCK" and r["comparable"] is False for r in doc["records"])
    assert all("MOCK" in r["non_comparable_reasons"] for r in doc["records"])
    assert all(c["comparable"] is False for c in doc["conversations"])
    assert all(r["human_review_status"] == "pending" for r in doc["records"])
    md = (tmp_path / "out" / "report-dry.md").read_text()
    assert md.startswith("# MOCK DRY RUN") and "LIVE A/B/C" not in md
    assert json.loads((tmp_path / "out" / "status-mock-dryrun.json").read_text())["status"] == "mock_dry_run"
    assert not (tmp_path / "out" / "status.json").exists()  # a dry run never replaces the live status


def test_live_success_records_everything(tmp_path):
    sleeps: list[float] = []
    code, doc = _run(tmp_path, _ok, sleeper=sleeps.append, scenario_ids=["p-tour-this-week"], label="ok")
    assert code == live_abc.EXIT_OK and doc["meta"]["execution"] == "LIVE"
    case_recs = [r for r in doc["records"] if r["kind"] == "case"]
    assert [r["mode"] for r in case_recs] == ["baseline", "prompt_only", "aware"]
    r = case_recs[0]
    assert r["served_model"] == MODEL and r["requested_model"] == MODEL and r["comparable"] is True
    assert r["raw_model_text"] and r["automated_grade"]["provisional_verdict"] in ("GOOD", "BAD")
    assert r["model_calls"][0]["input_tokens"] == 100 and r["model_calls"][0]["cost_source"] == "listing_price_x_tokens"
    assert "safety_notice" in r["safety"] and "care_kind" in r["safety"]
    assert {"routed", "action_kind", "records"} <= set(r["workflow"]) and "recommended" in r["handoff"]
    assert len(sleeps) == doc["meta"]["model_calls_made"] - 1  # paced between calls, not before the first
    assert any(c["kind"] == "conversation_turn" for c in doc["records"]) and doc["conversations"]
    assert FAKE_KEY not in (tmp_path / "out" / "results-ok.json").read_text()
    assert (tmp_path / "out" / "report-ok.md").read_text().startswith("# LIVE A/B/C")


def test_budget_limit_respected(tmp_path):
    hits = []

    def handler(req):
        hits.append(1)
        return _ok(req)
    code, doc = _run(tmp_path, handler, case_ids=["case1_high_intent_prospect", "case2_price_shopper"],
                     max_calls=4)
    assert len(hits) <= 4 and doc["meta"]["model_calls_made"] <= 4
    assert code == live_abc.EXIT_STOPPED and doc["meta"]["stop_code"] == "BUDGET_EXHAUSTED"
    # never an unbalanced A/B/C set: the second case did not start
    assert {r["item_id"] for r in doc["records"]} == {"case1_high_intent_prospect"}
    assert json.loads((tmp_path / "out" / "status.json").read_text())["status"] == "stopped"


def test_persistent_429_stops_cleanly_with_partial_results(tmp_path):
    hits = []

    def handler(req):
        hits.append(1)
        if len(hits) == 1:
            return _ok(req)
        return httpx.Response(429, headers={"retry-after": "0"}, json={"error": {"message": "rate limited"}})
    s = _settings(tmp_path, retries=1)
    code, doc = _run(tmp_path, handler, settings=s, case_ids=["case1_high_intent_prospect", "case2_price_shopper"])
    assert code == live_abc.EXIT_STOPPED and doc["meta"]["stop_code"] == "RATE_LIMITED"
    assert len(hits) == 3  # 1 ok + one 429 call with its single same-model retry; nothing after the stop
    recs = doc["records"]
    assert recs[0]["comparable"] is True
    assert recs[1]["status"] == "error" and recs[1]["error_code"] == "MODEL_RATE_LIMITED"
    assert recs[1]["comparable"] is False and len(recs) == 2
    assert (tmp_path / "out" / f"results-{doc['meta']['label']}.json").exists()


def test_timeout_recorded_as_error_not_success(tmp_path):
    def handler(req):
        raise httpx.ReadTimeout("slow")
    code, doc = _run(tmp_path, handler, scenario_ids=["a-injected-history"], modes=["aware"])
    case = next(r for r in doc["records"] if r["kind"] == "case")
    assert case["status"] == "error" and case["error_code"] == "MODEL_TIMEOUT" and case["comparable"] is False
    assert case["automated_grade"] is None
    turns = [r for r in doc["records"] if r["kind"] == "conversation_turn"]
    assert turns and not any(t["comparable"] for t in turns)
    fallback = [t for t in turns if t["reply_source"] == "template_after_model_error"]
    assert fallback and all(t["error_code"] == "MODEL_TIMEOUT" for t in fallback)
    assert all(c["comparable"] is False for c in doc["conversations"])
    agg = doc["summary"]["turns_by_mode"]["aware"]
    assert agg["comparable"] == 0 and agg["good"] == 0 and agg["errors"] >= 1


def test_model_switched_excluded(tmp_path):
    def handler(req):
        return httpx.Response(200, json=_reply("some/other-model"))
    code, doc = _run(tmp_path, handler)
    assert all(r["status"] == "error" and r["error_code"] == "MODEL_SWITCHED" for r in doc["records"])
    assert all(r["served_model"] == "some/other-model" and not r["comparable"] for r in doc["records"])
    assert all(a["comparable"] == 0 for a in doc["summary"]["cases_by_mode"].values())


def test_paid_or_unlisted_model_refused(tmp_path):
    s = _settings(tmp_path, eval_targets="openrouter:paid/model,openrouter:nope/x:free")
    code, doc = _run(tmp_path, _ok, settings=s, target="openrouter:paid/model")
    assert code == live_abc.EXIT_BLOCKED and doc["reason_code"] == "MODEL_NOT_FREE"
    code, doc = _run(tmp_path, _ok, settings=s, target="openrouter:nope/x:free")
    assert doc["reason_code"] == "MODEL_NOT_LISTED"


@pytest.mark.parametrize("raw", ["recommended"])
def test_recommended_target_needs_preflight(tmp_path, raw):
    code, doc = _run(tmp_path, _ok, target=raw)
    assert code == live_abc.EXIT_BLOCKED and doc["reason_code"] == "BAD_TARGET"
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "out" / "preflight.json").write_text(json.dumps({"recommended_target": TARGET}))
    code, doc = _run(tmp_path, _ok, target=raw)
    assert code == live_abc.EXIT_OK and doc["meta"]["target"] == TARGET and doc["meta"]["target_arg"] == raw
