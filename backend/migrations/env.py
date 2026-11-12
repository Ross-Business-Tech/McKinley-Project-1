"""Alembic environment. The database URL comes from settings (DATABASE_URL, else the SQLite DB_PATH) and is never
printed. Migrations are raw SQL per dialect: the app itself talks to the database with sqlite3 / psycopg (app/db.py),
SQLAlchemy is used here only to run these migrations."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import Settings


def database_url() -> str:
    """SQLAlchemy URL for the configured database. `-x url=...` overrides (used by tests)."""
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    s = Settings()
    raw = s.database_url.get_secret_value().strip() if s.database_url else ""
    if raw:
        return sqlalchemy_url(raw)
    return f"sqlite:///{s.resolve(s.db_path)}"


def sqlalchemy_url(raw: str) -> str:
    """postgresql://… (as Supabase shows it) -> postgresql+psycopg://… (psycopg 3 driver, already a dependency)."""
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


def run_migrations_offline() -> None:
    context.configure(url=database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = database_url()
    # prepare_threshold=None: works behind Supabase's transaction pooler too.
    from app.db import pg_tls_args  # TLS required for any non-local Postgres unless the URL sets sslmode
    connect_args = ({"prepare_threshold": None, **pg_tls_args(url.replace("+psycopg", "", 1))}
                    if url.startswith("postgresql+psycopg") else {})
    engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
