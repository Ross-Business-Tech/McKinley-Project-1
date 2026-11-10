"""Sprint 6: the optional MODEL pass of the understanding layer (offline, fake provider) and the workflow state
machine. The model pass must be validated, bounded and fall back to the rules on bad JSON, timeouts and errors; the
merge may only add (never confirm a save, grant entry permission, invent a reference or clear a possible emergency).
"""

import json
from types import SimpleNamespace

import pytest

import app.understanding as und
from app import workflow_state as wf
from app.llm import GenerationConfig, LLMError, Target
from app.state import get_state
from app.understanding import DialogueAct, merge, model_pass, parse_model_json, understand, understand_rules

GOOD = {"primary_intent": "handoff", "dialogue_acts": ["request_human"], "requests_human": True,
        "report_possible_emergency": False, "corrections": [], "entities": {}, "needs_clarification": False,
        "confidence": 0.9}


class FakeGateway:
    """Implements the slice of LLMGateway that model_pass uses. `behaviour` is a JSON string or an exception."""

    def __init__(self, behaviour, provider="openrouter", ready=True):
        self.behaviour, self.ready, self.calls = behaviour, ready, []
        self.default_target = Target(provider, "fake/model")

    def provider_ready(self, provider):
        return self.ready, "fake"

    def generation_config(self, target):
        return GenerationConfig(max_tokens=2000, temperature=0.2, timeout_seconds=30, max_retries=2)

    def complete(self, system, messages, target=None, strict_model=True, schema=None, schema_name="", cfg=None):
        self.calls.append({"schema_name": schema_name, "cfg": cfg, "messages": messages, "schema": schema})
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return SimpleNamespace(extra={"content": self.behaviour}, model="fake/model")


MODEL = SimpleNamespace(understanding_provider="model")
AUTO = SimpleNamespace(understanding_provider="auto")
RULES = SimpleNamespace(understanding_provider="rules")


def test_model_pass_is_validated_bounded_and_sees_no_account_data():
    gw = FakeGateway(json.dumps(GOOD))
    res, status = model_pass(gw, MODEL, "would love a word with whoever runs the place", "maintenance_request", "entry",
                             ["the sink leaks"])
    assert status == "ok" and res.requests_human
    call = gw.calls[0]
    assert call["schema_name"] == "mckinley_understanding" and call["schema"] == und.SCHEMA
    assert call["cfg"].max_retries == 0 and call["cfg"].timeout_seconds <= 20 and call["cfg"].temperature == 0
    sent = json.dumps(call["messages"])
    assert "maintenance_request" in sent and "Marisol" not in sent and "R001" not in sent


@pytest.mark.parametrize("behaviour,status", [
    ("not json at all", "bad_output"), ("{\"primary_intent\": \"handoff\"", "bad_output"),
    (json.dumps({**GOOD, "dialogue_acts": ["take_over_the_world"]}), "bad_output"),
    (json.dumps({**GOOD, "confidence": 7}), "bad_output"), ("[1, 2, 3]", "bad_output"),
    (LLMError("MODEL_TIMEOUT", "slow"), "timeout"), (LLMError("MODEL_API_ERROR", "500"), "error"),
    (LLMError("LLM_BUDGET_EXHAUSTED", "budget"), "budget"), (RuntimeError("boom"), "error"),
])
def test_model_failures_fall_back_to_the_rules(behaviour, status):
    gw = FakeGateway(behaviour)
    res, st = model_pass(gw, MODEL, "the sink is leaking", None, None)
    assert res is None and st == status
    u = understand("the sink is leaking", None, None, None, (res, st))
    assert u.source == "rules" and u.model_status == status and u.has(DialogueAct.NEW_REQUEST)


def test_json_in_a_code_fence_or_with_text_around_it_is_accepted():
    assert parse_model_json("```json\n" + json.dumps(GOOD) + "\n```").requests_human
    assert parse_model_json("Here you go: " + json.dumps(GOOD) + " done").requests_human


@pytest.mark.parametrize("settings,provider,ready,status", [
    (RULES, "openrouter", True, "not_used"), (MODEL, "mock", True, "mock"), (AUTO, "mock", True, "mock"),
    (MODEL, "openrouter", False, "unavailable")])
def test_model_pass_only_runs_when_configured_and_live(settings, provider, ready, status):
    gw = FakeGateway(json.dumps(GOOD), provider=provider, ready=ready)
    assert model_pass(gw, settings, "hi", None, None) == (None, status) and gw.calls == []


def test_provider_mode_defaults_to_rules(monkeypatch):
    monkeypatch.delenv("UNDERSTANDING_PROVIDER", raising=False)
    assert und.provider_mode(SimpleNamespace()) == "rules"
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "bogus")
    assert und.provider_mode(SimpleNamespace()) == "rules"
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "auto")
    assert und.provider_mode(SimpleNamespace()) == "auto"


def _m(**kw):
    return und.ModelUnderstanding.model_validate({**GOOD, **kw})


def test_merge_only_adds_and_never_confirms_or_grants_permission():
    msg = "would love a word with whoever runs the place"
    rules = understand_rules(msg, None, None)
    m = _m(dialogue_acts=["confirm", "request_human"], entities={"entry_permission": "yes, enter anytime"})
    u = merge(rules, m, "ok", msg)
    assert u.requests_human and u.source == "merged" and not u.has(DialogueAct.CONFIRM) and not u.explicit_send
    assert u.entities.entry_permission is None


def test_merge_drops_ungrounded_entities_and_references():
    msg = "I'd like to see the place"
    m = _m(entities={"community": "Heron Lake Apartments", "tour_date": "December 14", "budget": "Up to 1,500"},
           corrections=[{"field": "location", "value": "Kitchen"}])
    u = merge(understand_rules(msg, None, None), m, "ok", msg)
    assert u.entities.community is None and u.entities.tour_date is None and u.entities.budget is None
    assert not u.corrections and u.entities.reference_id is None


def test_merge_keeps_grounded_model_entities():
    msg = "thinking about heron lake apartments sometime in december"
    m = _m(primary_intent="tour", dialogue_acts=["new_request"], requests_human=False,
           entities={"community": "Heron Lake Apartments"})
    u = merge(understand_rules(msg, None, None), m, "ok", msg)
    assert u.entities.community == "Heron Lake Apartments"


def test_possible_emergency_is_or_ed_and_never_cleared_by_the_model():
    msg = "there's smoke coming from the outlet"
    rules = understand_rules(msg, None, None)
    assert rules.report_possible_emergency
    calm = merge(rules, _m(report_possible_emergency=False, dialogue_acts=["new_request"], requests_human=False),
                 "ok", msg)
    assert calm.report_possible_emergency  # the model saying "no danger" changes nothing
    quiet = "my neighbour hasn't answered the door in three days"
    raised = merge(understand_rules(quiet, None, None), _m(report_possible_emergency=True, requests_human=False,
                                                          dialogue_acts=[]), "ok", quiet)
    assert raised.report_possible_emergency and raised.model_emergency


def test_model_confidence_never_authorises_a_save():
    msg = "looks good"
    ready = {"kind": "maintenance_request", "fields": {k: {"value": "x", "source": "you_said"}
                                                       for k in ("issue", "location", "entry")}}
    u = merge(understand_rules(msg, ready, None), _m(dialogue_acts=["confirm"], requests_human=False,
                                                     confidence=1.0), "ok", msg)
    tr = wf.apply(wf.derive(ready), u)
    assert not tr.has("save")


# ---- end to end with the model mode on (the pass is faked; no network) -------------------------------------------


def test_model_mode_end_to_end_adds_a_handoff_the_rules_missed(client, monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "model")
    monkeypatch.setattr(get_state().deps.settings, "understanding_provider", "model")
    msg = "would love a word with whoever runs the place"
    assert not understand_rules(msg, None, None).requests_human  # the rules alone miss this wording
    seen = []

    def fake_pass(gateway, settings, m, kind, pending, recent=None):
        seen.append(m)
        return (_m(), "ok")
    monkeypatch.setattr(und, "model_pass", fake_pass)
    client.post("/api/chat", json={"message": "the bathroom fan is buzzing", "persona_id": "R003", "mode": "aware",
                                   "session_id": "mm1"})
    r = client.post("/api/chat", json={"message": msg, "persona_id": "R003", "mode": "aware",
                                       "session_id": "mm1"}).json()
    assert seen and r["action"]["kind"] == "staff_handoff" and r["records_created"] == []
    step = next(p for p in r["pipeline"] if p["step"] == "6a_understanding")
    assert "source=merged" in step["detail"] and "model=ok" in step["detail"]


def test_model_mode_bad_output_still_answers_from_the_rules(client, monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "model")
    monkeypatch.setattr(get_state().deps.settings, "understanding_provider", "model")
    monkeypatch.setattr(und, "model_pass", lambda *a, **k: (None, "bad_output"))
    r = client.post("/api/chat", json={"message": "the bathroom fan is buzzing", "persona_id": "R003",
                                       "mode": "aware", "session_id": "mm2"}).json()
    assert r["action"]["kind"] == "maintenance_request"
    step = next(p for p in r["pipeline"] if p["step"] == "6a_understanding")
    assert step["status"] == "warn" and "model=bad_output" in step["detail"]


def test_model_emergency_flag_raises_a_staff_review_only(client, monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "model")
    monkeypatch.setattr(get_state().deps.settings, "understanding_provider", "model")
    monkeypatch.setattr(und, "model_pass", lambda *a, **k: (_m(report_possible_emergency=True, requests_human=False,
                                                               dialogue_acts=[], primary_intent="other"), "ok"))
    r = client.post("/api/chat", json={"message": "my neighbour hasn't answered the door in three days",
                                       "persona_id": "R003", "mode": "aware", "session_id": "mm3"}).json()
    assert r["recommended_handoff"] and r["handoff"]["priority"] in ("high", "urgent")
    assert r["records_created"] == [] or all(x["status"] == "urgent_queued" for x in r["records_created"])


def test_model_mode_typed_yes_still_never_saves(client, monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_PROVIDER", "model")
    monkeypatch.setattr(get_state().deps.settings, "understanding_provider", "model")
    monkeypatch.setattr(und, "model_pass", lambda *a, **k: (_m(dialogue_acts=["confirm"], requests_human=False,
                                                               primary_intent="maintenance", confidence=1.0), "ok"))
    for m in ("the kitchen faucet is dripping", "yes you can come in", "yes", "sounds great, go"):
        r = client.post("/api/chat", json={"message": m, "persona_id": "R003", "mode": "aware",
                                           "session_id": "mm4"}).json()
    assert r["records_created"] == [] and get_state().store.records(session_id="mm4", limit=10) == []


# ---- the workflow state machine -----------------------------------------------------------------------------------

READY = {"kind": "maintenance_request", "fields": {k: {"value": "x", "source": "you_said"}
                                                   for k in ("issue", "location", "entry")}}
COLLECTING = {"kind": "maintenance_request", "fields": {"issue": {"value": "Sink leaks", "source": "you_said"}}}


def _u(msg, draft=None, pending=None):
    return understand_rules(msg, draft, pending)


@pytest.mark.parametrize("draft,state", [
    (None, wf.WState.IDLE), (READY, wf.WState.READY), (COLLECTING, wf.WState.COLLECTING),
    ({**COLLECTING, "vague_issue": True}, wf.WState.AWAITING_CLARIFICATION), ({**READY, "declined": True},
                                                                              wf.WState.DECLINED),
    ({"kind": "staff_handoff", "fields": {}, "parked": READY}, wf.WState.ESCALATION_RECOMMENDED)])
def test_state_is_derived_from_the_store(draft, state):
    assert wf.derive(draft).state is state


def test_states_after_records():
    assert wf.derive(None, [{"status": "submitted_for_review"}]).state is wf.WState.PENDING_STAFF_REVIEW
    assert wf.derive(None, [{"status": "urgent_queued"}]).state is wf.WState.ESCALATION_RECORDED


@pytest.mark.parametrize("msg,effect", [("send it", "save"), ("yes", "prompt_send"), ("ok", "prompt_send"),
                                        ("submit it please", "save")])
def test_only_an_explicit_confirmation_proposes_a_save(msg, effect):
    tr = wf.apply(wf.derive(READY), _u(msg, READY))
    assert tr.has(effect) and (effect == "save") == tr.has("save")


def test_send_button_is_an_explicit_confirmation():
    assert wf.apply(wf.derive(READY), _u("", READY), send_button=True).has("save")


@pytest.mark.parametrize("draft,msg,reason", [(COLLECTING, "send it", "missing"), (None, "send it", "nothing"),
                                              (None, "undo", "declined"), (COLLECTING, "yes", "never saves")])
def test_illegal_transitions_are_rejected(draft, msg, reason):
    tr = wf.apply(wf.derive(draft), _u(msg, draft, "location" if draft else None))
    assert not tr.allowed and not tr.has("save") and reason in tr.reason


def test_request_human_parks_the_open_card_then_opens_a_note():
    tr = wf.apply(wf.derive(COLLECTING), _u("put me through to your supervisor", COLLECTING, "location"))
    assert [e.kind for e in tr.effects] == ["park_draft", "open_handoff"]
    assert tr.after is wf.WState.ESCALATION_RECOMMENDED


def test_cancel_declines_and_skipping_a_note_restores_its_parked_card():
    note = {"kind": "staff_handoff", "fields": {}, "parked": COLLECTING}
    tr = wf.apply(wf.derive(note), _u("never mind", note))
    assert tr.has("decline") and any(e.kind == "restore" and e.field == "maintenance_request" for e in tr.effects)


def test_resume_restores_a_declined_card():
    d = {**READY, "declined": True}
    assert wf.apply(wf.derive(d), _u("I hit cancel by accident", d)).has("restore")


def test_switch_topic_keeps_the_card():
    tr = wf.apply(wf.derive(COLLECTING), _u("forget it, what are the pool hours?", COLLECTING, "location"))
    assert tr.event is wf.Event.SWITCH_TOPIC and tr.has("keep_card") and not tr.has("decline")


def test_two_issues_start_one_draft_and_queue_the_other():
    tr = wf.apply(wf.derive(None), _u("the kitchen faucet is leaking and the bathroom light keeps flickering"))
    assert tr.has("start_draft") and [e.value for e in tr.effects if e.kind == "queue_issue"] == [
        "the bathroom light keeps flickering"]


def test_possible_emergency_is_passed_to_safety_on_top_of_the_event():
    tr = wf.apply(wf.derive(READY), _u("send it, also I smell gas", READY))
    assert tr.effects[0].kind == "pass_to_safety"


def test_every_listed_transition_targets_a_known_state():
    for (state, event), nxt in wf.TRANSITIONS.items():
        assert isinstance(state, wf.WState) and isinstance(event, wf.Event)
        assert nxt in ("same", "recompute") or isinstance(nxt, wf.WState)
    assert (wf.WState.COLLECTING, wf.Event.CONFIRM_EXPLICIT) not in wf.TRANSITIONS
    assert (wf.WState.IDLE, wf.Event.CANCEL) not in wf.TRANSITIONS


def test_duplicate_of_matches_content_not_sources():
    rec = {"kind": "maintenance_request", "persona_id": "R003", "status": "submitted_for_review",
           "fields": [{"key": "issue", "value": "Sink leaks", "source": "you_said"},
                      {"key": "location", "value": "Kitchen", "source": "assistant"}]}
    same = {"fields": {"issue": {"value": "sink leaks", "source": "on_file"}, "location": {"value": "Kitchen"}}}
    other = {"fields": {"issue": {"value": "Toilet runs"}, "location": {"value": "Kitchen"}}}
    assert wf.duplicate_of([rec], "maintenance_request", same, "R003") is rec
    assert wf.duplicate_of([rec], "maintenance_request", other, "R003") is None
    assert wf.duplicate_of([rec], "maintenance_request", same, "R001") is None  # another person's record


def test_a_confident_rules_reading_is_not_overridden_by_the_model():
    # live finding: the model labelled "forget it, what are the pool hours?" as a request for a person
    msg = "forget it, what are the pool hours?"
    card = {"kind": "maintenance_request", "fields": {"issue": {"value": "Fan buzzing"}}}
    u = merge(understand_rules(msg, card, "location"), _m(dialogue_acts=["check_status", "request_human"]), "ok", msg)
    assert not u.requests_human and u.has(DialogueAct.SWITCH_TOPIC) and not u.has(DialogueAct.CHECK_STATUS)
    raised = merge(understand_rules(msg, card, "location"), _m(report_possible_emergency=True,
                                                               dialogue_acts=["report_possible_emergency"]), "ok", msg)
    assert raised.report_possible_emergency  # safety is the exception: always added
