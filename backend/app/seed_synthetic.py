"""Load the SYNTHETIC sample workbook into the reference tables (communities, residents, interactions).

    uv run alembic upgrade head                     # create / update the tables first
    uv run python -m app.seed_synthetic             # uses DATA_PATH and DATABASE_URL (else the local SQLite DB_PATH)
    uv run python -m app.seed_synthetic --dry-run   # parse and count only

Refuses any workbook whose README sheet does not say every value is synthetic: real McKinley data must never be
loaded into the prototype database. Replaces previous reference rows in one transaction. Never prints the database
URL or any row content.
"""

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.context import RESIDENT_COLUMNS, WorkbookError, load_workbook, workbook_readme
from app.db import Store

SYNTHETIC_MARKER = re.compile(r"EVERY VALUE IS SYNTHETIC", re.I)


def rows_from_workbook(path: Path) -> tuple[list[tuple[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    wb = load_workbook(path)
    residents = [{c: r.row.get(c, "") for c in RESIDENT_COLUMNS} for r in wb.residents.values()]
    communities = sorted({(r["community"], r.get("region", "")) for r in residents if r["community"]})
    interactions = []
    for r in wb.residents.values():
        for i in r.interactions:
            interactions.append({
                "interaction_id": i.interaction_id, "resident_id": i.resident_id,
                "timestamp": i.timestamp.strftime("%Y-%m-%d %H:%M") if i.timestamp else "",
                "channel": i.channel, "category": i.category, "subject": i.subject, "full_text": i.full_text,
                "status": i.status, "resolved_date": i.resolved_date.isoformat() if i.resolved_date else "",
                "follow_up_needed": i.follow_up_needed,
            })
    # one region per community: keep the first seen
    seen: dict[str, str] = {}
    for name, region in communities:
        seen.setdefault(name, region)
    return list(seen.items()), residents, interactions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workbook", type=Path, default=None, help="default: DATA_PATH")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    s = get_settings()
    path = a.workbook or s.resolve(s.data_path)
    try:
        readme = workbook_readme(path)
    except Exception as e:
        print(f"Cannot open the workbook ({type(e).__name__}).")
        return 2
    if not SYNTHETIC_MARKER.search(readme):
        print("REFUSED: the workbook's README sheet does not state that every value is synthetic. Only the synthetic "
              "sample workbook may be loaded into the prototype database.")
        return 3
    try:
        communities, residents, interactions = rows_from_workbook(path)
    except WorkbookError as e:
        print(f"Workbook error: {e}")
        return 2
    print(f"Synthetic workbook OK: {len(communities)} communities, {len(residents)} residents, "
          f"{len(interactions)} interactions.")
    if a.dry_run:
        return 0
    db_url = s.database_url.get_secret_value().strip() if s.database_url else ""
    try:
        store = Store(s.resolve(s.db_path), database_url=db_url or None)
        ready = store.has_reference_tables()
    except Exception as e:
        safe = str(e) if isinstance(e, ConnectionError | ValueError) else ""  # our scrubbed messages only
        print(f"Cannot use the database ({type(e).__name__}) {safe}")
        return 4
    if not ready:
        print("The reference tables do not exist yet. Run `uv run alembic upgrade head` first.")
        return 4
    try:
        store.replace_reference(communities, residents, interactions, {
            "source": path.name, "synthetic": "true", "loaded_at": datetime.now(UTC).isoformat(timespec="seconds")})
    except Exception as e:  # database messages can quote row content: report the type only
        print(f"Load failed ({type(e).__name__}); nothing was changed (one transaction).")
        return 5
    print(f"Loaded into the {store.dialect} database (previous reference rows replaced).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
