"""Sprint 6 development set (tests/sprint6_safety_devset.py): rules + policy + notice selection, semantic layer off.

These are DEVELOPMENT numbers: the detectors were built against this set, so they are not evidence of recall on new
wording. Recall must be measured on a fresh holdout written by someone else
(docs/safety/SAFETY_STATE_AND_EVALUATION.md).
The thresholds pin the Sprint 6 result so a later change cannot silently lose it.
"""

import pytest

from app.risk.pipeline import assess
from tests.sprint6_safety_devset import LOOKALIKES, POSITIVES, evaluate


def _fn(msg):
    d = assess(msg, [], None).decision
    return d.response, d.kind


@pytest.fixture(scope="module")
def result():
    return evaluate(_fn)


def test_devset_shape():
    assert all(len(v) >= 10 for v in POSITIVES.values())
    assert all(len(v) >= 5 for v in LOOKALIKES.values())
    spanish = sum(1 for v in POSITIVES.values() for m, _ in v if any(ch in m for ch in "áéíóúñ¿¡") or " el " in m)
    assert spanish >= 15  # at least one Spanish paraphrase in every category (heuristic count)


def test_devset_full_alert_recall(result):
    t = result["total"]
    assert t["alert"] / t["pos"] >= 0.97, result["misses"]


def test_devset_right_notice_for_the_incident(result):
    t = result["total"]
    assert t["right"] / t["pos"] >= 0.97, result["wrong"]
    assert not [w for w in result["wrong"] if w[0] == "trapped"]  # no hot car / child case gets the elevator text


def test_devset_every_positive_gets_some_guidance(result):
    t = result["total"]
    assert t["guided"] == t["pos"], result["misses"]


def test_devset_lookalike_full_alerts(result):
    t = result["total"]
    assert t["neg_alert"] <= 1, result["fp"]


@pytest.mark.parametrize("cat", sorted(POSITIVES))
def test_devset_each_category(result, cat):
    c = result["by_cat"][cat]
    assert c["alert"] >= c["pos"] - 1 and c["neg_alert"] == 0
