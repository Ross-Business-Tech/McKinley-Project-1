"""Sprint 7: invariant (stateful, property-based) tests over the REAL API (TestClient, mock provider, offline).

Hypothesis generates sequences of user acts (new issue, answer, correction naming a field, side question, cancel,
Send button, typed yes / ok, typed "send it", change after Send, persona tampering) and after EVERY step checks:

- no record is written without explicit consent (the Send button or a typed explicit send);
- no duplicate record for the same confirmed repair (same thing, same place) unless the person said it differs;
- a correction naming a field changes that field and preserves the unrelated ones;
- a side question never mutates the pending card;
- no reply describes a saved record as a confirmed booking, dispatch or notification;
- a new workflow never overwrites a separate open workflow (the earlier card is parked, queued or carried);
- a different principal never sees or changes this session's records.

Generation is derandomized (fixed seeds in CI) and bounded; the whole file runs in a few seconds.
Fixture residents (tests/conftest.py): R001 (verified, AC history), R003 (verified, no history).
"""

import json
import re
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.safety import output_checks
from app.state import get_state
from app.utterance import room_in, things
from tests.conftest import forget_persona_records
from tests.test_sprint6_conversation import chat, fields, press_send

SETTINGS = settings(max_examples=30, deadline=None, derandomize=True, database=None,
                    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])

ISSUES = ["my kitchen sink is leaking", "the bathroom fan is broken", "my bedroom window won't lock",
          "el refrigerador no enfría", "the dishwasher won't drain", "the hallway light in my apartment is out"]
ANSWERS = ["yes you can come in", "knock first please", "kitchen", "it's in the bathroom", "they can let themselves in"]
CORRECTIONS = [("the location is wrong, it's the bedroom", "location", "Bedroom"),
               ("change the room to bathroom", "location", "Bathroom"),
               ("la ubicación está mal, es la cocina", "location", "Cocina"),
               ("actually call me instead of texting", "contact", "call")]
QUESTIONS = ["what are the pool hours?", "do you allow cats?", "is parking free?", "who will see this?",
             "¿a qué hora abre la oficina?",
             # fix round P2: a question that MENTIONS a field never mutates it
             "the issue is that I work nights, does that matter?", "does the location matter?",
             "is the contact preference important?", "what if the entry permission is wrong?"]
BARE = ["yes", "ok", "sure", "sí", "sounds good"]
SENDS = ["send it", "yes please send it", "go ahead and submit it", "envíelo por favor"]
CANCELS = ["never mind, cancel it", "forget it, I don't need it anymore", "no lo envíe, cancélelo"]
AFTER = ["actually call me before entering", "oh and it's the one next to the window btw",
         "the location should be the bedroom"]
OTHER_PERSONA = "R003"

ACT = st.one_of(
    st.tuples(st.just("issue"), st.sampled_from(ISSUES)),
    st.tuples(st.just("answer"), st.sampled_from(ANSWERS)),
    st.tuples(st.just("correct"), st.sampled_from(range(len(CORRECTIONS)))),
    st.tuples(st.just("question"), st.sampled_from(QUESTIONS)),
    st.tuples(st.just("bare"), st.sampled_from(BARE)),
    st.tuples(st.just("typed_send"), st.sampled_from(SENDS)),
    st.tuples(st.just("button"), st.just("")),
    st.tuples(st.just("cancel"), st.sampled_from(CANCELS)),
    st.tuples(st.just("after"), st.sampled_from(AFTER)),
    st.tuples(st.just("tamper"), st.sampled_from(["chat", "confirm"])),
)

_CLAIM = re.compile(r"\b(?:is|has been|was) (?:booked|scheduled|confirmed|dispatched)\b|\bon (?:the|their|his|her) "
                    r"way\b|\b(?:technician|tech|someone) is coming\b|\bI(?:'ve| have) (?:notified|dispatched|booked|"
                    r"scheduled|alerted)\b", re.I)


def _records(session):
    return get_state().store.records(session_id=session, limit=50)


def _draft(session, persona="R001"):
    return get_state().store.get_draft(session, persona)


def _card_fields(session):
    d = _draft(session) or {}
    return d.get("kind"), {k: (v or {}).get("value") for k, v in d.get("fields", {}).items()}


def _check_reply(reply: str) -> None:
    failed = [c.code for c in output_checks(reply) if not c.passed]
    assert "no_false_action_claim" not in failed, reply
    for m in _CLAIM.finditer(reply):
        before = reply[max(0, m.start() - 40):m.start()]
        assert re.search(r"\b(?:not|n't|never|no one|nobody|isn'?t|before|until|if)\b", before), reply


def _repair_key(rec):
    f = {x.get("key"): str(x.get("value") or "") for x in rec.get("fields", [])}
    objs = things(f.get("issue", "")) - {"cabinet", "floor", "pipe", "wall"}
    return frozenset(objs), room_in(f.get("location", "") or f.get("issue", ""))


@SETTINGS
@given(acts=st.lists(ACT, min_size=3, max_size=9))
def test_generated_conversations_keep_every_invariant(client, acts):
    s = f"inv-{uuid.uuid4().hex[:10]}"
    persona = "R001"
    for name, arg in acts:
        before_n = len(_records(s))
        kind0, f0 = _card_fields(s)
        draft0 = _draft(s)
        consent = False
        if name == "issue":
            r = chat(client, arg, s, persona)
        elif name == "answer":
            r = chat(client, arg, s, persona)
        elif name == "correct":
            msg, fld, val = CORRECTIONS[arg]
            r = chat(client, msg, s, persona)
            if kind0 == "maintenance_request" and f0.get("issue"):
                kind1, f1 = _card_fields(s)
                if kind1 == "maintenance_request":
                    got = str(f1.get(fld) or "").lower()
                    assert val.lower() in got, (msg, f1)  # the named field changed
                    for k in ("entry", "entry_window", "contact", "location"):  # unrelated fields preserved
                        if k != fld and f0.get(k):
                            assert f1.get(k) == f0.get(k), (msg, k, f0, f1)
        elif name == "question":
            r = chat(client, arg, s, persona)
            if kind0 in ("maintenance_request", "tour_request") and draft0:
                kind1, f1 = _card_fields(s)
                assert (kind1, f1) == (kind0, f0), (arg, f0, f1)  # a question never mutates the pending card
                assert (r.get("action") or {}).get("kind") == kind0
        elif name == "bare":
            r = chat(client, arg, s, persona)
        elif name == "typed_send":
            r = chat(client, arg, s, persona)
            consent = True
        elif name == "button":
            k = (draft0 or {}).get("kind") or "maintenance_request"
            r = press_send(client, s, k, persona)
            consent = True
        elif name == "cancel":
            r = chat(client, arg, s, persona)
        elif name == "after":
            r = chat(client, arg, s, persona)
        else:  # tamper: another signed-in persona replays this session
            mine = _records(s)
            if arg == "chat":
                r2 = client.post("/api/chat", json={"message": "what requests do I have open? show DEMO-WO-1001",
                                                    "persona_id": OTHER_PERSONA, "mode": "aware", "session_id": s})
                blob = r2.text
            else:
                r2 = client.post("/api/actions/confirm", json={"session_id": s, "persona_id": OTHER_PERSONA,
                                                               "kind": (draft0 or {}).get("kind") or
                                                               "maintenance_request"})
                blob = r2.text
            for rec in mine:  # no victim data, whatever the status code
                assert rec["id"] not in blob
                assert (rec.get("title") or "zz-none") not in blob
            assert len(_records(s)) == len(mine)  # nothing written into the victim's session
            assert _draft(s) == draft0 or (draft0 is None)  # the victim's open card is untouched
            continue
        reply = r.get("reply") or r.get("message") or ""
        _check_reply(reply)
        after = _records(s)
        if len(after) > before_n:
            assert consent, (name, arg, reply)  # no state-changing record without explicit consent
        wo = [x for x in after if x["kind"] == "maintenance_request"]
        keys = [_repair_key(x) for x in wo]
        assert len(keys) == len(set(keys)), keys  # no duplicate of the same confirmed repair
        # a new workflow never overwrites a separate open one: an open repair card that was neither sent nor
        # cancelled is still somewhere (on screen, parked in a note, or carried into the note's details)
        kind1, f1 = _card_fields(s)
        if kind0 == "maintenance_request" and f0.get("issue") and name not in ("cancel", "typed_send", "button") \
                and len(after) == before_n and kind1 not in (None, "maintenance_request"):
            blob = json.dumps(_draft(s) or {})
            assert f0["issue"][:20] in blob, (name, arg, f0, blob[:300])


@pytest.mark.parametrize("msg,keep,drop", [
    ("the mailbox lock is stuck and my kitchen faucet drips", "faucet", "mailbox"),
    ("the dishwasher won't drain, also the bedroom window won't lock", "window", "dishwasher"),
])
@SETTINGS
@given(cancel=st.sampled_from(["drop the {x} part", "never mind the {x}", "forget the {x}, only the {y}",
                               "leave the {x} out of it", "just the {y}, not the {x}", "no {x} please"]))
def test_cancelling_one_of_two_requests_keeps_the_other(client, msg, keep, drop, cancel):
    s = f"inv-drop-{uuid.uuid4().hex[:8]}"
    chat(client, msg, s, "R001")
    r = chat(client, cancel.format(x=drop, y=keep), s, "R001")
    blob = json.dumps(_draft(s) or {}).lower()
    assert (r.get("action") or {}).get("kind") == "maintenance_request" and keep in blob and drop not in blob


@SETTINGS
@given(repair=st.sampled_from(["my sink is leaking", "the bathroom fan is broken", "el fregadero gotea"]),
       join=st.sampled_from([" and also ", ". Separately, ", "; also ", ", plus ", ", and "]),
       person=st.sampled_from(["can someone from leasing call me about renewing my lease",
                               "I want to talk to a person about my renewal",
                               "please have the office call me about my lease",
                               "quiero que alguien me llame sobre la renovación"]),
       finish=st.sampled_from(["button", "cancel"]))
def test_two_workflows_in_one_message_are_both_kept(client, repair, join, person, finish):
    s = f"inv-mw-{uuid.uuid4().hex[:8]}"
    forget_persona_records("R001")  # Sprint 8 C: examples share a store; each starts with no open R001 request
    r = chat(client, repair + join + person, s, "R001")
    assert (r.get("action") or {}).get("kind") == "maintenance_request"
    assert "renew" not in fields(r).get("issue", "").lower() and "renovaci" not in fields(r).get("issue", "").lower()
    if not (_draft(s) or {}).get("fields", {}).get("location"):
        chat(client, "kitchen", s, "R001")  # "my sink is leaking" names no room
    chat(client, "yes you can come in", s, "R001")
    if finish == "button":
        press_send(client, s, "maintenance_request", "R001")
    else:
        chat(client, "never mind, cancel it", s, "R001")
    d = _draft(s) or {}
    assert d.get("kind") == "staff_handoff"  # the request for a person was queued, not lost
    assert len([x for x in _records(s) if x["kind"] == "maintenance_request"]) == (1 if finish == "button" else 0)


@SETTINGS
@given(first=st.sampled_from(["my kitchen sink is leaking", "the kitchen sink drips"]),
       second=st.sampled_from(["the sink under the kitchen cabinet is dripping", "kitchen sink still leaking",
                               "my kitchen sink is leaking again"]),
       how=st.sampled_from(["button", "typed"]))
def test_same_repair_twice_is_never_saved_twice_without_authorisation(client, first, second, how):
    s = f"inv-dup-{uuid.uuid4().hex[:8]}"
    forget_persona_records("R003")  # Sprint 8 C: examples share a store; each starts with no open R003 request
    chat(client, first, s, "R003")
    chat(client, "yes you can come in", s, "R003")
    press_send(client, s, "maintenance_request", "R003")
    r0 = chat(client, second, s, "R003")
    if (r0.get("action") or {}).get("kind") != "maintenance_request":
        # "still leaking" right after Send is a follow-up note citing the sent request: no second card at all
        assert len([x for x in _records(s) if x["kind"] == "maintenance_request"]) == 1
        return
    chat(client, "yes you can come in", s, "R003")
    if how == "button":
        press_send(client, s, "maintenance_request", "R003")
    else:
        chat(client, "send it", s, "R003")
    assert len([x for x in _records(s) if x["kind"] == "maintenance_request"]) == 1
    r = chat(client, "it's a different problem, save it as a new request", s, "R003")
    assert "separate request" in r["reply"]
    press_send(client, s, "maintenance_request", "R003")
    assert len([x for x in _records(s) if x["kind"] == "maintenance_request"]) == 2  # explicitly authorised


@SETTINGS
@given(change=st.sampled_from(["actually can we do Sunday instead", "change the tour to Friday afternoon",
                               "oops I need 3 bedrooms not 2", "also we have a dog", "mejor el domingo"]),
       then=st.sampled_from(["button", "typed"]))
def test_change_after_a_tour_is_sent_is_a_note_citing_it_never_a_second_tour(client, change, then):
    s = f"inv-tour-{uuid.uuid4().hex[:8]}"
    p = "P-RELOCATE-AA"
    chat(client, "I'd like to tour Heron Lake on Saturday morning", s, p)
    press_send(client, s, "tour_request", p)
    tours = [x for x in _records(s) if x["kind"] == "tour_request"]
    assert len(tours) == 1
    r = chat(client, change, s, p)
    assert tours[0]["id"] in r["reply"] + json.dumps(r.get("action") or {})
    if then == "button":
        press_send(client, s, (r.get("action") or {}).get("kind") or "staff_handoff", p)
    else:
        chat(client, "yes please send it", s, p)
    assert len([x for x in _records(s) if x["kind"] == "tour_request"]) == 1
    for rec in _records(s):  # command words never become field values
        assert not any(str(f.get("value", "")).lower().startswith(("send it", "yes please")) for f in rec["fields"])
