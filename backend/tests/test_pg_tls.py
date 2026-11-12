"""TLS is required for any non-local Postgres (Supabase, a cloud DB) unless the URL already states an sslmode:
psycopg's default `prefer` would silently fall back to plaintext."""

import pytest

from app.db import pg_tls_args


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
