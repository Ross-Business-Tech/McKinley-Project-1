"""Hosted (Render) readiness: unsafe settings refuse to start, health shows deployment facts but no secrets."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
GOOD = dict(_env_file=None, app_env="hosted", cors_origins="https://mckinley-demo.vercel.app",
            staff_api_token="x" * 32, gate_override_enabled=False,
            database_url="postgresql://user:secret-password@db.example.com:5432/postgres")


def test_good_hosted_settings_have_no_problems():
    assert Settings(**GOOD).hosted_problems() == []


@pytest.mark.parametrize("override,needle", [
    ({"cors_origins": "*"}, "wildcards"),
    ({"cors_origins": "https://ok.vercel.app,http://localhost:3000"}, "localhost"),
    ({"cors_origins": "http://mckinley-demo.example.com"}, "https"),
    ({"staff_api_token": None}, "STAFF_API_TOKEN"),
    ({"staff_api_token": "short"}, "STAFF_API_TOKEN"),
    ({"gate_override_enabled": True}, "GATE_OVERRIDE_ENABLED"),
    ({"database_url": None}, "DATABASE_URL"),
])
def test_unsafe_hosted_settings_are_reported_without_values(override, needle):
    problems = Settings(**{**GOOD, **override}).hosted_problems()
    assert any(needle in p for p in problems)
    assert not any("secret-password" in p or "x" * 32 in p for p in problems)


def test_local_mode_is_not_restricted():
    assert Settings(_env_file=None, cors_origins="http://localhost:3000").hosted_problems() == []


def test_hosted_backend_with_unsafe_settings_refuses_to_start(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN", "DATABASE_URL"))}
    env.update(APP_ENV="hosted", CORS_ORIGINS="*", DB_PATH=str(tmp_path / "x.sqlite3"))
    r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode != 0 and "Unsafe settings for APP_ENV=hosted" in r.stderr


def test_health_shows_deployment_facts_but_no_secrets(client):
    from app.state import get_state
    s = get_state().deps.settings
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["database"] == "sqlite" and r["app_env"] == "local"
    assert r["is_mock"] is True and r["resident_source"]
    for secret in (s.staff_api_token, s.database_url, s.gemini_api_key, s.openrouter_api_key):
        assert secret is None or secret.get_secret_value() not in str(r)
