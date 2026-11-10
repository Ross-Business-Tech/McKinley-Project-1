"""Sprint 6 final fix round, from the independent UX judge (H-1, H-2).

H-1: a message that names another field ("the location is wrong, it should say kitchen") must change only that field,
never the problem text. H-2: a responder's all-clear ("the fire dept said it's fine") is not a new fire report.
Paraphrases are written from the behaviour, not copied from one repro.
"""

import pytest

from app.intake import extract_issue_restate, extract_location_change, names_other_field
from app.risk.detect import detect
from app.understanding import issue_rewrite

# ---- H-1: naming another field never rewrites the problem ---------------------------------------------------------
OTHER_FIELD = [
    ("the location is wrong, it should say kitchen", "Kitchen"),
    ("the room is wrong. it should say the bedroom", "Bedroom"),
    ("where is wrong - should be the bathroom", "Bathroom"),
    ("the location field is incorrect, it should read living room", "Living room"),
    ("the room part is off, should say kitchen", "Kitchen"),
    ("location should say bedroom", "Bedroom"),
    ("fix the location to the kitchen", "Kitchen"),
    ("the place is wrong, it should be the bathroom", "Bathroom"),
]


@pytest.mark.parametrize("msg,room", OTHER_FIELD)
def test_named_location_changes_only_the_location(msg, room):
    assert names_other_field(msg)
    assert extract_issue_restate(msg) is None
    assert issue_rewrite(msg) is None
    got = extract_location_change(msg, "Hallway")
    assert got and got.lower().startswith(room.lower().split()[0])


ISSUE_STILL = [
    ("the problem is wrong, it should say the sink drips", "Sink drips"),
    ("it should say the kitchen sink is leaking", "Kitchen sink is leaking"),
    ("change what's wrong to: the oven won't heat", "The oven won't heat"),
    ("the issue should be: shower has no hot water", "Shower has no hot water"),
]


@pytest.mark.parametrize("msg,want", ISSUE_STILL)
def test_problem_rewrites_still_work(msg, want):
    assert not names_other_field(msg)
    assert (issue_rewrite(msg) or "").lower() == want.lower()


NOT_OTHER_FIELD = ["the fan stopped working", "my room is cold", "the time I called before nobody came",
                   "it should say the faucet drips", "where do I send this?"]


@pytest.mark.parametrize("msg", NOT_OTHER_FIELD)
def test_near_misses_do_not_count_as_another_field(msg):
    assert not names_other_field(msg)


def chat(client, msg, session, persona):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def test_api_location_correction_keeps_the_problem(client):
    r = chat(client, "the exhaust fan in the bathroom quit on me", None, "R003")
    sid = r["session_id"]
    r = chat(client, "the location is wrong, it should say kitchen", sid, "R003")
    f = fields(r)
    assert f.get("location") == "Kitchen"
    assert "fan" in f.get("issue", "").lower() and f["issue"].lower() != "kitchen"


# ---- H-2: a responder's all-clear is not a fire --------------------------------------------------------------------
ALL_CLEAR = ["the fire dept said it's fine now, it was the stove knob",
             "fire dept came, they said everything is ok",
             "the fire crew checked and said it's safe",
             "the fire truck left, they said we're fine",
             "firemen said it's all good now"]


@pytest.mark.parametrize("msg", ALL_CLEAR)
def test_responder_mention_is_not_a_fire_report(msg):
    assert detect(msg).kind != "fire_smoke"


REAL_FIRE = ["the fire truck is here but the kitchen is still on fire", "there's a fire in the hallway",
             "fire in my bedroom, smoke everywhere", "the fire dept isn't here yet and there are flames"]


@pytest.mark.parametrize("msg", REAL_FIRE)
def test_real_fire_still_detected(msg):
    assert detect(msg).kind == "fire_smoke"


def test_api_gas_all_clear_does_not_raise_a_new_fire(client):
    r = chat(client, "strong gas smell in my unit right now", None, "R003")
    sid = r["session_id"]
    chat(client, "ok we're outside", sid, "R003")
    r = chat(client, "the fire dept said it's fine now, it was a stove knob left on. can someone look at the stove?",
             sid, "R003")
    reply = r.get("reply", "")
    assert "Get out now" not in reply
    a = r.get("action") or {}
    assert "fire" not in str(fields(r).get("about", "")).lower()
    assert a.get("kind") != "staff_handoff" or "fire" not in str(a).lower()


def test_api_responder_all_clear_but_hazard_continues_still_alerts(client):
    r = chat(client, "strong gas smell in my unit right now", None, "R003")
    sid = r["session_id"]
    r = chat(client, "the fire dept said it's fine but I still smell gas really strong", sid, "R003")
    assert r.get("emergency") or "911" in r.get("reply", "")


# ---- H-5: everyday entry permission --------------------------------------------------------------------------------
from app.intake import is_entry_plain_yes  # noqa: E402
from app.understanding import entry_value  # noqa: E402

ENTRY_MAY = ["fine, enter whenever", "enter whenever", "come in while I'm at work", "go in any time",
             "they can come in whenever they need to"]
ENTRY_PLAIN_YES = ["ok yes", "yes go ahead", "yeah thats fine", "sure, that works", "yep, no problem"]
ENTRY_NOT_YES = ["ok", "whatever you think", "no", "yes but call first", "no call me first", "not sure"]


@pytest.mark.parametrize("msg", ENTRY_MAY)
def test_entry_may_phrasings(msg):
    assert (entry_value(msg) or "").startswith("Yes")


@pytest.mark.parametrize("msg", ENTRY_PLAIN_YES)
def test_entry_plain_yes(msg):
    assert is_entry_plain_yes(msg)


@pytest.mark.parametrize("msg", ENTRY_NOT_YES)
def test_entry_not_yes(msg):
    assert not is_entry_plain_yes(msg)
    assert not (entry_value(msg) or "").startswith("Yes")


@pytest.mark.parametrize("answer", ["fine, enter whenever", "ok yes"])
def test_api_entry_answer_completes_the_card_without_saving(client, answer):
    r = chat(client, "my bedroom closet door came off its track", None, "R003")
    sid = r["session_id"]
    r = chat(client, answer, sid, "R003")
    f = fields(r)
    assert f.get("entry", "").startswith("Yes")
    from app.state import get_state
    assert get_state().store.records(session_id=sid, limit=10) == []  # typed yes never saves


# ---- Verifier P0-A: "not responding to me/us" about a person is a body state ---------------------------------------
from app.emergency import scan  # noqa: E402
from app.risk.incident import Incident, classify, is_retraction  # noqa: E402

BODY_NOT_RESPONDING = ["my grandpa is slumped in his chair and not responding to us",
                       "my son won't wake up and isn't responding to me",
                       "my mom is lying on the bathroom floor, not responding to me at all",
                       "my roommate hasn't responded for hours and is on the floor"]
STAFF_NOT_RESPONDING = ["maintenance is not responding to me", "the leasing office never replies to us",
                        "nobody is responding to my emails", "I'm not answering that",
                        "he stopped replying to my texts"]


@pytest.mark.parametrize("msg", BODY_NOT_RESPONDING)
def test_person_not_responding_is_medical(msg):
    assert scan(msg)[0] == "medical"


@pytest.mark.parametrize("msg", STAFF_NOT_RESPONDING)
def test_staff_not_replying_is_not_an_emergency(msg):
    assert scan(msg)[0] is None


# ---- Verifier P0-B: "nobody is hurt" / "not an emergency" never retract a hazard ------------------------------------
WEAK = ["no one is hurt", "nobody got hurt", "this isn't an emergency", "everyone's fine", "nadie está herido",
        "not an emergency, they just have the flu"]


@pytest.mark.parametrize("msg", WEAK)
@pytest.mark.parametrize("kind", ["gas", "co", "electrical", "medical"])
def test_weak_statements_are_not_retractions(msg, kind):
    assert not is_retraction(msg, kind)


HAZARD_STILL = ["false alarm, but it still smells", "falsa alarma, pero sigue oliendo",
                "I meant the other outlet, it's sparking too", "you misunderstood, the alarm is still beeping"]


@pytest.mark.parametrize("msg", HAZARD_STILL)
def test_retraction_with_the_hazard_still_present_is_not_a_retraction(msg):
    assert not is_retraction(msg, "gas")
    assert not is_retraction(msg, "electrical")


PERSON_STILL = ["I meant my neighbour downstairs, he's on the floor", "you misunderstood, she collapsed",
                "false alarm on the first part but he's turning blue"]


@pytest.mark.parametrize("msg", PERSON_STILL)
def test_retraction_with_a_body_state_is_not_a_retraction(msg):
    assert not is_retraction(msg, "medical")


REAL_RETRACT = ["false alarm, it was the trash, sorry", "I meant my phone, not my mom", "you misunderstood me, sorry",
                "just kidding, sorry about that"]


@pytest.mark.parametrize("msg", REAL_RETRACT)
def test_explicit_retractions_still_work(msg):
    inc = Incident(kind="medical", started_at="t", opened_turn=0, last_seen_turn=0, kinds=["medical"])
    assert classify(msg, inc) == "retracted"


def _turns(client, persona, msgs):
    sid, out = None, []
    for m in msgs:
        r = chat(client, m, sid, persona)
        sid = r["session_id"]
        out.append(r)
    return out


def _guided(r):
    d = (r.get("risk") or {}).get("decision") or {}
    return d.get("response") in ("full_alert", "care_line")


@pytest.mark.parametrize("msgs", [
    ["the hallway smells strongly of gas outside my door", "nobody is hurt"],
    ["my outlet is throwing sparks", "nobody got hurt", "it is still crackling"],
    ["our CO detector is screaming and my daughter threw up", "not an emergency, she has a bug, the alarm keeps going"],
    ["huele fuerte a gas en la cocina", "falsa alarma, pero sigue oliendo"],
])
def test_api_hazard_alert_survives_weak_or_contradicted_retraction(client, msgs):
    for r in _turns(client, "R003", msgs):
        assert _guided(r)


def test_api_retracted_alert_reopens_on_a_body_state(client):
    rs = _turns(client, "R003", ["my wife has crushing chest pain", "you misunderstood, she's fine",
                                 "she's pale and sweating now"])
    assert rs[2]["risk"]["decision"]["response"] == "full_alert"


def test_api_overdose_after_self_harm_is_never_retracted(client):
    rs = _turns(client, "R003", ["I don't want to be here anymore", "I took a whole bottle of pills",
                                 "nobody is hurt, never mind"])
    d = rs[2]["risk"]["decision"]
    assert d["response"] == "full_alert" or d.get("also_988")
