"""Alembic migrations + synthetic seed + reading residents back from the database.

SQLite always runs. Postgres runs only with TEST_DATABASE_URL pointing at a THROWAWAY database (the tests drop and
recreate every table there)."""

from pathlib import Path

import openpyxl
import pytest
from alembic import command
from alembic.config import Config

from app import seed_synthetic
from app.auth import TOOLING
from app.config import Settings
from app.context import load_workbook
from app.db import Store
from app.personas import build_context
from app.state import load_residents
from tests.conftest import REAL_WORKBOOK, throwaway_pg_url

BACKEND = Path(__file__).resolve().parents[1]
PG_URL = throwaway_pg_url()


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


def _has_table(store, name):
    if store.dialect == "postgres":
        return store._q("SELECT to_regclass(?) AS t", (f"public.{name}",)).fetchone()["t"] is not None
    return store._q("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def test_invite_list_migration_round_trips_and_matches_the_startup_schema(db):
    import re

    from app import db as app_db
    target, cfg, store = db
    assert _has_table(store, "user_profiles")
    command.downgrade(cfg, "0004")
    assert not _has_table(store, "user_profiles")
    command.upgrade(cfg, "head")
    assert _has_table(store, "user_profiles")
    # the table the app creates at startup and the one the migration creates must be the same definition
    source = (BACKEND / "migrations" / "versions" / "0005_user_profiles.py").read_text()

    def squash(text):
        return re.sub(r"\s+", "", text)
    startup = re.search(r"CREATE TABLE IF NOT EXISTS user_profiles \(.*?\n\);", app_db.AUTH_SCHEMA, re.S).group(0)
    migration = re.search(r"CREATE TABLE IF NOT EXISTS user_profiles \(.*?\n\)", source, re.S).group(0)
    assert squash(startup).rstrip(";") == squash(migration)


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
