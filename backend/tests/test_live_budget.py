"""Central live-call budget + metadata ledger, and the OpenRouter reasoning setting (all offline)."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import LLMError, LLMGateway
from app.llm.base import Target
from app.llm.openrouter import OpenRouterProvider

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
        gw.complete("s", [{"role": "user", "content": "x"}], target=Target("mock", "mock-deterministic-v1"))
    assert not (tmp_path / "l.jsonl").exists()


@pytest.mark.parametrize("effort,expected", [(None, None), ("none", {"enabled": False}), ("low", {"effort": "low"})])
def test_openrouter_reasoning_setting_is_sent_only_when_configured(tmp_path, effort, expected):
    sent: list = []
    gw, _ = _gw(tmp_path, budget=0, reasoning=effort, sent=sent)
    r = gw.complete("s", [{"role": "user", "content": "x"}])
    assert sent[0].get("reasoning") == expected
    assert r.extra["reasoning"] == (effort or "model default")
