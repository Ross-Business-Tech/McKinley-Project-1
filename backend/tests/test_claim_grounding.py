"""Claim grounding (app/claim_grounding.py): model sentences about staff/actions are checked against backend state.

The "unsupported" examples are real Gemini replies from the live journey runs of 2026-11-11 (synthetic data). The
"kept" examples are honest wording that must survive, including the planner's own approved templates.
"""

from types import SimpleNamespace

import pytest

from app.claim_grounding import GroundingResult, TurnState, ground_reply, unsupported_claim
from app.templates import CARD_NOTE, T

READY = TurnState(card_kind="maintenance_request", card_stage="ready")
COLLECTING = TurnState(card_kind="tour_request", card_stage="collecting")
NONE = TurnState()

UNSUPPORTED = [  # (clause, expected kind)
    ("Please review it and press Send to submit it to the maintenance team.", "delivery"),
    ("Please review your request below and press Send when you are ready to submit it to our leasing team.",
     "delivery"),
    ("Press Send so our team receives your request.", "staff_action"),
    ("Please check the note for the office and press Send so our team can follow up.", "staff_action"),
    ("Please check your request below and press Send so our office receives your details.", "staff_action"),
    ("A leasing team member should follow up to give you exact details.", "staff_action"),
    ("A member of our leasing team can follow up with exact parking details.", "staff_action"),
    ("Once sent, a staff member will follow up with you.", "staff_action"),
    ("Would you like me to note your contact information so the leasing staff can reach out to schedule an "
     "official appointment?", "staff_action"),
    ("Press Send to save it for our team", "delivery"),
    ("Is there a specific phone number or time of day you prefer for a call from the office team?", "staff_action"),
    ("Would you like me to highlight any times this week that work best for a manager to review it with you?",
     "staff_action"),
    ("I would be happy to save a tour request for our leasing team to review with you.", "staff_action"),
    ("I've flagged this request as urgent for our maintenance team to review.", "assistant_action"),
    ("I have sent your request to maintenance.", "assistant_action"),
    ("I've notified the office.", "assistant_action"),
    ("Great, you're all booked for Friday at 10am.", "booking"),
    ("Your tour is confirmed for Saturday morning.", "booking"),
    ("Would you like me to hand this over to our leasing team so they can contact you directly?", "staff_action"),
    ("Por favor presione Enviar para que la reciba el equipo de mantenimiento.", "staff_action"),
    ("El equipo se comunicará con usted pronto.", "staff_action"),
]

KEPT = [
    "I'm so sorry you're dealing with this again.",
    "Which days work best for your visit?",
    "If maintenance comes while you're out, may they enter, or should they contact you first?",
    "Do they have permission to enter if you're not home, or should they contact you first?",
    "Our leasing team has current rent prices.",
    "The leasing team can answer that.",
    "Our leasing team will be in the best position to share current rates.",
    "No one at McKinley will call you from this demo.",
    "It hasn't been sent to maintenance, so no visit is scheduled.",
    "Nothing is booked yet: I can't book or confirm a specific time here.",
    "Please check your request below and press Send to save it.",
    "In the real service, the leasing team would follow up with you.",
    "Don't send it yet if anything looks off.",
    "I've started a repair request for your sink.",
]


@pytest.mark.parametrize("clause,kind", UNSUPPORTED)
def test_unsupported_claims_are_detected_against_prototype_state(clause, kind):
    assert unsupported_claim(clause, READY) == kind


@pytest.mark.parametrize("clause", KEPT)
def test_honest_or_state_backed_sentences_are_kept(clause):
    assert unsupported_claim(clause, READY) is None


def test_repeat_marker_is_allowed_only_when_the_draft_carries_it():
    line = "I can see 3 related maintenance requests since June, so I have marked this as a repeat issue."
    assert unsupported_claim(line, TurnState(card_stage="collecting", repeat_marked=True)) is None
    assert unsupported_claim(line, TurnState(card_stage="collecting", repeat_marked=False)) == "assistant_action"
    staff = "I have flagged this for manager review, and the manager will call you."
    assert unsupported_claim(staff, TurnState(card_stage="collecting", repeat_marked=True)) == "staff_action"


def test_a_real_integration_would_make_delivery_claims_supported():
    """Delivery is grounded in records: only a non-prototype system (none exists today) supports it."""
    real = TurnState(card_stage="ready", delivered_parties=frozenset({"maintenance"}))
    assert unsupported_claim("Press Send so our team receives your request.", real) is None


def test_ready_card_keeps_warm_part_and_gets_the_state_next_step():
    reply = ("I'm sorry to hear your dishwasher is leaking. Your request is ready below, so please review it and press "
             "Send to submit it to the maintenance team.")
    res = ground_reply(reply, READY)
    assert res.removed and res.status_line_added and not res.needs_template
    assert res.reply == "I'm sorry to hear your dishwasher is leaking. When it looks right, press Send to save it."


def test_dash_clause_removal_keeps_the_question():
    reply = ("I understand. Please check your request below and press Send to save it for our team—is there anything "
             "else about the lock I should add?")
    res = ground_reply(reply, READY)
    assert "our team" not in res.reply and res.reply.endswith("should add?")


def test_collecting_reply_that_loses_its_question_falls_back_to_the_template():
    reply = "Great, the leasing team will call you to pick a time?"
    res = ground_reply(reply, COLLECTING)
    assert res.needs_template


def test_unchanged_reply_is_returned_verbatim():
    reply = "Got it, Friday works. What time of day is easiest for you: morning, afternoon, or evening?"
    res = ground_reply(reply, COLLECTING)
    assert isinstance(res, GroundingResult) and not res.changed and res.reply == reply


def test_spanish_status_line_on_a_ready_card():
    res = ground_reply("Gracias. Presione Enviar para que la reciba el equipo de mantenimiento.",
                       TurnState(card_stage="ready", lang="es"))
    assert res.reply == "Gracias. Cuando esté bien, presione Enviar para guardarla."


def test_state_is_read_from_the_plan_not_the_text():
    rec = SimpleNamespace(id="DEMO-WO-1001", system="prototype", team="maintenance")
    plan = SimpleNamespace(action=SimpleNamespace(kind="maintenance_request", stage="submitted", record=rec,
                                                  fields=[SimpleNamespace(value="repeat issue (history on record)")]),
                           records=[rec], facts=[])
    st = TurnState.from_plan(plan, "en")
    assert st.card_stage == "submitted" and st.records_written == ("DEMO-WO-1001",)
    assert st.delivered_parties == frozenset() and st.repeat_marked  # a prototype record reaches no one


@pytest.mark.parametrize("key", ["repeat_history_many", "repeat_history_one", "maint_ready_repeat",
                                 "repeat_history_saved"])
def test_planner_repeat_templates_survive_when_the_flag_is_set(key):
    text = T[key]["en"].format(n="3", window="since June")
    res = ground_reply(text, TurnState(card_stage="ready", repeat_marked=True))
    assert not res.removed, res.removed


@pytest.mark.parametrize("kind", ["maintenance_request", "tour_request", "staff_handoff"])
def test_card_demo_lines_are_honest_statements(kind):
    for stage in ("open", "saved"):
        for lang in ("en", "es"):
            assert not ground_reply(CARD_NOTE[stage][kind][lang], READY).removed


# ------------------------------------------------------------------------- through /api/chat (mock provider)
def _model_says(text):
    from app.llm.base import LLMResult, ModelOutput

    def fake(system, messages, target):
        return LLMResult(output=ModelOutput(reply=text), provider="mock", requested_model=target.model,
                         model=target.model, parse_mode="json", is_mock=True, stop_reason="end", input_tokens=1,
                         output_tokens=1, latency_ms=1)
    return fake


def _chat(client, message, session, persona="R001"):
    r = client.post("/api/chat", json={"message": message, "persona_id": persona, "mode": "aware",
                                       "session_id": session})
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_ready_card_claim_is_removed_and_warmth_kept(client, monkeypatch):
    from app.state import get_state

    monkeypatch.setattr(get_state().deps.llm, "complete", _model_says(
        "I'm sorry your kitchen sink is leaking. Please review your request below and press Send to submit it to "
        "our maintenance team so they can follow up with you."))
    r = None
    for m in ("My kitchen sink is leaking under the cabinet", "yes, they can come in if I'm not home"):
        r = _chat(client, m, "g-ready")
        if (r.get("action") or {}).get("stage") == "ready":
            break
    assert r and r["action"]["stage"] == "ready"
    if r["reply_source"] == "model":
        assert r["reply"].startswith("I'm sorry your kitchen sink is leaking.")
        assert "press Send to save it" in r["reply"]
    assert "maintenance team" not in r["reply"] and "follow up" not in r["reply"]
    checks = {c["code"]: c for c in r["output_checks"]}
    assert "Removed" in checks["claims_grounded"]["detail"] or r["reply_source"] != "model"
    assert checks["no_false_action_claim"]["passed"] is False  # the raw model claim stays visible to staff
    assert r["records_created"] == []  # nothing was written by the model's words


def test_chat_booking_claim_never_reaches_a_prospect(client, monkeypatch):
    from app.state import get_state

    monkeypatch.setattr(get_state().deps.llm, "complete", _model_says(
        "Great news, you're all booked for Saturday morning! The leasing team will call you to confirm."))
    r = _chat(client, "Can I tour a two-bed in Ann Arbor on Saturday morning?", "g-book", persona="P-RELOCATE-AA")
    assert "booked" not in r["reply"].lower() and "will call" not in r["reply"].lower()
    assert r["records_created"] == []


def test_journey_evaluator_treats_an_echoed_budget_as_the_users_number():
    from app.usability.journey_evaluator import _echoes_user_amount

    assert _echoes_user_amount("I can't confirm rates for 1 beds under $1,300 right now.", "i need under 1300. yes?")
    assert not _echoes_user_amount("A one-bed is $1,150 a month.", "i need under 1300")
    assert not _echoes_user_amount("No amounts here.", "1300")


@pytest.mark.parametrize("clause", [
    "You can now press Send on your request below to save it.",
    "Your request is ready below, so press Send when it looks right.",
    "Presione Enviar cuando esté bien.",
])
def test_send_step_is_only_allowed_on_a_ready_card(clause):
    assert unsupported_claim(clause, READY) is None
    for stage in ("collecting", "submitted", None):
        assert unsupported_claim(clause, TurnState(card_stage=stage)) == "card_stage", stage


def test_collecting_reply_claiming_ready_falls_back_to_the_question():
    res = ground_reply("Thank you for granting entry permission. You can now press Send on your request below to save "
                       "it.", TurnState(card_kind="maintenance_request", card_stage="collecting"))
    assert res.removed[0][0] == "card_stage" and res.needs_template


def test_not_ready_is_honest_on_any_stage():
    line = "Your tour request isn't sent yet; it's waiting for you to press Send."
    assert unsupported_claim(line, TurnState(card_stage="collecting")) is None


# ---- independent status-claim audit (2026-11-12): every probe it showed passing must now be caught ---------------
NO_CARD = TurnState()
AUDIT_FALSE = [  # (clause, state) the audit showed passing both grounding and the validator
    ("Your request is saved.", NO_CARD),
    ("Your work order DEMO-WO-9999 is saved.", NO_CARD),
    ("Your request has been received.", NO_CARD),
    ("Your request went to the office.", NO_CARD),
    ("You're all set for Saturday at 10!", NO_CARD),
    ("No need to wait, someone will contact you within 24 hours.", NO_CARD),
    ("Your tour is not a problem, they will confirm it.", NO_CARD),
    ("They will call you tomorrow.", NO_CARD),
    ("Expect a call within 24 hours.", NO_CARD),
    ("A technician is on the way.", NO_CARD),
    ("We'll be in touch shortly.", NO_CARD),
    ("Un miembro de nuestro equipo deberá ponerse en contacto con usted para ayudarle con los detalles.", READY),
    ("He preparado una nota para que un agente lo revise.", READY),
    ("The leasing office will be glad to walk you through all of your options.", READY),
    ("Puede indicar su respuesta y presionar Enviar para guardarla.", TurnState(card_stage="collecting", lang="es")),
    ("I am recommending that our office staff review this request right away.", READY),
    ("I've started a note for our office team so you can connect with someone about your deposit.", READY),
    ("I'll pass your request to the leasing team in a note so they can help you with current rates.", READY),
    ("I can gather your details for the leasing team to check open two-bed floor plans.", READY),
    ("I can help start a tour request for you to connect with our Florida leasing team.", READY),
]
# An offer of the real note/request action ("I can save a tour request to share with the leasing team", "I can send a
# note to the office") is kept, consistent with the approved backend offers; whether offers should be reworded is a
# product decision recorded in docs/evaluation/GEMINI_GATEWAY_ACCEPTANCE.md.


@pytest.mark.parametrize("clause,state", AUDIT_FALSE, ids=[c[:40] for c, _ in AUDIT_FALSE])
def test_audit_probes_are_caught(clause, state):
    assert unsupported_claim(clause, state) is not None


def test_saved_and_references_are_checked_against_real_records():
    real = TurnState(card_stage="submitted", records_written=("DEMO-WO-1001",))
    assert unsupported_claim("Your repair request DEMO-WO-1001 is saved.", real) is None
    assert unsupported_claim("Your repair request DEMO-WO-1002 is saved.", real) == "invented_reference"
    later = TurnState(session_records=("DEMO-TOUR-1010",))  # an earlier turn saved it; no card now
    assert unsupported_claim("Your tour request DEMO-TOUR-1010 is saved in this demo.", later) is None
    assert unsupported_claim("Your request is saved.", TurnState()) == "saved_without_record"


@pytest.mark.parametrize("clause", [
    "I've marked your preference for a morning time.",
    "Nothing has been saved in this chat yet.",
    "It hasn't been sent to maintenance, so no visit is scheduled.",
    "No one will call you from this demo.",
    "If maintenance comes while you're out, may they enter, or should they contact you first?",
    "The leasing team can answer that.",
    "Our leasing team has current rent prices.",
])
def test_audit_honest_sentences_survive(clause):
    assert unsupported_claim(clause, READY) is None


# ---- final independent audit (2026-11-12) -------------------------------------------------------------------------
@pytest.mark.parametrize("clause,state", [
    ("Could you update your contact details on your request below before pressing Send to save it?", NO_CARD),
    ("Please check your request below and press Send to save it for review.", READY),
    ("Please check it and press Send to save it for staff review.", READY),
    ("I'm recommending a handoff so a staff member can connect with you directly.", READY),
    ("I've prepared this so we can connect you with the right team.", READY),
    ("I've started a note for our office to connect you with staff.", TurnState(card_kind="staff_handoff",
                                                                                 card_stage="ready")),
])
def test_final_audit_borderlines_are_caught(clause, state):
    assert unsupported_claim(clause, state) is not None


def test_note_for_the_office_describing_its_content_is_kept():
    st = TurnState(card_kind="staff_handoff", card_stage="ready")
    line = 'I\'ve prepared a note for the office to add "the window latch" to your request.'
    assert unsupported_claim(line, st) is None
    assert unsupported_claim("I've prepared a note below asking the office to check on her.", st) is None
