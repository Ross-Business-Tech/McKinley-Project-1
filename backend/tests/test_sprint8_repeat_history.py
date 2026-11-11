"""Sprint 8 Workstream C: repeat-issue history from AUTHORIZED data only (app/maintenance_history.py + the planner).

Fixture R001 (tests/conftest.py) has maintenance history I002 "AC not cooling" (2026-06-08), I003 "AC out again"
(2026-08-19), I008 "AC rattling" (2026-10-27, open) and an amenity item "Dog park gate". R003 has no maintenance
history. Every window is computed against a fixed "now" (2026-11-10).
"""

import re
from dataclasses import dataclass
from datetime import datetime

import pytest

from app import maintenance_history as mh
from app.state import get_state

NOW = datetime(2026, 11, 10, 12, 0)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(mh, "current_time", lambda: NOW)


def chat(client, message, persona="R001", session="s"):
    r = client.post("/api/chat", json={"message": message, "persona_id": persona or None, "mode": "aware",
                                       "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client, persona="R001", session="s"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": "maintenance_request"}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def stored(persona=None):
    return [r for r in get_state().store.records(kind="maintenance_request", limit=50)
            if persona is None or r.get("persona_id") == persona]


@dataclass
class _I:
    interaction_id: str
    subject: str
    timestamp: datetime | None
    category: str = "maintenance"
    status: str = "closed"


@dataclass
class _R:
    interactions: list


def _rec(rid, issue, created, persona="R001", status="submitted_for_review"):
    return {"id": rid, "kind": "maintenance_request", "persona_id": persona, "created_at": created, "status": status,
            "title": issue, "fields": [{"key": "issue", "value": issue}]}


# ---- grouping rule (shared object lexicon), EN + ES, positives and near misses ---------------------------------

RELATED = [
    ("My AC stopped cooling again", "AC not cooling"), ("the air conditioner is blowing warm air", "AC out again"),
    ("el aire acondicionado no enfría", "AC rattling"), ("no hot water this morning", "Water heater leaking"),
    ("water leaking under my sink", "Leak under the sink"), ("the dishwasher won't drain", "Dishwasher leaking"),
    ("el refrigerador no enfría otra vez", "Fridge not cold"), ("toilet keeps running", "Toilet running all night"),
    ("bedroom AC is loud", "Living room AC not cooling"),  # a whole-home system is one system in any room
    ("la lavadora hace ruido", "Washer shaking"),
]
UNRELATED = [
    ("my toilet keeps running", "AC rattling"), ("kitchen sink drain clogged", "Tub drain slow"),
    ("bathroom sink leaking", "Kitchen sink leak"), ("ceiling fan wobbling", "Ceiling leak"),
    ("front door lock broken", "Door won't close"), ("it's not working", "AC not cooling"),
    ("la estufa no prende", "Fridge not cold"), ("something is wrong", "Dog park gate"),
]


@pytest.mark.parametrize("a,b", RELATED)
def test_related_requests_share_the_same_thing(a, b):
    assert mh.related(a, b)


@pytest.mark.parametrize("a,b", UNRELATED)
def test_unrelated_requests_are_never_grouped(a, b):
    assert not mh.related(a, b)


# ---- counts, windows, inclusion ----------------------------------------------------------------------------------

def test_zero_related_records_means_no_history():
    h = mh.related_history("the toilet keeps running", resident=_R([_I("I1", "AC not cooling", NOW)]),
                           persona_id="R001")
    assert h.count == 0 and h.window() == "" and mh.summary_line(h) == "" and h.references == []


def test_one_related_record_uses_singular_wording():
    h = mh.related_history("AC not cooling", resident=_R([_I("I1", "AC out", datetime(2026, 10, 25))]),
                           persona_id="R001")
    assert h.count == 1 and h.window(singular=True) == "in the last 30 days"
    assert mh.summary_line(h) == "1 earlier related request in the last 30 days (I1)"
    assert h.window("es", singular=True) == "de los últimos 30 días"


def test_multiple_related_records_from_both_sources_oldest_first():
    res = _R([_I("I3", "AC rattling", datetime(2026, 10, 27)), _I("I2", "AC not cooling", datetime(2026, 10, 20)),
              _I("I9", "Dog park gate", datetime(2026, 10, 1), category="amenity"),
              _I("I7", "Toilet running", datetime(2026, 10, 2))])
    recs = [_rec("DEMO-WO-1005", "AC blowing warm air", "2026-11-01T09:00:00+00:00")]
    h = mh.related_history("my AC is out again", resident=res, records=recs, persona_id="R001")
    assert h.count == 3 and h.references == ["I2", "I3", "DEMO-WO-1005"]
    assert h.window() == "over the last 30 days" and h.earliest.isoformat() == "2026-10-20"
    assert h.latest.isoformat() == "2026-11-01"
    rec = h.to_record()
    assert rec["count"] == 3 and rec["window"] == "over the last 30 days" and rec["includes_current_request"] is False


@pytest.mark.parametrize("earliest,en,es", [
    (datetime(2026, 11, 9), "over the last 7 days", "en los últimos 7 días"),
    (datetime(2026, 11, 3), "over the last 7 days", "en los últimos 7 días"),
    (datetime(2026, 10, 15), "over the last 30 days", "en los últimos 30 días"),
    (datetime(2026, 10, 11), "over the last 30 days", "en los últimos 30 días"),
    (datetime(2026, 10, 10), "since October", "desde octubre"),
    (datetime(2026, 3, 2), "since March", "desde marzo"),
    (datetime(2025, 3, 2), "since March 2025", "desde marzo de 2025"),
])
def test_window_is_computed_from_real_timestamps(earliest, en, es):
    res = _R([_I("I1", "AC out", earliest), _I("I2", "AC loud", datetime(2026, 11, 9))])
    h = mh.related_history("AC not cooling", resident=res, persona_id="R001")
    assert h.window() == en and h.window("es") == es


def test_now_is_injectable_and_undated_items_count_without_a_window():
    res = _R([_I("I1", "AC out", datetime(2026, 1, 5))])
    assert mh.related_history("AC broken", resident=res, now=datetime(2026, 1, 20)).window() == "over the last 30 days"
    h = mh.related_history("AC broken", resident=_R([_I("I1", "AC out", None), _I("I2", "AC loud", None)]))
    assert h.count == 2 and h.window() == ""


def test_current_request_excluded_and_no_duplicates():
    recs = [_rec("DEMO-WO-1001", "AC not cooling", "2026-11-01T09:00:00"),
            _rec("DEMO-WO-1001", "AC not cooling", "2026-11-01T09:00:00"),  # the same record twice: counted once
            _rec("DEMO-WO-1002", "AC not cooling", "2026-11-10T11:00:00")]
    h = mh.related_history("AC not cooling", records=recs, persona_id="R001", exclude={"DEMO-WO-1002"})
    assert h.count == 1 and h.references == ["DEMO-WO-1001"]


def test_records_of_another_persona_or_a_guest_are_never_counted():
    recs = [_rec("DEMO-WO-1001", "AC not cooling", "2026-11-01T09:00:00", persona="R003"),
            _rec("DEMO-WO-1002", "AC not cooling", "2026-11-01T09:00:00", persona=None),
            _rec("DEMO-WO-1003", "AC out", "2026-11-02T09:00:00", status="cancelled")]
    assert mh.related_history("AC not cooling", records=recs, persona_id="R001").count == 0
    assert mh.related_history("AC not cooling", records=recs, persona_id=None).count == 0


# ---- the planner and the saved request -------------------------------------------------------------------------

_DISHONEST = re.compile(r"notif|alerted|dispatch|will call|call you back|callback|refund|credit|\brent\b|concession|"
                        r"discount|scheduled|on (?:the|their) way|by (?:today|tomorrow|monday|tuesday|wednesday|"
                        r"thursday|friday)|within \d|\bavis[oó]|reembolso|descuento|\brenta\b", re.I)


def test_repeat_reply_names_the_real_count_and_window_and_record_carries_history(client):
    r = chat(client, "My AC stopped cooling again. This has happened multiple times.")
    assert "3 related maintenance requests since June" in r["reply"]
    assert "community manager to review" in r["reply"] and not _DISHONEST.search(r["reply"])
    f = fields(r)
    assert f["priority_note"] == "Repeat issue: manager review"
    assert f["related_history"] == "3 earlier related requests since June (I002, I003, I008)"
    chat(client, "Yes, you can enter")
    res = confirm(client)
    # lead: wording reconciled with the demo CONFIRM text ("no McKinley staff will see it"): marked for review, not seen
    assert res["ok"] and "marked for community manager review" in res["message"] and "nobody sees it yet" in \
        res["message"]
    recs = stored("R001")
    assert len(recs) == 1
    rec = recs[0]
    assert rec["repeat_history"] == {"count": 3, "window": "since June", "earliest": "2026-06-08",
                                     "latest": "2026-10-27", "references": ["I002", "I003", "I008"],
                                     "includes_current_request": False,
                                     "source": "signed-in resident's own history and prototype requests"}
    assert rec["manager_review"] is True and rec["review_queue"] == "community_manager" and rec["repeat"] is True
    assert confirm(client)["ok"] is False and len(stored("R001")) == 1  # no duplicate record


def test_unrelated_history_is_never_counted_or_claimed(client):
    r = chat(client, "the toilet in the hall bathroom keeps running")
    assert "related maintenance request" not in r["reply"] and "related_history" not in fields(r)
    r2 = chat(client, "the dog park gate is broken", session="g")  # an amenity contact is not a repair request
    assert "related maintenance request" not in r2["reply"]


def test_stated_repeat_with_no_related_history_makes_no_history_claim(client):
    r = chat(client, "the heat is out AGAIN", "R001", "h")
    assert "related maintenance request" not in r["reply"] and "repeat problem" in r["reply"]
    assert "related_history" not in fields(r) and "manager" in fields(r)["priority_note"].lower()


def test_one_own_earlier_request_gives_singular_wording(client):
    chat(client, "the dishwasher is leaking", "R003", "a")
    chat(client, "kitchen, yes you can enter", "R003", "a")
    assert confirm(client, "R003", "a")["ok"]
    r = chat(client, "the dishwasher is leaking again", "R003", "b")
    assert "I found 1 related maintenance request in the last 7 days" in r["reply"], r["reply"]
    assert "requests" not in r["reply"].split("community manager")[0].split("I found")[1]


def test_spanish_reply_names_count_and_window(client):
    r = chat(client, "el aire acondicionado no enfría otra vez", "R001", "es")
    assert "Encontré 3 solicitudes de mantenimiento relacionadas desde junio" in r["reply"]
    assert "gerente de la comunidad" in r["reply"] and not _DISHONEST.search(r["reply"])


def test_another_personas_records_and_history_are_never_counted(client):
    chat(client, "my AC stopped cooling", "R003", "x")  # R003 files nothing; R001 has AC history
    r = chat(client, "my AC stopped cooling again", "R003", "x")
    assert "related maintenance request" not in r["reply"] and "I002" not in str(r)
    # R001 files one AC request; R003 still sees nothing of it
    chat(client, "the fridge is not cold", "R001", "f")
    chat(client, "kitchen, yes you can enter", "R001", "f")
    assert confirm(client, "R001", "f")["ok"]
    r3 = chat(client, "my fridge is not cold again", "R003", "y")
    assert "related maintenance request" not in r3["reply"] and "DEMO-WO" not in r3["reply"]


def test_guest_gets_no_history(client):
    r = chat(client, "my AC stopped cooling again, third time", None, "guest")
    assert "related maintenance request" not in r["reply"] and "I002" not in str(r)


def test_non_holder_session_gets_no_history(client):
    chat(client, "I'm not the account holder, I'm using my mom's account", "R001", "nh")
    assert get_state().store.account_access_revoked("nh", "R001")
    r = chat(client, "my AC stopped cooling again, it keeps happening", "R001", "nh")
    assert "related maintenance request" not in r["reply"] and "I002" not in str(r) and "since June" not in str(r)


@pytest.mark.parametrize("key", ["repeat_history_many", "repeat_history_one", "repeat_history_lead",
                                 "repeat_history_ready", "repeat_history_saved"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_new_wording_is_honest(key, lang):
    from app.templates import T
    text = T[key][lang]
    assert not _DISHONEST.search(text), text
    if key in ("repeat_history_many", "repeat_history_one", "repeat_history_saved"):
        assert ("community manager" in text) if lang == "en" else ("gerente de la comunidad" in text)
