# ruff: noqa: E501
"""Round-2 regressions from the independent reviewers (C, D, E, G, B). Mock model."""

import pytest

from app.emergency import emergency_kind, possible_risk
from app.safety import redact
from app.state import get_state

from .test_customer_flows import chat, confirm

ORDINARY = [  # C R-1, E R1, G R2: substrings of crisis phrases inside ordinary words
    "ok forget it, then send my price question to leasing", "who exactly did you send my info to?",
    "please send my note", "can you send my request to the manager", "I want to end my lease early, what are the fees?",
    "end my contract", "end my tenancy", "please send it all to the office", "sending things over now",
    "no i'm not answering more questions", "they're not answering my calls", "the doorbell sparks joy lol",
    "cant leave my car in the fire lane?", "can I mix bleach and vinegar to clean the mold?",
]


@pytest.mark.parametrize("msg", ORDINARY)
def test_ordinary_sentences_are_not_emergencies(msg):
    assert emergency_kind(msg) is None, msg


def test_false_crisis_never_writes_an_urgent_note(client):
    r = chat(client, "ok forget it, then send my price question to leasing", persona="", session="fc1")
    assert r["emergency_kind"] is None and not r["records_created"] and "988" not in r["reply"]


def test_restore_never_overrides_an_emergency(client):  # G R3, R4
    chat(client, "closet door off the track", persona="R003", session="ro1")
    chat(client, "yes you can enter", persona="R003", session="ro1")
    chat(client, "never mind", persona="R003", session="ro1")
    r = chat(client, "actually send it after all, also I smell gas now", persona="R003", session="ro1")
    assert r["emergency_kind"] == "gas" and r["records_created"] and r["records_created"][0]["status"] == "urgent_queued"
    chat(client, "kitchen tap drips", persona="R003", session="ro2")
    chat(client, "yes you can enter", persona="R003", session="ro2")
    chat(client, "never mind", persona="R003", session="ro2")
    r = chat(client, "no I really don't want to send it", persona="R003", session="ro2")
    assert r["action"] is None or r["action"]["stage"] != "ready"


def test_self_harm_record_keeps_words_out_of_the_queue_and_status_list(client):  # G R6
    chat(client, "i want to kill myself", persona="R003", session="pv1")
    rec = get_state().store.records(session_id="pv1")[0]
    assert "kill" not in str(rec).lower()
    r = chat(client, "check my requests", persona="R003", session="pv2")
    assert not any("self_harm" in (i["title"] + i["status"]) for i in r["status_items"])


def test_danger_words_get_a_911_line_even_when_not_a_full_emergency(client):  # G R1, D G1
    for m in ("orange glow under the door and crackling", "water is leaking through the ceiling from upstairs"):
        assert possible_risk(m) == "danger", m
    assert emergency_kind("lights flicker, whole apt, smells kinda burnt") == "fire_smoke"
    r = chat(client, "orange glow under the door and crackling", persona="R003", session="dg1")
    assert r["emergency_kind"] == "fire_smoke" or (r["care_kind"] == "danger" and "911" in r["care_note"])


def test_care_line_is_not_triggered_by_everyday_frustration():  # G R9
    for m in ("what's the point of the amenity fee", "I'm confused about my renewal letter", "last straw with the noise"):
        assert possible_risk(m) is None, m
    assert possible_risk("i can't go on like this, everything is falling apart") == "distress"


def test_refusal_reply_not_triggered_by_a_normal_question_after_an_emergency(client):  # G R11
    chat(client, "I smell gas in the hall", persona="R003", session="rf1")
    r = chat(client, "i'm fine here, just a question about the pool", persona="R003", session="rf1")
    assert "Staying could be dangerous" not in r["reply"]


def test_repair_continues_after_an_urgent_note(client):  # C R-4
    chat(client, "kitchen faucet drips", persona="R003", session="uc1")
    chat(client, "the outlet is sparking", persona="R003", session="uc1")
    chat(client, "kitchen faucet drips", persona="R003", session="uc1")
    r = chat(client, "Yes, you can enter", persona="R003", session="uc1")
    assert r["action"] and r["action"]["kind"] == "maintenance_request"


def test_card_expiry_without_slash_is_redacted():  # G R10
    out = redact("charge 4111 1111 1111 1111 exp 0429")
    assert "0429" not in out and "redacted]exp" not in out


def test_back_to_x_is_not_saved_as_the_problem(client):  # B18
    r = chat(client, "Ok, back to the oven", persona="R003", session="bk1")
    issue = next((f["value"] for f in (r["action"] or {}).get("fields", []) if f["key"] == "issue"), "")
    assert "back to" not in issue.lower()


def test_yes_after_unclear_offer_prepares_the_note(client):  # D G5
    chat(client, "blorp", persona="R003", session="yo1")
    chat(client, "zzzz qqq", persona="R003", session="yo1")
    r = chat(client, "yes", persona="R003", session="yo1")
    assert r["action"] and r["action"]["kind"] == "staff_handoff" and r["action"]["stage"] == "ready"
    assert confirm(client, "staff_handoff", persona="R003", session="yo1")["ok"]


def test_cancel_an_earlier_request_prepares_an_office_note(client):  # D G4
    r = chat(client, "cancel my repair", persona="R003", session="cx1")
    assert r["action"] and r["action"]["kind"] == "staff_handoff"
