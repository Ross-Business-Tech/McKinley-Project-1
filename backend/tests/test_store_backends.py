"""The Store behaves the same on SQLite and on Postgres (for example Supabase).

SQLite always runs. Postgres runs only when TEST_DATABASE_URL points at a throwaway database, because the tests empty
its tables:  TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test uv run pytest tests/test_store_backends.py
"""


import pytest

from app.db import _TABLES, Store, session_hash
from tests.conftest import throwaway_pg_url

PG_URL = throwaway_pg_url()


NEEDS_PG = pytest.mark.skipif(not PG_URL, reason="no TEST_DATABASE_URL")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=NEEDS_PG)])
def store(request, tmp_path):
    if request.param == "sqlite":
        yield Store(tmp_path / "t.sqlite3")
        return
    s = Store(database_url=PG_URL)
    s._q(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
    yield s
    s._q(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")


def test_chat_history_round_trip(store):
    store.append_turns("s1", "aware|x", "p1", "my sink leaks", "Sorry to hear that.")
    store.append_turns("s1", "aware|x", "p1", "kitchen", "Thanks.")
    hist = store.history("s1", "aware|x", "p1")
    assert [m["role"] for m in hist] == ["user", "assistant", "user", "assistant"]
    assert store.user_messages("s1", "p1") == ["my sink leaks", "kitchen"]
    assert store.history("other", "aware|x", "p1") == []


def test_staff_conversation_views_use_hashes(store):
    store.append_turns("s1", "aware|x", "p1", "hello", "hi")
    store.log_gate("s1", "aware|x", "p1", {"workflow": "human_handoff", "risk_flags": []})
    convs = store.conversations()
    assert len(convs) == 1 and convs[0]["messages"] == 1
    assert convs[0]["session_hash"] == session_hash("s1") and "asked_for_person" in convs[0]["needs_action"]
    turns = store.conversation(session_hash("s1"))
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert store.conversation("nope") == []


def test_gate_log(store):
    store.log_gate("s1", "aware|x", "p1", {"urgency": "normal"})
    assert store.last_gate("s1", "aware|x", "p1") == {"urgency": "normal"}
    log = store.gate_log()
    assert log[0]["session"] == session_hash("s1") and log[0]["urgency"] == "normal"
    assert store.last_gate("s2", "aware|x", "p1") is None


def test_drafts(store):
    assert store.get_draft("s1", "p1") is None
    store.save_draft("s1", "p1", "maintenance", {"issue": "leak"})
    store.save_draft("s1", "p1", "maintenance", {"issue": "leak", "room": "kitchen"})  # upsert
    assert store.get_draft("s1", "p1") == {"kind": "maintenance", "issue": "leak", "room": "kitchen"}
    store.mark_stale("s1", "p1", "maintenance", {"issue": "leak", "declined": True})
    assert store.get_draft("s1", "p1") is None
    assert store.get_draft("s1", "p1", include_declined=True)["declined"] is True
    assert store.take_draft("s1", "p1", "tour") is None  # wrong kind
    assert store.take_draft("s1", "p1", "maintenance")["issue"] == "leak"
    assert store.take_draft("s1", "p1", "maintenance") is None  # taken only once
    store.save_draft("s1", "p1", "tour", {"a": 1})
    store.clear_draft("s1", "p1")
    assert store.get_draft("s1", "p1") is None


def test_records_and_once_keys(store):
    a = store.add_record("DEMO-WO", "work_order", "s1", "p1", {"issue": "leak"})
    b = store.add_record("DEMO-TOUR", "tour", "s1", None, {"day": "Sat"})
    assert a["id"] == "DEMO-WO-1001" and b["id"] == "DEMO-TOUR-1002"
    first = store.add_record_once("DEMO-TASK", "task", "s1", None, {"note": "x"}, "k1")
    again = store.add_record_once("DEMO-TASK", "task", "s1", None, {"note": "x"}, "k1")
    assert again["id"] == first["id"] and again["_existing"] is True  # NULL persona matched, not duplicated
    other = store.add_record_once("DEMO-TASK", "task", "s1", "p1", {"note": "x"}, "k1")
    assert other["id"] != first["id"]
    assert [r["id"] for r in store.records(kind="work_order")] == ["DEMO-WO-1001"]
    assert len(store.records(persona_id="p1")) == 2
    assert len(store.records(session_id="s1")) == 4
    assert len(store.records(session_id="nobody")) == 0
    assert store.records(limit=1)[0]["id"] == other["id"]  # newest first


def test_eval_runs_and_results(store):
    assert store.latest_run_id() is None
    run = store.create_run(["mock:m"], "aware-v1", "base-v1", 0.2)
    run2 = store.create_run(["mock:m"], "aware-v2", "base-v2", None)
    assert run2 == run + 1 and store.latest_run_id() == run2
    assert store.runs()[0]["targets"] == ["mock:m"] and store.runs()[0]["id"] == run2
    rid = store.add_result(run, "case1", "aware", {"created_at": "2026-01-01", "score": 3})
    assert store.results(run)[0]["score"] == 3
    store.update_result_data(rid, {"created_at": "2026-01-01", "score": 4})
    store.review(rid, "GOOD", "ok")
    got = store.get_result(rid)
    assert got["score"] == 4 and got["human_verdict"] == "GOOD" and got["human_notes"] == "ok"
    assert store.get_result(rid + 99) is None


def test_literal_percent_and_odd_text_survive(store):
    text = "100% sure it's \"leaking\"; DROP TABLE chat_turns; --"
    store.append_turns("s1", "aware|x", "p1", text, "ok")
    assert store.history("s1", "aware|x", "p1")[0]["content"] == text
