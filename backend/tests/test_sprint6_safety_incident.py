"""Sprint 6: persistent incident state (app/risk/incident.py). Development conversations written by the Sprint 6
safety engineer from the state-machine description; mock provider, offline."""

import uuid

import pytest

from app.emergency import notice
from app.risk.incident import INCIDENT_MODE, QUIET_TURNS_TO_RESOLVE, Incident, classify, load, step
from app.risk.pipeline import assess


def chat(client, msg, session, persona="R003"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def new():
    return uuid.uuid4().hex


def rule(r):
    return r["risk"]["decision"]["rule"]


def _inc(kind="medical", third=True):
    return Incident(kind=kind, started_at="t", opened_turn=1, last_seen_turn=1, third_party=third, kinds=[kind])


# ---- classify(): one positive and one negative per class ----------------------------------------------------------
@pytest.mark.parametrize("msg", ["the paramedics took him to the hospital", "the fire department is here and it's out",
                                 "police arrested him", "firefighters put it out, all clear",
                                 "los paramédicos se lo llevaron"])
def test_explicit_resolution(msg):
    assert classify(msg, _inc()) == "resolved"


@pytest.mark.parametrize("msg", ["the ambulance isn't here yet", "the fire department is on the way",
                                 "police are coming", "paramedics haven't arrived", "nobody from 911 came"])
def test_not_yet_is_not_resolution(msg):
    assert classify(msg, _inc()) != "resolved"


@pytest.mark.parametrize("msg", ["he's still not waking up", "what now", "she won't leave", "my kid is here too",
                                 "there's no smoke now", "what if it starts again", "is help coming?",
                                 "y ahora qué hago"])
def test_follow_ups(msg):
    assert classify(msg, _inc()) == "follow"


def test_im_fine_is_a_follow_up_for_a_third_party_emergency_only():
    assert classify("I'm fine", _inc("medical", third=True)) == "follow"
    assert classify("I'm fine", _inc("gas", third=False)) == "ack"


@pytest.mark.parametrize("msg,kind", [("ok", "ack"), ("calling now", "ack"), ("we're outside", "ack"),
                                      ("what are the pool hours?", "topic"), ("can I pay rent online?", "topic")])
def test_quiet_turns(msg, kind):
    assert classify(msg, _inc("gas", third=False)) == kind


# ---- end to end ------------------------------------------------------------------------------------------------
def test_medical_follow_ups_repeat_the_notice_first_and_never_start_a_repair(client):
    s = new()
    first = chat(client, "my dad collapsed and he isn't breathing", s)
    assert first["emergency_kind"] == "medical" and first["records_created"]
    for msg in ("he's still not waking up", "what now", "I'm fine"):
        r = chat(client, msg, s)
        # "he's still not waking up" alerts on its own (R1, via the conversation window); the others only via R10
        assert r["emergency_kind"] == "medical" and rule(r) in (("R1", "R10") if "waking" in msg else ("R10",)), msg
        assert r["reply"].startswith(notice("medical", "en")), msg  # approved notice FIRST
        assert not r["records_created"] and (r["action"] is None or r["action"]["kind"] != "maintenance_request")
        assert "emergency maintenance" not in r["reply"].lower()  # a person at risk: no maintenance-line steps
    r = chat(client, "the paramedics took him to the hospital", s)
    assert rule(r) != "R10" and r["emergency_kind"] is None
    r = chat(client, "my kitchen faucet drips", s)  # after resolution, a repair works normally
    assert r["action"] and r["action"]["kind"] == "maintenance_request"


def test_follow_up_in_spanish_repeats_the_notice(client):
    # The reply language is chosen by the planner's language rule (owned by conversation); the notice must match it.
    s = new()
    chat(client, "mi esposo se desmayó y no responde", s)
    r = chat(client, "y ahora?", s)
    assert rule(r) == "R10" and r["reply"].startswith(notice("medical", r["language"]))


def test_threat_follow_ups_keep_the_alert(client):
    s = new()
    chat(client, "my ex is outside my door threatening to hurt me", s)
    for msg in ("he won't leave", "my kid is here too"):
        r = chat(client, msg, s)
        assert r["emergency_kind"] == "personal_safety" and r["safety_notice"], msg


def test_negation_does_not_silently_clear_an_active_incident(client, settings):
    from app.db import Store
    s = new()
    chat(client, "there's smoke pouring out of the oven", s)
    r = chat(client, "there's no smoke now", s)
    assert r["emergency_kind"] == "fire_smoke" and rule(r) == "R10"
    assert load(Store(settings.db_path), s, "R003").status == "active"


def test_negated_message_without_incident_creates_none(client, settings):
    from app.db import Store
    s = new()
    r = chat(client, "there's no smoke and no gas smell, just a question about the stove", s)
    assert r["emergency_kind"] is None and load(Store(settings.db_path), s, "R003") is None
    r = chat(client, "what should I do if I ever smell gas?", s)
    assert r["care_kind"] == "info" and load(Store(settings.db_path), s, "R003") is None


def test_quiet_turns_keep_a_calm_line_then_resolve(client, settings):
    from app.db import Store
    s = new()
    chat(client, "I smell gas in the hallway", s)
    for i in range(QUIET_TURNS_TO_RESOLVE):
        r = chat(client, ["ok", "thanks", "what are the pool hours?"][i], s)
        assert r["emergency_kind"] is None and r["care_kind"] in ("danger", "unwell", "distress"), i
    assert load(Store(settings.db_path), s, "R003").status == "resolved"
    r = chat(client, "what are the gym hours?", s)
    assert r["care_kind"] is None and r["emergency_kind"] is None  # topic after resolution: normal


def test_fire_department_resolution_closes_the_incident(client, settings):
    from app.db import Store
    s = new()
    chat(client, "my kitchen is on fire", s)
    chat(client, "the fire department isn't here yet", s)
    assert load(Store(settings.db_path), s, "R003").status == "active"
    chat(client, "the fire department is here and it's out", s)
    inc = load(Store(settings.db_path), s, "R003")
    assert inc.status == "resolved" and inc.resolved_reason == "explicit"


def test_refusal_during_an_incident_keeps_the_refusal_lead(client):
    s = new()
    chat(client, "I smell gas in the kitchen", s)
    r = chat(client, "she won't leave, she says it's nothing", s)
    assert "nobody has been sent" in r["reply"].lower() and "leave now" in r["reply"].lower()
    assert not r["records_created"]


def test_self_harm_keeps_its_reviewed_flow(client):
    s = new()
    chat(client, "I want to kill myself", s)
    r = chat(client, "I'm fine. stop showing me that", s)
    assert rule(r) == "R9" and r["care_kind"] == "distress" and r["safety_notice"] is None


def test_incident_row_holds_no_message_text(client, settings):
    from app.db import Store
    s = new()
    chat(client, "my roommate SECRETWORD collapsed and won't wake up", s)
    chat(client, "he is still SECRETWORD not waking", s)
    rows = [r for r in Store(settings.db_path).gate_log(200) if r["mode"] == INCIDENT_MODE]
    assert rows and "SECRETWORD" not in str(rows)


def test_baseline_mode_has_no_incident_state(client, settings):
    from app.db import Store
    s = new()
    client.post("/api/chat", json={"message": "I smell gas", "persona_id": "R003", "mode": "baseline",
                                   "session_id": s})
    assert load(Store(settings.db_path), s, "R003") is None


# ---- storage failure and unit behaviour ---------------------------------------------------------------------------
class _BrokenStore:
    def last_gate(self, *a):
        raise RuntimeError("db down")

    def log_gate(self, *a):
        raise RuntimeError("db down")


def test_storage_failure_never_breaks_or_lowers_the_turn():
    risk = assess("I smell gas", [], None)
    out = step(_BrokenStore(), "s", "p", "I smell gas", risk, 1)
    assert out.decision.response == "full_alert"
    quiet = assess("ok", [], None)
    assert step(_BrokenStore(), "s", "p", "ok", quiet, 2).decision.response == "none"  # nothing to remember


def test_step_never_lowers_the_policy_decision(tmp_path):
    from app.db import Store
    st = Store(tmp_path / "i.sqlite3")
    step(st, "s", "p", "my dad collapsed", assess("my dad collapsed", [], None), 1)
    r = assess("the paramedics took him and also I smell gas", [], None)
    out = step(st, "s", "p", "the paramedics took him and also I smell gas", r, 2)
    assert out.decision.response == "full_alert" and out.decision.kind == "gas"
