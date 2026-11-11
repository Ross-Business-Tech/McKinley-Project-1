"""A/B/C runner sized for the first live run: 5 core cases x 3 modes = 15 comparable calls, strict budget, 429 stop.

Offline: fake OpenRouter over httpx.MockTransport; the public model list is mocked too.
"""

import json

import httpx

from app.config import Settings
from app.evals import CORE_CASE_IDS
from app.live_eval import abc as live_abc
from app.llm.openrouter import OpenRouterProvider

MODEL = "nvidia/nemotron-3.5-super-vl:free"
TARGET = f"openrouter:{MODEL}"
FAKE_KEY = "test-key-not-real"
REQUIRED_FIELDS = {"provider", "served_model", "prompt_version", "item_id", "mode", "source_context_fields", "reply",
                   "raw_model_text", "workflow", "safety", "latency_ms", "input_tokens", "output_tokens",
                   "estimated_cost_usd", "cost_source", "automated_grade", "human_review_status", "comparable"}


def _listing() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": [
        {"id": MODEL, "pricing": {"prompt": "0", "completion": "0"}, "context_length": 1000000,
         "supported_parameters": ["response_format", "structured_outputs"]}]})))


def _provider(calls: list, status: int = 200) -> dict:
    def handler(req):
        calls.append(json.loads(req.content)["model"])
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "slow down"}})
        content = json.dumps({"reply": "Thanks for reaching out. A leasing specialist can confirm options.",
                              "audience": "unknown", "recommended_handoff": False, "handoff_category": "none",
                              "handoff_reason": "", "language": "English"})
        return httpx.Response(200, json={"model": MODEL, "choices": [{"finish_reason": "stop", "message": {
            "content": content}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                             "completion_tokens_details": {"reasoning_tokens": 4}}})
    return {"openrouter": OpenRouterProvider(FAKE_KEY, "https://openrouter.test/api/v1", "t",
                                             client=httpx.Client(transport=httpx.MockTransport(handler)))}


def _run(tmp_path, calls, status=200, **kw):
    s = Settings(_env_file=None, openrouter_api_key=FAKE_KEY, llm_max_retries=0, db_path=tmp_path / "a.sqlite3")  # type: ignore[call-arg]
    return live_abc.run_live_eval(s, TARGET, out_dir=tmp_path / "out", providers=_provider(calls, status),
                                  models_client=_listing(), sleeper=lambda x: None, log=lambda m: None,
                                  case_ids=None, scenario_ids=[], label="abc15", **kw)


def test_five_cases_three_modes_is_fifteen_comparable_calls(tmp_path):
    calls: list = []
    code, doc = _run(tmp_path, calls, max_calls=15)
    cases = [r for r in doc["records"] if r["kind"] == "case"]
    assert code == live_abc.EXIT_OK and len(calls) == 15 and set(calls) == {MODEL}
    assert len(cases) == 15 and {r["item_id"] for r in cases} == set(CORE_CASE_IDS) and len(CORE_CASE_IDS) == 5
    assert all(r["comparable"] for r in cases), [r["non_comparable_reasons"] for r in cases]
    for r in cases:
        assert REQUIRED_FIELDS <= set(r), REQUIRED_FIELDS - set(r)
        assert r["provider"] == "openrouter" and r["human_review_status"] == "pending"
        assert {"routed", "action_kind", "gate_intent"} <= set(r["workflow"])
        assert r["model_calls"][0]["thinking_tokens"] == 4 and r["model_calls"][0]["schema_name"] == "mckinley_reply"
    assert set(doc["meta"]["prompt_versions"]) == set(live_abc.MODES)
    assert doc["meta"]["budget"]["max_calls"] == 15 and doc["meta"]["model_calls_made"] == 15


def test_budget_below_fifteen_never_starts_an_unbalanced_case(tmp_path):
    calls: list = []
    code, doc = _run(tmp_path, calls, max_calls=14)
    assert code == live_abc.EXIT_STOPPED and doc["meta"]["stop_code"] == "BUDGET_EXHAUSTED"
    assert len(calls) == 12  # four complete A/B/C sets; the fifth case is not started
    by_case: dict = {}
    for r in doc["records"]:
        by_case.setdefault(r["item_id"], []).append(r["mode"])
    assert all(sorted(m) == sorted(live_abc.MODES) for m in by_case.values())


def test_repeated_429_stops_the_run(tmp_path):
    calls: list = []
    code, doc = _run(tmp_path, calls, status=429, max_calls=15, max_rate_limit_errors=2)
    assert code == live_abc.EXIT_STOPPED and doc["meta"]["stop_code"] == "RATE_LIMITED"
    assert len(calls) == 2  # stopped after the second 429; no further calls
    assert all(not r["comparable"] for r in doc["records"])
    assert FAKE_KEY not in (tmp_path / "out" / "results-abc15.json").read_text()


def test_cases_none_means_skip_cases_as_documented(tmp_path):
    calls: list = []
    s = Settings(_env_file=None, openrouter_api_key=FAKE_KEY, llm_max_retries=0, db_path=tmp_path / "n.sqlite3")  # type: ignore[call-arg]
    code, doc = live_abc.run_live_eval(s, TARGET, out_dir=tmp_path / "out", providers=_provider(calls),
                                       models_client=_listing(), sleeper=lambda x: None, log=lambda m: None,
                                       case_ids=["none"], scenario_ids=["none"], label="none")
    assert code == live_abc.EXIT_OK and doc["meta"]["cases"] == [] and doc["meta"]["scenarios"] == [] and not calls
