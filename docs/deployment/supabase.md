# Supabase (Postgres) database

**Status: code and migrations ready; never run against a real Supabase or Postgres** (no access, and no local
Postgres was available). SQLite paths are tested.

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
3. Run the migrations and the synthetic seed **from your machine** (or a Render shell):
   ```bash
   cd backend
   DATABASE_URL='postgresql://…' uv run alembic upgrade head          # creates/updates tables (idempotent)
   DATABASE_URL='postgresql://…' uv run python -m app.seed_synthetic  # loads ONLY the synthetic workbook
   ```
   The seed refuses any workbook whose README does not say every value is synthetic, and replaces earlier
   reference rows in one transaction. **Never load real McKinley data** without written approval.
4. Put the same string in Render's `DATABASE_URL` secret. Render runs `alembic upgrade head` before every start.

## Migrations
- `backend/migrations/versions/0001_baseline.py` — the six application tables (idempotent: adopts a database the
  app already created). `0002_reference_data.py` — reference tables + views.
- New schema change: `uv run alembic revision -m "describe it"`, write raw SQL for both dialects (see 0002), test with
  `uv run pytest tests/test_migrations.py`, and with Postgres:
  `TEST_DATABASE_URL=postgresql://…/throwaway uv run pytest tests/test_migrations.py tests/test_store_backends.py`
  (**throwaway database only** — those tests drop tables).
- `alembic downgrade` deletes data; never run it on a shared database.

## Least privilege (before real users)
The prototype connects as the Supabase `postgres` owner role because the app creates tables at startup. For anything
beyond a demo: create a dedicated role that owns no tables and has only `SELECT/INSERT/UPDATE/DELETE` on the app
tables, run migrations with a separate migration role, and turn off startup DDL.
