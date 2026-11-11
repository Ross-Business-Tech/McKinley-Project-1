# Supabase (Postgres) database

> Sign-in (Supabase Auth) is separate from the database: see [../security/SUPABASE_AUTH.md](../security/SUPABASE_AUTH.md).
> The invite list is the `user_profiles` table (migration 0005), managed with `uv run python -m app.manage_users`.

**Status: code and migrations ready. Tested on SQLite and on a throwaway local Postgres 16 (the shared Store checks,
migrations, invite list, row-level security, and an end-to-end browser journey); never run against a real Supabase
project** (no access).

## How the backend uses it
- `DATABASE_URL` set → the Store (`backend/app/db.py`) uses Postgres through psycopg; empty → the local SQLite file
  `DB_PATH` (development fallback). The backend is the only database client; the browser never talks to Supabase.
- Tables: chat turns, gate log (no message text), drafts, prototype records (repairs / tours / office notes),
  evaluation runs/results, and synthetic reference data (communities, residents, interactions). Views
  `maintenance_requests`, `tour_requests`, `handoff_records` give readable columns over prototype records.
- **Row-level security is ON for every table with no policies**, so Supabase's public Data API (anon /
  authenticated keys) can read nothing; views use `security_invoker`. The backend connects as the table owner.
  Do not add policies or expose these tables to the browser without real authentication first.

## Set up
1. Create a project (ask Ross IT / the project owner first). Keep the database password private.
2. **Connect → Session pooler** connection string (`postgresql://…`); URL-encode symbols in the password.
3. Check `SHOW server_version` is **15 or later** (the read-only views use `security_invoker`).
4. Run the migrations and the synthetic seed **from your machine** (the synthetic workbook is git-ignored, so it is
   not on Render). Put the connection string in `backend/.env` as `DATABASE_URL=` rather than typing it on the
   command line (shell history), then:
   ```bash
   cd backend
   uv run alembic upgrade head          # creates/updates tables (idempotent)
   uv run python -m app.seed_synthetic  # loads ONLY the synthetic workbook
   ```
   The seed refuses any workbook whose README does not say every value is synthetic, and replaces earlier
   reference rows in one transaction. **Never load real McKinley data** without written approval.
5. Put the same string in Render's `DATABASE_URL` secret. Render runs `alembic upgrade head` before every start.
   Residents are read at startup: **restart the Render service after seeding**.
6. Confirm the lock-down as the `postgres` user: every table has `relrowsecurity = true`, and
   `information_schema.role_table_grants` shows nothing for `anon` / `authenticated` (migration 0002 revokes their
   table and sequence privileges, including defaults for future tables, and locks `alembic_version`).

## Migrations
- `backend/migrations/versions/0001_baseline.py` — the six application tables (idempotent: adopts a database the
  app already created). `0002_reference_data.py` — reference tables + views.
- New schema change: `uv run alembic revision -m "describe it"`, write raw SQL for both dialects (see 0002), test with
  `uv run pytest tests/test_migrations.py`, and with Postgres:
  `TEST_DATABASE_URL=postgresql://…/throwaway uv run pytest tests/test_migrations.py tests/test_store_backends.py`
  (**throwaway database only** — those tests drop tables; they refuse a URL that equals `DATABASE_URL` or points at a
  Supabase host unless `ALLOW_DESTRUCTIVE_DB_TESTS=1` is set for a throwaway Supabase project).
- `alembic downgrade` deletes data; never run it on a shared database.

## Least privilege (before real users)
The synthetic-only rule is procedural (the seed checks the workbook's README marker; rows carry `synthetic=true`), not
a technical guarantee: never point the seed at another file. The prototype connects as the Supabase `postgres`
owner role because the app creates tables at startup. For anything
beyond a demo: create a dedicated role that owns no tables and has only `SELECT/INSERT/UPDATE/DELETE` on the app
tables, run migrations with a separate migration role, and turn off startup DDL.
