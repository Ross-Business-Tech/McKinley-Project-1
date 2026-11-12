"""Customers get a fixed, safe message when the model fails; staff keep the provider's code for diagnostics."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.errors import customer_llm_error_response
from app.config import Settings
from app.db import Store
from app.llm import LLMError, LLMGateway
from app.main import app
from app.state import build_state, set_state

TOKEN = "t0k3n-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LEAKS = ("openrouter", ".env", "api_key", "api key", "http://", "https://", "traceback", "postgres")


@pytest.fixture
def no_key_hosted(workbook, tmp_path: Path):
    """A hosted backend whose OpenRouter key is missing (the Render 503 of 2026-11-11)."""
    s = Settings(_env_file=None, app_env="hosted", llm_provider="openrouter", llm_model="some/free-model:free",
                 db_path=tmp_path / "h.sqlite3", eval_results_path=tmp_path / "r.json",
                 eval_targets="openrouter:some/free-model:free", staff_api_token=SecretStr(TOKEN),
                 cors_origins="https://mckinley-frontend.onrender.com")
    set_state(build_state(settings=s, gateway=LLMGateway(s), workbook=workbook, store=Store(tmp_path / "s.sqlite3")))
    with TestClient(app) as c:
        yield c
    set_state(None)  # type: ignore[arg-type]


def _ask(c, headers=None):
    return c.post("/api/chat", json={"message": "what are your office hours?", "persona_id": None, "mode": "aware",
                                     "session_id": None}, headers=headers or {})


def test_missing_key_customer_sees_safe_unavailable_message(no_key_hosted):
    r = _ask(no_key_hosted)
    assert r.status_code == 503
    err = r.json()["error"]
    assert err == {"code": "ASSISTANT_UNAVAILABLE", "retryable": False,
                   "message": "The assistant is not available right now. Please contact the office directly."}
    assert not any(x in r.text.lower() for x in LEAKS)


def test_missing_key_staff_still_see_the_provider_code(no_key_hosted):
    r = _ask(no_key_hosted, {"X-Staff-Token": TOKEN})
    assert r.status_code == 503 and r.json()["error"]["code"] == "NEEDS_API_KEY"


@pytest.mark.parametrize("code,retryable,expected", [
    ("MODEL_RATE_LIMITED", True, "ASSISTANT_BUSY"),
    ("MODEL_TIMEOUT", True, "ASSISTANT_BUSY"),
    ("MODEL_CONNECTION_ERROR", True, "ASSISTANT_BUSY"),
    ("MODEL_API_ERROR", False, "ASSISTANT_BUSY"),
    ("NEEDS_API_KEY", False, "ASSISTANT_UNAVAILABLE"),
    ("MODEL_AUTH_ERROR", False, "ASSISTANT_UNAVAILABLE"),
    ("MODEL_PAYMENT_REQUIRED", False, "ASSISTANT_UNAVAILABLE"),
    ("MODEL_NOT_FOUND", False, "ASSISTANT_UNAVAILABLE"),
])
def test_error_mapping_temporary_vs_configuration(code, retryable, expected):
    secret_msg = "Could not connect to openrouter at https://openrouter.ai; set OPENROUTER_API_KEY in backend/.env"
    resp = customer_llm_error_response(LLMError(code, secret_msg, retryable=retryable))
    body = json.loads(resp.body)["error"]
    assert resp.status_code == 503 and body["code"] == expected
    assert body["retryable"] is (expected == "ASSISTANT_BUSY")
    assert not any(x in body["message"].lower() for x in LEAKS)
