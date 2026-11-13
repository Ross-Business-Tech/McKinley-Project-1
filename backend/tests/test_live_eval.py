"""Live-model preflight, fully offline (httpx.MockTransport; no network, no real key)."""

import json
from pathlib import Path

import httpx

from app.config import Settings
from app.live_eval.preflight import fetch_models, model_info, recommend, run_preflight
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
