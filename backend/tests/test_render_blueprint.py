"""render.yaml (the Render Blueprint) describes the intended demo deployment: hosted safeguards on, U-M GPT Toolkit
gpt-6.1-sol for chat and the safety classifier, no other provider or fallback model, secrets never committed, and the
Toolkit refused until the university approves public use. Offline: settings are built from the Blueprint's values
plus obviously fake secrets; nothing is deployed or called."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.llm import LLMGateway

BACKEND = Path(__file__).resolve().parent.parent
BLUEPRINT = yaml.safe_load((BACKEND.parent / "render.yaml").read_text())
SERVICES = {s["name"]: s for s in BLUEPRINT["services"]}
BACKEND_ENV = {e["key"]: e for e in SERVICES["mckinley-backend"]["envVars"]}
# What an operator types into Render for the sync:false / generated values (fake, never real)
FAKE_SECRETS = {"UM_TOOLKIT_API_KEY": "test-key-not-real", "DATABASE_URL": "postgresql://u:p@db.example.org:5432/x",
                "CORS_ORIGINS": "https://mckinley-frontend.onrender.com",
                "STAFF_API_TOKEN": "k7Qp2vX9mR4tL8wZ3nB6yC1dF5hJ0sGa"}


def blueprint_values(**overrides: str | None) -> dict[str, str]:
    env = {k: str(e["value"]) for k, e in BACKEND_ENV.items() if "value" in e}
    env.update(FAKE_SECRETS)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def settings_from(env: dict[str, str]) -> Settings:
    fields = Settings.model_fields
    kw = {k.lower(): v for k, v in env.items() if k.lower() in fields}
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_both_services_are_intact():
    assert set(SERVICES) == {"mckinley-backend", "mckinley-frontend"}
    be, fe = SERVICES["mckinley-backend"], SERVICES["mckinley-frontend"]
    assert (be["type"], be["runtime"], be["rootDir"], be["healthCheckPath"]) == ("web", "python", "backend",
                                                                                "/api/health")
    assert "uv sync --frozen --no-dev" in be["buildCommand"]
    assert "alembic upgrade head" in be["startCommand"] and "uvicorn app.main:app" in be["startCommand"]
    assert (fe["type"], fe["runtime"], fe["rootDir"], fe["staticPublishPath"]) == ("web", "static", "frontend", "out")
    fe_env = {e["key"]: e for e in fe["envVars"]}
    assert fe_env["NEXT_STATIC_EXPORT"]["value"] == "1" and fe_env["NEXT_PUBLIC_API_BASE_URL"]["sync"] is False


def test_intended_model_and_safeguards_are_pinned():
    v = {k: e.get("value") for k, e in BACKEND_ENV.items()}
    assert v["APP_ENV"] == "hosted"
    assert v["LLM_PROVIDER"] == "um_toolkit"
    assert v["LLM_MODEL"] == "gpt-6.1-sol" and v["UM_TOOLKIT_MODEL"] == "gpt-6.1-sol"
    assert v["UM_TOOLKIT_BASE_URL"] == "https://api.toolkit.umgpt.umich.edu/v1"
    assert v["SAFETY_CLASSIFIER"] == "auto" and "SAFETY_CLASSIFIER_TARGET" not in v
    assert v["RESIDENT_DATA_SOURCE"] == "database" and v["EVAL_TARGETS"] == "um_toolkit:gpt-6.1-sol"
    assert "DEMO_PERSONAS_ENABLED" not in v and "KNOWLEDGE_CONTENT_MODE" not in v  # hosted defaults: off / approved
    assert BACKEND_ENV["STAFF_API_TOKEN"].get("generateValue") is True


def test_no_other_provider_in_the_default_deployment():
    text = yaml.safe_dump(SERVICES["mckinley-backend"]).lower()
    for old in ("openrouter", "nemotron", "gemini", ":free", "mock"):
        assert old not in text


def test_secrets_and_the_approval_flag_are_never_committed_values():
    for key in ("UM_TOOLKIT_API_KEY", "DATABASE_URL", "CORS_ORIGINS", "UM_TOOLKIT_HOSTED_APPROVED"):
        assert BACKEND_ENV[key] == {"key": key, "sync": False}
    for key, e in BACKEND_ENV.items():
        if key.endswith(("_KEY", "_TOKEN", "_URL")) and key != "UM_TOOLKIT_BASE_URL":
            assert "value" not in e, key


def test_blueprint_resolves_to_gpt_61_sol_for_chat_and_classifier_with_no_fallback():
    s = settings_from(blueprint_values(UM_TOOLKIT_HOSTED_APPROVED="true"))
    gw = LLMGateway(s)
    assert gw.default_target.key == "um_toolkit:gpt-6.1-sol"
    assert [t.key for t in gw.eval_targets()] == ["um_toolkit:gpt-6.1-sol"]  # no mock / OpenRouter alternative
    assert s.safety_classifier == "auto" and s.safety_classifier_target is None  # = the chat default target
    assert gw.provider_ready("um_toolkit") == (True, "API key configured")
    assert s.app_env == "hosted" and s.demo_personas_allowed is False
    assert s.hosted_problems() == []


def test_without_university_approval_a_hosted_start_is_refused():
    problems = settings_from(blueprint_values()).hosted_problems()
    assert problems == [p for p in problems if "UM_TOOLKIT_HOSTED_APPROVED=true" in p] and len(problems) == 1
    for v in ("false", "0", "no"):
        assert any("UM_TOOLKIT_HOSTED_APPROVED" in p
                   for p in settings_from(blueprint_values(UM_TOOLKIT_HOSTED_APPROVED=v)).hosted_problems())


def test_missing_toolkit_key_is_refused_without_echoing_secrets():
    problems = settings_from(blueprint_values(UM_TOOLKIT_API_KEY=None, UM_TOOLKIT_HOSTED_APPROVED="true")
                             ).hosted_problems()
    assert any("UM_TOOLKIT_API_KEY must be set" in p for p in problems)
    assert not any(secret in p for p in problems for secret in FAKE_SECRETS.values())


@pytest.mark.parametrize("model", ["nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free"])
def test_a_leftover_openrouter_model_cannot_reach_the_toolkit(model):
    with pytest.raises(ValueError, match="OpenRouter model id"):
        settings_from(blueprint_values(LLM_MODEL=model))


def test_missing_model_uses_the_toolkit_model_and_missing_provider_is_refused():
    s = settings_from(blueprint_values(LLM_MODEL=None, UM_TOOLKIT_HOSTED_APPROVED="true"))
    assert s.llm_model == "gpt-6.1-sol" and s.hosted_problems() == []
    implicit = settings_from(blueprint_values(LLM_PROVIDER=None, LLM_MODEL=None, UM_TOOLKIT_HOSTED_APPROVED="true"))
    assert any("LLM_PROVIDER must be set" in p for p in implicit.hosted_problems())


def test_demo_personas_stay_refused_on_the_hosted_blueprint():
    s = settings_from(blueprint_values(UM_TOOLKIT_HOSTED_APPROVED="true", DEMO_PERSONAS_ENABLED="true"))
    assert any("DEMO_PERSONAS_ENABLED must be false" in p for p in s.hosted_problems())
    assert s.demo_personas_allowed is False


def test_the_backend_process_refuses_to_start_from_the_unapproved_blueprint(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN", "DATABASE_URL", "APPROVED"))}
    env.update(blueprint_values(), DB_PATH=str(tmp_path / "x.sqlite3"))
    r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode != 0 and "Unsafe settings for APP_ENV=hosted" in r.stderr
    assert "UM_TOOLKIT_HOSTED_APPROVED=true" in r.stderr
    assert not any(secret in r.stderr for secret in FAKE_SECRETS.values())
