"""Sprint 8 (D) fix round: findings from the independent verifier, red-team and resident simulator.

- P1-2: a failed / timed-out / rate-limited classifier (decision.degraded) means NO tips;
- unsafe tips: spreading water in any phrasing (EN + ES, typos), legacy "a few checks" behind the same safety checks
  and content gate (drafts: never shown as approved), explicit unsafe questions get a direct "no" and no tips;
- flow: the request text is never cut up ("nope" -> "pe"), a side question keeps the tips question open, a new
  problem during tips keeps the first one, a request started from tips has the same on-file fields as a direct one;
- tips the first version missed ("sink drains super slow", "half the lights stopped working").
Dev-A cases written from the findings' descriptions (the red-team / simulator cases themselves were not read).
"""

import uuid

import pytest

from app import quickfix as qf
from app.risk.models import RiskDecision, SemanticResult
from app.state import get_state
from app.workflows import legacy_draft_steps
from tests.test_sprint6_conversation import chat, fields


def none_risk(**kw):
    return RiskDecision(response="none", rule="R8", **kw)


def check(msg, **kw):
    return qf.check_eligibility(msg, none_risk(), mode="demo_drafts", **kw)


def sid():
    return f"qff-{uuid.uuid4().hex[:10]}"


# ---- spreading water: never tips ---------------------------------------------------------------------------------

WATER = [
    "the washer is flooding the laundry room and the drain is slow", "sink is clogged and water is spreading",
    "tub won't drain, water everywhere", "shower is clogged and water is pouring onto the floor",
    "the sink is clogged and it's gushing", "floding bathroom, the tub is clogged", "overfloing sink, its clogged",
    "standing water in the tub and it won't drain", "the clogged sink splashed all over the floor",
    "water heater leaking and the floor drain is slow", "the disposal hums and water is on the kitchen floor",
    "el lavabo está tapado y se inunda el baño", "la regadera tapada, agua por todo el piso",
    "el fregadero está tapado y está inundando la cocina", "la tina no drena y sale mucha agua",
]
DRY = ["kitchen sink drains super slow", "my bathtub is clogged", "la tina no drena", "the shower won't drain",
       "el lavabo drena muy lento", "the bathroom sink takes forever to drain"]


@pytest.mark.parametrize("msg", WATER)
def test_spreading_water_never_gets_tips(msg):
    r = check(msg)
    assert not r.eligible and r.reason.startswith(("excluded:", "safety_")), (msg, r)


@pytest.mark.parametrize("msg", DRY)
def test_a_dry_slow_drain_still_gets_tips(msg):
    r = check(msg, lang="es" if " la " in f" {msg} " or " el " in f" {msg} " else "en")
    assert r.eligible and r.entry_id == "qf-slow-drain", (msg, r)


# ---- tips the first version missed ---------------------------------------------------------------------------------

@pytest.mark.parametrize("msg,eid", [
    ("sink drains super slow", "qf-slow-drain"), ("the tub drains kind of slowly", "qf-slow-drain"),
    ("half the lights stopped working", "qf-breaker-reset"),
    ("half the lights in my bedroom stopped working", "qf-breaker-reset"),
    ("some of the lights in the living room went out", "qf-breaker-reset"),
    ("la mitad de las luces de la cocina no funcionan", "qf-breaker-reset"),
])
def test_missed_phrasings_now_get_tips(msg, eid):
    r = check(msg, lang="es" if "luces" in msg else "en")
    assert r.eligible and r.entry_id == eid, (msg, r)


@pytest.mark.parametrize("msg", ["all the lights in the building are out", "half the lights are flickering",
                                 "the lights went out in the whole apartment", "se fue la luz en todo el edificio",
                                 "the hallway lights outside my door are out"])
def test_light_near_misses_get_no_tips(msg):
    assert not check(msg).eligible, msg


# ---- explicit unsafe questions: a direct "no", never tips ---------------------------------------------------------

UNSAFE = [
    ("disposal jammed, can I reach in and grab it?", "disposal_hand"),
    ("can I stick my hand in the garbage disposal to unjam it?", "disposal_hand"),
    ("the disposal is stuck, should I pull the spoon out?", "disposal_hand"),
    ("i'm going to reach into the disposal and get it", "disposal_hand"),
    ("¿puedo meter la mano en el triturador?", "disposal_hand"),
    ("el triturador está trabado, ¿lo saco con la mano?", "disposal_hand"),
    ("breaker tripped, should I take the panel cover off?", "panel_cover"),
    ("can I remove the front cover of the breaker panel to look?", "panel_cover"),
    ("¿puedo quitar la tapa del panel de breakers?", "panel_cover"),
    ("sink is clogged, can I use drano?", "chemical_drain"),
    ("should I pour boiling water down the slow tub drain?", "chemical_drain"),
    ("¿puedo echarle cloro al lavabo tapado?", "chemical_drain"),
    ("the gfci outlet is dead, can I replace the outlet myself?", "wires"),
    ("can I touch the wires behind the bathroom outlet?", "wires"),
]
SAFE_QUESTIONS = ["my garbage disposal won't turn on", "where is the reset button on the disposal?",
                  "my breaker tripped, where is the panel?", "the sink is clogged, what should I do?",
                  "can you send someone for the disposal?", "el triturador no prende, ¿qué hago?",
                  "is it ok to use the shower while the sink is clogged?"]


@pytest.mark.parametrize("msg,kind", UNSAFE)
def test_unsafe_question_is_recognised_and_gets_no_tips(msg, kind):
    assert qf.unsafe_question(msg) == kind, msg
    r = check(msg)
    assert not r.eligible, (msg, r)


@pytest.mark.parametrize("msg", SAFE_QUESTIONS)
def test_safe_questions_are_not_called_unsafe(msg):
    assert qf.unsafe_question(msg) is None, msg


def test_every_unsafe_kind_has_a_direct_no_template():
    from app.safety import output_checks
    from app.templates import T

    for kind in qf.UNSAFE_QUESTIONS:
        for lang in ("en", "es"):
            text = T[f"quickfix_unsafe_{kind}"][lang]
            assert text.startswith("No."), text
            assert [c.code for c in output_checks(text) if not c.passed] == [], text


# ---- P1-2: a degraded classifier means no tips ----------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["my breaker tripped", "my bathtub is clogged", "garbage disposal won't turn on",
                                 "el enchufe del baño no funciona"])
def test_degraded_decision_gives_no_tips(msg):
    r = qf.check_eligibility(msg, none_risk(degraded=True), mode="demo_drafts")
    assert r.reason == "classifier_degraded"


class _FailingClassifier:
    def __init__(self, status):
        self.status = status

    def classify(self, message, recent=None):
        return SemanticResult(status=self.status, detail="FAKE")


@pytest.mark.parametrize("status", ["error", "timeout", "rate_limited", "bad_output", "unavailable"])
def test_failing_classifier_gives_no_tips_end_to_end(client, monkeypatch, status):
    monkeypatch.setattr(get_state().deps.settings, "quickfix_content_mode", "demo_drafts")
    monkeypatch.setattr(get_state().deps, "risk", _FailingClassifier(status))
    r = chat(client, "my bathtub is clogged", sid())
    assert "Did that fix it?" not in r["reply"] and "draft" not in r["reply"].lower()
    assert (r.get("action") or {}).get("kind") == "maintenance_request"  # the normal repair request instead


# ---- legacy "a few checks": same safety checks, same gate --------------------------------------------------------

def legacy(msg, mode="demo_drafts", category="plumbing_drip", approved=False):
    return qf.legacy_checks(msg, none_risk(), mode=mode, category=category, steps=legacy_draft_steps(category),
                            approved=approved)


def test_legacy_checks_are_drafts_and_hidden_by_default():
    assert legacy("my kitchen faucet has a little drip", mode="approved_only").reason == "no_approved_content"
    r = legacy("my kitchen faucet has a little drip")
    assert r.eligible and r.draft and r.label
    assert legacy("my kitchen faucet has a little drip", mode="approved_only", approved=True).eligible


@pytest.mark.parametrize("msg,category", [
    ("my faucet drips and I cut my hand on the handle", "plumbing_drip"),
    ("the water heater is leaking and it's spreading across the floor", "plumbing_drip"),
    ("the faucet is dripping and there's water on the floor", "plumbing_drip"),
    ("the tap leaks and water is coming through the ceiling below", "plumbing_drip"),
    ("la llave gotea y hay agua por todo el piso", "plumbing_drip"),
    ("the dishwasher won't start and I smell burning", "appliance"),
    ("the fridge stopped and the outlet sparked", "appliance"),
    ("the heat is out and I feel dizzy", "hvac"),
    ("roaches everywhere, can I set off a bug fogger?", "pest"),
])
def test_legacy_checks_never_shown_with_a_hazard(msg, category):
    assert not legacy(msg, category=category).eligible, msg


def test_legacy_checks_need_a_safety_decision():
    r = qf.legacy_checks("my kitchen faucet has a little drip", None, mode="demo_drafts", category="plumbing_drip",
                         steps=legacy_draft_steps("plumbing_drip"), approved=False)
    assert r.reason == "no_safety_decision"


def test_default_mode_shows_no_legacy_checks_end_to_end(client):
    for msg in ["my kitchen faucet has a little drip", "the dishwasher won't start", "the AC isn't cooling"]:
        r = chat(client, msg, sid())
        assert "a few checks" not in r["reply"] and "safe checks" not in r["reply"], (msg, r["reply"])


# ---- the follow-up answer and the request text --------------------------------------------------------------------

ISSUE = "the bathroom outlet stopped working"


@pytest.mark.parametrize("answer", ["I'd rather not touch the panel, can you just send someone", "nope, still dead",
                                    "nope, still not working", "no", "nah it didn't work", "still nothing",
                                    "no funcionó", "no, sigue igual", "mejor manden a alguien",
                                    "I didn't want to try it, just put in a request"])
def test_the_request_text_is_the_original_issue_word_for_word(answer):
    step, _ = qf.follow_up({"state": "offered", "entry": "qf-gfci-reset", "asked": 0}, answer, none_risk())
    assert step.action == "intake", answer
    assert qf.intake_message(ISSUE, answer) == ISSUE


@pytest.mark.parametrize("answer,clauses", [
    ("no, it's the hall bathroom, come in any time", ["it's the hall bathroom", "come in any time"]),
    ("still dead. it's in the master bath", ["it's in the master bath"]),
    ("no funcionó, es el baño de arriba, pueden entrar cuando quieran", ["es el baño de arriba",
                                                                          "pueden entrar cuando quieran"]),
])
def test_extra_details_are_appended_as_whole_clauses(answer, clauses):
    out = qf.intake_message(ISSUE, answer)
    assert out.startswith(ISSUE + ". ")
    for c in clauses:
        assert c in out and c in answer


def test_side_question_and_new_problem_are_not_answers():
    pending = {"state": "offered", "entry": "qf-slow-drain", "asked": 0, "side": 0}
    for msg in ["also when is my rent due?", "also my closet door is off the track", "¿a qué hora abre la oficina?"]:
        assert qf.follow_up(pending, msg, none_risk())[0].action == "other", msg
    assert qf.follow_up(pending, "ok it's still not working though", none_risk())[0].action == "intake"


# ---- API replays of the flow bugs ---------------------------------------------------------------------------------

@pytest.fixture
def demo(client, monkeypatch):
    monkeypatch.setattr(get_state().deps.settings, "quickfix_content_mode", "demo_drafts")
    monkeypatch.setattr(get_state().deps.settings, "safety_classifier", "off")  # rules only: not degraded
    return client


def _values(r):
    return " | ".join(fields(r).values()).lower()


@pytest.mark.parametrize("answer", ["I'd rather not touch the panel, can you just send someone", "nope, still dead",
                                    "nope, still not working"])
def test_api_request_text_not_corrupted(demo, answer):
    s = sid()
    assert "Did that fix it?" in chat(demo, "my breaker tripped", s)["reply"]
    r = chat(demo, answer, s)
    assert (r.get("action") or {}).get("kind") == "maintenance_request", r["reply"]
    vals = _values(r)
    assert "breaker tripped" in fields(r).get("issue", "").lower()
    for junk in ("pe,", "nope", "i'd   touch", "can you", "someone", "still"):
        assert junk not in fields(r).get("issue", "").lower(), (junk, vals)
    assert "2 problems" not in r["reply"] and "dos problemas" not in r["reply"]


def test_api_side_question_keeps_the_tips_question(demo):
    s = sid()
    chat(demo, "my bathtub is clogged", s)
    r = chat(demo, "also when is my rent due?", s)
    assert r["reply"].strip() != "Did those steps fix it? Reply yes, or no and I'll start a repair request."
    assert "did the tips fix it?" in r["reply"]
    r2 = chat(demo, "ok it's still not working though", s)
    assert (r2.get("action") or {}).get("kind") == "maintenance_request"
    assert "clogged" in fields(r2).get("issue", "").lower()
    assert "still not working" not in fields(r2).get("issue", "").lower()


def test_api_new_problem_during_tips_keeps_the_first(demo):
    s = sid()
    chat(demo, "my bathtub is clogged", s)
    r = chat(demo, "also my closet door is off the track", s)
    assert (r.get("action") or {}).get("kind") == "maintenance_request"
    assert "closet" in fields(r).get("issue", "").lower()
    assert "bathtub is clogged" in r["reply"].lower()  # named, kept as the next request


def test_api_request_from_tips_has_the_same_on_file_fields(demo):
    direct = chat(demo, "my bathtub is clogged, just send maintenance", sid(), persona="R001")
    s = sid()
    chat(demo, "my bathtub is clogged", s, persona="R001")
    via = chat(demo, "no, still slow", s, persona="R001")
    assert (via.get("action") or {}).get("kind") == "maintenance_request"
    for key in ("entry_window", "contact"):
        assert fields(via).get(key) == fields(direct).get(key), (key, fields(via), fields(direct))
    assert fields(via).get("entry_window")  # the fixture's "mornings (8-11 AM)"


def test_api_unsafe_question_gets_a_direct_no(demo):
    for msg, lead in [("disposal jammed, can I reach in and grab it?", "No. Please never put your hand"),
                      ("my sink is clogged, can I use drano?", "No. Please don't use chemical drain cleaners")]:
        r = chat(demo, msg, sid())
        assert r["reply"].startswith(lead), r["reply"]
        assert "Did that fix it?" not in r["reply"]


def test_api_legacy_checks_in_demo_mode_are_labelled_draft(demo):
    r = chat(demo, "my kitchen faucet has a little drip", sid())
    assert "draft checks for this demo (not yet approved by McKinley)" in r["reply"], r["reply"]
    assert "safe checks" not in r["reply"]


@pytest.mark.parametrize("msg", ["my kitchen faucet drips and I cut my hand on it",
                                 "the water heater is leaking and the water is spreading into the hallway",
                                 "the faucet is dripping and there's water all over the bathroom floor"])
def test_api_legacy_checks_never_with_a_hazard(demo, msg):
    r = chat(demo, msg, sid())
    assert "checks" not in r["reply"].lower(), r["reply"]
