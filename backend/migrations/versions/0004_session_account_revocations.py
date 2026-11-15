"""Sprint 7 authorization: sticky "not the account holder" per (session, persona), and records scoped to a session by
a full 256-bit key (see app/db.py ScopedStore and session_key).

1. session_account_revocations:
Once a person says the account is not theirs ("I'm her roommate", "borrowing my mom's login"), the backend records it
here, so every later request for that session and persona (chat turns, confirm, cancel) gets no account data, even
if the wording is not detected again. The app also creates this table at startup (app/db.py AUTH_SCHEMA); this
migration keeps Alembic-managed databases in step. Row-level security is on with no policies (Supabase's public Data
API reads nothing).

2. prototype_records.session_key: the full sha256 of the session id. Session-scoped record reads (a guest's own note,
"send it", duplicates) used the 10-hex display hash (40 bits), which a crafted session id could collide with. Existing
rows keep NULL and are never matched by a session filter (fail closed); owners still list their own old records.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS session_account_revocations (
  session_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (session_id, persona_id)
)""")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE session_account_revocations ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE prototype_records ADD COLUMN IF NOT EXISTS session_key TEXT")
    else:  # SQLite has no ADD COLUMN IF NOT EXISTS; the app may already have added it at startup
        cols = {r[1] for r in bind.exec_driver_sql("PRAGMA table_info(prototype_records)").fetchall()}
        if "session_key" not in cols:
            op.execute("ALTER TABLE prototype_records ADD COLUMN session_key TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_records_session_key ON prototype_records(session_key, kind, seq)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_records_session_key")
    op.execute("ALTER TABLE prototype_records DROP COLUMN session_key")  # SQLite >= 3.35 and Postgres
    op.execute("DROP TABLE IF EXISTS session_account_revocations")
