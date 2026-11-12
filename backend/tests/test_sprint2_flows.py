"""Sprint 2 conversation regressions, each from an independent reviewer's reproduction (B=UX, C=frustrated
resident, D=ordinary resident, E=prospect, G=safety). Mock model; tests the deterministic product pipeline."""


from tests.wording import says_not_sent

from .test_customer_flows import chat, confirm


def fields(r):
    return {f["key"]: f["value"] for f in (r["action"] or {}).get("fields", [])}


def test_fan_noise_is_a_repair_not_a_neighbour_complaint(client):  # D F1, C-4
    r = chat(client, "bathroom fan is loud", persona="R003", session="fan1")
    assert r["action"]["kind"] == "maintenance_request"
    r = chat(client, "the upstairs neighbor plays loud music every night", persona="R003", session="fan2")
    assert r["action"]["kind"] == "staff_handoff"


def test_correction_replaces_issue_and_drops_repeat_flag(client):  # B1
    chat(client, "the AC isn't cooling", persona="R001", session="sw1")
    r = chat(client, "wait, it's not the AC, it's the bathroom fan", persona="R001", session="sw1")
    f = fields(r)
    assert f["issue"] == "Bathroom fan" and "Also:" not in f["issue"]
    assert "priority_note" not in f and "changed the problem" in r["reply"]


def test_location_change_is_applied_and_announced(client):  # B3 (J12)
    chat(client, "toilet keeps running", persona="R003", session="lc1")
    r = chat(client, "Change the location to the hall bathroom", persona="R003", session="lc1")
    assert "updated" in r["reply"].lower() and fields(r)["location"] in ("Bathroom", "Hall bathroom")


def test_decline_can_be_undone_once(client):  # B2, B4
    chat(client, "kitchen faucet drips", persona="R003", session="un1")
    chat(client, "yes you can enter", persona="R003", session="un1")
    r = chat(client, "never mind", persona="R003", session="un1")
    assert r["action"] is None and "send it after all" in r["reply"]
    assert confirm(client, "maintenance_request", persona="R003", session="un1")["ok"] is False
    r = chat(client, "actually send it after all", persona="R003", session="un1")
    assert r["action"]["stage"] == "ready"
    assert confirm(client, "maintenance_request", persona="R003", session="un1")["ok"] is True


def test_after_send_questions_are_answered_honestly(client):  # E F9, C-8, G12
    chat(client, "I want to talk to a person", persona="P-RELOCATE-AA", session="as1")
    confirm(client, "staff_handoff", persona="P-RELOCATE-AA", session="as1")
    for q in ("when will they call me?", "did someone get it??", "so a tech is coming tomorrow?"):
        r = chat(client, q, persona="P-RELOCATE-AA", session="as1")
        assert says_not_sent(r["reply"]) and r["action"] is None and not r["records_created"], q


def test_send_it_after_sending_points_to_existing_request(client):  # suite r-drop-and-return, C-3
    chat(client, "The smoke detector keeps chirping in the hallway", persona="R003", session="ss1")
    chat(client, "yes you can enter", persona="R003", session="ss1")
    confirm(client, "maintenance_request", persona="R003", session="ss1")
    r = chat(client, "OK, and about the smoke detector, please send it.", persona="R003", session="ss1")
    assert r["action"] is None and "DEMO-WO-" in r["reply"]


def test_unclear_twice_offers_instead_of_filing_a_note(client):  # D F3, E F9
    chat(client, "only text me after 6pm", persona="R003", session="uc0")  # contact preference -> office note
    r1 = chat(client, "blorp", persona="R003", session="uc1")
    r2 = chat(client, "zzzz qqq", persona="R003", session="uc1")
    assert not r1["records_created"] and not r2["records_created"]
    assert r2["action"] is None or r2["action"]["kind"] != "staff_handoff"


def test_office_note_from_a_chip_carries_the_residents_words(client):  # D F3
    chat(client, "my closet door squeaks a lot when it rains maybe", persona="R003", session="qa1")
    r = chat(client, "Talk to the office", persona="R003", session="qa1")
    msg = fields(r)["message"]
    assert "Talk to the office" not in msg or "squeaks" in msg


def test_contact_preference_is_recorded_not_ignored(client):  # D F5
    chat(client, "closet door off the track", persona="R003", session="cp1")
    r = chat(client, "only text me after 6pm", persona="R003", session="cp1")
    assert fields(r)["contact"] == "Only text me after 6pm" and "can't change" in r["reply"]
    r = chat(client, "pls stop calling me, text only", persona="R003", session="cp2")
    assert r["action"]["kind"] == "staff_handoff" and "can't change" in r["reply"]


def test_policy_questions_name_the_topic_and_offer_the_office(client):  # D F6
    for q, topic in (("where do packages go", "packages"), ("quiet hours?", "quiet hours"),
                     ("How long can a guest stay with me?", "guests")):
        r = chat(client, q, persona="R003", session=f"pq-{topic.replace(' ', '-')}")
        assert topic in r["reply"] and "Ask the office" in r["suggested_replies"], q


def test_manager_requests_win_over_an_open_form(client):  # C-2
    chat(client, "my dishwasher is leaking", persona="R001", session="mg1")
    for q in ("just get me the property manager", "speak to whoever is in charge"):
        r = chat(client, q, persona="R001", session="mg1")
        assert r["action"]["kind"] == "staff_handoff", q


def test_vague_issue_asks_what_first(client):  # D F7
    r = chat(client, "it's not working", persona="R003", session="vg1")
    assert "What is it that isn't working" in r["reply"]
    r = chat(client, "the dishwasher", persona="R003", session="vg1")
    assert "dishwasher" in fields(r)["issue"].lower()


def test_repeat_failure_skips_troubleshooting(client):  # C-9
    r = chat(client, "4th time the AC broke this summer", persona="R001", session="rp1")
    assert "safe checks" not in r["reply"] and "troubleshoot" in r["reply"]


def test_unsafe_diy_gets_a_plain_warning(client):  # G7, G10
    r = chat(client, "the breaker keeps tripping, should I tape it so it stays on?", persona="R003", session="dy1")
    assert "don't tape" in r["reply"]
    r = chat(client, "the smoke detector keeps going off when I cook, can I just take the battery out?",
             persona="R003", session="dy2")
    assert r["emergency_kind"] is None and "keep the battery" in r["reply"]


def test_tour_details_from_anywhere_in_the_message(client):  # E F4, F2, F3
    r = chat(client, "can I tour thursday afternoon at Heron Lake", persona="", session="tr1")
    f = fields(r)
    assert f.get("area") == "Heron Lake Apartments" and "Thursday" in f.get("days", "")
    r = chat(client, "I want to see a 2 bed this week", persona="", session="tr2")
    assert "move_in" not in fields(r)
    r = chat(client, "thursday around 4?", persona="", session="tr2")
    assert "4 PM" in fields(r).get("time", "")
    r = chat(client, "Hola, busco un apartamento en Sandpiper Pointe por la mañana", persona="", session="tr3")
    f = fields(r)
    assert f.get("area") == "Sandpiper Pointe" and f.get("days") is None


def test_last_stated_move_in_wins(client):  # E F1
    chat(client, "Looking to move in Dec 1 in Ann Arbor", persona="", session="mv1")
    chat(client, "actually make it January 15", persona="", session="mv1")
    r = chat(client, "change it to February 1", persona="", session="mv1")
    assert fields(r)["move_in"] == "February 1"


def test_stated_price_is_never_confirmed(client):  # E F5
    r = chat(client, "the website says $999 and 6 weeks free, right?", persona="", session="pc1")
    assert "can't confirm prices" in r["reply"] and "noted" not in r["reply"]


def test_guest_wanting_an_apartment_is_not_asked_who_they_are(client):  # E F6
    r = chat(client, "hello i want see apartment", persona="", session="gw1")
    assert "current McKinley resident" not in r["reply"] and r["action"]["kind"] == "tour_request"
    r = chat(client, "I want to talk to a salesperson", persona="", session="gw2")
    assert r["action"]["kind"] == "staff_handoff"


def test_internal_account_notes_never_show_on_customer_cards(client):  # B13
    """The fixture workbook's private notes, contact details and rent must never reach the customer response."""
    for persona, session in (("R003", "in1"), ("R001", "in2")):
        r = chat(client, "kitchen faucet drips", persona=persona, session=session)
        blob = str(r).lower()  # the whole response, card fields and reply included
        for private in ("overnight shifts", "works from home", "biscuit", "@example.com", "555-01", "1585", "1349"):
            assert private not in blob, (persona, private)


def test_distress_gets_care_line_and_no_form(client):  # fork screenshot note
    r = chat(client, "what's the point of fixing the sink if i won't matter next week anyway", persona="R003",
             session="ds1")
    assert r["care_kind"] == "distress" and r["action"] is None and "no rush" in r["reply"]


def test_spanish_resident_gets_spanish_reply(client):  # fork screenshot note, D F14
    r = chat(client, "el refrigerador no enfría", persona="R003", session="es1")
    assert r["language"] == "es"


def test_self_harm_note_goes_to_management_not_maintenance(client):  # fork screenshot note
    r = chat(client, "i want to kill myself", persona="R003", session="sh2")
    assert r["records_created"] and r["records_created"][0]["team"] == "management"
