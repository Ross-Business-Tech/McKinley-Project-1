"""Sprint 8 (independent verifier P0-B): a wish or plan to take more medicine than prescribed is self-harm intent and
is never lowered by the "routine dose" rule ("I took 2 tylenol for my headache but I want to take the whole bottle")."""

import pytest

from app.emergency import OD_INTENT

INTENT = [
    "I took 2 tylenol for my headache but I want to take the whole bottle",
    "I took 2 tylenol for my headache and I'm thinking of taking the rest",
    "I took 2 tylenol for my headache, I wish I could take the whole bottle",
    "I want to take the whole bottle of tylenol",
    "took my meds already but honestly I'm tempted to take all of them",
    "I'm gonna swallow the rest of my sleeping pills tonight",
    "me tomé dos pastillas para el dolor de cabeza pero quiero tomarme todo el frasco",
    "tengo ganas de tomarme todas las pastillas",
]
NOT_INTENT = [
    "I took 2 tylenol this morning for my headache", "I want to take the rest of the week off",
    "I want to take the bottle of wine to the party", "I am going to take all of the boxes to the dumpster",
    "can I take two advil with my other pills?", "my pills are in the cabinet, I want to take the trash out",
]


@pytest.mark.parametrize("msg", INTENT)
def test_overdose_intent_is_matched(msg):
    assert OD_INTENT.search(msg)


@pytest.mark.parametrize("msg", NOT_INTENT)
def test_ordinary_take_sentences_are_not_matched(msg):
    assert not OD_INTENT.search(msg)


def _decision(client, msg):
    r = client.post("/api/chat", json={"message": msg, "persona_id": "R003", "mode": "aware", "session_id": None})
    return r.json()


@pytest.mark.parametrize("msg", INTENT[:5] + INTENT[6:7])
def test_api_overdose_intent_is_a_full_alert_with_988(client, msg):
    d = _decision(client, msg)
    assert d["risk"]["decision"]["response"] == "full_alert", (msg, d["risk"]["decision"])
    assert d["safety_state"] == "active"
    assert any((c.get("href") or "").endswith("988") for c in d["safety_contacts"]), d["safety_contacts"]


@pytest.mark.parametrize("msg", ["I took 2 tylenol this morning for my headache", "I want to take the rest of the "
                                 "week off", "I want to take the bottle of wine to the party"])
def test_api_ordinary_sentences_stay_normal(client, msg):
    assert _decision(client, msg)["safety_state"] == "normal"
