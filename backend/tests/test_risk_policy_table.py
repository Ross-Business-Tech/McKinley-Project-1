"""One decision per policy rule (app/risk/policy.py), asserted by rule id, plus the 'never less cautious when the
classifier fails' property. Development examples only (not holdout data)."""

import pytest

from app.risk.detect import detect
from app.risk.models import DeterministicRisk, SemanticResult, SemanticRisk
from app.risk.policy import decide


def sem(level="none", cats=(), immediate=False, conf=0.9):
    return SemanticResult(status="ok", risk=SemanticRisk(risk_level=level, risk_categories=list(cats),
                                                         immediate_danger=immediate, confidence=conf))


FAILURES = [SemanticResult(status=s) for s in ("timeout", "error", "bad_output", "unavailable", "mock", "rate_limited")]

CASES = [  # (deterministic, semantic, prior hazards, expected rule, expected response, expected care)
    (DeterministicRisk(kind="gas", framing="report"), sem("none", conf=0.99), [], "R1", "full_alert", None),
    (DeterministicRisk(), sem("emergency", ["medical"], immediate=True), [], "R2", "full_alert", None),
    (DeterministicRisk(mentioned_kind="self_harm", framing="joking"), sem("none"), [], "R3", "care_line", "distress"),
    (DeterministicRisk(), sem("urgent", ["self_harm"]), [], "R4", "care_line", "distress"),
    (DeterministicRisk(mentioned_kind="gas", framing="past"), sem("none"), [], "R5", "safety_info", "info"),
    (DeterministicRisk(care="unwell"), sem("none", conf=0.99), [], "R6", "care_line", "unwell"),
    (DeterministicRisk(care="danger"), sem("none", conf=0.5), [], "R7", "care_line", "danger"),
    # Sprint 7 (stricter, moved): this case used to be "R7-suppressed" (semantic none at >= 0.8 removed the broad 911
    # line). The semantic layer may now only add guidance, so the line is kept and the disagreement recorded.
    (DeterministicRisk(care="danger"), sem("none", conf=0.95), [], "R7", "care_line", "danger"),
    (DeterministicRisk(care="danger"), sem("none", conf=0.99), ["personal_safety"], "R9e", "full_alert", None),
    (DeterministicRisk(), sem("none"), ["self_harm"], "R9", "care_line", "distress"),
    (DeterministicRisk(), sem("none"), [], "R8", "none", None),
]


@pytest.mark.parametrize("det,s,prior,rule,response,care", CASES, ids=[c[3] for c in CASES])
def test_each_policy_rule(det, s, prior, rule, response, care):
    d = decide(det, s, prior)
    assert (d.rule, d.response) == (rule, response)
    if care:
        assert d.care == care


def test_r7_suppression_is_blocked_after_an_earlier_person_hazard():
    d = decide(DeterministicRisk(care="danger"), sem("none", conf=0.99), ["self_harm"])
    assert d.response == "care_line" and d.care == "distress"


def test_r9e_uses_the_most_recent_person_hazard():
    d = decide(DeterministicRisk(care="danger"), SemanticResult(status="timeout"), ["medical", "personal_safety"])
    assert d.kind == "personal_safety"


RANK = {"none": 0, "safety_info": 1, "care_line": 2, "full_alert": 3}


@pytest.mark.parametrize("det,s,prior,rule,response,care", CASES, ids=[c[3] for c in CASES])
def test_a_failed_classifier_is_never_less_cautious_than_the_rules_alone(det, s, prior, rule, response, care):
    rules_only = decide(det, SemanticResult(status="disabled"), prior)
    for f in FAILURES:
        d = decide(det, f, prior)
        assert RANK[d.response] >= RANK[rules_only.response], (rule, f.status)
        assert d.degraded


def test_joking_self_harm_end_to_end_keeps_988(client):
    # Sprint 7 fix round (stricter, moved): this used to expect the R3 988 care line with no alert. A laugh marker may
    # no longer lower a live disclosure (monotone-safe lowering), so it is the full self-harm alert, which still
    # leads with 988. R3 stays in the policy table for a deterministic "joking" framing built directly.
    det = detect("i want to kill myself lol")
    assert det.kind == "self_harm" and det.framing == "report" and det.care == "distress"
    r = client.post("/api/chat", json={"message": "i want to kill myself lol", "persona_id": "R001",
                                       "mode": "aware", "session_id": "r3"}).json()
    assert r["safety_notice"] and "988" in r["safety_notice"]
    assert r["risk"]["decision"]["rule"] == "R1" and r["risk"]["decision"]["kind"] == "self_harm"
