"""Synthetic reference data (communities, residents, interactions) and read-only views over prototype records.

Residents and interactions are loaded only from the synthetic sample workbook by `app.seed_synthetic` (it refuses a
workbook without the "EVERY VALUE IS SYNTHETIC" marker). Every row carries synthetic=true. The backend reads them
when the workbook file is not present (a hosted backend has no git-ignored XLSX). `residents.data` holds the full
normalized source row as JSON; the context builder still forwards only allowlisted fields to any model.

Views maintenance_requests / tour_requests / handoff_records give Supabase's table editor readable columns without
duplicating the prototype store. In Postgres they use security_invoker, so they never bypass row-level security.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ("dataset_meta", "communities", "residents", "interactions")
VIEWS = {
    "maintenance_requests": "maintenance_request",
    "tour_requests": "tour_request",
    "handoff_records": "staff_handoff",
}


def _view_sql(name: str, kind: str, postgres: bool) -> str:
    def j(key: str) -> str:
        return f"(data::jsonb ->> '{key}')" if postgres else f"json_extract(data, '$.{key}')"

    opts = " WITH (security_invoker = true)" if postgres else ""
    return (f"CREATE VIEW {name}{opts} AS SELECT id, persona_id, session_hash, created_at, "
            f"{j('status')} AS status, {j('priority')} AS priority, {j('team')} AS team, "
            f"{j('summary')} AS summary FROM prototype_records WHERE kind = '{kind}'")


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.execute("""CREATE TABLE IF NOT EXISTS dataset_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
)""")
    op.execute("""CREATE TABLE IF NOT EXISTS communities (
  name TEXT PRIMARY KEY,
  region TEXT,
  synthetic BOOLEAN NOT NULL DEFAULT TRUE
)""")
    op.execute("""CREATE TABLE IF NOT EXISTS residents (
  resident_id TEXT PRIMARY KEY,
  community TEXT REFERENCES communities(name),
  first_name TEXT,
  preferred_language TEXT,
  data TEXT NOT NULL,
  synthetic BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (synthetic)
)""")
    op.execute("""CREATE TABLE IF NOT EXISTS interactions (
  interaction_id TEXT PRIMARY KEY,
  resident_id TEXT NOT NULL REFERENCES residents(resident_id) ON DELETE CASCADE,
  "timestamp" TEXT,
  channel TEXT,
  category TEXT,
  subject TEXT,
  full_text TEXT,
  status TEXT,
  resolved_date TEXT,
  follow_up_needed BOOLEAN NOT NULL DEFAULT FALSE,
  synthetic BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (synthetic)
)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_interactions_resident ON interactions(resident_id)")
    for name, kind in VIEWS.items():
        op.execute(f"DROP VIEW IF EXISTS {name}")
        op.execute(_view_sql(name, kind, postgres))
    if postgres:
        for t in TABLES:
            op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for name in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {name}")
    for t in ("interactions", "residents", "communities", "dataset_meta"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
