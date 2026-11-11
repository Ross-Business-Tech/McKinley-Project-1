"""Sprint 8 (D) API replays for quick-fix tips, after the actions.py hook is wired (lead applies Agent D's diff).

Flow: eligible low-risk issue -> tips (draft-labelled in demo_drafts) -> "fixed" closes with no record; "no" /
"just send maintenance" -> the normal repair card with the original issue; at most one round per issue;
approved_only (default) and hazards never show tips. Synthetic resident R003, mock provider, offline.
"""

import uuid

import pytest

from app.state import get_state
from tests.test_sprint6_conversation import chat, fields

TIP_MARK = {"en": "Did that fix it?", "es": "¿Se resolvió?"}


def sid():
    return f"qf-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def demo(client, monkeypatch):
    monkeypatch.setattr(get_state().deps.settings, "quickfix_content_mode", "demo_drafts")
    # fix round P1-2: tips need a non-degraded safety decision; the mock "classifier" is degraded (status "mock"),
    # so these replays run with the semantic layer off (status "disabled": the rules alone decide)
    monkeypatch.setattr(get_state().deps.settings, "safety_classifier", "off")
    return client


def recs(s):
    return get_state().store.records(session_id=s, limit=50)


def offered(r, lang="en"):
    return TIP_MARK[lang] in r["reply"]


@pytest.mark.parametrize("msg,lang", [
    ("my breaker tripped", "en"), ("the bathroom outlet stopped working", "en"),
    ("garbage disposal won't turn on", "en"), ("my bathtub is clogged", "en"),
    ("la pastilla de la cocina se botó y no hay luz", "es"), ("el enchufe del baño no funciona", "es"),
    ("el triturador de basura no prende", "es"), ("la regadera está tapada", "es"),
])
def test_eligible_issue_gets_labelled_draft_tips_and_no_card(demo, msg, lang):
    r = chat(demo, msg, sid())
    assert offered(r, lang), r["reply"]
    assert ("not yet approved by McKinley" if lang == "en" else "aún no aprobados por McKinley") in r["reply"]
    assert not r.get("action")  # no repair card yet


def test_fixed_closes_without_a_record(demo):
    s = sid()
    assert offered(chat(demo, "my bathtub is clogged", s))
    r = chat(demo, "yes that worked, thanks", s)
    assert "haven't sent anything" in r["reply"] and not r.get("action")
    assert recs(s) == []


@pytest.mark.parametrize("answer", ["no, still slow", "just send maintenance", "Still not working", "not sure"])
def test_not_fixed_or_skip_opens_the_repair_card_with_the_issue(demo, answer):
    s = sid()
    assert offered(chat(demo, "my bathtub is clogged", s))
    r = chat(demo, answer, s)
    assert (r.get("action") or {}).get("kind") == "maintenance_request", r["reply"]
    assert "clogged" in fields(r).get("issue", "").lower()
    assert recs(s) == []  # nothing is sent until the resident presses Send


def test_skip_in_the_first_message_goes_straight_to_the_card(demo):
    r = chat(demo, "my bathtub is clogged, just send maintenance", sid())
    assert not offered(r) and (r.get("action") or {}).get("kind") == "maintenance_request"


def test_no_second_round_of_tips_for_the_same_issue(demo):
    s = sid()
    chat(demo, "my breaker tripped", s)
    chat(demo, "yes", s)
    r = chat(demo, "my breaker tripped again", s)
    assert not offered(r)
    s2 = sid()
    chat(demo, "my breaker tripped", s2)
    chat(demo, "fixed", s2)
    assert not offered(chat(demo, "my breaker tripped", s2))  # already offered in this conversation


@pytest.mark.parametrize("msg", ["my breaker keeps tripping and I smell burning",
                                 "disposal hums and there's water under the sink", "drain is clogged and overflowing",
                                 "the bathroom outlet is sparking", "la pastilla se botó y huele a quemado"])
def test_hazard_never_gets_tips(demo, msg):
    assert not offered(chat(demo, msg, sid()))


def test_default_approved_only_shows_no_tips(client):
    r = chat(client, "my bathtub is clogged", sid())
    assert not offered(r) and (r.get("action") or {}).get("kind") == "maintenance_request"


def test_follow_up_emergency_wins(demo):
    s = sid()
    chat(demo, "my breaker tripped", s)
    r = chat(demo, "no and now the outlet is sparking and smoking", s)
    assert not offered(r) and r.get("emergency_kind")
