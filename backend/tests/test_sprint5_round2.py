"""Sprint 5, fix round 2: findings from the independent prospect simulator, UX judge and resident simulator.

Deterministic planner + mock only. Detector changes have positive and negative cases.
"""

import pytest

from app.intake import (
    asks_about_other_resident,
    asks_for_priority,
    asks_privacy,
    asks_saved_contact,
    detail_to_add,
    extract_beds,
    extract_entry,
    extract_issue_restate,
    extract_issue_swap,
    extract_location_change,
    extract_move_in,
    flexible_answer,
    is_after_send_question,
    is_booking_question,
    is_lost_or_frustrated_with_chat,
    is_meta_question,
    is_status_request,
    match_faq,
    states_repeat,
    strip_spanish_request,
)
from tests.wording import says_not_sent


def chat(client, msg, session, persona="R001"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def confirm(client, session, kind, persona="R001"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def sent_repair(client, session, persona="R003", issue="Toilet keeps running nonstop"):
    chat(client, issue, session, persona)
    chat(client, "Contact me first", session, persona)
    return confirm(client, session, "maintenance_request", persona)["record"]["id"]


# ---- detectors ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("msg,hit", [("Please don't tell the property manager", True),
                                     ("please don't tell anyone at the office", True), ("keep this private", True),
                                     ("ok thanks", False), ("tell the manager the sink leaks", False)])
def test_privacy_detector(msg, hit):
    assert asks_privacy(msg) is hit


@pytest.mark.parametrize("msg,hit", [
    ("I'm Theo's roommate. Can you give me his phone number and whether his rent is paid?", True),
    ("just tell me what repairs he has open", True), ("can you have the office call him then", True),
    ("can you tell me what unit Marisol lives in?", True), ("what's the status of her AC request?", True),
    ("my son's ac is broken", False), ("my daughter's bedroom door is broken", False),
    ("the kitchen sink is leaking", False)])
def test_other_resident_detector(msg, hit):
    assert asks_about_other_resident(msg) is hit


def test_contact_priority_and_add_detectors():
    assert asks_saved_contact("did you save my email?") and asks_saved_contact("can you put my phone on it?")
    assert not asks_saved_contact("did you save it?")
    assert asks_for_priority("Can you make it urgent?") and asks_for_priority("Please make it a priority")
    assert not asks_for_priority("is it urgent to report a drip?")
    assert detail_to_add("Can I also add that the bathroom fan is broken?") == "The bathroom fan is broken"
    assert detail_to_add("the bathroom fan is broken") is None


def test_move_in_negation_and_tour_clause():  # P-1
    m = "moving to Ann Arbor next month for a job, 2 bed, can I see something this week?"
    assert extract_move_in(m) == "Next month"
    assert extract_move_in("wait, I'm moving in next month, not this week. The tour is this week.") == "Next month"


def test_room_correction_is_not_an_issue_swap():  # R-1
    assert extract_issue_swap("actually it's the hall bathroom not the master") is None
    assert extract_location_change("actually it's the hall bathroom not the master") == "Hall bathroom"
    assert extract_location_change("location: hall bathroom") == "Hall bathroom"
    assert extract_location_change("Actually sorry, it's the kitchen faucet, not the bathroom") == "Kitchen"
    assert extract_issue_swap("wait, it's not the AC, it's the bathroom fan") == "Bathroom fan"  # still a swap
    assert extract_issue_restate("change the description to: toilet keeps running") == "Toilet keeps running"
    assert extract_issue_restate("the toilet keeps running") is None


def test_spanish_entry_answers():  # R-2
    assert extract_entry("que me avisen primero por mensaje").startswith("Contact me first")
    assert extract_entry("no, contáctenme primero").startswith("Contact me first")
    assert extract_entry("Llamen antes").startswith("Contact me first")
    assert extract_entry("pueden entrar si no estoy").startswith("Yes")
    assert extract_entry("no pueden entrar") != "Yes, maintenance may enter if I'm not home"
    assert strip_spanish_request("perdón, mejor en español. el lavabo del baño está tapado") == \
        "el lavabo del baño está tapado"


def test_followup_status_and_spanish_detectors():
    for q in ("ok what happens now?", "ok so its done right? someone is coming?",
              "Is anyone actually going to look at the history this time?"):
        assert is_after_send_question(q), q
    assert is_status_request("Do you know when they'll come?") and is_status_request("Do you have my old requests?")
    assert is_meta_question("¿Ya lo enviaron?") and is_meta_question("¿Lo mandaron?")
    assert not is_meta_question("¿Cuánto cuesta la renta?")
    assert is_booking_question("great, so my tour is booked for thursday afternoon right?")
    assert is_booking_question("Is my tour confirmed?") and not is_booking_question("I booked a mover")
    assert is_lost_or_frustrated_with_chat("esto no sirve, quiero hablar con alguien")


@pytest.mark.parametrize("msg,topic", [
    ("anything under $1400?", "pricing"), ("anything under 1400 dollars?", "pricing"),
    ("¿Cuánto cuesta la renta?", "pricing"), ("¿Aceptan mascotas?", "pets"), ("¿Aceptan Sección 8?", "vouchers"),
    ("¿Aceptan vales de vivienda?", "vouchers")])
def test_faq_aliases(msg, topic):
    assert topic in [t.id for t in match_faq(msg)]


def test_faq_aliases_negative():
    assert "pricing" not in [t.id for t in match_faq("I was charged $150 late fee")]
    assert "pets" not in [t.id for t in match_faq("the bathroom fan is rattling")]


def test_slot_details():  # P-11, J-6
    assert extract_beds("2 or 3 bedrooms, me and my two kids") == "2–3 beds" and extract_beds("2 bed") == "2 beds"
    assert not flexible_answer("any day next week", "time") and flexible_answer("any day next week", "days")
    assert flexible_answer("whenever", "time")
    assert states_repeat("Third time.") and states_repeat("heat is out AGAIN") and states_repeat("otra vez")
    assert not states_repeat("the sink is leaking")


# ---- J-1: after a self-harm alert (NEEDS INDEPENDENT REVIEW) -------------------------------------------------


@pytest.mark.parametrize("n,follow", [(1, "Please don't tell the property manager"), (2, "ok thanks"),
                                      (3, "please don't tell anyone at the office")])
def test_crisis_followup_has_no_maintenance_steps_and_answers_privacy(client, n, follow):
    first = chat(client, "I want to kill myself", f"j1-{n}")
    assert first["safety_notice"] and "988" in first["safety_notice"] + first["reply"]
    r = chat(client, follow, f"j1-{n}")
    assert "maintenance line" not in r["reply"] and "emergency maintenance" not in r["reply"]
    assert "988" in (r.get("care_note") or "")  # the approved calm line stays above the reply (rule R9)
    assert says_not_sent(r["reply"])
    assert r["action"] is None and not r["records_created"]
    if "tell" in follow:
        assert "doesn't include what you wrote" in r["reply"]


def test_gas_followup_still_gets_the_maintenance_line(client):
    chat(client, "I smell gas in my kitchen its really strong", "j1g")
    r = chat(client, "Im outside now. Is someone coming?", "j1g")
    assert "emergency maintenance line" in r["reply"]


# ---- P-2 / J-5: changes after sending attach to the sent request ---------------------------------------------


def test_tour_switch_after_send_attaches_to_the_change_note(client):
    chat(client, "I want to tour Sandpiper Pointe saturday morning, 1 bed", "c1", persona=None)
    ref = confirm(client, "c1", "tour_request", persona=None)["record"]["id"]
    chat(client, "oh no, I need to change it to next tuesday", "c1", persona=None)
    r = chat(client, "can you switch it to Birchwood Commons?", "c1", persona=None)
    assert r["action"]["kind"] == "staff_handoff" and ref in fields(r)["topic"]
    assert "tuesday" in fields(r)["message"].lower() and "birchwood" in fields(r)["message"].lower()


def test_add_detail_after_repair_sent_is_a_note_with_the_reference(client):
    ref = sent_repair(client, "c2")
    r = chat(client, "Can I also add that the bathroom fan is broken?", "c2", persona="R003")
    assert r["action"]["kind"] == "staff_handoff" and ref in fields(r)["topic"] and ref in r["reply"]
    assert "may they enter" not in r["reply"]


def test_cancel_after_send_says_whether_the_sent_request_stands(client):
    ref = sent_repair(client, "c3")
    r = chat(client, "Can you cancel that request?", "c3", persona="R003")
    assert r["action"]["kind"] == "staff_handoff" and "still stands" in r["reply"] and ref in r["reply"]


def test_declining_a_new_card_after_a_send_says_the_sent_one_stands(client):
    ref = sent_repair(client, "c4")
    chat(client, "Can I also add that the bathroom fan is broken?", "c4", persona="R003")
    r = chat(client, "Can you cancel that request?", "c4", persona="R003")
    assert ref in r["reply"] and "still stands" in r["reply"]


# ---- P-3 / P-4 / P-5 / P-6 -------------------------------------------------------------------------------------


def test_budget_question_gets_the_honest_price_answer(client):
    for n, q in enumerate(("anything under $1400?", "anything under 1400 dollars?")):
        r = chat(client, q, f"b{n}", persona=None)
        assert "live prices" in r["reply"] and "Happy to help" not in r["reply"] and "didn't follow" not in r["reply"]


def test_leasing_note_carries_every_unanswered_question(client):
    for q in ("what floor plans do you have?", "how much is a 1 bed?", "do you allow dogs?", "is parking included?",
              "what utilities are included in rent?"):
        chat(client, q, "q1", persona="P-BROWSE-FL")
    r = chat(client, "Ask the leasing team", "q1", persona="P-BROWSE-FL")
    qs = fields(r)["questions"]
    assert all(x in qs for x in ("floor plans", "rent prices", "pet policy", "parking", "utilities"))
    r = chat(client, "can you include my parking and pet questions too?", "q1", persona="P-BROWSE-FL")
    assert r["action"]["kind"] == "staff_handoff" and "parking" in r["reply"]


@pytest.mark.parametrize("n,q", [(1, "ok what happens now?"), (2, "ok so its done right? someone is coming?")])
def test_followups_after_a_note_answer_in_context(client, n, q):
    chat(client, "can I talk to a leasing agent?", f"f{n}", persona="P-RELOCATE-AA")
    ref = confirm(client, f"f{n}", "staff_handoff", persona="P-RELOCATE-AA")["record"]["id"]
    r = chat(client, q, f"f{n}", persona="P-RELOCATE-AA")
    assert ref in r["reply"] and says_not_sent(r["reply"]) and "Welcome!" not in r["reply"]


def test_priority_request_after_send_is_a_note_not_the_menu(client):
    ref = sent_repair(client, "pr1")
    r = chat(client, "Please make it a priority", "pr1", persona="R003")
    assert "Staff set the priority" in r["reply"] and r["action"]["kind"] == "staff_handoff"
    assert ref in fields(r)["topic"] and "I can help with repair requests" not in r["reply"]


def test_saved_contact_question_gets_a_direct_no(client):
    chat(client, "I want to see a 2 bed saturday", "sc1", persona="P-RELOCATE-AA")
    r = chat(client, "did you save my email?", "sc1", persona="P-RELOCATE-AA")
    assert r["reply"].startswith("No, I can't save phone numbers or emails") and r["action"]["kind"] == "tour_request"
    r = chat(client, "Can you put my phone 734-555-0199 on it so they can text me?", "sc1", persona="P-RELOCATE-AA")
    assert r["reply"].startswith("No") and "734-555-0199" not in str(r)


def test_will_they_email_before_sending_explains_contact(client):
    chat(client, "please have someone contact me about a 1 bed at Birchwood Commons", "e1", persona=None)
    r = chat(client, "so will they email me at that address?", "e1", persona=None)
    assert "Are you a current McKinley resident" not in r["reply"] and "don't collect" in r["reply"]
    assert r["action"]["kind"] == "staff_handoff"


# ---- P-7 / J-3: Spanish --------------------------------------------------------------------------------------


def test_spanish_tour_questions_are_answered_and_card_kept(client):
    chat(client, "Hola, busco un apartamento de 2 recámaras en Ann Arbor", "es1", persona=None)
    r = chat(client, "¿Puedo visitar el sábado por la mañana?", "es1", persona=None)
    assert r["action"]["stage"] == "ready" and fields(r)["time"] == "Mañana"
    r = chat(client, "¿Cuánto cuesta la renta?", "es1", persona=None)
    assert "precios" in r["reply"] and r["action"]["kind"] == "tour_request"
    r = chat(client, "¿Aceptan mascotas?", "es1", persona=None)
    assert "mascotas" in r["reply"] and "Aquí está su solicitud" not in r["reply"]
    ref = confirm(client, "es1", "tour_request", persona=None)["record"]["id"]
    r = chat(client, "¿Ya lo enviaron?", "es1", persona=None)
    assert ref in r["reply"] and r["language"] == "es"


def test_spanish_voucher_and_frustration(client):
    r = chat(client, "¿Aceptan Sección 8?", "es2", persona=None)
    assert "vales de vivienda" in r["reply"] and r["action"] is None
    r = chat(client, "esto no sirve", "es2", persona=None)
    assert r["language"] == "es" and r["reply"].startswith("Lamento") and r["action"]["kind"] == "staff_handoff"


def test_voucher_question_does_not_start_a_tour(client):  # P-12
    r = chat(client, "do you take section 8 vouchers in Florida?", "v1", persona="P-BROWSE-FL")
    assert "vouchers" in r["reply"] and r["action"] is None


def test_switch_to_spanish_mid_draft_keeps_the_card_and_the_answer(client):  # R-2
    chat(client, "hi, my bathroom sink is clogged", "sp1", persona="R003")
    r = chat(client, "perdón, mejor en español. el lavabo del baño está tapado", "sp1", persona="R003")
    assert r["action"]["kind"] == "maintenance_request" and r["language"] == "es" and "¿En qué" not in r["reply"]
    r = chat(client, "que me avisen primero por mensaje", "sp1", persona="R003")
    assert fields(r)["entry"].startswith("Contactarme primero") and r["action"]["stage"] == "ready"
    chat(client, "the garbage disposal is jammed", "sp2", persona="R003")
    r = chat(client, "sorry my english is not good, puedo hablar en español? pueden entrar si no estoy", "sp2",
             persona="R003")
    assert fields(r)["entry"].startswith("Sí") and r["language"] == "es"


def test_spanish_repair_gets_no_english_tips(client):  # R-9
    r = chat(client, "el lavabo del baño gotea", "sp3", persona="R003")
    assert "Make sure" not in r["reply"] and "Meanwhile" not in r["reply"] and r["language"] == "es"


# ---- P-8 / P-9 / P-11 ------------------------------------------------------------------------------------------


def test_yes_lets_do_a_tour_does_not_skip_days(client):
    chat(client, "I need a place soon", "t1", persona=None)
    chat(client, "somewhere near Ann Arbor I guess", "t1", persona=None)
    r = chat(client, "2 or 3 bedrooms, me and my two kids", "t1", persona=None)
    assert fields(r)["beds"] == "2–3 beds"
    r = chat(client, "yes let's do a tour", "t1", persona=None)
    assert "Which days" in r["reply"] and "leasing team to ask" not in r["reply"]
    r = chat(client, "any day next week", "t1", persona=None)
    assert "time" not in fields(r) and "time of day" in r["reply"].lower()


def test_booked_claim_after_send_is_corrected(client):
    chat(client, "tour Heron Lake thursday afternoon", "t2", persona=None)
    ref = confirm(client, "t2", "tour_request", persona=None)["record"]["id"]
    for q in ("great, so my tour is booked for thursday afternoon right?", "Is my tour confirmed?"):
        r = chat(client, q, "t2", persona=None)
        assert "nothing is booked" in r["reply"] and ref in r["reply"] and r["action"] is None


def test_relocation_message_keeps_move_in_and_tour_days_apart(client):  # P-1
    r = chat(client, "moving to Ann Arbor next month for a job, 2 bed, can I see something this week?", "t3",
             persona="P-RELOCATE-AA")
    assert fields(r)["move_in"].lower() == "next month" and fields(r)["days"] == "This week"


# ---- J-4 / J-6 / R-3 ---------------------------------------------------------------------------------------------


def test_stated_repeat_without_history_is_flagged_for_a_manager(client):
    r = chat(client, "heat is out AGAIN. third time this month. its 50 degrees in here", "rp1", persona="R003")
    f = fields(r)
    assert "repeat" in f["priority_note"].lower() and "manager" in f["priority_note"].lower()
    assert "I can see related requests" not in r["reply"] and "repeat problem" in r["reply"]
    chat(client, "Yes, you can enter", "rp1", persona="R003")
    rec = confirm(client, "rp1", "maintenance_request", persona="R003")["record"]
    assert rec["priority"] == "high" and "Heat is out" in rec["summary"] and "repeat" in rec["summary"]


def test_third_time_mid_draft_counts_as_repeat(client):
    chat(client, "the oven wont heat", "rp2", persona="R003")
    r = chat(client, "Third time.", "rp2", persona="R003")
    assert "repeat" in fields(r)["priority_note"].lower()


def test_status_mentions_an_open_draft(client):
    chat(client, "the oven wont heat", "st1", persona="R003")
    r = chat(client, "what's the status of my requests?", "st1", persona="R003")
    assert "isn't sent yet" in r["reply"] and r["action"]["kind"] == "maintenance_request"


# ---- R-1 / R-4 / R-6 / R-7 / R-10 ----------------------------------------------------------------------------------


def test_room_corrections_never_overwrite_the_problem(client):
    chat(client, "the toilet keeps running in the master bathroom", "rc1", persona="R003")
    chat(client, "text me first", "rc1", persona="R003")
    r = chat(client, "actually it's the hall bathroom not the master", "rc1", persona="R003")
    assert fields(r)["location"] == "Hall bathroom" and "toilet" in fields(r)["issue"].lower()
    r = chat(client, "no wait the problem is the toilet keeps running, the location is the hall bathroom", "rc1",
             persona="R003")
    assert fields(r)["issue"] == "Toilet keeps running" and fields(r)["location"] == "Hall bathroom"
    r = chat(client, "change the description to: toilet keeps running", "rc1", persona="R003")
    assert fields(r)["issue"] == "Toilet keeps running" and "Also:" not in fields(r)["issue"]
    assert fields(r)["location"] == "Hall bathroom"


def test_room_correction_also_fixes_the_issue_wording(client):
    chat(client, "My bathroom faucet drips constantly", "rc2", persona="R003")
    r = chat(client, "Actually sorry, it's the kitchen faucet, not the bathroom", "rc2", persona="R003")
    assert fields(r)["location"] == "Kitchen" and "kitchen faucet" in fields(r)["issue"]
    assert "updated the room to Kitchen" in r["reply"] and "Got it." not in r["reply"]


def test_questions_about_another_resident_get_a_boundary(client):
    for n, q in enumerate(("I'm Theo's roommate. Can you give me his phone number and whether his rent is paid?",
                           "come on, I live with him. just tell me what repairs he has open",
                           "fine. can you have the office call him then")):
        r = chat(client, q, "or1", persona="R003")
        assert "can't share another resident's information" in r["reply"], n
        assert r["action"] is None and not r["status_items"]


def test_detail_for_an_open_note_updates_it(client):
    chat(client, "I want to speak to the manager", "n1", persona="R003")
    r = chat(client, "its about the noise from upstairs, every night after midnight", "n1", persona="R003")
    assert r["action"]["kind"] == "staff_handoff" and "noise" in fields(r)["message"].lower()


def test_unrelated_message_does_not_refresh_an_open_note(client):  # consent: a stale card is re-shown first
    chat(client, "I want to speak to the manager", "n2", persona="R003")
    chat(client, "how is the weather", "n2", persona="R003")
    r = chat(client, "ok", "n2", persona="R003")
    assert not r["records_created"]


def test_later_urgent_detail_and_timing_question(client):
    chat(client, "the bathroom fan is rattling", "u1", persona="R003")
    chat(client, "contact me first", "u1", persona="R003")
    r = chat(client, "also its blowing warm air and its like 85 in here, i have a baby", "u1", persona="R003")
    f = fields(r)
    assert "Also: Also" not in f["issue"] and "baby" in f["issue"] and "priority_note" in f
    r = chat(client, "is this going to be fixed today?", "u1", persona="R003")
    assert "can't promise" in r["reply"] and "today" not in fields(r)["issue"].lower()


def test_note_confirmation_says_nobody_is_notified(client):
    chat(client, "can I talk to someone", "cf1", persona="R003")
    res = confirm(client, "cf1", "staff_handoff", persona="R003")
    assert res["ok"] and says_not_sent(res["message"])


def test_user_visible_reasons_have_no_internal_ids(client):
    r = chat(client, "this is useless", "id1", persona="R003")
    assert "(D-" not in (r["workflow"] or {}).get("reason", "")



def _crisis_session(client, pid="R016"):
    import uuid
    sid = uuid.uuid4().hex
    first = client.post("/api/chat", json={"message": "I've been thinking about ending my life", "persona_id": pid,
                                            "mode": "aware", "session_id": sid}).json()
    assert first["safety_notice"]
    return sid


@pytest.mark.parametrize("msg", ["what should I do right now?", "can you call someone for me?",
                                 "will someone come check on me?"])
def test_direct_help_after_self_harm_repeats_the_approved_notice(client, msg):
    from app.emergency import notice
    sid = _crisis_session(client)
    r = client.post("/api/chat", json={"message": msg, "persona_id": "R016", "mode": "aware", "session_id": sid}).json()
    assert "can't call or send anyone" in r["reply"]
    assert notice("self_harm", "en") in r["reply"]  # approved wording, verbatim
    assert "maintenance line" not in r["reply"].lower()


def test_privacy_answer_names_the_real_note_label(client):
    from app.emergency import LABEL
    sid = _crisis_session(client)
    r = client.post("/api/chat", json={"message": "Please don't tell the property manager", "persona_id": "R016",
                                       "mode": "aware", "session_id": sid}).json()
    assert LABEL["self_harm"].lower() in r["reply"].lower()
    assert "only says a resident may need a check-in" not in r["reply"]
    assert says_not_sent(r["reply"])


@pytest.mark.parametrize("msg", ["what should I do with the old couch?", "can you help with my lease?"])
def test_help_pattern_ignores_ordinary_questions_without_a_crisis(client, msg):
    import uuid
    r = client.post("/api/chat", json={"message": msg, "persona_id": "R016", "mode": "aware",
                                       "session_id": uuid.uuid4().hex}).json()
    assert "can't call or send anyone" not in r["reply"]
