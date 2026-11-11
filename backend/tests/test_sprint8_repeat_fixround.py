"""Sprint 8 Workstream C fix round: cross-session duplicates, counting only repair requests, empathy scaled to the
count, handoff notes that carry the repeat history, planner misroutes, and request-phrase stripping.

Fixture R001 (tests/conftest.py): AC history I002 / I003 / I008 (open). R003: no maintenance history.
"""

from datetime import datetime

import pytest

from app import actions as A
from app import maintenance_history as mh
from app.context import Interaction, detect_topics
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


def confirm(client, persona="R001", session="s", kind="maintenance_request"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def kind(r):
    return (r.get("action") or {}).get("kind")


def repairs(persona):
    return [r for r in get_state().store.records(kind="maintenance_request", limit=100) if r["persona_id"] == persona]


def file_repair(client, issue, persona="R003", session="first"):
    chat(client, issue, persona, session)
    r = chat(client, "kitchen, yes you can enter", persona, session)
    if (r.get("action") or {}).get("stage") != "ready":
        r = chat(client, "yes you can enter", persona, session)
    res = confirm(client, persona, session)
    assert res["ok"], res
    return res["record"]["id"]


# ---- 1. an open request from an earlier session is never filed twice ------------------------------------------

SAME_AGAIN = ["the dishwasher is leaking again", "my dishwasher is leaking", "dishwasher still leaking",
              "the dishwasher leaks again, water on the floor", "el lavaplatos sigue goteando",
              "the dishwasher is leaking AGAIN", "dishwasher leak is back", "my dishwasher is still leaking water"]


@pytest.mark.parametrize("msg", SAME_AGAIN)
def test_open_request_from_an_earlier_session_gets_a_follow_up_note(client, msg):
    ref = file_repair(client, "the dishwasher is leaking")
    r = chat(client, msg, "R003", "later")
    assert kind(r) == "staff_handoff" and ref in r["reply"], r["reply"]
    assert "won't start a duplicate" in r["reply"] or "no abro otra" in r["reply"]
    assert fields(r)["topic"].startswith(f"Follow-up on {ref}")
    assert len(repairs("R003")) == 1


@pytest.mark.parametrize("msg", ["the bathroom fan is loud", "my toilet keeps running", "the oven won't heat",
                                 "what's the status of my dishwasher request?"])
def test_different_problem_or_status_question_is_not_a_follow_up(client, msg):
    ref = file_repair(client, "the dishwasher is leaking")
    r = chat(client, msg, "R003", "later")
    assert not (kind(r) == "staff_handoff" and f"Follow-up on {ref}" in fields(r).get("topic", "")), r["reply"]


def test_saying_it_is_a_different_problem_still_allows_a_new_card(client):
    file_repair(client, "the dishwasher is leaking")
    r = chat(client, "the dishwasher is leaking, it's a different problem", "R003", "later")
    assert kind(r) == "maintenance_request"


def test_confirm_refuses_a_cross_session_near_duplicate(client):
    """Defence in depth at save time: the same repair, saved open in another session, is not written again."""
    ref = file_repair(client, "the dishwasher is leaking")
    store = get_state().store
    store.save_draft("later2", "R003", "maintenance_request", {
        "fields": {"issue": {"value": "Dishwasher leaking", "source": "you_said"},
                   "location": {"value": "Kitchen", "source": "you_said"},
                   "entry": {"value": "Yes, you can enter", "source": "you_said"}}, "lang": "en"})
    res = confirm(client, "R003", "later2")
    assert res["ok"] is False and res["error_code"] == "POSSIBLE_DUPLICATE" and ref in res["message"]
    assert len(repairs("R003")) == 1


def test_another_personas_open_request_is_never_cited(client):
    file_repair(client, "the dishwasher is leaking", persona="R003")
    r = chat(client, "the dishwasher is leaking", "R001", "mine")
    assert kind(r) == "maintenance_request" and "DEMO-WO" not in r["reply"]


def test_follow_up_does_not_inflate_the_history_count(client):
    ref = file_repair(client, "the dishwasher is leaking")
    note = chat(client, "the dishwasher is leaking again", "R003", "later")
    assert kind(note) == "staff_handoff"
    assert confirm(client, "R003", "later", kind="staff_handoff")["ok"]
    h = mh.related_history("dishwasher leaking", records=get_state().store.records(limit=50), persona_id="R003")
    assert h.count == 1 and h.references == [ref]


# ---- 2. only repair requests are counted ------------------------------------------------------------------------

REQUESTS = ["AC not cooling", "AC out again", "AC rattling", "Kitchen sink leaking - 4th time", "No heat",
            "Roaches back", "El horno no calienta", "Puerta del balcón trabada", "Bathroom ceiling drywall repair",
            "Toilet keeps running"]
CONTACTS = ["Is the AC getting replaced?", "Callback: HVAC vendor visit", "HVAC vendor evaluation", "Pest follow-up",
            "When will the ceiling be fixed?", "Annual inspection notice", "Seguimiento: fuga del fregadero",
            "¿Cuándo vienen a arreglar el horno?", "Follow up on sink leak", "Pest control reminder"]


@pytest.mark.parametrize("subject", REQUESTS)
def test_problem_subjects_are_repair_requests(subject):
    assert mh.is_repair_request(subject)


@pytest.mark.parametrize("subject", CONTACTS)
def test_questions_callbacks_and_follow_ups_are_not_counted(subject):
    assert not mh.is_repair_request(subject)


def test_count_includes_only_requests_not_every_contact():
    res = type("R", (), {"interactions": [
        Interaction(i, "R001", datetime(2026, m, 1), "chat", "maintenance", subj, "", "closed", None, False)
        for i, m, subj in [("I002", 6, "AC not cooling"), ("I003", 8, "AC out again"),
                           ("I004", 8, "Is the AC getting replaced?"), ("I005", 9, "Callback: HVAC vendor visit"),
                           ("I006", 9, "HVAC vendor evaluation"), ("I008", 10, "AC rattling")]]})()
    h = mh.related_history("my AC stopped cooling again", resident=res, persona_id="R001")
    assert h.count == 3 and h.references == ["I002", "I003", "I008"]


# ---- 3. empathy scales with the real count --------------------------------------------------------------------

def test_empathy_key_scales_with_count():
    assert A._heard_key(1) == "repeat_heard_one" and A._heard_key(2) == "repeat_heard_two"
    assert A._heard_key(3) == A._heard_key(7) == "repeat_heard"
    from app.templates import t
    assert "before" in t("repeat_heard_one") and "twice" in t("repeat_heard_two")
    assert "this many times" in t("repeat_heard") and "visits" not in t("repeat_heard")
    assert "antes" in t("repeat_heard_one", "es") and "dos veces" in t("repeat_heard_two", "es")


def test_three_prior_requests_say_this_many_times(client):
    r = chat(client, "My AC stopped cooling again. This has happened multiple times.")
    assert "this many times" in r["reply"] and "3 related maintenance requests" in r["reply"]


# ---- 4. a note for a person carries the pending repair and its history ------------------------------------------

@pytest.mark.parametrize("ask", ["forget it, just connect me with a human", "never mind, I want to talk to a person",
                                 "cancel that, let me talk to someone", "olvídalo, quiero hablar con una persona"])
def test_handoff_note_keeps_the_pending_repeat_repair(client, ask):
    chat(client, "my AC stopped cooling again", "R001", "h")
    r = chat(client, ask, "R001", "h")
    assert kind(r) == "staff_handoff", r["reply"]
    f = fields(r)
    assert "AC stopped cooling" in f.get("earlier", ""), f
    assert "3 earlier related" in f.get("related_history", "") or "3 solicitudes" in f.get("related_history", "")
    res = confirm(client, "R001", "h", kind="staff_handoff")
    assert res["ok"]
    note = next(x for x in get_state().store.records(session_id="h", limit=10) if x["kind"] == "staff_handoff")
    assert note["repeat_history"]["count"] == 3 and note["manager_review"] is True


def test_handoff_note_without_a_repeat_has_no_history(client):
    chat(client, "the toilet in the hall bathroom keeps running", "R001", "n")
    r = chat(client, "forget it, just connect me with a human", "R001", "n")
    assert kind(r) == "staff_handoff" and "related_history" not in fields(r)
    assert "toilet" in fields(r).get("earlier", "").lower()


# ---- 5. planner misroutes --------------------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["whats the status of my AC rattling request?", "any update on the AC rattling?",
                                 "what's the status of my AC repair", "¿cómo va mi solicitud del aire?"])
def test_status_question_about_an_open_item_is_a_status_answer(client, msg):
    r = chat(client, msg, "R001", "st")
    assert r["workflow"]["id"] == "status_lookup", (msg, r["workflow"], r["reply"])
    assert kind(r) != "staff_handoff"


NEW_ASKS = [("can I put in a request to fix the stove burner?", "stove burner"),
            ("could I submit a request for the broken blinds?", "blinds"),
            ("can I open a ticket about the bathroom fan", "fan"),
            ("I want to submit a request to fix my dishwasher", "dishwasher"),
            ("I'd like to file a request for the leaky faucet", "faucet"),
            ("how do I put in a request for the garbage disposal?", "disposal"),
            ("¿puedo hacer una solicitud para arreglar la estufa?", "estufa"),
            ("quiero hacer un reporte del horno", "horno")]


@pytest.mark.parametrize("msg,word", NEW_ASKS)
def test_asking_to_put_in_a_request_starts_a_repair_card(client, msg, word):
    r = chat(client, msg, "R003", "new")
    assert kind(r) == "maintenance_request", (msg, r["workflow"], r["reply"])
    issue = fields(r).get("issue", "").lower()
    assert word in issue and "put in a request" not in issue and "submit" not in issue, issue


PRAISE = ["the pool party was fire, this place is killer", "the new gym is sick", "that barbecue last night was lit",
          "this place is amazing", "the clubhouse looks great", "loved the pool party", "la fiesta estuvo padrísima",
          "la alberca está genial", "the rooftop event was a blast", "honestly this community slaps"]
NOT_PRAISE = ["the party upstairs was so loud I can't sleep", "the neighbors' music is too loud every night",
              "the party next door is still going at 2am", "la música del vecino está muy alta otra vez",
              "the pool party was fire but they left trash everywhere", "my fridge is sick, it won't cool"]


@pytest.mark.parametrize("msg", PRAISE)
def test_slang_praise_is_small_talk_not_a_complaint(client, msg):
    r = chat(client, msg, "R001", "p")
    assert kind(r) is None and "noise" not in r["reply"].lower(), (msg, r["reply"])
    assert r["workflow"]["id"] in ("general_inquiry", "resident_support") and not r["records_created"]


@pytest.mark.parametrize("msg", NOT_PRAISE)
def test_complaints_and_repairs_are_not_treated_as_praise(msg):
    assert not A._praise_only(msg)


# ---- 6. the request phrase is not the problem; direct requests get on-file fields -------------------------------

DIRECT = [("my bathtub is clogged, just send maintenance", "My bathtub is clogged"),
          ("the sink is leaking, please send someone", "The sink is leaking"),
          ("toilet won't flush, can you send a plumber asap", "Toilet won't flush"),
          ("the oven doesn't heat. just send a tech", "The oven doesn't heat"),
          ("my dishwasher is broken - send someone out", "My dishwasher is broken"),
          ("the AC is not cooling, need someone to come look", "The AC is not cooling"),
          ("el inodoro gotea, manden a alguien", "El inodoro gotea"),
          ("la ducha está tapada, que venga mantenimiento", "La ducha está tapada")]


@pytest.mark.parametrize("msg,issue", DIRECT)
def test_request_clause_is_stripped_from_the_issue(msg, issue):
    assert A._issue_text(msg) == issue


@pytest.mark.parametrize("msg", ["the sink is leaking and the tech said the pipe is cracked",
                                 "someone left the gate broken", "send help, the ceiling fan fell down",
                                 "the maintenance closet door is stuck"])
def test_clauses_with_their_own_problem_are_kept(msg):
    assert A._issue_text(msg).lower().rstrip(".") == msg.lower()


@pytest.mark.parametrize("msg", ["my bathtub is clogged", "the bath tub won't drain", "la ducha no drena",
                                 "the ice maker is broken", "el microondas no sirve", "the blinds are bent",
                                 "persianas rotas", "mi secadora no calienta"])
def test_repair_topics_recognised_from_the_shared_lexicon(msg):
    assert {"plumbing", "appliance", "hvac", "pest", "maintenance_general"} & set(detect_topics(msg)), msg


@pytest.mark.parametrize("msg", ["the pool is closed", "what are the gym hours", "hola", "when is rent due"])
def test_non_repair_messages_get_no_repair_topic(msg):
    assert not {"plumbing", "appliance", "hvac", "pest", "maintenance_general"} & set(detect_topics(msg)), msg


def test_direct_bathtub_request_gets_the_on_file_entry_window(client):
    r = chat(client, "my bathtub is clogged, just send maintenance", "R001", "tub")
    f = fields(r)
    assert f["issue"] == "My bathtub is clogged" and f.get("entry_window") == "mornings (8-11 AM)"
