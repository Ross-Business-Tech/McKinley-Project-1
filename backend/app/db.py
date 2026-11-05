"""SQLite store for demo session turns and eval outcomes (local, gitignored)."""

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
        return [{"id": r["id"], "session_id": r["session_id"], "mode": r["mode"], "persona_id": r["persona_id"],
                 "created_at": r["created_at"], **json.loads(r["data"])} for r in rows]

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
