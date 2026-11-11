"""Manage the sign-in invite list (the `user_profiles` table). Run from backend/ with DATABASE_URL set to the
Supabase connection string (or without it, for the local SQLite file):

    uv run python -m app.manage_users add --email name@example.com --role resident --persona R001
    uv run python -m app.manage_users add --email name@example.com --role staff
    uv run python -m app.manage_users list
    uv run python -m app.manage_users disable --email name@example.com      (enable / remove work the same way)

Real email addresses live ONLY in this table. Never put one in the repository, a pull request or a chat. A resident
is linked to ONE synthetic resident id (the made-up people in the seed data), never to a real person's record.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

from app.config import Settings, get_settings
from app.db import Store
from app.state import load_residents

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _open_store(settings: Settings) -> Store:
    url = settings.database_url.get_secret_value().strip() if settings.database_url else ""
    return Store(settings.resolve(settings.db_path), database_url=url or None)


def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if not _EMAIL.fullmatch(email):
        raise SystemExit(f"'{raw}' does not look like an email address")
    return email


def main(argv: Sequence[str] | None = None, settings: Settings | None = None, store: Store | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.manage_users", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="invite someone (or change an existing invite)")
    add.add_argument("--email", required=True)
    add.add_argument("--role", required=True, choices=["resident", "staff"])
    add.add_argument("--persona", help="the SYNTHETIC resident id for a resident, e.g. R001")
    add.add_argument("--no-check", action="store_true", help="do not check that the resident id exists in the data")
    sub.add_parser("list", help="show everyone on the list")
    for name in ("remove", "disable", "enable"):
        sub.add_parser(name).add_argument("--email", required=True)
    args = ap.parse_args(argv)

    settings = settings or get_settings()
    store = store or _open_store(settings)

    if args.cmd == "list":
        rows = store.profiles()
        if not rows:
            print("The invite list is empty.")
        for r in rows:
            who = r["persona_id"] or "-"
            seen = "has signed in" if r["user_id"] else "not signed in yet"
            print(f"{r['email']:40} {r['role']:9} {who:8} {'DISABLED' if r['disabled'] else 'active':9} {seen}")
        return 0

    email = _clean_email(args.email)
    if args.cmd == "add":
        persona = (args.persona or "").strip() or None
        if args.role == "staff" and persona:
            print("A staff invite is not linked to a resident id; leave --persona out.", file=sys.stderr)
            return 2
        if args.role == "resident":
            if not persona:
                print("A resident invite needs --persona (a synthetic resident id such as R001).", file=sys.stderr)
                return 2
            if not args.no_check:
                wb, err = load_residents(settings, store)
                if wb is None:
                    print(f"Could not check the resident id: {err}\nFix the data, or use --no-check.", file=sys.stderr)
                    return 2
                if persona not in wb.residents:
                    known = ", ".join(sorted(wb.residents)[:12])
                    print(f"'{persona}' is not a resident in the synthetic data. Known ids start: {known}",
                          file=sys.stderr)
                    return 2
        store.upsert_profile(email, args.role, persona)
        print(f"Invited {email} as {args.role}" + (f" linked to {persona}" if persona else "") + ".")
        return 0
    if args.cmd == "remove":
        ok = store.remove_profile(email)
    else:
        ok = store.set_profile_disabled(email, args.cmd == "disable")
    print(f"{args.cmd}: {email}" if ok else f"{email} is not on the invite list.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
