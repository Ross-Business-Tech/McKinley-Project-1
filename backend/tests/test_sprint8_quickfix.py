"""Sprint 8 (workstream D): quick-fix tips before a repair request (app/quickfix.py, app/content/quickfix_drafts.py).

Module-level tests: the planner hook in app/actions.py is not wired yet, so the API-level replays live in the Agent D
report for the lead to add after wiring. Mechanisms under test:
- trigger families (object + symptom, EN + ES), >= 8 phrasings and >= 4 near misses per entry;
- a negative safety finding is required (RiskDecision "none", plus the deterministic detector), every exclusion class;
- the content-approval gate (off / approved_only / demo_drafts; hosted fails closed);
- the follow-up flow (resolved -> no record; not resolved / skip -> intake with the issue kept; no repeat offer).
These are dev-A cases written from the behaviour description.
"""

import re

import pytest

from app import quickfix as qf
from app.config import Settings
from app.content import quickfix_drafts as content
from app.risk.models import RiskDecision
from app.risk.pipeline import assess

GOOD_HOSTED = dict(_env_file=None, app_env="hosted", cors_origins="https://mckinley-demo.vercel.app",
                   staff_api_token="k7Qp2vX9mR4tL8wZ3nB6yC1dF5hJ0sGa", gate_override_enabled=False,
                   database_url="postgresql://user:secret-password@db.example.com:5432/postgres")


def none_risk(**kw):
    return RiskDecision(response="none", rule="R8", **kw)


def check(msg, mode="demo_drafts", lang="en", **kw):
    return qf.check_eligibility(msg, none_risk(), mode=mode, lang=lang, **kw)


def real(msg, mode="demo_drafts", lang="en"):
    """Through the real safety pipeline (rules only, no classifier): what the planner would pass."""
    return qf.check_eligibility(msg, assess(msg, None, None).decision, mode=mode, lang=lang)


# ---- trigger families --------------------------------------------------------------------------------------------

FAMILIES = {
    "qf-breaker-reset": [
        ("my breaker tripped", "en"), ("I think a circuit breaker tripped", "en"),
        ("the breaker for the kitchen flipped off", "en"), ("half my outlets stopped working in the bedroom", "en"),
        ("lost power in the living room but the rest of the apartment is fine", "en"),
        ("the lights and outlets in my office don't work", "en"), ("tripped a breaker using the hair dryer", "en"),
        ("se botó la pastilla", "es"), ("se fue la luz en la recámara", "es"),
        ("se bajó el breaker de la cocina", "es"),
        ("no hay luz en el cuarto, lo demás sí", "es"),
    ],
    "qf-gfci-reset": [
        ("the bathroom outlet stopped working", "en"), ("gfci outlet won't work", "en"),
        ("my GFI by the kitchen sink is dead", "en"), ("kitchen counter plugs aren't working", "en"),
        ("the outlet with the test and reset buttons doesn't work", "en"), ("patio outlet has no power", "en"),
        ("el enchufe del baño no funciona", "es"), ("el tomacorriente de la cocina dejó de funcionar", "es"),
        ("el contacto de la lavandería no sirve", "es"),
    ],
    "qf-disposal-reset": [
        ("garbage disposal won't turn on", "en"), ("the disposal just hums", "en"),
        ("my garbage disposal stopped working", "en"), ("disposal is dead, nothing happens", "en"),
        ("the food disposal is jammed", "en"), ("garbage disposal isn't working", "en"),
        ("el triturador de basura no prende", "es"), ("la trituradora no funciona", "es"),
        ("el triturador solo zumba", "es"),
    ],
    "qf-slow-drain": [
        ("kitchen sink drains really slowly", "en"), ("my bathtub is clogged", "en"),
        ("the shower won't drain", "en"), ("bathroom sink is clogged", "en"), ("slow drain in the tub", "en"),
        ("water just sits in the sink", "en"), ("la regadera está tapada", "es"), ("el lavabo drena muy lento", "es"),
        ("el fregadero se tapó", "es"), ("la tina no drena", "es"),
    ],
}


@pytest.mark.parametrize("eid,msg,lang", [(e, m, lang) for e, ms in FAMILIES.items() for m, lang in ms])
def test_family_member_is_eligible_with_its_entry(eid, msg, lang):
    r = check(msg, lang=lang)
    assert r.eligible and r.entry_id == eid, (msg, r)
    assert 1 <= len(r.tips) <= 3
    assert r.tips == content.ENTRIES[[e["id"] for e in content.ENTRIES].index(eid)]["steps"][lang][:3]
    rr = real(msg, lang=lang)  # the real rules pipeline agrees there is no safety signal
    assert rr.eligible and rr.entry_id == eid, (msg, rr)


NEAR_MISSES = [
    # breaker
    "I had breakfast already", "I tripped on the stairs yesterday, is the gym open?", "my power bill is too high",
    "the power went out", "se fue la luz",  # whole home: may be an outage or the main breaker -> repair request
    # gfci / outlet
    "I need an outlet installed in the bathroom", "where is the outlet for the TV in the kitchen?",
    "how many outlets does the 2-bed have?", "¿cuántos enchufes tiene la cocina?",
    # disposal
    "where do I dispose of garbage?", "when is waste disposal pickup?", "can I put rice in the garbage disposal?",
    "¿dónde tiro la basura?",
    # drain
    "I feel so drained", "how do I drain the water heater?", "the parking lot drain is clogged with leaves maybe",
    "my toilet is clogged", "el inodoro está tapado", "estoy agotada", "is there a sink in the laundry room?",
]


@pytest.mark.parametrize("msg", NEAR_MISSES)
def test_near_miss_gets_no_tips(msg):
    assert not check(msg).eligible, msg


# ---- safety: a negative finding is required ----------------------------------------------------------------------

EXCLUSION_CASES = [
    ("my breaker keeps tripping and I smell burning", None),
    ("disposal hums and there's water under the sink", None),
    ("drain is clogged and overflowing", None),
    ("the breaker tripped and I smell gas", None), ("breaker tripped and there was smoke", None),
    ("the bathroom outlet stopped working, it sparked first", None), ("breaker tripped, there are bare wires", None),
    ("the gfci outlet is dead and I got a shock", None), ("gfci outlet is wet and not working", None),
    ("the kitchen sink is clogged and leaking", None), ("tub is clogged and water is on the floor", None),
    ("breaker tripped and the co alarm is beeping", None), ("disposal won't turn on, I cut my hand", None),
    ("sink is clogged and smells like sewage", None), ("breaker tripped, it's an emergency", None),
    ("la pastilla se botó y huele a quemado", None), ("el triturador zumba y hay agua debajo del fregadero", None),
    ("el lavabo está tapado y se desborda", None), ("el enchufe del baño echa chispas", None),
    ("el fregadero está tapado y hay una fuga", None), ("se fue la luz en la cocina y huele a gas", None),
]


@pytest.mark.parametrize("msg,_", EXCLUSION_CASES)
def test_exclusion_blocks_tips_even_if_the_risk_decision_says_none(msg, _):
    r = check(msg)  # the planner's decision says "none": the module's own exclusions still refuse
    assert not r.eligible and r.reason.startswith(("excluded:", "safety_detector")), (msg, r)
    assert not real(msg).eligible


@pytest.mark.parametrize("msg,reason", [
    ("my breaker keeps tripping", "excluded:repeat_trip"), ("the breaker trips every time I use the microwave",
                                                            "excluded:repeat_trip"),
    ("the main breaker tripped", "excluded:panel_not_accessible"),
    ("breaker tripped, the panel is in the locked utility room", "excluded:panel_not_accessible"),
    ("the whole building lost power, is it a breaker?", "excluded:outage"),
    ("breaker tripped and the neighbors have no power either", "excluded:outage"),
    ("breaker panel is buzzing", "safety_detector"),
    ("the gfci won't stay reset", "excluded:wont_stay"), ("the bathroom outlet is warm and not working", None),
    ("a spoon fell into the garbage disposal and it won't turn on", "excluded:object_inside"),
    ("I poured drano in the bathroom sink, it drains slowly", "excluded:chemical"),
    ("both sinks are clogged", "excluded:several_drains"), ("the tub keeps clogging", "excluded:repeat_clog"),
    ("se sigue botando la pastilla", "excluded:repeat_trip"), ("se fue la luz en todo el edificio", None),
    ("se me cayó una cuchara en el triturador y no prende", "excluded:object_inside"),
    ("le eché destapacaños químico al lavabo tapado", "excluded:chemical"),
    ("the parking garage floor drain is clogged", "excluded:outside_home"),
])
def test_entry_specific_exclusions(msg, reason):
    r = check(msg)
    assert not r.eligible, (msg, r)
    if reason:
        assert r.reason == reason or r.reason.startswith(("excluded:", "safety_detector")), (msg, r)


@pytest.mark.parametrize("decision", [
    RiskDecision(response="full_alert", kind="electrical", rule="R1", person_danger=True),
    RiskDecision(response="care_line", care="danger", rule="R7"),
    RiskDecision(response="care_line", care="danger", rule="R9"),  # remembered line from an earlier incident
    RiskDecision(response="safety_info", kind="electrical", care="info", rule="R5"),
    RiskDecision(response="none", rule="R8", incident="electrical"),
    RiskDecision(response="none", rule="R8", needs_human=True),
    RiskDecision(response="none", rule="R8", person_danger=True),
])
def test_any_safety_signal_blocks_tips(decision):
    r = qf.check_eligibility("my breaker tripped", decision, mode="demo_drafts")
    assert not r.eligible and r.reason == "safety_decision"


def test_no_safety_decision_fails_closed():
    assert qf.check_eligibility("my breaker tripped", None, mode="demo_drafts").reason == "no_safety_decision"


def test_gate_emergency_blocks_tips():
    assert check("my breaker tripped", urgency="emergency").reason == "safety_decision"


@pytest.mark.parametrize("msg", ["the bathroom outlet stopped working and it feels hot",
                                 "breaker tripped and there was a weird noise", "the disposal hums and smells odd",
                                 "el triturador hace un ruido raro y no prende"])
def test_degraded_or_uncertain_classifier_with_possible_risk_gives_no_tips(msg):
    degraded = RiskDecision(response="none", rule="R8", degraded=True)
    assert not qf.check_eligibility(msg, degraded, mode="demo_drafts").eligible
    assert not qf.check_eligibility(msg, none_risk(), mode="demo_drafts", semantic_level="uncertain").eligible


def test_degraded_classifier_without_any_risk_word_still_allows_tips():
    degraded = RiskDecision(response="none", rule="R8", degraded=True)
    assert qf.check_eligibility("my breaker tripped", degraded, mode="demo_drafts").eligible


@pytest.mark.parametrize("msg", ["my breaker tripped, just send maintenance", "the disposal won't turn on. please "
                                 "send someone", "kitchen sink is clogged, I'd like to submit a work order",
                                 "bathroom outlet stopped working, no tips please", "el lavabo está tapado, manden a "
                                 "alguien", "el triturador no prende, solo quiero la solicitud"])
def test_asking_for_the_request_skips_tips(msg):
    assert check(msg).reason == "resident_wants_intake"


@pytest.mark.parametrize("msg", ["I already reset the breaker and the kitchen is still dead",
                                 "tried resetting the gfci outlet in the bathroom, still dead",
                                 "ya reinicié la pastilla y la recámara sigue sin luz"])
def test_already_tried_skips_tips(msg):
    assert not check(msg).eligible


def test_repeat_issue_gets_no_tips():
    assert check("my bathtub is clogged", repeat=True).reason == "repeat_issue"


# ---- content-approval gate --------------------------------------------------------------------------------------

def test_default_mode_is_approved_only_and_serves_nothing_today():
    s = Settings(_env_file=None)
    assert s.quickfix_content_mode == "approved_only" and qf.effective_mode(s) == "approved_only"
    r = check("my breaker tripped", mode="approved_only")
    assert not r.eligible and r.reason == "no_approved_content"


def test_off_mode_serves_nothing():
    assert check("my breaker tripped", mode="off").reason == "mode_off"
    assert qf.effective_mode(Settings(_env_file=None, quickfix_content_mode="off")) == "off"


def test_approved_entry_is_served_without_draft_label(monkeypatch):
    approved = [{**e, "status": "approved", "approved_by": "Maintenance director (role)", "approved_on": "2026-12-01"}
                if e["id"] == "qf-slow-drain" else e for e in content.ENTRIES]
    monkeypatch.setattr(qf, "_BY_ID", {e["id"]: e for e in approved})
    r = check("my bathtub is clogged", mode="approved_only")
    assert r.eligible and not r.draft and r.label is None
    assert not check("my breaker tripped", mode="approved_only").eligible  # still a draft


def test_status_approved_without_approver_is_not_approved(monkeypatch):
    half = [{**e, "status": "approved"} for e in content.ENTRIES]
    monkeypatch.setattr(qf, "_BY_ID", {e["id"]: e for e in half})
    assert check("my bathtub is clogged", mode="approved_only").reason == "no_approved_content"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_demo_drafts_are_labelled_as_drafts(lang):
    r = check("my bathtub is clogged", lang=lang)
    assert r.eligible and r.draft and r.label == qf.DRAFT_LABEL[lang]
    assert ("not yet approved by McKinley" if lang == "en" else "aún no aprobados por McKinley") in r.label


def test_demo_drafts_only_local():
    local = Settings(_env_file=None, quickfix_content_mode="demo_drafts")
    assert qf.effective_mode(local) == "demo_drafts"
    assert qf.effective_mode(local, local_request=False) == "approved_only"  # reached through a proxy: fail closed
    hosted = Settings(**GOOD_HOSTED, quickfix_content_mode="demo_drafts")
    assert qf.effective_mode(hosted) == "approved_only"
    assert any("QUICKFIX_CONTENT_MODE" in p for p in hosted.hosted_problems())  # startup refuses it
    assert Settings(**GOOD_HOSTED).hosted_problems() == []  # the default is fine on a hosted backend


def test_unknown_mode_fails_closed():
    class Odd:
        quickfix_content_mode = "everything"
        app_env = "local"
    assert qf.effective_mode(Odd()) == "off"
    assert qf.effective_mode(object()) == "off"


# ---- content audit ----------------------------------------------------------------------------------------------

_FORBIDDEN = re.compile(r"screwdriver|wrench|allen|hex key|pliers|unscrew|plunger|drano|vinegar|baking soda|"
                        r"destornillador|llave (allen|inglesa)|pinzas|desatornill|vinagre|bicarbonato", re.I)


@pytest.mark.parametrize("entry", content.ENTRIES, ids=lambda e: e["id"])
def test_every_entry_is_a_safe_pending_draft(entry):
    assert entry["status"] == "DRAFT — Pending McKinley Approval" and not entry["approved_by"]
    for k in ("id", "category", "triggers", "exclusions", "author", "date"):
        assert entry[k]
    for lang in ("en", "es"):
        steps = entry["steps"][lang]
        assert 1 <= len(steps) <= 3
        for s in steps:
            assert not _FORBIDDEN.search(s), s
            if re.search(r"cover|tapa\b", s, re.I):
                assert re.search(r"cover on|never remove|nunca quite", s, re.I), s
            if re.search(r"chemical|qu[ií]mic|boiling|hirviendo", s, re.I):
                assert re.search(r"don'?t use|no use", s, re.I), s
            if re.search(r"hand inside|meta la mano", s, re.I):
                assert re.search(r"never|nunca", s, re.I), s
        assert re.search(r"repair request|solicitud de reparaci", steps[-1], re.I)  # always an exit to intake


def test_entries_cover_the_four_issues():
    assert {e["id"] for e in content.ENTRIES} == {"qf-breaker-reset", "qf-gfci-reset", "qf-disposal-reset",
                                                  "qf-slow-drain"}


# ---- the follow-up flow -----------------------------------------------------------------------------------------

def offered(eid="qf-slow-drain"):
    mem: dict = {}
    r = check({"qf-slow-drain": "my bathtub is clogged", "qf-breaker-reset": "my breaker tripped"}[eid])
    qf.offered_memory(mem, r)
    return mem


@pytest.mark.parametrize("msg", ["yes", "yes that worked, thanks", "it works now", "that fixed it!", "all good now",
                                 "yep, back on", "sí, ya funciona", "sí funcionó, gracias", "ya quedó", "listo"])
def test_resolved_closes_the_flow_without_intake(msg):
    mem = offered()
    step, keep = qf.follow_up(mem.pop(qf.MEM_KEY), msg, none_risk())
    assert step.action == "close_resolved" and keep is None


@pytest.mark.parametrize("msg", ["no", "nope, still slow", "it didn't work", "still clogged", "no luck",
                                 "yes I tried but it's still slow", "not sure", "I can't find the stopper",
                                 "no, sigue igual", "no funcionó", "todavía no baja el agua",
                                 "yes but now it's leaking"])
def test_not_resolved_goes_to_intake(msg):
    step, keep = qf.follow_up(offered()[qf.MEM_KEY], msg, none_risk())
    assert step.action == "intake" and step.reply == "not_resolved" and keep is None, msg


@pytest.mark.parametrize("msg", ["just send maintenance", "skip, send someone", "please submit a work order",
                                 "no tips, send a request", "manden a alguien", "mejor envíen a mantenimiento"])
def test_skip_goes_to_intake(msg):
    step, _ = qf.follow_up(offered()[qf.MEM_KEY], msg, none_risk())
    assert step.action == "intake" and step.reply == "skip"


def test_unclear_answer_is_asked_once_then_intake():
    pending = offered()[qf.MEM_KEY]
    step, keep = qf.follow_up(pending, "hmm ok", none_risk())
    assert step.action == "ask_again" and keep and keep["asked"] == 1
    step2, keep2 = qf.follow_up(keep, "thanks", none_risk())
    assert step2.action == "intake" and keep2 is None


def test_a_safety_signal_on_the_follow_up_ends_the_flow():
    alert = RiskDecision(response="full_alert", kind="fire_smoke", rule="R1", person_danger=True)
    step, keep = qf.follow_up(offered()[qf.MEM_KEY], "no and now there's smoke", alert)
    assert step.action == "none" and keep is None


def test_a_different_topic_is_not_trapped_in_the_flow():
    step, keep = qf.follow_up(offered()[qf.MEM_KEY], "what are the office hours for the leasing office today",
                              none_risk())
    assert step.action == "none" and keep is None


def test_no_repeat_offer_for_the_same_issue():
    mem = offered("qf-breaker-reset")
    assert check("my breaker tripped", used=mem[qf.USED_KEY]).reason == "already_offered"
    assert check("my bathtub is clogged", used=mem[qf.USED_KEY]).eligible  # a different issue may still get tips


def test_memory_holds_ids_only():
    mem = offered()
    assert mem == {qf.MEM_KEY: {"state": "offered", "entry": "qf-slow-drain", "asked": 0},
                   qf.USED_KEY: ["qf-slow-drain"]}


def test_no_pending_offer_does_nothing():
    assert qf.follow_up(None, "no", none_risk())[0].action == "none"


def test_issue_is_kept_for_intake():
    recent = ["hi", "my bathtub is clogged", "no it's still slow, it's the hall bathroom"]
    issue = qf.issue_from_recent(recent, "qf-slow-drain")
    assert issue == "my bathtub is clogged"
    assert qf.intake_message(issue, "no") == "my bathtub is clogged"
    assert qf.intake_message(issue, "just send maintenance") == "my bathtub is clogged"
    assert qf.intake_message(issue, recent[-1]).startswith("my bathtub is clogged. ")
    assert "hall bathroom" in qf.intake_message(issue, recent[-1])
    assert qf.issue_from_recent(["what's up", "no"], "qf-slow-drain") is None
    assert qf.intake_message(None, "no") == "no"


@pytest.mark.parametrize("entry", content.ENTRIES, ids=lambda e: e["id"])
def test_tip_text_passes_the_reply_output_checks(entry):
    from app.safety import output_checks

    for lang in ("en", "es"):
        text = qf.DRAFT_LABEL[lang] + "\n" + "\n".join(entry["steps"][lang])
        assert [c.code for c in output_checks(text) if not c.passed] == [], (entry["id"], lang)
