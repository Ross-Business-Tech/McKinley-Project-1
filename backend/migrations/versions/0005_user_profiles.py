"""Invite list for Supabase sign-in (see docs/security/SUPABASE_AUTH.md and app/identity.py).

user_profiles maps an invited email address to a role (resident or staff) and, for a resident, to ONE synthetic
resident id. Real email addresses are stored only here, never in the repository. Nobody who is not on this list is
treated as signed in, even with a valid Supabase account. The app also creates this table at startup (app/db.py
AUTH_SCHEMA); this migration keeps Alembic-managed databases in step. Row-level security is on with no policies
(Supabase's public Data API reads nothing).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
  email TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('resident','staff')),
  persona_id TEXT,
  user_id TEXT,
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
)""")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_profiles")
