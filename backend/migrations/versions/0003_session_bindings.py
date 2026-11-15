"""Session -> principal binding (authorization; see app/auth.py and docs/security/AUTHORIZATION_BOUNDARIES.md).

A chat session id is bound to the (principal kind, persona key) that first used it. A later request that reuses the
session id as a different persona is refused, so it can never see the first persona's history, drafts or records.
The app also creates this table at startup (app/db.py AUTH_SCHEMA); this migration keeps Alembic-managed databases
in step. Row-level security is on with no policies (Supabase's public Data API reads nothing).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS session_bindings (
  session_id TEXT PRIMARY KEY,
  principal_kind TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  created_at TEXT NOT NULL
)""")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE session_bindings ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_bindings")
