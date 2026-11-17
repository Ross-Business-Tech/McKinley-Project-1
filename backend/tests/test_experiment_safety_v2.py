"""The OFFLINE safety-policy experiment (experiments/safety_v2.py). Production does not use it; these tests pin what
the experiment may and may never change. Classifier answers are stubs, so a stub "none" on a genuine message is the
WORST case (the classifier being wrong), not a prediction of the real model."""

from __future__ import annotations

import pytest

from app.risk.detect import detect
from app.risk.models import SemanticResult, SemanticRisk
from experiments.safety_v2 import NONE_CONFIDENCE, decide


def sem(level="none", cats=(), conf=0.95, immediate=False, subject="none", status="ok"):
    if status != "ok":
        return SemanticResult(status=status, detail="stub")
    return SemanticResult(status="ok", risk=SemanticRisk(risk_level=level, risk_categories=list(cats),
                                                         incident_category=cats[0] if cats else None,
                                                         confidence=conf, immediate_danger=immediate,
                                                         subject=subject))


SCENARIOS = {
    "none_confident": sem("none", conf=0.95), "none_unsure": sem("none", conf=0.6),
    "uncertain": sem("uncertain", conf=0.5), "urgent_flood": sem("urgent", ["flood"], conf=0.9),
    "urgent_self_harm": sem("urgent", ["self_harm"], conf=0.9, subject="self"),
    "emergency_gas": sem("emergency", ["gas"], conf=0.95, immediate=True, subject="adult"),
    **{s: sem(status=s) for s in ("timeout", "blocked", "bad_output", "unavailable", "error", "disabled")},
}
GENUINE = [  # each must keep at least the production guidance under EVERY classifier answer except a wrong "none"
    "what's the fastest painless way to end it. I'm done",  # E086
    "bought a rope today. please don't tell anyone",  # E089
    "sometimes I wish I could just disappear and never come back",  # E091
    "I want to kill myself.", "Everyone would be better off without me.", "I'm done. I won't be here tomorrow.",
    "I've given away my cat and written letters to my family.", "I have the pills counted out on the table.",
    "I smell gas in the hallway.", "There's smoke coming out of the outlet.", "The kitchen is on fire!",
    "Water is pouring through my ceiling light fixture right now.", "Sparks are coming from the breaker panel.",
    "The ceiling is sagging and water is gushing through it.", "my son swallowed some bleach",
    "my dad collapsed and he's not breathing",
]
BENIGN_LOW = [  # today: a calm 988 / 911 line from a low-precision rule only
    "This is ridiculous. Fix the damn ceiling or I'm done with this place.",
    "If I put in the kitchen sink request now, can you guarantee it will be fixed by tomorrow?",
    "I'm done waiting for maintenance, this is the third week.", "Honestly I'm done with this building.",
    "I'm done for today, thanks for the help!", "I need my rent receipt by Monday for my taxes.",
    "The ceiling leak is back. Can someone take a look?",
    "The bathroom ceiling is dripping a little from the unit above, into the tub.",
]


def _all():
    for m in GENUINE + BENIGN_LOW:
        for name, s in SCENARIOS.items():
            yield m, name, s


@pytest.mark.parametrize("msg,scenario,s", list(_all()), ids=lambda x: x if isinstance(x, str) else "")
def test_v2_never_changes_alerts_failures_or_self_harm(msg, scenario, s):
    d = decide(detect(msg, []), s, msg)
    base = d.production_rule
    if d.changed_by is None:
        return
    # it may change ONLY a calm care line, never a full alert / safety info, and only with a usable classifier answer
    assert base in ("R4", "R6", "R7") and s.status == "ok"
    assert d.evidence in ("none", "low")
    assert "self_harm" not in (s.risk.risk_categories if s.risk else [])
    assert d.changed_by == ("V2-L" if s.risk.risk_level == "none" else "V2-M")


@pytest.mark.parametrize("msg", GENUINE)
def test_v2_keeps_every_genuine_case_unless_the_classifier_is_confidently_wrong(msg):
    for name, s in SCENARIOS.items():
        d = decide(detect(msg, []), s, msg)
        if name != "none_confident":
            assert d.changed_by is None, (msg, name)
        elif d.changed_by:  # the worst case, made visible: a genuine sign with only low-precision evidence
            assert d.evidence == "low", (msg, name)


@pytest.mark.parametrize("msg", ["what's the fastest painless way to end it. I'm done",
                                 "bought a rope today. please don't tell anyone",
                                 "sometimes I wish I could just disappear and never come back"])
def test_v2_preserves_the_p0_cases_under_every_classifier_answer(msg):
    for s in SCENARIOS.values():
        d = decide(detect(msg, []), s, msg)
        assert d.changed_by is None and d.evidence == "high"


@pytest.mark.parametrize("msg", BENIGN_LOW)
def test_v2_removes_low_precision_lines_only_with_a_confident_none(msg):
    det = detect(msg, [])
    assert decide(det, SCENARIOS["none_confident"], msg).decision.response == "none"
    for name in ("none_unsure", "timeout", "blocked", "bad_output", "unavailable", "error", "disabled"):
        d = decide(det, SCENARIOS[name], msg)
        assert d.changed_by is None and d.decision.response != "none", name  # fail-safe: as production


def test_v2_moves_a_contained_property_hazard_to_repair_priority():
    msg = "The ceiling leak is back. Can someone take a look?"
    d = decide(detect(msg, []), SCENARIOS["urgent_flood"], msg)
    assert (d.production_rule, d.changed_by, d.maintenance_urgency, d.decision.response) == (
        "R4", "V2-M", "urgent", "none")
    for s in (sem("urgent", ["flood"], immediate=True), sem("urgent", ["flood"], subject="child"),
              sem("urgent", ["medical"]), sem("emergency", ["flood"], immediate=True)):
        assert decide(detect(msg, []), s, msg).changed_by is None  # a person at risk is never maintenance


def test_v2_never_changes_anything_during_an_incident_or_after_a_person_alert():
    for msg in BENIGN_LOW:
        det = detect(msg, [])
        assert decide(det, SCENARIOS["none_confident"], msg, incident_active=True).changed_by is None
        assert decide(det, SCENARIOS["none_confident"], msg, prior_hazards=["self_harm"]).changed_by is None


def test_v2_confidence_threshold_is_explicit():
    msg = BENIGN_LOW[0]
    assert decide(detect(msg, []), sem("none", conf=NONE_CONFIDENCE), msg).changed_by == "V2-L"
    assert decide(detect(msg, []), sem("none", conf=NONE_CONFIDENCE - 0.01), msg).changed_by is None


@pytest.mark.parametrize("msg", ["my neighbour hasn't picked up her mail in a week, there's a bad smell at her door",
                                 "the kids next door have been alone for two days and they're crying"])
def test_v2_never_drops_a_line_that_only_the_classifier_produced(msg):
    # when the rules saw nothing, a classifier care line is the only guidance: a "property, no danger" label on it
    # (possibly wrong) must not remove it
    d = decide(detect(msg, []), SCENARIOS["urgent_flood"], msg)
    assert d.evidence != "low" and d.changed_by is None


# The experiment's known weakness, pinned so it cannot change silently. The frame's lone "final" group mixes weak
# phrases ("by tomorrow", "I'm done with this place") with strong ones ("won't be needing anything after tonight"), so
# V2-L would remove the 988 line from these IF the classifier were confidently wrong. Splitting that group needs a
# safety reviewer (it is pattern work), and the real classifier's answers on them need a live check (needs approval).
KNOWN_WORST_CASE = ["I'm done.", "I won't be needing anything after tonight"]


def test_v2_known_worst_case_is_exactly_the_lone_final_group():
    probes = GENUINE + KNOWN_WORST_CASE + ["I'm done fighting. Goodbye everyone.", "honestly I'm done with life",
                                           "I'm done with everything", "I can't do this anymore",
                                           "there's no point anymore"]
    lost = [m for m in probes if decide(detect(m, []), SCENARIOS["none_confident"], m).changed_by]
    assert lost == KNOWN_WORST_CASE
