"""Sprint 9: warm, concise replies; one honest status; the demo limit said once per step (layered disclosure).

The tour journey below is the product owner's own development example. Independent unseen scenarios were run by
separate reviewers outside the repo; these tests pin the behaviour, not those transcripts."""
import re

import pytest

from app.models import STATUS_LABEL, with_status_label
from app.templates import CARD_NOTE, CONFIRM, T
from tests.wording import says_not_sent

# Phrases the pre-Sprint 9 replies repeated in nearly every turn
_OLD_BOILERPLATE = re.compile(r"in this prototype nobody is notified|no McKinley staff will see it|office's real "
                              r"contact details aren't connected|In the real service the leasing team would pick", re.I)
_READBACK = re.compile(r"(?:Community or city|Preferred days|Time of day):")
_FALSE_STATUS = re.compile(r"leasing team to confirm|waiting for staff review|in the office queue|team (?:has|have) "
                           r"received|will confirm|confirmed booking|is booked", re.I)


def chat(client, msg, session, persona=None):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def confirm(client, session, kind, persona=None):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona,
                                                     "kind": kind}).json()


def words(text: str) -> int:
    return len(text.split())


def test_product_owner_tour_example_is_warm_short_and_honest(client):
    r = chat(client, "Request a tour", "v1")
    sid = r["session_id"]
    assert r["reply"].startswith("I'd be happy to help") and "community" in r["reply"] and words(r["reply"]) <= 25
    r = chat(client, "Ann Arbor, next week", sid)
    # no form-like read-back, and only a city was given: never "you've chosen the Ann Arbor community"
    assert not _READBACK.search(r["reply"]) and "Ann Arbor" not in r["reply"] and "time of day" in r["reply"].lower()
    r = chat(client, "Morning", sid)
    assert r["action"]["stage"] == "ready" and "next week in the morning" in r["reply"] and not _READBACK.search(
        r["reply"])
    assert says_not_sent(r["action"]["note"]) and "no time is booked" in r["action"]["note"]  # at the point of Send
    res = confirm(client, sid, "tour_request")
    assert res["ok"] and res["record"]["status_label"] == "Saved in demo"
    msg = res["message"]
    assert "saved in this demo" in msg and "time isn't confirmed" in msg and says_not_sent(msg)
    assert res["record"]["id"] not in msg and not _READBACK.search(msg) and words(msg) <= 30
    assert not _OLD_BOILERPLATE.search(msg) and not _FALSE_STATUS.search(msg)
    nxt = chat(client, "What happens next?", sid)["reply"]
    assert says_not_sent(nxt) and "no time is confirmed" in nxt and not _READBACK.search(nxt) and words(nxt) <= 40
    call = chat(client, "Will someone call me?", sid)["reply"]
    assert call.startswith("No,") and says_not_sent(call) and words(call) <= 40
    assert nxt != call  # the two follow-ups get different, direct answers (not the same paragraph twice)


def test_status_labels_are_one_honest_vocabulary():
    assert set(STATUS_LABEL) == {"submitted_for_review", "requested", "queued", "urgent_queued"}
    for label in STATUS_LABEL.values():
        assert "demo" in label.lower() and not _FALSE_STATUS.search(label)
    old = {"status": "requested", "status_label": "Requested; leasing team to confirm a time"}
    assert with_status_label(old)["status_label"] == "Saved in demo"  # rows saved before Sprint 9 are relabelled
    assert with_status_label({"status": "unknown", "status_label": "x"})["status_label"] == "x"


def test_record_reads_use_the_authoritative_label(client):
    sid = chat(client, "tour Heron Lake saturday morning", "v2")["session_id"]
    rec = confirm(client, sid, "tour_request")["record"]
    from app.state import get_state
    rows = get_state().store.records(session_id=sid)
    assert rows and rows[0]["id"] == rec["id"] and rows[0]["status_label"] == rec["status_label"] == "Saved in demo"


def test_card_notes_state_the_demo_limit_once_per_kind():
    for stage in ("open", "saved"):
        for kind in ("maintenance_request", "tour_request", "staff_handoff"):
            for lang in ("en", "es"):
                note = CARD_NOTE[stage][kind][lang]
                assert says_not_sent(note) and len(note.split()) <= 18, (stage, kind, lang)


@pytest.mark.parametrize("kind", ["maintenance_request", "tour_request", "staff_handoff", "staff_handoff_plain"])
def test_confirmations_are_short_and_say_nothing_was_sent(kind):
    for lang in ("en", "es"):
        text = CONFIRM[kind][lang].format(id="DEMO-X-1001", when="")
        assert says_not_sent(text) and words(text) <= 32 and not _OLD_BOILERPLATE.search(text), (kind, lang)
        assert "DEMO-X-1001" not in text  # the card shows the reference


def test_tour_correction_is_one_natural_sentence(client):
    sid = chat(client, "I'd like to tour Heron Lake on Saturday morning", "v3")["session_id"]
    r = chat(client, "actually make it Sunday afternoon", sid)
    assert "changed it to Sunday in the afternoon" in r["reply"] and "Updated:" not in r["reply"]
    assert {f["key"]: f["value"] for f in r["action"]["fields"]}["days"] == "Sunday"


def test_side_questions_do_not_repeat_the_same_tour_question(client):
    sid = chat(client, "Do you have 2 bed floor plans under $1400?", "v4")["session_id"]
    a = chat(client, "What's available right now?", sid)["reply"]
    b = chat(client, "Do you accept housing vouchers?", sid)
    ask = "Which McKinley community"
    assert (ask in a) + (ask in b["reply"]) <= 1 and b["action"]["stage"] == "collecting"  # card kept, asked once


def test_live_and_unapproved_topics_share_one_referral(client):
    r = chat(client, "Do you have 2 bed floor plans under $1400?", "v5")
    assert r["reply"].count("leasing team") <= 2 and r["reply"].count("won't guess") + r["reply"].count(
        "rather not guess") == 1


def test_resident_repair_journey_is_concise(client):
    sid = chat(client, "My kitchen faucet is dripping", "v6", persona="R003")["session_id"]
    r = chat(client, "yes you can come in", sid, persona="R003")
    assert r["action"]["stage"] == "ready" and words(r["reply"]) <= 25
    res = confirm(client, sid, "maintenance_request", persona="R003")
    assert res["ok"] and res["record"]["status_label"] == "Saved in demo" and says_not_sent(res["message"])
    assert "no visit is scheduled" in res["message"] and words(res["message"]) <= 30
    came = chat(client, "is someone coming today?", sid, persona="R003")["reply"]
    assert says_not_sent(came) and res["record"]["id"] in came and "on the way" not in came.lower()


def test_repeat_issue_has_one_apology_and_no_double_opener(client):
    r = chat(client, "my AC is broken again, it's blowing warm air", "v7", persona="R001")
    reply = r["reply"]
    assert reply.count("sorry") == 1 and "Got it" not in reply and "repeat issue" in reply


def test_system_prompt_states_the_voice_rules():
    from app.config import Settings
    from app.prompts import load_aware_prompt

    p = load_aware_prompt(Settings(_env_file=None).prompt_path)
    assert p.version.startswith("mckinley-v0.2")
    for rule in ("1–3 short sentences", "never pretend to be a person", "never shorten emergency steps",
                 "Do not apologize in every message"):
        assert rule in p.system


def test_plan_section_tells_the_model_not_to_add_disclaimers():
    from types import SimpleNamespace

    from app.chat_engine import PLAN_SECTION_VERSION, plan_prompt_section

    text = plan_prompt_section(SimpleNamespace(template="Hi.", action=None, facts=[]), "web_chat", "en")
    assert PLAN_SECTION_VERSION == "plan-s9" and "do not add disclaimers" in text and "reference number" in text
    assert "never apologize" in text
    assert "1-3 short sentences" in text


def test_safety_templates_are_not_shortened():
    # Sprint 9 must not touch the fixed emergency wording (shown in full, never model-written)
    assert "Leave the area now and call 911" in T["emergency_steps"]["en"]
    assert "call 911" in T["lockout"]["en"] and "after-hours or emergency maintenance line" in T["lockout"]["en"]


# ---- Sprint 9 review round (independent conversation, workflow and simulator findings) ----

@pytest.mark.parametrize("text", [
    "Your note was sent to the office.", "The leasing team will confirm a time.",
    "Maintenance has received your request.", "It is waiting for staff review.",
    "I've passed it along to the leasing team.", "Su solicitud fue enviada al personal.",
    "El equipo le confirmará la hora.",
])
def test_validator_rejects_demo_status_claims(text):
    from app.safety import output_checks
    check = next(c for c in output_checks(text) if c.code == "no_false_action_claim")
    assert not check.passed, text


@pytest.mark.parametrize("text", [
    "Your repair request (DEMO-WO-1001) is saved in this demo, but it hasn't been sent to the maintenance team.",
    "No, nobody will call or email from this demo, because your note wasn't sent to McKinley staff.",
    "In the real service, the leasing team would follow up with you.",
    "Sending saves a demo request. It won't notify McKinley staff.",
    "Su solicitud no se envió al personal de McKinley.",
    "An urgent note is saved in the staff queue, but this prototype can't page or call anyone.",
])
def test_validator_allows_honest_negated_or_conditional_wording(text):
    from app.safety import output_checks
    assert next(c for c in output_checks(text) if c.code == "no_false_action_claim").passed, text


@pytest.mark.parametrize("msg,contact", [
    ("Will someone call me?", True), ("will you email me?", True), ("when will I hear back?", True),
    ("¿Me van a llamar?", True), ("is anyone going to reach out", True),
    ("is there a text version of the tips?", False), ("Can I text a friend the link?", False),
    ("When will someone come?", False),
])
def test_contact_question_detection_is_narrow(msg, contact):
    from app.actions import _ASKS_CONTACT
    assert bool(_ASKS_CONTACT.search(msg)) is contact


def test_booking_question_after_send_never_says_it_is_with_the_team(client):
    sid = chat(client, "tour Heron Lake saturday morning", "v8")["session_id"]
    confirm(client, sid, "tour_request")
    r = chat(client, "so I'm booked for Saturday?", sid)["reply"]
    assert "nothing is booked" in r.lower() and "waiting for the leasing team" not in r and says_not_sent(r)


def test_guest_note_follow_up_names_the_office(client):
    sid = chat(client, "Talk to a person", "v9")["session_id"]
    confirm(client, sid, "staff_handoff")
    r = chat(client, "Will someone call me?", sid)["reply"]
    assert r.startswith("No,") and "leasing team would" not in r and "property management" not in r


def test_upset_follow_up_on_an_open_request_is_acknowledged_first(client):
    r = chat(client, "This is ridiculous, I've reported the AC three times and nobody fixed it", "v10",
             persona="R001")["reply"]
    assert r.startswith("I understand why that's frustrating") and r.count("sorry") + r.count("frustrating") <= 2


def test_tour_when_handles_lists_and_lowercase_days():
    from app.actions import tour_when
    d = lambda days, time="Morning": {"fields": {"days": {"value": days}, "time": {"value": time}}}  # noqa: E731
    assert tour_when(d("on saturday"), "en") == "Saturday in the morning"
    assert tour_when(d("Next week"), "en") == "next week in the morning"
    assert tour_when(d("this weekend, Next Monday"), "en") == ""
    assert tour_when(d("next Tuesday or Wednesday"), "en") == ""
    assert tour_when(d("Saturday"), "es") == ""


def test_nothing_saved_summary_has_no_contradiction(client):
    sid = chat(client, "My kitchen faucet is dripping", "v11", persona="R003")["session_id"]
    r = chat(client, "did that go in?", sid, persona="R003")["reply"]
    assert "saved: nothing" not in r and "Nothing has been saved in this chat yet" in r


# ---- Sprint 9 final review round (independent safety reviewer G, regression verifier H) ----

@pytest.mark.parametrize("text", [
    "I can't book it. The office will call you to confirm.", "No time is set. Staff will review it shortly.",
    "No problem! I've sent it to the office.", "Don't worry, the leasing team will reach out soon.",
    "Sin problema, fue enviada al equipo.", "Your visit is confirmed.", "It's in the maintenance queue.",
    "It's on its way to the office.", "Su solicitud fue enviada a mantenimiento.", "El equipo le llamará.",
    "If you send it, the office will get back to you.",
])
def test_validator_negation_is_scoped_to_the_same_sentence(text):
    from app.safety import _demo_status_claim
    assert _demo_status_claim(text), text


def test_tour_time_correction_reads_back_the_time(client):
    sid = chat(client, "tour Heron Lake", "v12")["session_id"]
    chat(client, "Saturday", sid)
    chat(client, "morning", sid)
    r = chat(client, "actually make it 3pm", sid)
    assert "3 PM" in r["reply"] and "changed it to Saturday." not in r["reply"]


def test_guest_repair_reply_points_to_a_path_that_exists(client):
    r = chat(client, "my sink is leaking", "v13")
    assert "sign-in" in r["reply"] and "Talk to a person" in r["reply"] and "I can start a note" not in r["reply"]


def test_repeat_history_save_says_nobody_sees_it():
    from app.templates import t
    assert "no one at McKinley sees it" in t("repeat_history_saved") and "community manager" in t(
        "repeat_history_saved")


@pytest.mark.parametrize("text", [  # live Gemini review on f6a32a7 (peer session): Send framed as delivery
    "Please review the details and press Send when you are ready to submit it to our Sandpiper Pointe maintenance "
    "team.", "Please check your request below and press Send so our office receives your details.",
    "Please review your request below and press Send so our team can follow up with you.",
    "A leasing team member should follow up to give you exact details.",
    "Revise la solicitud y pulse Enviar para que la reciba el equipo de mantenimiento.",
    "Once you send it, staff can review it.", "Once you tap Send, a staff member can follow up with you.",
])
def test_validator_rejects_send_framed_as_delivery(text):
    from app.safety import _demo_status_claim
    assert _demo_status_claim(text), text


def test_offers_are_not_claims():
    from app.safety import _demo_status_claim
    assert not _demo_status_claim("I can pass your question to the leasing team in a note.")


def test_ok_cool_is_not_an_ac_repair(client):
    sid = chat(client, "I'd like to tour Heron Lake on Saturday", "v14")["session_id"]
    r = chat(client, "ok cool. mornings please", sid)
    assert r["action"]["kind"] == "tour_request" and r["action"]["stage"] == "ready"
    from app.context import detect_topics
    assert "hvac" in detect_topics("the AC won't cool") and "hvac" in detect_topics("it wont cool anymore")
    assert "hvac" not in detect_topics("ok cool, thanks")


def test_nvm_after_cancel_answers_the_question_that_follows(client):
    # live Gemini review (peer session): "nvm. whats your phone number" got "There's nothing waiting to be sent"
    sid = chat(client, "can i talk to a human", "v15")["session_id"]
    client.post("/api/actions/cancel", json={"session_id": sid, "persona_id": None, "kind": "staff_handoff"})
    r = chat(client, "nvm. whats your phone number", sid)["reply"]
    assert "phone" in r.lower() or "number" in r.lower()
    assert "nothing waiting" not in r and "911" in r
    assert chat(client, "nvm", sid)["reply"].startswith("No problem")
