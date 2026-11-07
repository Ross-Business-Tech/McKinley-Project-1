"""SQLite store for demo session turns and eval outcomes (local, gitignored)."""

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_turns_session ON chat_turns(session_id, mode, persona_id, id);
-- Gate decisions: safe routing metadata only (no message text, no context values).
CREATE TABLE IF NOT EXISTS gate_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gate_session ON gate_decisions(session_id, mode, persona_id, id);
-- In-progress customer action drafts (one per session + persona). Values are redacted message slots only.
CREATE TABLE IF NOT EXISTS action_drafts (
  session_id TEXT NOT NULL,
  persona_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  data TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (session_id, persona_id)
);
-- PROTOTYPE system of record (stands in for Yardi work orders / CRM tour requests / staff queue). Nobody is
-- notified and nothing leaves this database.
CREATE TABLE IF NOT EXISTS prototype_records (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  session_hash TEXT NOT NULL,
  persona_id TEXT,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_persona ON prototype_records(persona_id, kind, seq);
CREATE TABLE IF NOT EXISTS eval_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  targets TEXT NOT NULL,
  aware_prompt_version TEXT NOT NULL,
  baseline_prompt_version TEXT NOT NULL,
  temperature REAL
);
CREATE TABLE IF NOT EXISTS eval_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES eval_runs(id),
  case_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  created_at TEXT NOT NULL,
  data TEXT NOT NULL,
  human_verdict TEXT,
  human_notes TEXT
);
"""

MAX_HISTORY_TURNS = 6


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    # ---- chat sessions ----
    def history(self, session_id: str, mode: str, persona_id: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM chat_turns WHERE session_id=? AND mode=? AND persona_id=? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, mode, persona_id, MAX_HISTORY_TURNS * 2),
            ).fetchall()
        msgs = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        while msgs and msgs[0]["role"] != "user":  # API requires history to start with a user turn
            msgs.pop(0)
        return msgs

    def append_turns(self, session_id: str, mode: str, persona_id: str, user: str, assistant: str) -> None:
        ts = now_iso()
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO chat_turns(session_id, mode, persona_id, role, content, created_at) "
                "VALUES (?,?,?,?,?,?)",
                [(session_id, mode, persona_id, "user", user, ts),
                 (session_id, mode, persona_id, "assistant", assistant, ts)],
            )

    def conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        """STAFF view: recent aware-mode conversations, keyed by a one-way session hash (never the session id)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id, persona_id, COUNT(*) AS n, MIN(created_at) AS started, MAX(created_at) AS last "
                "FROM chat_turns WHERE mode LIKE 'aware|%' GROUP BY session_id, persona_id "
                "ORDER BY MAX(id) DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"session_hash": hashlib.sha256(r["session_id"].encode()).hexdigest()[:10],
                 "persona_id": r["persona_id"] if r["persona_id"] not in ("", "none") else None,
                 "messages": r["n"] // 2, "started": r["started"], "last": r["last"]} for r in rows]

    def conversation(self, session_hash: str, limit: int = 200) -> list[dict[str, str]]:
        with self._lock:
            ids = [r["session_id"] for r in self._conn.execute(
                "SELECT DISTINCT session_id FROM chat_turns WHERE mode LIKE 'aware|%'").fetchall()]
            sid = next((i for i in ids if hashlib.sha256(i.encode()).hexdigest()[:10] == session_hash), None)
            if sid is None:
                return []
            rows = self._conn.execute(
                "SELECT role, content, persona_id, created_at FROM chat_turns "
                "WHERE session_id=? AND mode LIKE 'aware|%' "
                "ORDER BY id LIMIT ?", (sid, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---- gate decision log ----
    def log_gate(self, session_id: str, mode: str, persona_id: str, data: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO gate_decisions(session_id, mode, persona_id, created_at, data) VALUES (?,?,?,?,?)",
                (session_id, mode, persona_id, now_iso(), json.dumps(data)),
            )

    def last_gate(self, session_id: str, mode: str, persona_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM gate_decisions WHERE session_id=? AND mode=? AND persona_id=? "
                "ORDER BY id DESC LIMIT 1", (session_id, mode, persona_id),
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def gate_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM gate_decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        # Session ids are bearer-like (they key chat history), so only a short one-way hash is exposed.
        return [{"id": r["id"], "session": hashlib.sha256(r["session_id"].encode()).hexdigest()[:10],
                 "mode": r["mode"], "persona_id": r["persona_id"],
                 "created_at": r["created_at"], **json.loads(r["data"])} for r in rows]

    # ---- customer action drafts ----
    def get_draft(self, session_id: str, persona_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT kind, data FROM action_drafts WHERE session_id=? AND persona_id=?",
                                     (session_id, persona_id)).fetchone()
        return {"kind": row["kind"], **json.loads(row["data"])} if row else None

    def save_draft(self, session_id: str, persona_id: str, kind: str, data: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO action_drafts(session_id, persona_id, kind, data, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(session_id, persona_id) DO UPDATE SET kind=excluded.kind, data=excluded.data, "
                "updated_at=excluded.updated_at", (session_id, persona_id, kind, json.dumps(data), now_iso()))

    def take_draft(self, session_id: str, persona_id: str, kind: str) -> dict[str, Any] | None:
        """Atomically remove and return the draft, so concurrent confirms can write at most one record."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "DELETE FROM action_drafts WHERE session_id=? AND persona_id=? AND kind=? RETURNING kind, data",
                (session_id, persona_id, kind)).fetchone()
        return {"kind": row["kind"], **json.loads(row["data"])} if row else None

    def mark_stale(self, session_id: str, persona_id: str, kind: str, data: dict[str, Any]) -> None:
        """Update only; never re-inserts a draft that a concurrent confirm already took."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE action_drafts SET data=? WHERE session_id=? AND persona_id=? AND kind=?",
                               (json.dumps(data), session_id, persona_id, kind))

    def clear_draft(self, session_id: str, persona_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM action_drafts WHERE session_id=? AND persona_id=?",
                               (session_id, persona_id))

    # ---- prototype records ----
    def add_record(self, prefix: str, kind: str, session_id: str, persona_id: str | None,
                   data: dict[str, Any]) -> dict[str, Any]:
        """Write a prototype record and return it with its generated id. Raises on any DB error."""
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:10]
        created = now_iso()
        with self._lock, self._conn:
            seq = (self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM prototype_records").fetchone()["m"]
                   + 1)
            rid = f"{prefix}-{1000 + seq}"
            self._conn.execute(
                "INSERT INTO prototype_records(seq, id, kind, session_hash, persona_id, created_at, data) "
                "VALUES (?,?,?,?,?,?,?)", (seq, rid, kind, session_hash, persona_id, created, json.dumps(data)))
        return {**data, "id": rid, "kind": kind, "session_hash": session_hash, "persona_id": persona_id,
                "created_at": created}

    def add_record_once(self, prefix: str, kind: str, session_id: str, persona_id: str | None,
                        data: dict[str, Any], once_key: str) -> dict[str, Any]:
        """Insert unless a record with the same (session, persona, once_key) exists; check and insert under one lock."""
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:10]
        with self._lock, self._conn:
            for r in self._conn.execute("SELECT * FROM prototype_records WHERE session_hash=? AND kind=? AND "
                                        "persona_id IS ?", (session_hash, kind, persona_id)).fetchall():
                d = json.loads(r["data"])
                if d.get("once_key") == once_key:
                    return {**d, "id": r["id"], "kind": r["kind"], "session_hash": r["session_hash"],
                            "persona_id": r["persona_id"], "created_at": r["created_at"], "_existing": True}
            seq = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM prototype_records").fetchone()["m"] + 1
            rid, created = f"{prefix}-{1000 + seq}", now_iso()
            payload = {**data, "once_key": once_key}
            self._conn.execute(
                "INSERT INTO prototype_records(seq, id, kind, session_hash, persona_id, created_at, data) "
                "VALUES (?,?,?,?,?,?,?)", (seq, rid, kind, session_hash, persona_id, created, json.dumps(payload)))
        return {**payload, "id": rid, "kind": kind, "session_hash": session_hash, "persona_id": persona_id,
                "created_at": created}

    def records(self, persona_id: str | None = None, kind: str | None = None,
                session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM prototype_records WHERE 1=1", []
        if persona_id is not None:
            sql += " AND persona_id=?"
            args.append(persona_id)
        if kind is not None:
            sql += " AND kind=?"
            args.append(kind)
        if session_id is not None:
            sql += " AND session_hash=?"
            args.append(hashlib.sha256(session_id.encode()).hexdigest()[:10])
        sql += " ORDER BY seq DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [{**json.loads(r["data"]), "id": r["id"], "kind": r["kind"], "session_hash": r["session_hash"],
                 "persona_id": r["persona_id"], "created_at": r["created_at"]} for r in rows]

    # ---- evals ----
    def create_run(self, targets: list[str], aware_v: str, baseline_v: str, temperature: float | None) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO eval_runs(created_at, targets, aware_prompt_version, baseline_prompt_version, "
                "temperature) VALUES (?,?,?,?,?)",
                (now_iso(), json.dumps(targets), aware_v, baseline_v, temperature),
            )
            return int(cur.lastrowid)  # type: ignore[arg-type]

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM eval_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "targets": json.loads(r["targets"])} for r in rows]

    def add_result(self, run_id: int, case_id: str, mode: str, data: dict[str, Any]) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO eval_results(run_id, case_id, mode, created_at, data) VALUES (?,?,?,?,?)",
                (run_id, case_id, mode, data["created_at"], json.dumps(data)),
            )
            return int(cur.lastrowid)  # type: ignore[arg-type]

    def latest_run_id(self) -> int | None:
        with self._lock:
            row = self._conn.execute("SELECT MAX(id) AS id FROM eval_runs").fetchone()
        return row["id"] if row and row["id"] is not None else None

    def results(self, run_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM eval_results WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_result(self, result_id: int) -> dict[str, Any] | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM eval_results WHERE id=?", (result_id,)).fetchone()
        return self._row(r) if r else None

    def update_result_data(self, result_id: int, data: dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE eval_results SET data=? WHERE id=?", (json.dumps(data), result_id))

    def review(self, result_id: int, verdict: str | None, notes: str | None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE eval_results SET human_verdict=?, human_notes=? WHERE id=?", (verdict, notes, result_id)
            )

    @staticmethod
    def _row(r: sqlite3.Row) -> dict[str, Any]:
        data = json.loads(r["data"])
        data.update(id=r["id"], run_id=r["run_id"], case_id=r["case_id"], mode=r["mode"],
                    human_verdict=r["human_verdict"], human_notes=r["human_notes"])
        return data
