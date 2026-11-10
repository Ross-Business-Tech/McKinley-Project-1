"""Sprint 5 conversation fixes for the simulator findings D-8..D-22 (docs/design/MOBILE_UX_AUDIT.md).

Deterministic planner + mock only. Each planner branch gets a behaviour test; each new detector gets positive and
negative cases.
"""

import pytest

from app.intake import (
    asks_for_manager,
    asks_how_reached,
    channel_said,
    existing_request_words,
    extract_days,
    extract_move_in,
    flexible_answer,
    is_after_send_question,
    is_bare_ok,
    is_lease_break,
    is_lost_or_frustrated_with_chat,
    is_security_repair,
    is_staff_request,
    matches_words,
    says_repeat_es,
)


def chat(client, msg, session, persona="R001"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def confirm(client, session, kind, persona="R001"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


NEVER = ("has been notified", "was notified", "staff were notified", "is booked", "is confirmed", "we'll call you")


def honest(reply):
    return not any(p in reply.lower() for p in NEVER)


# ---- detectors: positive and negative ---------------------------------------------------------------------


@pytest.mark.parametrize("msg", ["what do I do now??", "this isn't helping", "this isnt helping", "???",
                                 "i already told you", "you're useless", "this is useless", "I'm so confused",
                                 "no me ayuda", "ya le dije"])
def test_lost_detector_positive(msg):
    assert is_lost_or_frustrated_with_chat(msg)


@pytest.mark.parametrize("msg", ["the dishwasher isn't working", "what do i do with my trash?", "is it useful to "
                                 "reset the breaker", "are you even listening", "the light is not helping me see",
                                 "what?"])
def test_lost_detector_negative(msg):
    assert not is_lost_or_frustrated_with_chat(msg)


@pytest.mark.parametrize("msg", ["actually yes I want a person", "can I talk to someone", "manager please",
                                 "the manager", "I want to talk to the manager", "connect me with someone",
                                 "Talk to a person", "Ask the leasing team", "quiero hablar con alguien"])
def test_person_request_positive(msg):
    assert is_staff_request(msg)


@pytest.mark.parametrize("msg", ["I need someone to fix my sink", "i want a person to fix it", "the kitchen sink "
                                 "is leaking", "how many people can live in a 2 bed"])
def test_person_request_negative(msg):
    assert not is_staff_request(msg)


def test_manager_detector():
    assert asks_for_manager("manager please") and asks_for_manager("get me whoever is in charge")
    assert not asks_for_manager("can I talk to someone")


@pytest.mark.parametrize("msg", ["will someone email me?", "will someone call me?", "when will they confirm?",
                                 "how will I know?", "did my tour get confirmed?"])
def test_after_send_followup_positive(msg):
    assert is_after_send_question(msg)


@pytest.mark.parametrize("msg", ["I will call the office myself", "someone left the gate open"])
def test_after_send_followup_negative(msg):
    assert not is_after_send_question(msg)


def test_move_in_and_tour_days_are_separate_fields():  # D-8
    m = "I'm moving to Ann Arbor next month… want to tour this week"
    assert extract_move_in(m) == "Next month" and extract_days(m) == "This week"
    assert extract_move_in("moving next week") == "Next week" and extract_days("moving next week") is None
    assert extract_move_in("tour next week") is None and extract_days("tour next week") == "Next week"
    assert extract_move_in("Looking to move in March 1 in Ann Arbor") == "March 1"


@pytest.mark.parametrize("msg,hit", [("I want to move out early", True), ("can I break my lease?", True),
                                     ("terminate my lease", True), ("romper mi contrato", True),
                                     ("I want to renew my lease", False), ("when is move-in day", False)])
def test_lease_break_detector(msg, hit):
    assert is_lease_break(msg) is hit


@pytest.mark.parametrize("msg,hit", [("door lock is broken", True), ("front door won't lock", True),
                                     ("the deadbolt is jammed", True), ("the closet door is off its track", False),
                                     ("I'm locked out", False), ("the fridge door won't close", False),
                                     ("the bathroom sink is leaking", False)])
def test_security_repair_detector(msg, hit):
    assert is_security_repair(msg) is hit


def test_existing_request_reference_detector():
    assert existing_request_words("the one for the sink leak") == ["sink", "leak"]
    assert existing_request_words("the AC one") == ["ac"]
    assert existing_request_words("the kitchen sink is leaking") == []
    assert matches_words(["sink", "leak"], "The kitchen sink is leaking")
    assert matches_words(["ac"], "AC rattling") and not matches_words(["sink"], "AC rattling")


def test_small_detectors():
    assert is_bare_ok("ok") and is_bare_ok("Okay.") and not is_bare_ok("yes") and not is_bare_ok("ok you can enter")
    assert channel_said("text me first") == "text" and channel_said("call me first") == "call"
    assert channel_said("the text on the card is wrong") is None
    assert flexible_answer("whenever") and flexible_answer("any day works") and not flexible_answer("saturday")
    assert says_repeat_es("ya pasó antes") and says_repeat_es("gotea otra vez") and says_repeat_es("de nuevo")
    assert not says_repeat_es("el baño gotea")
    assert asks_how_reached("how will you contact me?") and asks_how_reached("you can reach me at [email redacted]")
    assert not asks_how_reached("how do I reach the pool?")


# ---- D-12: lost or frustrated -------------------------------------------------------------------------------


def test_lost_with_open_card_apologises_once_restates_step_and_offers_a_person(client):
    chat(client, "the kitchen sink is leaking", "l1")
    r = chat(client, "what do I do now??", "l1")
    assert r["reply"].startswith("I'm sorry") and "entry permission" in r["reply"]
    assert "Talk to a person" in r["suggested_replies"] and r["action"]["kind"] == "maintenance_request"
    assert "Which room" not in r["reply"] and honest(r["reply"])
    r = chat(client, "this isn't helping", "l1")  # second time: the note, carrying the repair details
    assert r["action"]["kind"] == "staff_handoff" and "sink" in fields(r)["earlier"].lower()
    assert "nobody is notified" in r["reply"] and not r["records_created"]
    assert r["reply"].count("sorry") <= 1


def test_lost_without_card_prepares_a_note_without_questions(client):
    r = chat(client, "this is useless", "l2")
    assert r["action"]["kind"] == "staff_handoff" and r["action"]["stage"] == "ready"
    assert "?" not in r["reply"] and "nobody is notified" in r["reply"] and not r["records_created"]


def test_lost_prospect_keeps_the_tour_card(client):
    chat(client, "I want to tour Heron Lake", "l3", persona=None)
    r = chat(client, "???", "l3", persona=None)
    assert r["action"]["kind"] == "tour_request" and "preferred days" in r["reply"]


def test_two_unproductive_turns_in_a_row_offer_a_person(client):
    chat(client, "the kitchen sink is leaking", "u1")
    r2 = chat(client, "hmm", "u1")  # nothing new, the same question again: unproductive #1
    assert "may they enter" in r2["reply"] and not r2["reply"].startswith("I'm sorry")
    r3 = chat(client, "the weather is nice today", "u1")  # unproductive #2 -> recovery, card kept
    assert r3["reply"].startswith("I'm sorry") and "Talk to a person" in r3["suggested_replies"]
    assert r3["action"]["kind"] == "maintenance_request"


def test_a_productive_turn_resets_the_unproductive_streak(client):
    chat(client, "the kitchen sink is leaking", "u2")
    chat(client, "hmm", "u2")
    r = chat(client, "yes you can come in", "u2")
    assert r["action"]["stage"] == "ready" and not r["reply"].startswith("I'm sorry")


# ---- D-11: a person in any state ----------------------------------------------------------------------------


def test_person_request_right_after_declining_a_card(client):
    chat(client, "the bathroom fan is rattling", "p1")
    assert "haven't sent" in chat(client, "no thanks, cancel it", "p1")["reply"]
    r = chat(client, "actually yes I want a person", "p1")
    assert r["action"]["kind"] == "staff_handoff" and "fan" in fields(r).get("earlier", "").lower()
    assert r["action"]["kind"] != "maintenance_request"  # not the declined card restored


def test_manager_request_from_a_prospect_goes_to_management(client):
    chat(client, "I want to tour Heron Lake", "p2", persona=None)
    r = chat(client, "manager please", "p2", persona=None)
    assert r["action"]["kind"] == "staff_handoff" and r["handoff"]["team"] == "management"
    assert "management" in fields(r)["topic"].lower()


def test_soft_person_request_from_a_prospect_stays_with_leasing(client):
    r = chat(client, "can I talk to someone", "p3", persona=None)
    assert r["action"]["kind"] == "staff_handoff" and r["handoff"]["team"] == "leasing"


# ---- D-9 / D-10: after sending, and during an incomplete draft ----------------------------------------------


def test_after_repair_sent_followups_answer_about_that_request(client):
    chat(client, "the kitchen faucet is dripping", "s1")
    chat(client, "yes you can come in", "s1")
    ref = confirm(client, "s1", "maintenance_request")["record"]["id"]
    for q in ("will someone call me?", "when will they confirm?", "did it go through?"):
        r = chat(client, q, "s1")
        assert ref in r["reply"] and "faucet" in r["reply"].lower() and "nobody is notified" in r["reply"], q
        assert r["action"] is None and not r["records_created"] and honest(r["reply"])


def test_after_tour_sent_email_question_says_not_a_booking(client):
    chat(client, "tour Heron Lake saturday morning", "s2", persona=None)
    ref = confirm(client, "s2", "tour_request", persona=None)["record"]["id"]
    r = chat(client, "will someone email me?", "s2", persona=None)
    assert ref in r["reply"] and "not a booking" in r["reply"] and "Heron Lake" in r["reply"]
    assert "nobody is notified" in r["reply"] and "Happy to help" not in r["reply"]


def test_did_it_go_through_during_incomplete_draft_lists_what_is_missing(client):
    chat(client, "the bathroom fan is rattling", "s3")
    r = chat(client, "did it go through?", "s3")
    assert "not sent yet" in r["reply"] and "entry permission" in r["reply"] and "press Send" not in r["reply"]


def test_did_it_go_through_with_ready_draft_says_press_send(client):
    chat(client, "the bathroom fan is rattling", "s4")
    chat(client, "yes you can come in", "s4")
    r = chat(client, "did it go through?", "s4")
    assert "press Send" in r["reply"] and r["action"]["stage"] == "ready"


# ---- D-8: move-in vs tour days; no third ask ----------------------------------------------------------------


def test_tour_timing_and_move_in_are_separate_on_the_card(client):
    r = chat(client, "I'm moving to Ann Arbor next month… want to tour this week", "t1", persona=None)
    f = fields(r)
    assert f["move_in"] == "Next month" and f["days"] == "This week"


def test_tour_question_is_not_asked_a_third_time(client):
    chat(client, "I want to tour Heron Lake", "t2", persona=None)
    r2 = chat(client, "hmm", "t2", persona=None)
    assert "Which days" in r2["reply"]
    r3 = chat(client, "not sure", "t2", persona=None)
    assert "Which days" not in r3["reply"] and "leasing team to ask" in r3["reply"]
    assert "time of day" in r3["reply"].lower()


def test_whenever_answers_the_days_question(client):
    chat(client, "I want to tour Heron Lake", "t3", persona=None)
    r = chat(client, "whenever", "t3", persona=None)
    assert fields(r)["days"] == "Any day (flexible)" and "Preferred days: Any day" in r["reply"]


# ---- D-14 / D-13 / D-15 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("n,msg", [(1, "I want to move out early"), (2, "can I break my lease?")])
def test_early_move_out_is_its_own_topic_not_renewal(client, n, msg):
    r = chat(client, msg, f"lb{n}")
    assert r["action"]["kind"] == "staff_handoff" and "lease break" in fields(r)["topic"].lower()
    assert "renewal" not in r["reply"].lower() and r["handoff"]["team"] == "leasing"


def test_door_lock_offers_front_door_and_is_high_priority(client):
    r = chat(client, "door lock is broken", "d1")
    assert r["suggested_replies"][0] == "Front door" and "front (entry) door" in r["reply"]
    assert "security" in fields(r)["priority_note"].lower()
    r = chat(client, "Front door", "d1")
    assert fields(r)["location"] == "Front door"


def test_front_door_wont_lock_is_high_priority_with_location(client):
    r = chat(client, "front door won't lock", "d2")
    assert fields(r)["location"] == "Front door" and "security" in fields(r)["priority_note"].lower()


def test_closet_door_is_not_a_security_repair(client):
    r = chat(client, "the bedroom closet door is off its track", "d3")
    assert "security" not in fields(r).get("priority_note", "").lower()


def test_reference_to_an_open_request_answers_about_it(client):
    chat(client, "the kitchen sink is leaking", "e1")
    chat(client, "yes you can come in", "e1")
    ref = confirm(client, "e1", "maintenance_request")["record"]["id"]
    chat(client, "check my requests", "e1")
    r = chat(client, "the one for the sink leak", "e1")
    assert ref in r["reply"] and r["action"] is None and not r["records_created"]
    r = chat(client, "the AC one", "e1")
    assert "I008" in r["reply"] and r["action"] is None


def test_reference_without_a_match_starts_a_clean_new_request(client):
    r = chat(client, "the one for the window crack", "e2")
    assert r["action"]["kind"] == "maintenance_request" and "the one for" not in fields(r)["issue"].lower()


# ---- B1: tour card stages, corrections, contact route -------------------------------------------------------


def test_tour_card_stages_and_corrections_say_what_changed(client):
    r = chat(client, "tour Heron Lake saturday", "b1", persona=None)
    assert r["action"]["stage"] == "collecting" and fields(r)["contact_route"] == "Not collected in this prototype"
    r = chat(client, "morning", "b1", persona=None)
    assert r["action"]["stage"] == "ready" and "Time of day: Morning" in r["reply"]
    r = chat(client, "actually make it sunday", "b1", persona=None)
    assert "Updated: Preferred days → Sunday" in r["reply"] and fields(r)["days"] == "Sunday"
    r = chat(client, "actually Birchwood", "b1", persona=None)
    assert "Updated: Community or city → Birchwood Commons" in r["reply"]
    res = confirm(client, "b1", "tour_request", persona=None)
    assert res["ok"] and res["action"]["stage"] == "submitted"
    assert res["record"]["status_label"] == "Requested; leasing team to confirm a time"
    assert "booked" not in res["message"].lower() and "isn't a booking" in res["message"]


def test_cancelled_tour_card_is_cleared(client):
    chat(client, "tour Heron Lake saturday morning", "b2", persona=None)
    r = chat(client, "never mind", "b2", persona=None)
    assert r["action"] is None and r["action_cleared"] == "tour_request"
    assert not confirm(client, "b2", "tour_request", persona=None)["ok"]


def test_prospect_asking_how_they_are_reached_gets_an_honest_answer(client):
    chat(client, "tour Heron Lake saturday", "b3", persona=None)
    r = chat(client, "how will you contact me?", "b3", persona=None)
    assert "don't collect phone numbers or emails in chat" in r["reply"]
    assert r["action"]["kind"] == "tour_request"
    r = chat(client, "you can reach me at alex@example.com", "b3", persona=None)
    assert "alex@example.com" not in str(r) and "don't collect" in r["reply"]


def test_prospect_profile_contact_route_label(client):
    r = chat(client, "I want to tour Heron Lake saturday", "b4", persona="P-RELOCATE-AA")
    assert fields(r)["contact_route"] == "Not collected in this prototype"  # fixture profiles have no contact


# ---- D-21: floor plans and the tour pitch ---------------------------------------------------------------------


def test_floor_plan_questions_are_honest_and_the_tour_pitch_is_not_repeated(client):
    r1 = chat(client, "floor plans?", "f1", persona=None)
    assert "verified floor plans" in r1["reply"] and r1["action"] is None
    r2 = chat(client, "how big are the 2 beds", "f1", persona=None)
    assert "verified floor plans" in r2["reply"] and r2["action"] is None  # not a tour form
    r3 = chat(client, "do you allow pets?", "f1", persona=None)
    for r in (r2, r3):
        assert "Would you like to request a tour" not in r["reply"]
        assert "leasing team" in r["reply"]


# ---- small: D-17, D-20, D-16, D-19, D-22 ----------------------------------------------------------------------


def test_bare_ok_to_entry_question_asks_to_confirm(client):
    chat(client, "the bathroom fan is rattling", "o1")
    r = chat(client, "ok", "o1")
    assert "Just to check" in r["reply"] and "entry" not in fields(r)
    assert r["suggested_replies"] == ["Yes, you can enter", "Contact me first"]
    r = chat(client, "yes", "o1")
    assert fields(r)["entry"].startswith("Yes")


def test_second_bare_ok_takes_the_conservative_choice(client):
    chat(client, "the bathroom fan is rattling", "o2")
    chat(client, "ok", "o2")
    r = chat(client, "ok", "o2")
    assert fields(r)["entry"].startswith("Contact me first")


def test_channel_said_in_chat_overrides_profile_on_card(client):
    chat(client, "the bathroom sink is clogged", "c1", persona="R003")  # R003 prefers text on file
    r = chat(client, "call me first", "c1", persona="R003")
    f = {x["key"]: x for x in r["action"]["fields"]}
    assert f["contact"]["value"] == "Prefers call" and f["contact"]["source"] == "you_said"


def test_later_symptom_is_added_to_the_issue(client):
    chat(client, "the dishwasher wont drain", "y1", persona="R003")
    r = chat(client, "now theres water on the floor too", "y1", persona="R003")
    assert "water on the floor" in fields(r)["issue"]


def test_spanish_repeat_words_raise_priority(client):
    r = chat(client, "el lavabo del baño gotea de nuevo", "es1", persona="R003")
    assert r["language"] == "es" and fields(r)["priority_note"].startswith(("Prioridad alta", "Problema repetido"))
    r = chat(client, "el lavabo del baño gotea", "es2", persona="R003")
    assert "priority_note" not in fields(r)


def test_first_tour_value_is_not_called_an_update(client):
    chat(client, "I want to tour Heron Lake", "w1", persona=None)
    r = chat(client, "saturday", "w1", persona=None)
    assert "Preferred days: Saturday" in r["reply"] and "Updated" not in r["reply"]


def test_more_tour_talk_after_sending_does_not_open_a_duplicate(client):
    chat(client, "tour Heron Lake saturday morning", "x1", persona=None)
    ref = confirm(client, "x1", "tour_request", persona=None)["record"]["id"]
    r = chat(client, "sure a tour is fine", "x1", persona=None)
    assert ref in r["reply"] and "already saved" in r["reply"] and r["action"] is None
    assert "Which city" not in r["reply"]


def test_second_community_tour_carries_days_and_time(client):
    chat(client, "tour Heron Lake saturday morning", "x2", persona=None)
    assert confirm(client, "x2", "tour_request", persona=None)["ok"]
    r = chat(client, "I'd also like to tour Birchwood", "x2", persona=None)
    f = fields(r)
    assert f["area"] == "Birchwood Commons" and f["days"] == "Saturday" and f["time"] == "Morning"
    assert r["action"]["stage"] == "ready" and "Which days" not in r["reply"]


def test_new_day_after_tour_sent_becomes_a_change_note(client):
    chat(client, "tour Heron Lake saturday morning", "x3", persona=None)
    ref = confirm(client, "x3", "tour_request", persona=None)["record"]["id"]
    r = chat(client, "thursday around 4?", "x3", persona=None)
    assert r["action"]["kind"] == "staff_handoff" and ref in fields(r)["topic"]
    assert "thursday" in fields(r)["message"].lower()
