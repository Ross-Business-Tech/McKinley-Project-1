"""Repeat-issue history: open-request matching, cross-session duplicates and new vs repeat problems, from authorized
data only."""

import re
from dataclasses import dataclass
from datetime import datetime

import pytest

from app import actions as A
from app import maintenance_history as mh
from app.context import Interaction, detect_topics
from app.state import get_state
from tests.wording import says_not_sent

# ---- Sprint 8 Workstream C: repeat-issue history from AUTHORIZED data only (app/maintenance_history.py + the planner).

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
    assert res["ok"] and "community manager review" in res["message"] and says_not_sent(res["message"])
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
    # Fix round: an OPEN own prototype request for the same thing now gets a follow-up note (not a new card), so the
    # single earlier request here is a CLOSED workbook item of R003's own (synthetic, added for this test)
    from app.context import Interaction
    get_state().deps.workbook.residents["R003"].interactions.append(Interaction(
        interaction_id="I950", resident_id="R003", timestamp=datetime(2026, 11, 5, 9, 0), channel="chat",
        category="maintenance", subject="Dishwasher leaking", full_text="", status="closed", resolved_date=None,
        follow_up_needed=False))
    r = chat(client, "the dishwasher is leaking again", "R003", "b")
    assert "I can see 1 related maintenance request in the last 7 days" in r["reply"], r["reply"]
    assert "You've reported this before" in r["reply"] and "this many" not in r["reply"]
    assert "requests" not in r["reply"].split("community manager")[0].split("I can see")[1]


def test_spanish_reply_names_count_and_window(client):
    r = chat(client, "el aire acondicionado no enfría otra vez", "R001", "es")
    assert "Veo 3 solicitudes de mantenimiento relacionadas desde junio" in r["reply"]
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


# ---- Sprint 8 Workstream C fix round: cross-session duplicates, counting only repair requests, empathy scaled to the

def confirm_s8rf(client, persona="R001", session="s", kind="maintenance_request"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": kind}).json()


def kind(r):
    return (r.get("action") or {}).get("kind")


def repairs(persona):
    return [r for r in get_state().store.records(kind="maintenance_request", limit=100) if r["persona_id"] == persona]


def file_repair(client, issue, persona="R003", session="first"):
    chat(client, issue, persona, session)
    r = chat(client, "kitchen, yes you can enter", persona, session)
    if (r.get("action") or {}).get("stage") != "ready":
        r = chat(client, "yes you can enter", persona, session)
    res = confirm_s8rf(client, persona, session)
    assert res["ok"], res
    return res["record"]["id"]


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
    res = confirm_s8rf(client, "R003", "later2")
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
    assert confirm_s8rf(client, "R003", "later", kind="staff_handoff")["ok"]
    h = mh.related_history("dishwasher leaking", records=get_state().store.records(limit=50), persona_id="R003")
    assert h.count == 1 and h.references == [ref]


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


@pytest.mark.parametrize("ask", ["forget it, just connect me with a human", "never mind, I want to talk to a person",
                                 "cancel that, let me talk to someone", "olvídalo, quiero hablar con una persona"])
def test_handoff_note_keeps_the_pending_repeat_repair(client, ask):
    chat(client, "my AC stopped cooling again", "R001", "h")
    r = chat(client, ask, "R001", "h")
    assert kind(r) == "staff_handoff", r["reply"]
    f = fields(r)
    assert "AC stopped cooling" in f.get("earlier", ""), f
    assert "3 earlier related" in f.get("related_history", "") or "3 solicitudes" in f.get("related_history", "")
    res = confirm_s8rf(client, "R001", "h", kind="staff_handoff")
    assert res["ok"]
    note = next(x for x in get_state().store.records(session_id="h", limit=10) if x["kind"] == "staff_handoff")
    assert note["repeat_history"]["count"] == 3 and note["manager_review"] is True


def test_handoff_note_without_a_repeat_has_no_history(client):
    chat(client, "the toilet in the hall bathroom keeps running", "R001", "n")
    r = chat(client, "forget it, just connect me with a human", "R001", "n")
    assert kind(r) == "staff_handoff" and "related_history" not in fields(r)
    assert "toilet" in fields(r).get("earlier", "").lower()


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


# ---- Sprint 8 Workstream C final round: a different room / fixture / pest / specific part failure is a NEW request;

def chat_s8refi(client, message, persona="R003", session="s"):
    r = client.post("/api/chat", json={"message": message, "persona_id": persona or None, "mode": "aware",
                                       "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


def confirm_s8refi(client, persona="R003", session="s", kind="maintenance_request"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": kind}).json()


def add_open(persona, iid, subject):
    get_state().deps.workbook.residents[persona].interactions.append(Interaction(
        iid, persona, datetime(2026, 10, 23, 9, 45), "chat", "maintenance", subject, "", "open", None, False))


def save_repair(client, issue, persona="R003", session="first"):
    chat_s8refi(client, issue, persona, session)
    r = chat_s8refi(client, "kitchen, yes you can come in", persona, session)
    if (r.get("action") or {}).get("stage") != "ready":
        r = chat_s8refi(client, "yes you can come in", persona, session)
    res = confirm_s8refi(client, persona, session)
    assert res["ok"], res
    return res["record"]["id"]


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
    r = chat_s8refi(client, msg, "R003", "n")
    assert kind(r) == "maintenance_request", (msg, r["reply"])
    assert "I046" not in r["reply"]


@pytest.mark.parametrize("subject,msg", STILL_FOLLOWUP)
def test_same_thing_same_symptom_or_generic_is_still_a_follow_up(client, subject, msg):
    add_open("R003", "I046", subject)
    r = chat_s8refi(client, msg, "R003", "f")
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
    chat_s8refi(client, "the dishwasher door latch snapped, it won't stay closed", "R003", "p")
    r = chat_s8refi(client, "kitchen, yes you can come in", "R003", "p")
    res = confirm_s8refi(client, "R003", "p")
    assert res["ok"] and res.get("error_code") != "POSSIBLE_DUPLICATE", (r["reply"], res)


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
    r = chat_s8refi(client, msg, "R003", "lq")
    if r["safety_state"] == "active":  # e.g. a burning smell: the safety layer's decision, not this test's
        return
    assert kind(r) == "maintenance_request", (msg, r["workflow"], r["reply"])


@pytest.mark.parametrize("msg", ["is it normal for the fridge to hum?", "is it ok for the AC to drip a little outside?",
                                 "¿es normal que la nevera zumbe?", "should the dishwasher make a clicking sound?"])
def test_general_questions_still_get_the_answer_and_offer(client, msg):
    r = chat_s8refi(client, msg, "R003", "gq")
    assert kind(r) is None and ("technician" in r["reply"] or "técnico" in r["reply"]), r["reply"]


@pytest.mark.parametrize("reply", ["yes", "report it", "yes please", "sí, reportarlo"])
def test_yes_after_the_offer_opens_a_prefilled_card(client, reply):
    chat_s8refi(client, "is it normal for the fridge to hum?", "R003", "y")
    r = chat_s8refi(client, reply, "R003", "y")
    assert kind(r) == "maintenance_request", r["reply"]
    assert "fridge" in fields(r)["issue"].lower() and "nothing waiting" not in r["reply"].lower()


def test_no_after_the_offer_starts_nothing(client):
    chat_s8refi(client, "is it normal for the fridge to hum?", "R003", "yn")
    r = chat_s8refi(client, "no thanks", "R003", "yn")
    assert kind(r) is None


@pytest.mark.parametrize("answer,entry", [("yes you can enter", "Yes"), ("you can come in", "Yes"),
                                          ("contact me first", "Contact"), ("sí, pueden entrar", "S")])
def test_answer_after_an_alert_goes_onto_the_resumed_card(client, answer, entry):
    chat_s8refi(client, "the kitchen faucet is dripping", "R003", "bp")
    chat_s8refi(client, "a pipe burst under the sink and water is everywhere", "R003", "bp")
    r = chat_s8refi(client, answer, "R003", "bp")
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
    r = chat_s8refi(client, "get me the manager", "R001", "m")
    assert kind(r) == "staff_handoff"
    d = get_state().store.get_draft("m", "R001")
    assert d["repeat_history"]["count"] == 3 and d["manager_review"] is True  # I008 AC rattling + I002 + I003
    assert confirm_s8refi(client, "R001", "m", kind="staff_handoff")["ok"]
    note = get_state().store.records(session_id="m", limit=5)[0]
    assert note["repeat_history"]["references"] == ["I002", "I003", "I008"]


def test_manager_note_without_open_repairs_says_none_explicitly(client):
    chat_s8refi(client, "get me the manager", "R003", "m0")
    d = get_state().store.get_draft("m0", "R003")
    assert "repeat_history" in d and d["repeat_history"] is None
    assert confirm_s8refi(client, "R003", "m0", kind="staff_handoff")["ok"]
    note = get_state().store.records(session_id="m0", limit=5)[0]
    assert "repeat_history" in note and note["repeat_history"] is None


@pytest.mark.parametrize("msg", ["I'm fine, I just want it fixed", "we're ok, just fix it", "nobody is hurt, I just "
                                 "need it repaired", "estoy bien, solo quiero que lo arreglen"])
def test_after_an_alert_im_fine_just_fix_it_proceeds_with_that_repair(client, msg):
    chat_s8refi(client, "the outlet shocked me when I plugged in the lamp", "R003", "sh")
    r = chat_s8refi(client, msg, "R003", "sh")
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


# ---- Sprint 8 Workstream C last round: best open-request match by object AND symptom, citing by title, separate pro...

def confirm_s8rl(client, persona="R001", session="s", kind="maintenance_request"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona or None,
                                                     "kind": kind}).json()


def draft(session, persona="R001"):
    return get_state().store.get_draft(session, persona) or {}


def save_repair_s8rl(client, issue, persona="R001", session="first"):
    chat(client, issue, persona, session)
    r = chat(client, "yes you can come in", persona, session)
    if (r.get("action") or {}).get("stage") != "ready":
        r = chat(client, "kitchen", persona, session)
    res = confirm_s8rl(client, persona, session)
    assert res["ok"], res
    return res["record"]["id"]


SAME = [("the AC is rattling louder now", "AC rattling"), ("my AC makes a loud noise", "AC rattling"),
        ("AC quit cooling again", "AC not cooling"), ("the AC is blowing warm air", "AC not cooling"),
        ("the dishwasher died again", "Dishwasher leaking"),  # a generic failure matches any symptom
        ("kitchen sink still dripping", "Leak under kitchen sink"), ("el aire hace ruido", "AC rattling"),
        ("el fregadero sigue goteando", "Kitchen sink leaking")]


DIFFERENT = [("the AC is rattling louder now", "AC quit cooling again"), ("the AC smells musty", "AC rattling"),
             ("the toilet is clogged", "Toilet leaking at the base"), ("el aire no enfría", "AC rattling")]


@pytest.mark.parametrize("new,old", SAME)
def test_same_object_and_compatible_symptom_is_the_same_request(new, old):
    assert mh.match_score(new, old) > 0


@pytest.mark.parametrize("new,old", DIFFERENT)
def test_same_object_with_a_different_symptom_is_a_different_request(new, old):
    assert mh.match_score(new, old) == 0


def test_best_open_prefers_the_symptom_match():
    rec = {"id": "DEMO-WO-1001", "fields": [{"key": "issue", "value": "ugh the AC quit cooling again"}]}
    item = type("I", (), {"subject": "AC rattling", "interaction_id": "I008"})()
    assert A._best_open("the AC is rattling louder now", [(rec, "ugh the AC quit cooling again"),
                                                           (item, "AC rattling")]) is item


@pytest.mark.parametrize("text,lang,label", [
    ("ugh the AC quit cooling again, its like 80 in here", "en", "your AC repair request"),
    ("my dishwasher died lol", "en", "your dishwasher repair request"),
    ("the stupid toilet keeps running", "en", "your toilet repair request"),
    ("something is wrong", "en", "your repair request"),
    ("el lavaplatos no sirve", "es", "su solicitud de reparación: lavaplatos"),
    ("el inodoro gotea", "es", "su solicitud de reparación: inodoro"),
])
def test_saved_requests_are_cited_by_what_they_are_about(text, lang, label):
    assert mh.request_label(text, lang) == label


def test_n12_rattling_matches_i008_by_subject_and_the_sink_gets_its_own_request(client):
    ref = save_repair_s8rl(client, "ugh the AC quit cooling again, its like 80 in here")
    r = chat(client, "the AC is rattling louder now, and separately my bathroom sink is clogged", "R001", "b")
    assert kind(r) == "staff_handoff" and "AC rattling (I008)" in r["reply"] and ref not in r["reply"]
    assert "ugh" not in r["reply"] and "80 in here" not in r["reply"]
    assert "sink" not in fields(r)["topic"].lower() and "its own repair request" in r["reply"]
    assert draft("b")["parked"]["fields"]["issue"]["value"] == "My bathroom sink is clogged"
    res = confirm_s8rl(client, "R001", "b", kind="staff_handoff")
    assert res["ok"]
    nxt = draft("b")
    assert nxt.get("kind") == "maintenance_request" and "sink" in nxt["fields"]["issue"]["value"].lower()


@pytest.mark.parametrize("msg", ["my AC stopped working again", "the AC quit cooling again", "AC is out again",
                                 "el aire no enfría otra vez"])
def test_follow_up_cites_the_saved_request_by_title_never_raw_words(client, msg):
    ref = save_repair_s8rl(client, "ugh the AC quit cooling again, its like 80 in here")
    r = chat(client, msg, "R001", "p3")
    assert kind(r) == "staff_handoff" and ref in r["reply"], r["reply"]
    assert "ugh" not in r["reply"] and ("your AC repair request" in r["reply"] or "aire acondicionado" in r["reply"])


@pytest.mark.parametrize("extra", ["I want a refund on rent and someone to call me today",
                                   "I want a rent credit for this", "have someone call me back today",
                                   "quiero un reembolso y que me llamen hoy"])
def test_extra_asks_on_a_follow_up_are_kept_and_never_promised(client, extra):
    ref = save_repair_s8rl(client, "the dishwasher is not working", "R003", "c1")
    r = chat(client, f"dishwasher died for the fourth time. {extra}", "R003", "c2")
    assert kind(r) == "staff_handoff" and ref in r["reply"], r["reply"]
    held = (fields(r).get("requests", "") + " " + fields(r).get("message", "")).lower()
    assert any(w in held for w in ("refund", "credit", "call", "reembolso", "llamen")), fields(r)
    low = r["reply"].lower()
    assert "will call" not in low and "refund is" not in low and "credit is" not in low
    assert "can't promise" in low or "no puedo prometer" in low


def test_staff_summary_matches_the_cited_record_and_the_repair_only_count(client):
    ref = save_repair_s8rl(client, "ugh the AC quit cooling again, its like 80 in here")
    chat(client, "my AC stopped working again", "R001", "p2")
    d = draft("p2")
    assert d["summary"].startswith(f"Follow-up on open request {ref}") and "no work order exists" not in d["summary"]
    assert "4 earlier related repair request(s) since June" in d["summary"]  # I002, I003, I008 + the saved one
    assert d["repeat_history"]["count"] == 4 and d["manager_review"] is True


@pytest.mark.parametrize("ask", ["get me the manager", "I want to talk to a person", "can a human help me",
                                 "quiero hablar con el gerente"])
def test_note_for_a_person_after_a_repeat_card_carries_the_history(client, ask):
    chat(client, "My AC stopped cooling again. This has happened multiple times.", "R001", "d2")
    chat(client, ask, "R001", "d2")
    d = draft("d2")
    assert d.get("kind") == "staff_handoff" and d["repeat_history"]["count"] == 3 and d["manager_review"] is True


def test_note_after_a_sent_repeat_repair_carries_its_history(client):
    chat(client, "My AC stopped cooling again. This has happened multiple times.", "R001", "d3")
    chat(client, "yes you can come in", "R001", "d3")
    assert confirm_s8rl(client, "R001", "d3")["ok"]
    chat(client, "get me the manager", "R001", "d3")
    d = draft("d3")
    assert d.get("kind") == "staff_handoff" and d["repeat_history"]["count"] == 3


NORMAL_Q = ["is it normal for the water heater to pop?", "is it normal that my fridge hums?",
            "should the dishwasher make a clicking sound?", "why does my toilet gurgle sometimes?",
            "is it ok for the AC to drip a little outside?", "is that normal for a water heater?",
            "¿es normal que el calentador haga ruido?", "¿es normal que la nevera zumbe?"]


REPORTS = ["the water heater is popping really loud right now", "my fridge is leaking water",
           "is the water heater supposed to be leaking everywhere right now?", "el calentador gotea ahora"]


@pytest.mark.parametrize("msg", NORMAL_Q)
def test_is_it_normal_questions_are_answered_not_filed(client, msg):
    r = chat(client, msg, "R003", "q")
    assert kind(r) is None and not r["records_created"], (msg, r["reply"])
    assert "technician" in r["reply"] or "técnico" in r["reply"]


@pytest.mark.parametrize("msg", REPORTS)
def test_reports_are_not_treated_as_is_it_normal_questions(msg):
    assert A._is_normal_question(msg) is None


def test_water_heater_is_not_filed_under_heating_and_cooling(client):
    r = chat(client, "the water heater is popping really loud", "R003", "wh")
    assert fields(r).get("location") != "Heating / cooling system"


PLAN = ["can I get a payment plan for this month's rent?", "I need a payment plan", "is a payment plan possible?",
        "can I pay my rent in installments", "can I split the rent this month", "I'd like to set up a paymentplan",
        "¿puedo tener un plan de pagos?", "quiero pagar la renta en partes"]


@pytest.mark.parametrize("msg", PLAN)
def test_payment_plan_is_a_billing_note(client, msg):
    r = chat(client, msg, "R003", "pp")
    assert kind(r) == "staff_handoff", (msg, r["reply"])
    assert fields(r)["topic"].startswith(("Payment plan request", "Lease or billing", "Balance"))
    assert "Follow-up still owed" not in fields(r)["topic"]


@pytest.mark.parametrize("msg", ["my plan is to pay rent on friday", "my rent went up",
                                 "where do I pay rent", "the plan for the pool is great"])
def test_payment_plan_near_misses(msg):
    assert not A._PAYMENT_PLAN.search(msg)


@pytest.fixture
def tips(client, monkeypatch):
    monkeypatch.setattr(get_state().deps.settings, "quickfix_content_mode", "demo_drafts")
    monkeypatch.setattr(get_state().deps.settings, "safety_classifier", "off")
    return client


@pytest.mark.parametrize("answer", ["Still not working", "no, still clogged", "didn't help", "sigue tapada"])
def test_tips_did_not_help_raises_no_priority(tips, answer):
    chat(tips, "my bathtub is clogged", "R003", "t")
    r = chat(tips, answer, "R003", "t")
    assert kind(r) == "maintenance_request", r["reply"]
    assert "priority_note" not in fields(r) and draft("t", "R003").get("priority") in (None, "normal")


def test_earlier_card_comes_back_after_the_alert_settles(client):
    chat(client, "the kitchen faucet is dripping", "R003", "fl")
    chat(client, "oh no there's water flooding all over the bathroom floor!", "R003", "fl")
    assert draft("fl", "R003").get("suspended") is True
    r = chat(client, "ok the water is shut off now, what next?", "R003", "fl")
    if r["safety_state"] == "active":
        pytest.skip("the safety layer still treats this turn as active (Agent A owns that decision)")
    assert kind(r) == "maintenance_request" and fields(r)["issue"] == "The kitchen faucet is dripping"
    assert "hasn't been sent" in r["reply"] and not r["records_created"]
