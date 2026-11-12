"""Sprint 7 fix round: issue classes from the independent verifier, simulators and the browser UX judge.

Each class is a family (>= 8 own phrasings, EN + ES where it applies) plus >= 4 near misses, over the real API
(TestClient, mock provider, offline), and invariant/metamorphic tests where a property holds for every member.
Fixture residents (tests/conftest.py): R001 (AC history, I008 "AC rattling" open), R003 (no history).
"""

import json
import time
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.intake import is_security_repair, not_account_holder
from app.state import get_state
from app.understanding import contact_pref, entry_value, field_edits, understand_rules
from app.utterance import ends_as_question, split_problems
from tests.test_sprint6_conversation import chat, fields, press_send
from tests.wording import says_not_sent

P = "P-RELOCATE-AA"
FIRST = "Contact me first; only enter when I'm home"
MAY = "Yes, maintenance may enter if I'm not home"
CARD = {"kind": "maintenance_request",
        "fields": {"issue": {"value": "My kitchen sink is leaking"}, "location": {"value": "Kitchen"},
                   "entry": {"value": MAY}, "contact": {"value": "Prefers text"}}}
META = settings(max_examples=30, deadline=None, derandomize=True, database=None,
                suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])


def sid():
    return f"fx-{uuid.uuid4().hex[:10]}"


def kind(r):
    return (r.get("action") or {}).get("kind")


def recs(s):
    return get_state().store.records(session_id=s, limit=50)


def draft(s, p="R001"):
    return get_state().store.get_draft(s, p) or {}


def sent_repair(c, s, p="R001", msg="my kitchen sink is leaking"):
    chat(c, msg, s, p)
    chat(c, "yes you can come in", s, p)
    return press_send(c, s, "maintenance_request", p)["record"]["id"]


# ---- P2-13: bounded, linear analysis ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["the sink, " * 500, "a" * 5000, "the sink leaks and " * 300,
                                  "never mind the mailbox " * 250, "kitchen bathroom location room " * 200])
def test_analysis_is_bounded_on_long_input(text):
    t0 = time.perf_counter()
    split_problems(text)
    understand_rules(text, CARD, "entry")
    field_edits(text, CARD, "maintenance_request")
    assert time.perf_counter() - t0 < 0.5


def test_long_message_through_the_api_is_fast(client):
    t0 = time.perf_counter()
    chat(client, "the sink, " * 500, sid(), "R001")
    assert time.perf_counter() - t0 < 2.0


# ---- P2-12: a question never mutates a card ---------------------------------------------------------------------

@META
@given(field=st.sampled_from(["issue", "problem", "location", "room", "contact preference", "entry permission"]),
       q=st.sampled_from(["the {f} is that I work nights, does that matter?", "does the {f} matter?",
                          "is the {f} important?", "what if the {f} is wrong?", "can you explain the {f}?",
                          "why do you need the {f}?"]))
def test_question_that_names_a_field_never_edits_it(field, q):
    msg = q.format(f=field)
    assert ends_as_question(msg) and field_edits(msg, CARD, "maintenance_request") == [], msg


@pytest.mark.parametrize("msg", ["the location is wrong, it's the bathroom", "can you fix the room? it's the bathroom",
                                 "where: bedroom", "change the issue to: slow drip under the sink"])
def test_question_guard_near_misses_still_edit(msg):
    assert field_edits(msg, CARD, "maintenance_request")


# ---- P1-1: a cancel targets the named workflow -----------------------------------------------------------------

MULTI = "my kitchen faucet drips and can someone from leasing call me about my renewal"


@pytest.mark.parametrize("msg", ["actually cancel the callback", "forget the call from leasing", "no call needed, "
                                 "just the faucet", "drop the note for the office", "scrap the renewal call",
                                 "never mind the phone call", "cancel the leasing callback, keep the faucet",
                                 "olvide la llamada"])
def test_cancelling_the_callback_keeps_the_repair(client, msg):
    s = sid()
    chat(client, MULTI, s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and not draft(s).get("queued_note")
    chat(client, "yes you can come in", s, "R001")
    press_send(client, s, "maintenance_request", "R001")
    assert len(recs(s)) == 1 and draft(s).get("kind") != "staff_handoff"  # the callback is not offered again


@pytest.mark.parametrize("msg", ["no, I meant cancel the callback, keep the faucet", "keep the faucet repair",
                                 "I still want the faucet fixed, cancel the call", "bring back the faucet one"])
def test_correcting_a_wrong_cancel_brings_the_repair_back(client, msg):
    s = sid()
    chat(client, MULTI, s, "R001")
    chat(client, "never mind, cancel it", s, "R001")  # cancelled the repair; the queued note opened
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and "faucet" in fields(r)["issue"].lower()


@pytest.mark.parametrize("msg", ["never mind, cancel it", "cancel the faucet repair", "the faucet is fine now",
                                 "yes you can come in"])
def test_cancel_target_near_misses(client, msg):
    s = sid()
    chat(client, MULTI, s, "R001")
    chat(client, msg, s, "R001")
    d = draft(s)
    assert d.get("kind") == "staff_handoff" or d.get("queued_note")  # the callback is never silently lost


# ---- P1-2/3/4: tours -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["never mind Sandpiper Pointe, just Heron Lake", "forget sandpiper pointe",
                                 "drop Sandpiper Pointe", "skip sandpiper pointe, heron lake only",
                                 "no sandpiper pointe", "just Heron Lake please", "scratch Sandpiper Pointe",
                                 "only heron lake, not sandpiper pointe"])
def test_dropping_one_of_two_communities_keeps_the_tour(client, msg):
    s = sid()
    chat(client, "I'd like to tour Heron Lake on Saturday and Sandpiper Pointe on Sunday", s, P)
    r = chat(client, msg, s, P)
    f = fields(r)
    assert kind(r) == "tour_request" and f["area"].startswith("Heron Lake") and "Sunday" not in f.get("days", "")


@pytest.mark.parametrize("msg", ["I'd love to see Heron Lake and Sandpiper Pointe, sunday afternoon",
                                 "can I check out Heron Lake saturday?", "me interesa ver Heron Lake el domingo en la "
                                 "tarde", "looking at Sandpiper Pointe this weekend", "I'd like to visit Heron Lake",
                                 "could I see Sandpiper Pointe on Friday morning",
                                 "quiero conocer Heron Lake el sábado",
                                 "stop by Heron Lake monday afternoon"])
def test_guest_tour_without_the_word_tour_gets_a_card(client, msg):
    r = chat(client, msg, sid(), "")
    assert kind(r) == "tour_request" and fields(r).get("area")


@pytest.mark.parametrize("msg", ["is Heron Lake pet friendly?", "where is Sandpiper Pointe?",
                                 "no tour, just want to know if Heron Lake has a pool", "what's Heron Lake like?"])
def test_guest_tour_near_misses(client, msg):
    assert kind(chat(client, msg, sid(), "")) != "tour_request"


def _tour_sent(c, s):
    chat(c, "I'd like to tour Heron Lake on Saturday morning", s, P)
    return press_send(c, s, "tour_request", P)["record"]["id"]


@pytest.mark.parametrize("msg", ["different question — do you have 3 bedrooms?", "do you have any 1 bedrooms?",
                                 "are there 2 bed units available?", "is there parking?", "do you allow cats?",
                                 "what's the pet policy?", "¿tienen apartamentos de 3 recámaras?",
                                 "how big are the 2 beds?"])
def test_a_question_after_a_tour_is_sent_is_answered_not_a_second_tour(client, msg):
    s = sid()
    _tour_sent(client, s)
    r = chat(client, msg, s, P)
    assert kind(r) != "tour_request" and "already saved" not in r["reply"]
    assert len([x for x in recs(s) if x["kind"] == "tour_request"]) == 1


@pytest.mark.parametrize("msg", ["I meant the following week", "I said morning but evenings are better",
                                 "actually make it Sunday", "can we do the afternoon instead",
                                 "mejor el domingo", "wrong day, Friday", "thursday… i mean the 19th",
                                 "push it to next week"])
def test_a_tour_correction_after_send_is_a_change_note_citing_it(client, msg):
    s = sid()
    ref = _tour_sent(client, s)
    r = chat(client, msg, s, P)
    assert kind(r) == "staff_handoff" and ref in r["reply"] + json.dumps(r["action"])
    assert len([x for x in recs(s) if x["kind"] == "tour_request"]) == 1


def test_no_tour_is_respected_and_a_second_tour_asks_its_days(client):
    s = sid()
    r = chat(client, "no tour, just want to know about pets", s, P)
    assert "request a tour" not in r["reply"].lower()
    s2 = sid()
    _tour_sent(client, s2)
    r = chat(client, "I'd also like to tour Sandpiper Pointe", s2, P)
    assert "days" not in fields(r)


# ---- P1-5: history and reference questions ----------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["what did I report last month?", "have I reported anything before?",
                                 "what did I put in a few weeks ago?", "anything I submitted last year?",
                                 "qué reporté el mes pasado", "my previous requests?", "what have I asked to get fixed "
                                 "in the past", "did I report the AC before?"])
def test_history_questions_list_and_never_open_a_card(client, msg):
    s = sid()
    r = chat(client, msg, s, "R001")
    assert kind(r) != "maintenance_request" and "I00" in r["reply"] and not recs(s)


@pytest.mark.parametrize("msg", ["what's my reference number?", "is the window one closed yet",
                                 "what's the ticket number for my sink?", "is the sink one done yet?"])
def test_reference_and_status_of_one_never_open_a_card(client, msg):
    s = sid()
    sent_repair(client, s, msg="my bedroom window won't lock")
    r = chat(client, msg, s, "R001")
    assert kind(r) != "maintenance_request"


# ---- P1-6/7: keep the complaint note; frustration while waiting ------------------------------------------------

@pytest.mark.parametrize("msg", ["no I don't want to start a new request, the old one wasn't fixed",
                                 "I don't want a new ticket, the first one was never fixed",
                                 "no new request please, the last one wasn't done", "no quiero una nueva solicitud",
                                 "the old one is the problem, I don't want a new one"])
def test_the_open_complaint_note_is_kept(client, msg):
    s = sid()
    chat(client, "the tech came last week and didn't fix my sink, I want to file a complaint", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and "complaint" in json.dumps(r["action"]).lower()


@pytest.mark.parametrize("msg", ["I asked you an hour ago about my closet light and nothing, what's going on",
                                 "I asked about it yesterday and still nothing", "nothing has happened since monday",
                                 "I messaged two days ago and nobody got back to me", "hace días pregunté y nada",
                                 "still nothing on my request?", "no one answered me", "I wrote this morning, still "
                                 "nothing"])
def test_waiting_frustration_gets_a_note_naming_open_requests(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert kind(r) == "staff_handoff" or r.get("status_items")


# ---- P1-8: a short answer to "which room?" ---------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["guest bathroom", "the guest bedroom", "hall closet", "master bath", "garage",
                                 "kids bedroom", "el baño de visitas", "living room"])
def test_room_answer_is_the_answer_not_an_faq(client, msg):
    s = sid()
    chat(client, "my sink is clogged", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and fields(r).get("location")


# ---- P1-9: contact preferences ---------------------------------------------------------------------------------

@pytest.mark.parametrize("msg,want", [
    ("put down that I'd rather get a phone call than texts", "call"), ("email me updates instead of the portal",
                                                                         "email"),
    ("text me instead of email from now on", "text"), ("I prefer phone calls", "call"),
    ("please use email, not texts", "email"), ("calls are better than texts for me", "call"),
    ("prefiero que me llamen", "call"), ("text is easier for me", "text")])
def test_contact_preference_family(msg, want):
    assert contact_pref(msg) == want


@pytest.mark.parametrize("msg", ["will they call me?", "nobody answered my 2 emails", "call me first before they come "
                                 "in", "have someone from the office call me about parking"])
def test_contact_preference_near_misses(msg):
    assert contact_pref(msg) is None


def test_a_stated_preference_applies_to_later_cards(client):
    s = sid()
    chat(client, "put down that I'd rather get a phone call than texts", s, "R001")
    r = chat(client, "my kitchen sink is leaking", s, "R001")
    assert fields(r)["contact"] == "Prefers call"


# ---- P1-10/11: details and corrections after Send --------------------------------------------------------------

@pytest.mark.parametrize("msg", ["one more detail: it gurgles when the dishwasher runs", "the pipe under it is loose",
                                 "my cat will be home, please knock", "it's the tub, not the sink",
                                 "correction: it's the faucet and it smells", "it only leaks when the dishwasher runs",
                                 "the cabinet under it is soaked", "it's the faucet not the sink"])
def test_after_send_details_and_corrections_are_change_notes(client, msg):
    s = sid()
    ref = sent_repair(client, s)
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"] + json.dumps(r["action"])


@pytest.mark.parametrize("msg", ["also my bedroom window won't lock", "the fridge stopped working",
                                 "the bathroom fan is broken too", "my dryer won't spin"])
def test_after_send_new_problems_are_new_cards(client, msg):
    s = sid()
    sent_repair(client, s)
    assert kind(chat(client, msg, s, "R001")) == "maintenance_request"


def test_object_swap_correction_moves_the_room():
    got = {c.field: c.value for c in field_edits("it's the tub, not the sink", CARD, "maintenance_request")}
    assert got == {"issue": "My tub is leaking", "location": "Bathroom"}


def test_further_corrections_join_the_open_change_note(client):
    s = sid()
    sent_repair(client, s)
    chat(client, "actually call me first before they come in", s, "R001")
    r = chat(client, "it's the hall closet actually", s, "R001")
    msg_f = fields(r)["message"]
    assert kind(r) == "staff_handoff" and "Hall closet" in msg_f and "call me first" in msg_f
    assert fields(r)["contact"] != "Prefers call"  # "call me first" is entry permission, not a contact preference


# ---- P2-14: entry permission polarity, Spanish field correction ------------------------------------------------

@pytest.mark.parametrize("msg,value", [("ok to enter without me", MAY), ("they can come in without me", MAY),
                                       ("pueden entrar sin mí", MAY), ("please don't come in without me", FIRST),
                                       ("not without me", FIRST), ("no sin mí", FIRST), ("llámame primero", FIRST),
                                       ("fine to go in without me", MAY)])
def test_entry_polarity(msg, value):
    assert entry_value(msg) == value


def test_spanish_field_named_entry_correction():
    assert {c.field: c.value for c in field_edits("cambia la entrada: llámame primero", CARD,
                                                  "maintenance_request")} == {"entry": FIRST}


# ---- P2-15/16 and judge items ----------------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["the garage door opener isn't working", "my mailbox lock is stuck",
                                 "the storage locker won't lock", "the remote for the gate is broken"])
def test_not_a_home_entry_lock(msg):
    assert not is_security_repair(msg)


@pytest.mark.parametrize("msg", ["my front door won't lock", "the deadbolt is broken", "front door lock is jammed",
                                 "la cerradura de la puerta está rota"])
def test_home_entry_lock_still_is(msg):
    assert is_security_repair(msg)


@pytest.mark.parametrize("cmd", ["ok fine actually do send the note", "actually yes send it", "yes please send it",
                                 "fine, send the note"])
def test_typed_send_after_dont_send_sends_that_card(client, cmd):
    s = sid()
    chat(client, "I'd like someone from the office to call me about parking", s, "R001")
    chat(client, "don't send it", s, "R001")
    chat(client, cmd, s, "R001")
    assert [x["kind"] for x in recs(s)] == ["staff_handoff"]


@pytest.mark.parametrize("bare", ["ok", "yes", "sure", "sí"])
def test_bare_yes_after_dont_send_never_sends(client, bare):
    # ("send it after all", the phrase the decline reply teaches, brings the card back for a Send: Sprint 2 W-3)
    s = sid()
    chat(client, "I'd like someone from the office to call me about parking", s, "R001")
    chat(client, "don't send it", s, "R001")
    chat(client, bare, s, "R001")
    assert not recs(s)


@pytest.mark.parametrize("a,b", [("my bathroom mirror is cracked", "the bathroom mirror has a crack"),
                                 ("kitchen sink leaking", "the kitchen sink is leaking again"),
                                 ("the closet shelf fell down", "closet shelf is down"),
                                 ("my bedroom blinds are broken", "the bedroom blinds broke")])
def test_reworded_duplicate_is_not_saved_twice(client, a, b):
    s = sid()
    sent_repair(client, s, "R003", a)
    r = chat(client, b, s, "R003")
    if kind(r) == "maintenance_request":
        chat(client, "yes you can come in", s, "R003")
        press_send(client, s, "maintenance_request", "R003")
    assert len([x for x in recs(s) if x["kind"] == "maintenance_request"]) == 1


def test_false_alarm_after_an_urgent_note_changes_nothing(client):
    s = sid()
    ref = sent_repair(client, s)
    chat(client, "I smell smoke in the hallway", s, "R001")
    for m in ("never mind, false alarm, it was a candle", "false alarm it was toast"):
        r = chat(client, m, s, "R001")
        assert kind(r) is None and ref not in r["reply"] and "Cancel" not in json.dumps(r.get("action") or {})


def test_a_second_need_in_a_safety_message_is_kept(client):
    r = chat(client, "I smell gas in my kitchen and I need someone to call me about my lease", sid(), "R001")
    assert "lease" in r["reply"] and "lease" in json.dumps(r["action"])


def test_dropping_an_item_takes_its_fields(client):
    s = sid()
    chat(client, "the mailbox lock is stuck and my kitchen faucet drips", s, "R001")
    chat(client, "drop the mailbox part", s, "R001")
    d = json.dumps(draft(s)).lower()
    assert "mailbox" not in d and "common area" not in d and "security" not in d


def test_meta_complaint_never_goes_into_the_problem_and_reply_differs(client):
    s = sid()
    first = chat(client, "my fridge is warm", s, "R001")
    r = chat(client, "I already said the fridge is warm", s, "R001")
    assert fields(r)["issue"] == "My fridge is warm" and r["reply"] != first["reply"]


def test_repeated_renewal_message_does_not_repeat_the_reply(client):
    s = sid()
    a = chat(client, "when is my lease up for renewal?", s, "R001")
    b = chat(client, "I want to renew my lease", s, "R001")
    assert a["reply"] != b["reply"] and fields(b)["topic"].endswith("leasing team")


def test_saved_reply_matches_the_demo_card(client):
    s = sid()
    chat(client, "my kitchen sink is leaking", s, "R001")
    chat(client, "yes you can come in", s, "R001")
    r = press_send(client, s, "maintenance_request", "R001")
    assert "saved in this demo" in r["message"] and says_not_sent(r["message"])


def test_spanish_after_send_names_the_team_in_spanish(client):
    s = sid()
    chat(client, "el refrigerador no enfría", s, "R001")
    chat(client, "sí pueden entrar", s, "R001")
    press_send(client, s, "maintenance_request", "R001")
    r = chat(client, "¿alguien va a venir?", s, "R001")
    assert "maintenance" not in r["reply"]


@pytest.mark.parametrize("msg", ["can you push them", "please expedite my requests", "can you speed it up",
                                 "nudge them for me", "¿pueden apurarlos?", "ask them to hurry"])
def test_asking_to_expedite_offers_a_note_citing_open_requests(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert kind(r) == "staff_handoff" and "I008" in json.dumps(r["action"])


def test_on_my_account_is_not_a_borrowed_device():
    assert not not_account_holder("anything still open on my account?")
    assert not_account_holder("I'm on her phone")


# ---- with Agent A: no repair intake while a person may be in danger THIS turn ----------------------------------

DANGER_TURNS = ["my toddler is on the balcony railing and the railing is loose",
                "my dad fell in the shower and can't get up, also the shower is leaking",
                "someone is trapped in the elevator and the button is broken",
                "my grandma is confused and burning up and the ac is broken",
                "mi hijo está atrapado en el baño y la cerradura no abre",
                "my friend collapsed in the kitchen and the sink is leaking",
                "my son swallowed something and the cabinet lock is broken",
                "she's not breathing right and the heater is broken"]


@pytest.mark.parametrize("msg", DANGER_TURNS)
def test_no_ordinary_repair_card_while_a_person_is_in_danger(client, msg):
    r = chat(client, msg, sid(), "R001")
    d = (r.get("risk") or {}).get("decision") or {}
    if d.get("person_danger") and d.get("rule") not in ("R9", "R9e", "R10", "R10q"):
        assert kind(r) != "maintenance_request", (msg, d)


@pytest.mark.parametrize("msg", ["the bathroom sink is leaking", "my oven light is burned out", "the heat is out",
                                 "the AC is broken"])
def test_danger_guard_near_misses_still_open_repairs(client, msg):
    assert kind(chat(client, msg, sid(), "R001")) == "maintenance_request"


@pytest.mark.parametrize("msg", ["the bathroom sink is leaking", "my oven won't heat", "el fregadero gotea",
                                 "the AC is broken", "my bedroom window won't lock", "the toilet keeps running",
                                 "the dishwasher won't drain", "the hallway light in my apartment is out"])
def test_guard_with_a_person_danger_care_line_this_turn(client, monkeypatch, msg):
    """The safety layer's verdict is forced (care line from a person sign, person_danger) so the planner guard is
    tested on its own: no repair card is opened while that line is shown."""
    import app.chat_engine as ce

    real = ce.incident_step

    def forced(*a, **kw):
        risk = real(*a, **kw)
        d = risk.decision.model_copy(update={"response": "care_line", "care": "danger", "rule": "R6",
                                             "person_danger": True})
        return risk.model_copy(update={"decision": d})

    monkeypatch.setattr(ce, "incident_step", forced)
    r = chat(client, msg, sid(), "R001")
    assert kind(r) != "maintenance_request" and ("safety steps" in r["reply"] or "seguridad" in r["reply"])


@pytest.mark.parametrize("rule", ["R9", "R10", "R10q", "R8"])
def test_guard_near_misses_remembered_or_property_follow_ups_still_repair(client, monkeypatch, rule):
    import app.chat_engine as ce

    real = ce.incident_step

    def forced(*a, **kw):
        risk = real(*a, **kw)
        d = risk.decision.model_copy(update={"response": "care_line", "care": "danger", "rule": rule,
                                             "person_danger": rule != "R8"})
        return risk.model_copy(update={"decision": d})

    monkeypatch.setattr(ce, "incident_step", forced)
    assert kind(chat(client, "the bathroom sink is leaking", sid(), "R001")) == "maintenance_request"


# ---- last round ------------------------------------------------------------------------------------------------

OVEN_CALL = "the oven won't heat, and I'd like someone from leasing to call me about my lease"


@pytest.mark.parametrize("msg", ["cancel the oven repair, I just want the call", "skip the repair, only the callback",
                                 "never mind the oven, just have leasing call me", "forget the oven, keep the call",
                                 "drop the oven request, I only need the call", "no repair needed, just the callback",
                                 "scrap the oven, I want the phone call", "olvide el horno, solo la llamada"])
def test_cancelling_the_repair_keeps_the_call(client, msg):
    s = sid()
    chat(client, OVEN_CALL, s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and "lease" in json.dumps(r["action"]).lower() and not recs(s)


@pytest.mark.parametrize("msg", ["cancel the call, keep the oven", "forget the call from leasing",
                                 "no call needed, just the oven", "skip the callback"])
def test_cancelling_the_call_keeps_the_repair_near_misses(client, msg):
    s = sid()
    chat(client, OVEN_CALL, s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and not draft(s).get("queued_note")


@pytest.mark.parametrize("msg", ["the closet light died", "the light quit working", "my bathroom fan died",
                                 "the disposal gave out", "the hallway light in my apartment went out",
                                 "my fridge conked out", "the outlet in my bedroom is dead", "el ventilador del baño "
                                 "no funciona"])
def test_a_fixture_that_died_is_a_repair(client, msg):
    assert kind(chat(client, msg, sid(), "R001")) == "maintenance_request"


@pytest.mark.parametrize("msg", ["my phone died", "the party died down", "I quit my job", "the music stopped"])
def test_died_near_misses_are_not_repairs(client, msg):
    assert kind(chat(client, msg, sid(), "R001")) != "maintenance_request"


@pytest.mark.parametrize("msg", ["you can let yourself in", "come on in", "enter ok", "ok to enter without me",
                                 "fine to go in without me", "they can let themselves in", "yes, enter",
                                 "go ahead and enter"])
def test_entry_answers_never_re_ask_and_send_works(client, msg):
    s = sid()
    chat(client, "my kitchen sink is leaking", s, "R001")
    r = chat(client, msg, s, "R001")
    assert fields(r).get("entry") == MAY
    assert press_send(client, s, "maintenance_request", "R001")["ok"]


def test_walk_in_closet_room_answer(client):
    s = sid()
    chat(client, "my sink is clogged", s, "R001")
    assert fields(chat(client, "the walk-in closet in the hallway", s, "R001"))["location"] == "Closet"


@pytest.mark.parametrize("msg", ["i said dont open another ticket, the first one is not done",
                                 "don't make a new request, the old one isn't fixed", "do not create another ticket",
                                 "stop opening a new one, the first one wasn't done"])
def test_no_new_ticket_replaces_the_new_card_with_a_follow_up(client, msg):
    s = sid()
    ref = sent_repair(client, s)
    chat(client, "my kitchen faucet drips", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"] and "First" not in json.dumps(r["action"])


@pytest.mark.parametrize("msg", ["I'd like to tour fernhill or birchwood", "tour fernhill and birchwood",
                                 "fernhill / birchwood tour please", "quiero visitar fernhill o birchwood"])
def test_either_or_communities_keep_both_and_one_can_be_dropped(client, msg):
    s = sid()
    r = chat(client, msg, s, P)
    assert "Fernhill" in fields(r)["area"] and "Birchwood" in fields(r)["area"]
    r = chat(client, "lets drop fernhill", s, P)
    assert fields(r)["area"] == "Birchwood Commons"


@pytest.mark.parametrize("msg", ["been waiting since monday for someone to look at my fan", "still waiting on my AC",
                                 "waiting for maintenance since last week", "llevo esperando desde el lunes"])
def test_waiting_complaints_check_existing_requests(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert kind(r) == "staff_handoff" and "I008" in json.dumps(r["action"])


@pytest.mark.parametrize("msg", ["unrelated - the hallway carpet has a stain", "separately, the bedroom window won't "
                                 "lock", "different issue: my dryer won't spin", "otro tema: la luz del closet no "
                                 "prende"])
def test_an_unrelated_problem_is_queued_not_appended(client, msg):
    s = sid()
    chat(client, "my kitchen sink is leaking", s, "R001")
    chat(client, msg, s, "R001")
    d = draft(s)
    assert "Also:" not in d["fields"]["issue"]["value"] and d.get("queued")


@pytest.mark.parametrize("msg,want", [("only send someone on weekends", "Weekends"), ("afternoons only", "Afternoons"),
                                      ("weekday mornings only", "morning"), ("solo por la tarde", "tarde")])
def test_visit_window_preferences_are_kept(client, msg, want):
    s = sid()
    chat(client, "my kitchen sink is leaking", s, "R001")
    r = chat(client, msg, s, "R001")
    assert want.lower() in fields(r)["entry_window"].lower()


def test_any_weekday_answers_the_days_question(client):
    s = sid()
    chat(client, "I'd like to tour Heron Lake", s, P)
    assert "Weekday" in fields(chat(client, "any weekday evening", s, P)).get("days", "")


@pytest.mark.parametrize("msg", ["nope, still no tour, thanks", "no tour please", "I don't want a tour",
                                 "no quiero una visita"])
def test_no_tour_gets_an_answer_not_the_welcome(client, msg):
    r = chat(client, msg, sid(), P)
    assert "Welcome" not in r["reply"] and kind(r) is None


@pytest.mark.parametrize("msg", ["what's the status of the pool renovation?", "any update on the gym renovation?",
                                 "status of the lobby construction", "news about the clubhouse renovation?"])
def test_community_projects_are_not_repair_status_or_renewal(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert not r.get("status_items") and "Renewal" not in json.dumps(r.get("action") or {})


def test_a_foreign_typed_reference_is_never_cited(client):
    s = sid()
    sent_repair(client, s)
    r = chat(client, "cancel DEMO-WO-1009", s, "R001")
    assert "DEMO-WO-1009" not in fields(r)["topic"] and "couldn't match" in r["reply"]


def test_a_change_targets_the_original_request_not_the_last_note(client):
    s = sid()
    ref = sent_repair(client, s)
    chat(client, "actually call me first before they come in", s, "R001")
    press_send(client, s, "staff_handoff", "R001")
    r = chat(client, "also it's the left cabinet", s, "R001")
    assert ref in json.dumps(r["action"]) and "DEMO-TASK" not in fields(r)["topic"]


# ---- final round -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["take fernhill off the list", "cross off fernhill", "remove fernhill from the list",
                                 "drop fernhill from the list", "cross fernhill out", "take fernhill apartments off",
                                 "remove fernhill", "quita fernhill"])
def test_list_removal_keeps_the_other_option(client, msg):
    s = sid()
    chat(client, "I'd like to tour fernhill or birchwood", s, P)
    assert fields(chat(client, msg, s, P))["area"] == "Birchwood Commons"


@pytest.mark.parametrize("msg", ["tour in jacksonville next sunday morning", "can I see a place in boston on saturday",
                                 "tour in chicago this weekend", "visit near miami friday afternoon",
                                 "quiero visitar en houston el sábado", "tour in denver next week",
                                 "looking to tour in seattle tomorrow", "a tour in phoenix on monday please"])
def test_unknown_city_is_answered_honestly_and_keeps_the_day(client, msg):
    s = sid()
    r = chat(client, msg, s, "")
    assert kind(r) == "tour_request" and ("this demo" in r["reply"] or "demostración" in r["reply"])
    assert fields(r).get("days")
    r2 = chat(client, "send it", s, "")
    assert "missing" in r2["reply"] or "falta" in r2["reply"]


@pytest.mark.parametrize("msg", ["tour in ann arbor next sunday", "tour in the morning", "tour in person please",
                                 "tour in orlando saturday"])
def test_unknown_city_near_misses(client, msg):
    assert "this demo" not in chat(client, msg, sid(), "")["reply"]


@pytest.mark.parametrize("msg", ["no visit please", "still not looking to visit", "no tour", "not planning to visit",
                                 "no viewings, thanks", "no quiero visitar", "I'm not looking to tour", "no tours"])
def test_no_visit_suppresses_the_tour_for_the_session(client, msg):
    s = sid()
    chat(client, msg, s, P)
    r = chat(client, "I'm moving next month, what's available?", s, P)
    assert kind(r) != "tour_request" and "Which days" not in r["reply"]


@pytest.mark.parametrize("msg", ["please dont make a new ticket, the old one was never finished",
                                 "don't open another ticket", "do not create a new request, the first one isn't done",
                                 "no new ticket please, the old one wasn't fixed"])
def test_no_new_ticket_follows_up_on_the_earlier_request(client, msg):
    s = sid()
    ref = sent_repair(client, s)
    chat(client, "my kitchen faucet drips", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"]


@pytest.mark.parametrize("msg", ["been waiting since monday for someone to fix my sink", "still waiting on the sink",
                                 "waiting for maintenance since yesterday", "sigo esperando lo del fregadero"])
def test_waiting_after_send_follows_up_on_that_request(client, msg):
    s = sid()
    ref = sent_repair(client, s)
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"] and len(recs(s)) == 1


@pytest.mark.parametrize("msg", ["scratch the light repair, I only need the phone call",
                                 "I'll fix the light myself, but I still want the call",
                                 "I'll handle the light myself, just the callback please",
                                 "I can take care of the light, keep the call"])
def test_more_cancel_the_repair_keep_the_call(client, msg):
    s = sid()
    chat(client, "the hallway light in my apartment is out and can someone from leasing call me about my lease", s,
         "R001")
    assert kind(chat(client, msg, s, "R001")) == "staff_handoff"


@pytest.mark.parametrize("msg,win,issue", [
    ("only mornings work for visits. the bedroom closet door is off the track", "Mornings", "closet door"),
    ("evenings are best for visits. my kitchen faucet drips", "Evenings", "faucet"),
    ("visits after 5pm please, the bathroom fan is broken", "After 5pm", "fan"),
    ("weekends only for visits. the dishwasher won't drain", "Weekends", "dishwasher")])
def test_visit_window_in_the_first_message(client, msg, win, issue):
    f = fields(chat(client, msg, sid(), "R001"))
    assert win.lower() in f["entry_window"].lower() and issue in f["issue"].lower()
    assert "visit" not in f["issue"].lower()


@pytest.mark.parametrize("msg", ["doorbell stopped working", "garbage disposal stopped working", "intercom won't work",
                                 "my peephole broke", "the buzzer died", "doorknob is loose", "smoke alarm stopped "
                                 "working", "towel bar fell off"])
def test_named_fixture_is_not_vague(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert "What is it that isn't working" not in r["reply"] and not fields(r)["issue"].startswith("Door:")


@pytest.mark.parametrize("msg", ["you have my permission to come in", "you've got my ok to enter",
                                 "tienen mi permiso para entrar", "come on in"])
def test_more_entry_permission(client, msg):
    s = sid()
    chat(client, "my kitchen sink is leaking", s, "R001")
    assert fields(chat(client, msg, s, "R001")).get("entry", "").startswith(("Yes", "Sí"))


@pytest.mark.parametrize("msg", ["unrelated question: when is rent due", "quick question: is there a gym",
                                 "question: when is trash day", "pregunta: ¿cuándo se paga la renta?"])
def test_side_question_after_send_gets_an_honest_answer(client, msg):
    s = sid()
    sent_repair(client, s)
    r = chat(client, msg, s, "R001")
    assert "I can help with repair requests" not in r["reply"]


@pytest.mark.parametrize("msg", ["is the leasing office open on sundays", "what are the office hours",
                                 "is the office open saturday?", "¿la oficina abre los domingos?"])
def test_office_hours_question_keeps_the_tour_draft_unchanged(client, msg):
    s = sid()
    chat(client, "I'd like to tour Heron Lake", s, P)
    r = chat(client, msg, s, P)
    assert kind(r) == "tour_request" and "days" not in fields(r)


@pytest.mark.parametrize("msg", ["my washing machine died mid cycle with water still in it",
                                 "the washing machine won't spin", "dryer stopped heating", "la lavadora no funciona"])
def test_laundry_is_inferred(client, msg):
    assert fields(chat(client, msg, sid(), "R001")).get("location") in ("Laundry area", "Lavandería", "Área de lavado")


@pytest.mark.parametrize("msg", ["please have them bring a ladder, it's high up", "add: it started after the storm",
                                 "they'll need to bring a ladder", "it started last week"])
def test_more_details_after_send_are_change_notes(client, msg):
    s = sid()
    ref = sent_repair(client, s)
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"] + json.dumps(r["action"])


def test_unmatched_reference_note_links_no_record(client):
    s = sid()
    sent_repair(client, s)
    r = chat(client, "cancel DEMO-WO-1033", s, "R001")
    f = fields(r)
    assert "DEMO-WO-1033" not in f["topic"] and "earlier" not in f
