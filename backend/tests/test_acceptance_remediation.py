"""Regression tests for the 2026-11-17 acceptance remediation (focused; no safety policy change).

MN6  a prospect's pricing note was treated as a visitor REPAIR (needed an apartment unit, so it could never be sent) and
     a tour asked for alongside it became an "Also asked about" note: neither "send it" nor Send saved the tour.
MN9  the assistant stated a Fair Housing legal conclusion as fact; the fair-housing gate had been disconnected.
Obs. the per-turn decision log now says WHY the safety layer decided (rule ids, classifier level, policy rule) and
     which reply checks failed, without message text.

The provider is scripted call by call, so these replay the model behaviour seen in the acceptance run with NEW
wording (the acceptance cases themselves are not used as test inputs: they stay an evaluation, not a training set).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.assistant import TASK_FIELDS
from app.config import Settings
from app.db import Store
from app.llm import LLMGateway
from app.llm.base import LLMResult, ModelOutput
from app.main import app
from app.state import build_state, set_state
from tests.helpers import chat, fields, press_send

PROSPECT, RESIDENT = "P-RELOCATE-AA", "R003"
NONE_RISK = {"risk_level": "none", "risk_categories": [], "immediate_danger": False, "needs_human": False,
             "confidence": 0.9, "framing": "none", "reason": "routine", "incident_category": "none",
             "ongoing": "unknown", "subject": "none"}


def turn(reply="Happy to help.", op="none", kind="none", team="none", reason="", other=None, **values) -> str:
    """One scripted conversation-model answer (the JSON the real model returns)."""
    return json.dumps({"reply": reply, "task": {"op": op, "kind": kind, "fields": {
        f: values.get(f, "") for f in TASK_FIELDS}}, "other_needs": other or [], "show_my_requests": False,
        "include_history": "none", "handoff": {"team": team, "reason": reason}, "language": "en"})


class Sequenced:
    """Classifier calls get `risk`; conversation calls get the next scripted answer in order."""
    name = "openrouter"

    def __init__(self, answers: list[str], risk: dict | None = None):
        self.answers, self.risk, self.chat_calls = list(answers), risk or NONE_RISK, 0

    def complete(self, system, messages, target, cfg, schema=None, schema_name="mckinley_reply"):
        if schema_name == "mckinley_risk":
            content = json.dumps(self.risk)
        else:
            self.chat_calls += 1
            content = self.answers.pop(0) if self.answers else turn()
        return LLMResult(output=ModelOutput(reply=""), provider="openrouter", requested_model=target.model,
                         model=target.model, stop_reason="stop", input_tokens=5, output_tokens=5, latency_ms=3,
                         parse_mode="json", extra={"content": content})


@pytest.fixture
def make(tmp_path, workbook):
    """make([answers...], risk=...) -> (TestClient, provider, store) on the real app."""
    made = []

    def build(answers, risk=None):
        s = Settings(_env_file=None, llm_provider="openrouter", llm_model="test/chat-model",
                     openrouter_api_key="test-not-a-real-key", db_path=tmp_path / f"a{len(made)}.sqlite3",
                     demo_personas_enabled=True, safety_classifier="auto")
        prov, store = Sequenced(answers, risk), Store(s.db_path)
        set_state(build_state(settings=s, gateway=LLMGateway(s, {"openrouter": prov}), workbook=workbook,
                              store=store))
        made.append(1)
        return TestClient(app), prov, store
    yield build
    set_state(None)  # type: ignore[arg-type]


def saved(store, kind=None):
    return [r for r in store.records(limit=100) if r.get("status") != "urgent_queued" and (not kind or
                                                                                          r["kind"] == kind)]


# ==== Scope A: MN6 tour and staff-note routing ========================================================================
def test_a_prospect_pricing_note_is_not_a_repair_and_the_tour_waits_as_a_tour(make):
    c, prov, store = make([
        turn("I don't have current rent for a two-bedroom at Willow Bend. Want a note for the leasing team?"),
        turn("Here's a note for the leasing team about rent; your tour request is next.", op="start",
             kind="staff_handoff", team="leasing", reason="Rent question", community="Willow Bend",
             message="What does a two-bedroom rent for at Willow Bend?", topic="Two-bedroom rent",
             other=[{"text": "tour Willow Bend on Sunday at 2pm", "kind": "tour_request"}]),
        turn("Great, the tour card has Willow Bend, Sunday, 2pm.", op="update", kind="tour_request",
             area="Willow Bend", days="Sunday", time="2pm"),
    ])
    sid = "mn6-a"
    chat(c, "How much is a two-bedroom at Willow Bend?", sid, PROSPECT)
    r = chat(c, "Sure. And can I come see Willow Bend on Sunday at 2pm?", sid, PROSPECT)
    card = r["action"]
    assert card["kind"] == "staff_handoff" and card["missing"] == [] and card["stage"] == "ready"
    assert "unit" not in fields(r) and "Unit" not in json.dumps(card)  # a prospect is never asked for a unit number
    draft = store.get_draft(sid, PROSPECT, include_declined=True)
    assert not draft.get("guest_repair") and draft["team"] == "leasing"
    assert [w["kind"] for w in draft["waiting"]] == ["tour_request"]  # a TOUR card, not an "Also asked about" note
    assert saved(store) == []  # nothing saved by any of it

    note = press_send(c, sid, "staff_handoff", PROSPECT)
    assert note["ok"] and "tour request is back on screen" in note["message"]
    r = chat(c, "Sunday at 2pm at Willow Bend", sid, PROSPECT)
    assert r["action"]["kind"] == "tour_request" and r["action"]["stage"] == "ready"
    r = chat(c, "send it", sid, PROSPECT)  # explicit typed consent sends the card on screen: the tour
    assert [x["kind"] for x in r["records_created"]] == ["tour_request"]
    assert "Nothing is booked" in r["reply"] and "confirmed" not in r["reply"].lower()
    again = press_send(c, sid, "tour_request", PROSPECT)
    assert not again["ok"] and again["error_code"] == "ALREADY_SAVED"
    assert [x["kind"] for x in saved(store)] == ["tour_request", "staff_handoff"]  # one of each, no duplicate
    assert prov.chat_calls == 3  # "send it" was handled by the backend, not the model


def test_a_tour_asked_for_while_a_note_is_open_becomes_the_card_on_screen(make):
    c, _, store = make([
        turn("Here's a note for the leasing team.", op="start", kind="staff_handoff", team="leasing",
             message="Are utilities included?", topic="Utilities"),
        turn("Here's a tour request for Maple Court on Friday morning.", op="start", kind="tour_request",
             area="Maple Court", days="Friday", time="morning"),
    ])
    sid = "mn6-b"
    chat(c, "Are utilities included? Please ask the office.", sid, PROSPECT)
    r = chat(c, "Also I want to tour Maple Court Friday morning", sid, PROSPECT)
    assert r["action"]["kind"] == "tour_request" and r["action"]["stage"] == "ready"
    assert [w["kind"] for w in store.get_draft(sid, PROSPECT)["waiting"]] == ["staff_handoff"]  # waits, unsent
    sent = press_send(c, sid, "tour_request", PROSPECT)
    assert sent["ok"] and sent["record"]["kind"] == "tour_request" and "note is back on screen" in sent["message"]
    assert [x["kind"] for x in saved(store)] == ["tour_request"]  # the note was not sent along with it


def test_a_send_it_on_an_incomplete_card_saves_nothing_and_says_what_is_missing(make):
    c, prov, store = make([turn("Happy to set up a tour. What time works?", op="start", kind="tour_request",
                                area="Maple Court", days="Saturday")])
    sid = "mn6-c"
    chat(c, "I'd like to tour Maple Court on Saturday", sid, PROSPECT)
    r = chat(c, "ok send it", sid, PROSPECT)
    assert r["records_created"] == [] and saved(store) == []
    assert "nothing was saved" in r["reply"] and "time of day" in r["reply"]
    assert r["action"]["kind"] == "tour_request" and prov.chat_calls == 1  # the backend answered, not the model


def test_a_send_button_never_saves_a_card_that_is_not_on_screen(make):
    c, _, store = make([turn("Here's a note for the leasing team.", op="start", kind="staff_handoff",
                             team="leasing", message="Is there a waitlist?", topic="Waitlist")])
    sid = "mn6-d"
    chat(c, "Is there a waitlist? Ask the office please.", sid, PROSPECT)
    r = press_send(c, sid, "tour_request", PROSPECT)
    assert not r["ok"] and r["error_code"] == "NO_PENDING_ACTION" and "your note" in r["message"]
    assert r["action"]["kind"] == "staff_handoff" and saved(store) == []


def test_a_a_visitor_repair_note_still_needs_community_and_unit(make):
    c, _, store = make([turn("Since you're not signed in, I'll make a note for maintenance. Which community?",
                             op="start", kind="maintenance_request", issue="hallway light out")])
    sid = "mn6-e"
    r = chat(c, "the hallway light outside my door is out", sid, "")
    assert r["action"]["kind"] == "staff_handoff"
    assert set(r["action"]["missing"]) == {"Community", "Unit"}
    assert press_send(c, sid, "staff_handoff", "")["error_code"] == "INCOMPLETE" and saved(store) == []


@pytest.mark.parametrize("team,values,repair", [
    ("leasing", {"community": "Heron Lake", "message": "rent for a 1BR?"}, False),
    ("none", {"community": "Heron Lake", "message": "is there a waitlist?"}, False),
    ("maintenance", {"community": "Heron Lake", "message": "the gate is broken"}, True),
    ("none", {"issue": "the lobby door won't lock", "message": "lobby door"}, True),
])
def test_a_only_a_repair_note_from_a_visitor_is_a_guest_repair(team, values, repair):
    from app.chat_engine import _guest_repair
    assert _guest_repair("staff_handoff", values, team, verified=False, audience="unknown") is repair
    # a prospect is never asked for a unit for a note, and a signed-in resident's note is never a guest repair
    assert _guest_repair("staff_handoff", values, team, verified=False, audience="prospect") is False
    assert _guest_repair("staff_handoff", values, team, verified=True, audience="resident") is False
    assert _guest_repair("maintenance_request", values, team, verified=False, audience="unknown") is True


def test_a_resident_handoff_keeps_the_waiting_repair(make):
    c, _, store = make([
        turn("Sorry about that. Which room?", op="start", kind="maintenance_request", issue="faucet dripping"),
        turn("Here's a note for the office.", op="start", kind="staff_handoff", team="management",
             message="I want to talk to someone", topic="Asked for a person"),
    ])
    sid = "mn6-f"
    chat(c, "my faucet is dripping", sid, RESIDENT)
    r = chat(c, "I want to talk to someone", sid, RESIDENT)
    assert r["action"]["kind"] == "staff_handoff" and "faucet" in fields(r).get("earlier", "")
    assert [w["kind"] for w in store.get_draft(sid, RESIDENT)["waiting"]] == ["maintenance_request"]


# ==== Scope B: MN9 legal / fair-housing boundary =====================================================================
LEGAL_REPLIES = [
    "Generally, fair housing law prohibits pet rent for an emotional support cat.",
    "Under the Fair Housing Act, they have to approve your request.",
    "Legally, the property cannot charge you for a service animal.",
    "Charging you would be illegal.",
    "You have a legal right to a reasonable accommodation.",
    "Assistance animals aren't charged pet rent, and they are not considered pets.",
    "You're entitled to a reasonable accommodation for your wheelchair.",
    "By law, a landlord must allow a support dog.",
]
FINE_REPLIES = [
    "I don't have McKinley's pet policy. Want me to prepare a note for the leasing team?",
    "I can't give legal advice. The leasing team handles accommodation requests; want a note?",
    "I don't know what the law says on that; the office can help.",
    "I can prepare a note for the office about your service dog.",
    "I can't recommend a community based on who lives there.",
    "Your note is saved in this demo only.",
]


@pytest.mark.parametrize("reply", LEGAL_REPLIES)
def test_b_legal_determinations_are_detected(reply):
    from app.guardrails import legal_conclusion
    assert legal_conclusion(reply)


@pytest.mark.parametrize("reply", FINE_REPLIES)
def test_b_referrals_and_ordinary_replies_are_not_legal_determinations(reply):
    from app.guardrails import legal_conclusion
    assert legal_conclusion(reply) is None


@pytest.mark.parametrize("lang,prospect", [("en", True), ("en", False), ("es", True), ("es", False)])
def test_b_the_referral_is_provisional_until_approved_and_never_a_legal_answer(lang, prospect):
    from app.guardrails import legal_conclusion, legal_referral
    text, status = legal_referral(lang, prospect)
    assert status == "provisional" and text and "{team}" not in text and legal_conclusion(text) is None
    team = {("en", True): "our leasing team", ("en", False): "our management team",
            ("es", True): "nuestro equipo de arrendamiento", ("es", False): "nuestro equipo de administración"}
    assert team[(lang, prospect)] in text
    assert ("can't confirm an accommodation decision" in text) if lang == "en" else ("determinación legal" in text)


def test_b_an_approved_answer_replaces_the_provisional_wording(monkeypatch):
    from app import guardrails
    topic = {"id": "fair_housing", "status": "approved", "answer": "APPROVED: {team} handles these.",
             "answer_es": "APROBADO: {team}."}
    monkeypatch.setattr(guardrails, "_kb", lambda: [topic])
    assert guardrails.legal_referral("en", True) == ("APPROVED: our leasing team handles these.", "approved")


def test_b_the_knowledge_base_marks_the_fair_housing_wording_as_pending():
    from app.guardrails import _kb, property_facts
    t = next(x for x in _kb() if x["id"] == "fair_housing")
    assert t["status"] == "pending_approval" and "answer" not in t and "NEEDS McKINLEY" in t["source"]
    assert "accommodations, assistance animals and fair housing: no approved answer" in property_facts()


@pytest.mark.parametrize("persona,team,word", [(PROSPECT, "leasing", "our leasing team"),
                                              (RESIDENT, "management", "our management team")])
def test_b_a_legal_conclusion_is_replaced_and_the_note_goes_to_people(make, persona, team, word):
    c, _, store = make([
        turn("Generally, fair housing law prohibits pet rent for a support animal. Want a note?"),
        turn("Here's a note.", op="start", kind="staff_handoff", message="Pet rent for my support animal?",
             topic="Support animal question"),
    ])
    sid = f"mn9-{persona}"
    r = chat(c, "Do I have to pay pet rent for my emotional support animal?", sid, persona)
    assert r["reply_source"] == "template_after_validation" and word in r["reply"]
    assert "prohibits" not in r["reply"] and "fair housing law" not in r["reply"]
    assert any(x["code"] == "no_legal_conclusion" and "provisional" in x["detail"] for x in r["output_checks"])
    r = chat(c, "Yes, please make a note about my support animal accommodation.", sid, persona)
    assert r["action"]["kind"] == "staff_handoff" and r["records_created"] == []  # offered, never sent
    assert store.get_draft(sid, persona)["team"] == team


def test_b_an_ordinary_question_keeps_the_model_reply(make):
    c, _, _ = make([turn("I don't have details about the pool hours. Want a note for the office?")])
    r = chat(c, "What are the pool hours?", "mn9-neg", RESIDENT)
    assert r["reply_source"] == "model" and r["reply"].startswith("I don't have details")
    assert all(x["code"] != "no_legal_conclusion" for x in r["output_checks"])


@pytest.mark.parametrize("msg,hit", [("Can you legally charge pet rent for my service dog?", True),
                                     ("I need a reasonable accommodation for my disability", True),
                                     ("is this discrimination?", True), ("What are the pool hours?", False),
                                     ("my dog needs a walk area, where is the dog park?", False)])
def test_b_the_reconnected_gate_recognises_legal_topics(msg, hit):
    from app.guardrails import legal_sensitive
    assert legal_sensitive(msg) is hit


# ==== Scope C: safety observability (no decision changes) =========================================================
def test_c_the_decision_log_explains_a_care_line_without_message_text(make):
    c, _, store = make([turn("Sorry about the ceiling. Which room?")])
    secret = "Quokkaville"
    r = chat(c, f"Honestly I'm done with this place, {secret} ceiling again", "obs-a", RESIDENT)
    assert r["safety_state"] == "concern"  # unchanged: observability only (the known false alarm stays visible)
    g = store.gate_log(1)[0]
    t = g["safety_trace"]
    assert t["policy"]["rule"] == "R6" and t["policy"]["response"] == "care_line"
    assert t["deterministic"]["frame_reason"] == "possible self-harm sign: final"
    assert t["classifier"]["status"] == "ok" and t["classifier"]["level"] == "none"
    assert t["safety_level"] == "concern"
    assert secret not in json.dumps(g) and "done with this place" not in json.dumps(g)


def test_c_the_decision_log_names_the_phrase_rule_and_the_classifier_category(make):
    risk = {**NONE_RISK, "risk_level": "uncertain", "risk_categories": ["flood"], "incident_category": "flood"}
    c, _, store = make([turn("Sorry about that. Which room?")], risk=risk)
    chat(c, "the ceiling is dripping again", "obs-b", RESIDENT)
    t = store.gate_log(1)[0]["safety_trace"]
    assert t["deterministic"]["care"] == "danger" and t["deterministic"]["care_rule"] == "danger_vocabulary"
    assert t["classifier"]["level"] == "uncertain" and t["classifier"]["categories"] == ["flood"]
    assert t["policy"]["rule"] == "R4"


def test_c_the_decision_log_records_why_a_model_reply_was_replaced(make):
    c, _, store = make([turn("Done! Your request has been sent to the office.")])
    r = chat(c, "can you pass this along?", "obs-c", RESIDENT)
    assert r["reply_source"] == "template_after_validation"
    g = store.gate_log(1)[0]
    assert "grounded_claims" in g["validator_failed"] or "no_false_action_claim" in g["validator_failed"]
    assert all("sent to the office" not in x for x in g["validator_reasons"])  # reason codes, never reply text


@pytest.mark.parametrize("msg,tier,rule", [
    ("I'm not suicidal but I feel awful", "distress", "negated_self_harm"),
    ("the ceiling is leaking", "danger", "danger_vocabulary"),
    ("what color are the cabinets?", None, None),
])
def test_c_possible_risk_evidence_matches_possible_risk(msg, tier, rule):
    from app.emergency import possible_risk, possible_risk_evidence
    assert possible_risk_evidence(msg) == (tier, rule) and possible_risk(msg) == tier


def test_c_backend_templates_are_not_reported_as_failed_reply_checks(make):
    c, _, store = make([turn("The repair card is ready.", op="start", kind="maintenance_request",
                             issue="sink clogged", location="bathroom", entry="anytime")])
    chat(c, "my bathroom sink is clogged, come in anytime", "obs-d", RESIDENT)
    r = chat(c, "send it", "obs-d", RESIDENT)
    assert r["records_created"] and r["reply_source"] == "template"
    assert store.gate_log(1)[0]["validator_failed"] == []  # "no visit is scheduled" is the backend's own text



# ==== Final review: a tour placed BEHIND an existing, unsent note (the model keeps the note on screen) ===========
def test_final_a_tour_behind_an_existing_note_is_kept_shown_and_never_sent_by_mistake(make):
    c, _, store = make([
        turn("Here's a note for the leasing team.", op="start", kind="staff_handoff", team="leasing",
             message="Is there a waitlist at Maple Court?", topic="Waitlist"),
        turn("Sure, I can help with a visit too.", other=[{"text": "see Maple Court Thursday at 11am",
                                                           "kind": "tour_request"}]),
        turn("Here's a visit too.", other=[{"text": "tour Maple Court", "kind": "tour_request"}]),
        turn("The tour card has Maple Court, Thursday, 11am.", op="update", kind="tour_request",
             area="Maple Court", days="Thursday", time="11am"),
    ])
    sid, P = "fr-a", PROSPECT
    note = chat(c, "Is there a waitlist at Maple Court? Ask the office.", sid, P)["action"]
    r = chat(c, "Also can I see Maple Court Thursday at 11am?", sid, P)
    # not lost, not sent, and the person is told: the note stays on screen unchanged, the tour waits as a TOUR card
    assert r["action"] == note and r["records_created"] == [] and saved(store) == []
    assert r["reply"].endswith("Your tour request is waiting as the next card, after this one. Nothing has been sent.")
    assert [w["kind"] for w in store.get_draft(sid, P)["waiting"]] == ["tour_request"]
    r = chat(c, "and a tour of Maple Court", sid, P)  # asked again: still exactly one waiting tour, no second line
    assert [w["kind"] for w in store.get_draft(sid, P)["waiting"]] == ["tour_request"]
    assert "waiting as the next card" not in r["reply"]

    wrong = press_send(c, sid, "tour_request", P)  # the Send button of a card that is not on screen
    assert not wrong["ok"] and wrong["error_code"] == "NO_PENDING_ACTION" and saved(store) == []
    r = chat(c, "send it", sid, P)  # typed consent sends the card ON SCREEN (the note), never the waiting tour
    assert [x["kind"] for x in r["records_created"]] == ["staff_handoff"]
    assert "tour request is back on screen, not sent yet" in r["reply"]
    assert r["action"]["kind"] == "tour_request" and r["action"]["stage"] == "collecting"  # now the card on screen
    again = press_send(c, sid, "staff_handoff", P)
    assert not again["ok"] and again["error_code"] == "ALREADY_SAVED" and len(saved(store)) == 1

    r = chat(c, "Thursday 11am at Maple Court", sid, P)
    assert r["action"]["kind"] == "tour_request" and r["action"]["stage"] == "ready"
    assert [x["kind"] for x in chat(c, "send it", sid, P)["records_created"]] == ["tour_request"]
    assert press_send(c, sid, "tour_request", P)["error_code"] == "ALREADY_SAVED"
    assert chat(c, "send it", sid, P)["records_created"] == []  # nothing left on screen: nothing to send
    assert sorted(x["kind"] for x in saved(store)) == ["staff_handoff", "tour_request"]  # one each, no duplicates


def test_final_an_incomplete_waiting_tour_is_never_sent_by_a_typed_send(make):
    c, _, store = make([
        turn("Here's a note.", op="start", kind="staff_handoff", team="leasing", message="Parking?", topic="Parking"),
        turn("Sure.", other=[{"text": "tour sometime", "kind": "tour_request"}]),
    ])
    sid, P = "fr-b", PROSPECT
    chat(c, "Where do guests park? Ask the office please.", sid, P)
    chat(c, "also I want a tour sometime", sid, P)
    assert [x["kind"] for x in chat(c, "send it", sid, P)["records_created"]] == ["staff_handoff"]
    r = chat(c, "send it", sid, P)  # the tour came back with nothing filled in: refused, not saved
    assert r["records_created"] == [] and "Still needed" in r["reply"] and r["action"]["kind"] == "tour_request"
    assert [x["kind"] for x in saved(store)] == ["staff_handoff"]


# ==== Final review: fair-housing boundary matrix (sensitive determinations vs ordinary facts) ===================
BOUNDARY = [
    # (topic, persona, question, model reply, replaced by the referral?)
    ("assistance animal", PROSPECT, "Do I pay pet rent for my emotional support dog?",
     "Assistance animals aren't charged pet rent because they are not pets.", True),
    ("assistance animal", RESIDENT, "Can I keep a service dog?",
     "I don't have that policy; the management team handles service animal requests. Want a note?", False),
    ("wheelchair ramp", RESIDENT, "Can I get a wheelchair ramp at my entrance?",
     "Under the ADA you're entitled to a reasonable accommodation, so they must build it.", True),
    ("wheelchair ramp", RESIDENT, "Can I get a wheelchair ramp at my entrance?",
     "I don't know whether a ramp can be added. I can prepare a note for the management team.", False),
    ("reasonable accommodation", RESIDENT, "Can I have a reasonable accommodation for a reserved parking spot?",
     "Fair housing law requires the property to approve that request.", True),
    ("reasonable accommodation", PROSPECT, "How do I request a reasonable accommodation?",
     "The leasing team handles accommodation requests; I can prepare a note for them.", False),
    ("demographics", PROSPECT, "Which community has fewer families with kids?",
     "Maple Court has fewer families with children, so it's quieter.", True),
    ("demographics", PROSPECT, "Are the residents at Maple Court mostly older?",
     "Residents there are mostly older, so it's very calm.", True),
    ("demographics", PROSPECT, "Which community has fewer families with kids?",
     "I can't describe or compare communities by who lives there. I can help with floor plans or a tour.", False),
    ("pet policy", PROSPECT, "Do you allow cats?",
     "Sample: up to two cats or dogs per home are welcome, with a one-time pet fee; some breed limits apply.", False),
    ("pet policy", RESIDENT, "Is there pet rent for a cat?",
     "I don't have the approved pet policy. Want me to prepare a note for the office?", False),
    ("amenities", PROSPECT, "Is there a playground?",
     "Sample: the community has a fitness room, a seasonal pool and a playground for kids.", False),
    ("amenities", RESIDENT, "When does the pool open?",
     "I don't have the pool hours. Want a note for the office?", False),
]


@pytest.mark.parametrize("topic,persona,question,reply,replaced", BOUNDARY,
                         ids=[f"{b[0]}-{'referral' if b[4] else 'answer'}-{i}" for i, b in enumerate(BOUNDARY)])
def test_final_fair_housing_boundary(make, topic, persona, question, reply, replaced):
    c, _, store = make([turn(reply)])
    r = chat(c, question, f"fh-{abs(hash((question, reply))) % 99999}", persona)
    flagged = any(x["code"] == "no_legal_conclusion" for x in r["output_checks"])
    assert flagged is replaced and r["records_created"] == [] and saved(store) == []
    if replaced:
        assert r["reply_source"] == "template_after_validation"
        assert r["reply"].startswith("Questions about accommodations or community policies may require review by")
        assert ("our leasing team" if persona == PROSPECT else "our management team") in r["reply"]
        assert reply.split(",")[0] not in r["reply"]  # the determination itself is never shown
    else:
        assert r["reply_source"] == "model" and r["reply"] == reply  # ordinary facts and referrals stay answerable
