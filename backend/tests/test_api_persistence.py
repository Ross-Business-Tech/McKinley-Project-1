"""API behaviour and persistence: HTTP contract, SQLite/Postgres store, migrations, TLS, hosted settings and test
environment isolation."""

import os
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest
from alembic import command
from alembic.config import Config

from app import seed_synthetic
from app.auth import TOOLING
from app.config import Settings
from app.context import load_workbook
from app.db import _TABLES, Store, pg_tls_args, session_hash
from app.personas import build_context
from app.state import load_residents
from tests.conftest import REAL_WORKBOOK, throwaway_pg_url
from tests.test_authorization import AC_MSG, RENEWAL_MSG  # noqa: F401

# ---- test_api

def test_health_and_models_hide_secrets(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["provider"] == "mock" and h["data_loaded"]
    models = client.get("/api/models")
    assert models.status_code == 200
    text = models.text.lower()
    assert "sk-" not in text and "openrouter_api_key" not in text and "base_url" not in text
    by_key = {m["key"]: m for m in models.json()}
    assert by_key["mock:mock-deterministic-v1"]["is_mock"]
    assert by_key["openrouter:google/gemma-4-31b-it:free"]["status"] == "NEEDS_API_KEY"


def test_personas(client):
    ps = client.get("/api/personas").json()
    assert {"P-RELOCATE-AA", "P-BROWSE-FL", "U-NOMATCH", "R001"} <= {p["id"] for p in ps}


def test_chat_aware_vs_baseline(client):
    a = client.post("/api/chat", json={"message": AC_MSG, "persona_id": "R001", "mode": "aware",
                                       "session_id": "s1"}).json()
    b = client.post("/api/chat", json={"message": AC_MSG, "persona_id": "R001", "mode": "baseline",
                                       "session_id": "s1"}).json()
    assert a["is_mock"] and a["provider"] == "mock" and a["model"] == "mock-deterministic-v1"
    assert a["recommended_handoff"] and a["handoff_is_recommendation_only"]
    assert a["source_context_fields"] and b["source_context_fields"] == []
    assert a["prompt_version"].startswith("mckinley-v0.2") and b["prompt_version"].startswith("baseline-v1")
    assert {c["code"] for c in a["output_checks"]} >= {"terminology", "no_false_action_claim", "structured_output"}


def test_aware_policy_gate_forces_handoff(client):
    r = client.post("/api/chat", json={"message": "I smell gas in my kitchen", "persona_id": "U-NOMATCH",
                                       "mode": "aware"}).json()
    assert r["recommended_handoff"] and r["handoff_category"] == "safety_emergency"


def test_chat_validation_and_errors(client):
    assert client.post("/api/chat", json={"message": "", "mode": "aware"}).status_code == 422
    assert client.post("/api/chat", json={"message": "x", "mode": "other"}).status_code == 422
    assert client.post("/api/chat", json={"message": "x", "mode": "aware", "extra": 1}).status_code == 422
    r = client.post("/api/chat", json={"message": "x", "mode": "aware", "target": "openrouter:evil/model"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNKNOWN_TARGET"
    r = client.post("/api/chat", json={"message": "x", "mode": "aware",
                                       "target": "openrouter:google/gemma-4-31b-it:free"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "NEEDS_API_KEY"


def test_session_separation(client, settings):
    from app.db import Store
    store = Store(settings.db_path)
    client.post("/api/chat", json={"message": RENEWAL_MSG, "persona_id": "R003", "mode": "aware",
                                   "session_id": "A"})
    assert store.history("A", "aware|mock:mock-deterministic-v1", "R003")
    assert store.history("B", "aware|mock:mock-deterministic-v1", "R003") == []
    assert store.history("A", "baseline|mock:mock-deterministic-v1", "R003") == []


def test_configured_key_never_returned(settings, workbook):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.db import Store
    from app.llm import LLMGateway
    from app.main import app
    from app.state import build_state, set_state

    settings.openrouter_api_key = SecretStr("sk-or-v1-SUPERSECRET")
    set_state(build_state(settings=settings, gateway=LLMGateway(settings), workbook=workbook,
                          store=Store(settings.db_path)))
    with TestClient(app) as c:
        for path in ("/api/health", "/api/models", "/api/personas"):
            assert "SUPERSECRET" not in c.get(path).text
        assert {m["key"]: m for m in c.get("/api/models").json()}[
            "openrouter:google/gemma-4-31b-it:free"]["ready"]
    set_state(None)  # type: ignore[arg-type]


# ---- The Store behaves the same on SQLite and on Postgres (for example Supabase).

PG_URL = throwaway_pg_url()


NEEDS_PG = pytest.mark.skipif(not PG_URL, reason="no TEST_DATABASE_URL")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=NEEDS_PG)])
def store(request, tmp_path):
    if request.param == "sqlite":
        yield Store(tmp_path / "t.sqlite3")
        return
    s = Store(database_url=PG_URL)
    s._q(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
    yield s
    s._q(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")


def test_chat_history_round_trip(store):
    store.append_turns("s1", "aware|x", "p1", "my sink leaks", "Sorry to hear that.")
    store.append_turns("s1", "aware|x", "p1", "kitchen", "Thanks.")
    hist = store.history("s1", "aware|x", "p1")
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]
    assert store.user_messages("s1", "p1") == ["my sink leaks", "kitchen"]
    assert store.history("other", "aware|x", "p1") == []


def test_staff_conversation_views_use_hashes(store):
    store.append_turns("s1", "aware|x", "p1", "hello", "hi")
    store.log_gate("s1", "aware|x", "p1", {"workflow": "human_handoff", "risk_flags": []})
    convs = store.conversations()
    assert len(convs) == 1 and convs[0]["messages"] == 1
    assert convs[0]["session_hash"] == session_hash("s1") and "asked_for_person" in convs[0]["needs_action"]
    turns = store.conversation(session_hash("s1"))
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert store.conversation("nope") == []


def test_gate_log(store):
    store.log_gate("s1", "aware|x", "p1", {"urgency": "normal"})
    assert store.last_gate("s1", "aware|x", "p1") == {"urgency": "normal"}
    log = store.gate_log()
    assert log[0]["session"] == session_hash("s1") and log[0]["urgency"] == "normal"
    assert store.last_gate("s2", "aware|x", "p1") is None


def test_drafts(store):
    assert store.get_draft("s1", "p1") is None
    store.save_draft("s1", "p1", "maintenance", {"issue": "leak"})
    store.save_draft("s1", "p1", "maintenance", {"issue": "leak", "room": "kitchen"})  # upsert
    assert store.get_draft("s1", "p1") == {"kind": "maintenance", "issue": "leak", "room": "kitchen"}
    store.mark_stale("s1", "p1", "maintenance", {"issue": "leak", "declined": True})
    assert store.get_draft("s1", "p1") is None
    assert store.get_draft("s1", "p1", include_declined=True)["declined"] is True
    assert store.take_draft("s1", "p1", "tour") is None  # wrong kind
    assert store.take_draft("s1", "p1", "maintenance")["issue"] == "leak"
    assert store.take_draft("s1", "p1", "maintenance") is None  # taken only once
    store.save_draft("s1", "p1", "tour", {"a": 1})
    store.clear_draft("s1", "p1")
    assert store.get_draft("s1", "p1") is None


def test_records_and_once_keys(store):
    a = store.add_record("DEMO-WO", "work_order", "s1", "p1", {"issue": "leak"})
    b = store.add_record("DEMO-TOUR", "tour", "s1", None, {"day": "Sat"})
    assert a["id"] == "DEMO-WO-1001" and b["id"] == "DEMO-TOUR-1002"
    first = store.add_record_once("DEMO-TASK", "task", "s1", None, {"note": "x"}, "k1")
    again = store.add_record_once("DEMO-TASK", "task", "s1", None, {"note": "x"}, "k1")
    assert again["id"] == first["id"] and again["_existing"] is True  # NULL persona matched, not duplicated
    other = store.add_record_once("DEMO-TASK", "task", "s1", "p1", {"note": "x"}, "k1")
    assert other["id"] != first["id"]
    assert [r["id"] for r in store.records(kind="work_order")] == ["DEMO-WO-1001"]
    assert len(store.records(persona_id="p1")) == 2
    assert len(store.records(session_id="s1")) == 4
    assert len(store.records(session_id="nobody")) == 0
    assert store.records(limit=1)[0]["id"] == other["id"]  # newest first


def test_literal_percent_and_odd_text_survive(store):
    text = "100% sure it's \"leaking\"; DROP TABLE chat_turns; --"
    store.append_turns("s1", "aware|x", "p1", text, "ok")
    assert store.history("s1", "aware|x", "p1")[0]["content"] == text


# ---- Alembic migrations + synthetic seed + reading residents back from the database.

BACKEND = Path(__file__).resolve().parents[1]


def alembic_cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    return cfg


def sa_url(target):
    return f"sqlite:///{target}" if isinstance(target, Path) else "postgresql+psycopg://" + target.split("://", 1)[1]


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not PG_URL,
                                                                                     reason="no TEST_DATABASE_URL"))])
def db(request, tmp_path):
    target = tmp_path / "m.sqlite3" if request.param == "sqlite" else PG_URL
    cfg = alembic_cfg(sa_url(target))
    command.downgrade(cfg, "base") if request.param == "postgres" else None
    command.upgrade(cfg, "head")
    store = Store(target, None) if isinstance(target, Path) else Store(None, database_url=target)
    yield target, cfg, store
    if request.param == "postgres":
        command.downgrade(cfg, "base")


def test_upgrade_creates_tables_and_downgrade_round_trips(db):
    target, cfg, store = db
    assert store.has_reference_tables()
    command.downgrade(cfg, "0001")
    assert not store.has_reference_tables()
    command.upgrade(cfg, "head")
    assert store.has_reference_tables()


def test_baseline_adopts_a_database_the_app_already_created(tmp_path):
    path = tmp_path / "existing.sqlite3"
    Store(path)  # app startup creates the six core tables itself
    command.upgrade(alembic_cfg(sa_url(path)), "head")  # must not fail on existing tables
    assert Store(path).has_reference_tables()


def _non_synthetic_workbook(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.active.title = "README"
    wb.active.append(["Customer export"])
    wb.create_sheet("Residents").append(["resident_id"])
    wb.create_sheet("Interactions").append(["interaction_id"])
    path = tmp_path / "export.xlsx"
    wb.save(path)
    return path


def test_seed_refuses_a_workbook_not_marked_synthetic(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "s.sqlite3"))
    assert seed_synthetic.main(["--workbook", str(_non_synthetic_workbook(tmp_path))]) == 3


@pytest.mark.skipif(not REAL_WORKBOOK.exists(), reason="synthetic workbook not present")
def test_seed_then_database_residents_match_the_file(db, monkeypatch):
    target, _, store = db
    if isinstance(target, Path):
        monkeypatch.setenv("DB_PATH", str(target))
    else:
        monkeypatch.setenv("DATABASE_URL", target)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        assert seed_synthetic.main(["--workbook", str(REAL_WORKBOOK)]) == 0
    finally:
        get_settings.cache_clear()
    file_wb = load_workbook(REAL_WORKBOOK)
    s = Settings(_env_file=None, resident_data_source="database", data_path=Path("/nonexistent.xlsx"))
    db_wb, err = load_residents(s, store)
    assert err is None and db_wb is not None and db_wb.source.startswith("database")
    assert set(db_wb.residents) == set(file_wb.residents)
    for rid in sorted(file_wb.residents):
        for msg in ("my AC is broken again", "what about my renewal?", "can you text me instead"):
            a = build_context(rid, msg, file_wb, principal=TOOLING).model_dump()
            b = build_context(rid, msg, db_wb, principal=TOOLING).model_dump()
            assert a == b, (rid, msg)


def test_without_file_or_seed_the_error_says_what_to_run(tmp_path):
    s = Settings(_env_file=None, data_path=Path("/nonexistent.xlsx"))
    wb, err = load_residents(s, Store(tmp_path / "e.sqlite3"))
    assert wb is None and "seed_synthetic" in err


def test_startup_schema_and_baseline_migration_never_drift():
    """app/db.py creates the core tables at startup; 0001 must stay identical (normalized) for both dialects."""
    import importlib.util
    import re

    from app import db

    spec = importlib.util.spec_from_file_location("m0001", BACKEND / "migrations" / "versions" / "0001_baseline.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def norm(sql: str) -> list[str]:
        sql = re.sub(r"--[^\n]*", "", sql)
        return [re.sub(r"\s+", " ", x).strip() for x in sql.split(";") if x.strip()]
    assert norm(db.SCHEMA) == norm(";".join(m._statements(False)))
    assert norm(db._postgres_schema()) == norm(";".join(m._statements(True)))


def test_nul_characters_are_stripped_before_writing(tmp_path):
    s = Store(tmp_path / "nul.sqlite3")
    s.append_turns("s", "aware|x", "p", "a\x00b", "ok\x00")
    assert s.user_messages("s", "p") == ["ab"]


# ---- TLS is required for any non-local Postgres (Supabase, a cloud DB) unless the URL already states an sslmode:

@pytest.mark.parametrize("url", [
    "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
    "postgresql://u:p@db.abcdefgh.supabase.co:5432/postgres",
    "postgres://u:p@dpg-x.oregon-postgres.render.com/db",
])
def test_remote_postgres_requires_tls(url):
    assert pg_tls_args(url) == {"sslmode": "require"}


@pytest.mark.parametrize("url", [
    "postgresql://u:p@db.x.supabase.co:5432/postgres?sslmode=verify-full",
    "postgresql://u:p@localhost:5432/t", "postgresql://u:p@127.0.0.1/t", "postgresql://u:p@[::1]/t",
])
def test_explicit_sslmode_or_local_host_is_left_alone(url):
    assert pg_tls_args(url) == {}


# ---- Hosted (Render) readiness: unsafe settings refuse to start, health shows deployment facts but no secrets.

GOOD = dict(_env_file=None, app_env="hosted", llm_provider="openrouter", cors_origins="https://mckinley-demo.vercel.app",  # noqa: E501
            staff_api_token="k7Qp2vX9mR4tL8wZ3nB6yC1dF5hJ0sGa", gate_override_enabled=False,
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
    assert not any("secret-password" in p or "k7Qp2vX9mR4tL8wZ" in p for p in problems)


def test_trailing_slash_in_cors_origins_is_normalised():
    s = Settings(**{**GOOD, "cors_origins": "https://mckinley-demo.vercel.app/ , https://b.example.org"})
    assert s.cors_origin_list == ["https://mckinley-demo.vercel.app", "https://b.example.org"]
    assert s.hosted_problems() == []


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


@pytest.mark.parametrize("override,needle", [
    ({"staff_api_token": " " * 30}, "STAFF_API_TOKEN"),
    ({"staff_api_token": "a" * 30}, "STAFF_API_TOKEN"),
    ({"cors_origins": "null"}, "bare origin"),
    ({"cors_origins": "https://ok.vercel.app/path"}, "bare origin"),
])
def test_weak_tokens_and_malformed_origins_are_refused(override, needle):
    assert any(needle in p for p in Settings(**{**GOOD, **override}).hosted_problems())


def test_bad_database_url_never_echoes_the_password():
    from app.db import Store
    for url in ("user:hunter2-secret@db.example.com/postgres",
                "postgresql://user:hunter2-secret@127.0.0.1:1/postgres?connect_timeout=1"):
        with pytest.raises((ValueError, ConnectionError)) as ei:
            Store(None, database_url=url)
        assert "hunter2-secret" not in str(ei.value) and ei.value.__cause__ is None


# ---- Tests never read backend/.env: a developer's real DATABASE_URL (e.g. Supabase) or provider key there must never

def test_settings_in_tests_ignore_the_env_file():
    from app.config import Settings, get_settings

    assert Settings.model_config.get("env_file") is None
    s = get_settings()
    assert not (s.database_url and s.database_url.get_secret_value().strip())
    assert not s.openrouter_api_key and not s.gemini_api_key and not s.staff_api_token
