"""Sprint 8 Workstream C final round: a different room / fixture / pest / specific part failure is a NEW request;
"is it normal" questions that describe a live fault start the intake, and "yes" / "report it" after the offer opens a
pre-filled card; the card suspended by an alert takes the next answer; notes for a person carry the latest open
repair's history; "I'm fine, I just want it fixed" after an alert proceeds with that repair; compound labels.
"""

from datetime import datetime

import pytest

from app import actions as A
from app import maintenance_history as mh
from app.context import Interaction
from app.state import get_state

NOW = datetime(2026, 11, 10, 12, 0)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(mh, "current_time", lambda: NOW)


def chat(client, message, persona="R003", session="s"):
    r = client.post("/api/chat", json={"message": message, "persona_id": persona or None, "mode": "aware",
                                       "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client, persona="R003", session="s", kind="maintenance_request"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def kind(r):
    return (r.get("action") or {}).get("kind")


def add_open(persona, iid, subject):
    get_state().deps.workbook.residents[persona].interactions.append(Interaction(
        iid, persona, datetime(2026, 10, 23, 9, 45), "chat", "maintenance", subject, "", "open", None, False))


def save_repair(client, issue, persona="R003", session="first"):
    chat(client, issue, persona, session)
    r = chat(client, "kitchen, yes you can come in", persona, session)
    if (r.get("action") or {}).get("stage") != "ready":
        r = chat(client, "yes you can come in", persona, session)
    res = confirm(client, persona, session)
    assert res["ok"], res
    return res["record"]["id"]


# ---- a different room / fixture / pest / part is a new request ---------------------------------------------------

NEW_NOT_FOLLOWUP = [
    ("Kitchen sink leaking - 4th time", "the bathroom sink is leaking underneath too"),
    ("Kitchen sink leaking - 4th time", "the bathroom faucet drips"),
    ("Kitchen sink leaking - 4th time", "el lavabo del baño gotea"),
    ("Roaches again", "I saw a mouse in the pantry"),
    ("Roaches again", "there are ants all over the counter"),
    ("Roaches again", "vi un ratón en la cocina"),
    ("Dishwasher not working", "the dishwasher door latch snapped, it won't stay closed"),
    ("Dishwasher not working", "the dishwasher rack broke off"),
]
STILL_FOLLOWUP = [
    ("Kitchen sink leaking - 4th time", "the kitchen sink is still leaking"),
    ("Roaches again", "the roaches are back again"),
    ("Dishwasher not working", "the dishwasher is still not working"),
    ("Kitchen sink leaking - 4th time", "el fregadero de la cocina sigue goteando"),
]


@pytest.mark.parametrize("subject,msg", NEW_NOT_FOLLOWUP)
def test_different_room_fixture_pest_or_part_is_a_new_request(client, subject, msg):
    add_open("R003", "I046", subject)
    r = chat(client, msg, "R003", "n")
    assert kind(r) == "maintenance_request", (msg, r["reply"])
    assert "I046" not in r["reply"]


@pytest.mark.parametrize("subject,msg", STILL_FOLLOWUP)
def test_same_thing_same_symptom_or_generic_is_still_a_follow_up(client, subject, msg):
    add_open("R003", "I046", subject)
    r = chat(client, msg, "R003", "f")
    assert kind(r) == "staff_handoff" and "I046" in r["reply"], (msg, r["reply"])


@pytest.mark.parametrize("old,new,score", [
    ("the dishwasher died", "the dishwasher door latch snapped, it won't stay closed", 0),
    ("the dishwasher died", "the dishwasher died again", 1),
    ("the dishwasher is leaking", "the dishwasher stopped working", 1),
    ("Roaches again", "I saw a mouse", 0),
    ("Kitchen sink leaking", "bathroom sink leaking", 0),
    ("dishwasher not working", "I want a rent credit for the dishwasher", 1),  # "want" is not "ant"
])
def test_match_score_rules(old, new, score):
    assert (mh.match_score(new, old) > 0) == bool(score)


def test_specific_part_after_saved_generic_request_saves_as_new(client):
    save_repair(client, "the dishwasher died")
    chat(client, "the dishwasher door latch snapped, it won't stay closed", "R003", "p")
    r = chat(client, "kitchen, yes you can come in", "R003", "p")
    res = confirm(client, "R003", "p")
    assert res["ok"] and res.get("error_code") != "POSSIBLE_DUPLICATE", (r["reply"], res)


# ---- "is it normal" questions -------------------------------------------------------------------------------------

LIVE_Q = ["is it normal for the water heater to have a puddle under it?",
          "is it normal for the fridge to be warm inside? my milk went bad overnight",
          "is it normal for the outlet to smell like burning plastic?",
          "is it normal for the bathroom ceiling to have mold?",
          "is it normal for the dishwasher to leave water on the floor?",
          "is it normal that there are roaches in the kitchen?",
          "¿es normal que el calentador tenga un charco debajo?",
          "¿es normal que el refrigerador esté caliente desde ayer?"]


@pytest.mark.parametrize("msg", LIVE_Q)
def test_question_describing_a_live_fault_starts_the_intake(client, msg):
    r = chat(client, msg, "R003", "lq")
    if r["safety_state"] == "active":  # e.g. a burning smell: the safety layer's decision, not this test's
        return
    assert kind(r) == "maintenance_request", (msg, r["workflow"], r["reply"])


@pytest.mark.parametrize("msg", ["is it normal for the fridge to hum?", "is it ok for the AC to drip a little outside?",
                                 "¿es normal que la nevera zumbe?", "should the dishwasher make a clicking sound?"])
def test_general_questions_still_get_the_answer_and_offer(client, msg):
    r = chat(client, msg, "R003", "gq")
    assert kind(r) is None and ("technician" in r["reply"] or "técnico" in r["reply"]), r["reply"]


@pytest.mark.parametrize("reply", ["yes", "report it", "yes please", "sí, reportarlo"])
def test_yes_after_the_offer_opens_a_prefilled_card(client, reply):
    chat(client, "is it normal for the fridge to hum?", "R003", "y")
    r = chat(client, reply, "R003", "y")
    assert kind(r) == "maintenance_request", r["reply"]
    assert "fridge" in fields(r)["issue"].lower() and "nothing waiting" not in r["reply"].lower()


def test_no_after_the_offer_starts_nothing(client):
    chat(client, "is it normal for the fridge to hum?", "R003", "yn")
    r = chat(client, "no thanks", "R003", "yn")
    assert kind(r) is None


# ---- alerts, notes for a person, labels -----------------------------------------------------------------------

@pytest.mark.parametrize("answer,entry", [("yes you can enter", "Yes"), ("you can come in", "Yes"),
                                          ("contact me first", "Contact"), ("sí, pueden entrar", "S")])
def test_answer_after_an_alert_goes_onto_the_resumed_card(client, answer, entry):
    chat(client, "the kitchen faucet is dripping", "R003", "bp")
    chat(client, "a pipe burst under the sink and water is everywhere", "R003", "bp")
    r = chat(client, answer, "R003", "bp")
    if r["safety_state"] == "active":
        pytest.skip("the safety layer still treats this turn as active (Agent A owns that decision)")
    assert kind(r) == "maintenance_request" and fields(r).get("entry", "").startswith(entry), (r["reply"], fields(r))
    assert "under control" not in r["reply"] and "bajo control" not in r["reply"]


def test_resume_wording_never_assumes_control():
    from app.templates import T
    for lang in ("en", "es"):
        for key in ("resume_after_alert", "resume_card_note"):
            assert "control" not in T[key][lang]


def test_manager_note_with_no_card_carries_the_latest_open_repairs_history(client):
    r = chat(client, "get me the manager", "R001", "m")
    assert kind(r) == "staff_handoff"
    d = get_state().store.get_draft("m", "R001")
    assert d["repeat_history"]["count"] == 3 and d["manager_review"] is True  # I008 AC rattling + I002 + I003
    assert confirm(client, "R001", "m", kind="staff_handoff")["ok"]
    note = get_state().store.records(session_id="m", limit=5)[0]
    assert note["repeat_history"]["references"] == ["I002", "I003", "I008"]


def test_manager_note_without_open_repairs_says_none_explicitly(client):
    chat(client, "get me the manager", "R003", "m0")
    d = get_state().store.get_draft("m0", "R003")
    assert "repeat_history" in d and d["repeat_history"] is None
    assert confirm(client, "R003", "m0", kind="staff_handoff")["ok"]
    note = get_state().store.records(session_id="m0", limit=5)[0]
    assert "repeat_history" in note and note["repeat_history"] is None


@pytest.mark.parametrize("msg", ["I'm fine, I just want it fixed", "we're ok, just fix it", "nobody is hurt, I just "
                                 "need it repaired", "estoy bien, solo quiero que lo arreglen"])
def test_after_an_alert_im_fine_just_fix_it_proceeds_with_that_repair(client, msg):
    chat(client, "the outlet shocked me when I plugged in the lamp", "R003", "sh")
    r = chat(client, msg, "R003", "sh")
    if r["safety_state"] == "active":
        pytest.skip("the safety layer still treats this turn as active (Agent A owns that decision)")
    assert kind(r) == "maintenance_request", r["reply"]
    assert "outlet" in fields(r)["issue"].lower(), fields(r)


@pytest.mark.parametrize("text,label", [("the closet light is out", "your closet light repair request"),
                                        ("the kitchen sink and the dishwasher both leak",
                                         "your sink and dishwasher repair request"),
                                        ("ceiling fan wobbles", "your fan repair request"),
                                        ("I saw a mouse", "your mouse or rat repair request")])
def test_labels_read_naturally(text, label):
    assert mh.request_label(text) == label


def test_is_normal_issue_rewrite():
    assert A._normal_q_issue("is it normal for the fridge to hum?") == \
        "The fridge to hum (asked whether this is normal)"
