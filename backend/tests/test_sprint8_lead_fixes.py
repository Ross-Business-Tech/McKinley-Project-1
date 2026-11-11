"""Sprint 8 lead fixes from the independent verifier: (1) whitespace runs never stall the detectors; (2) draft
quick-fix tips are never served to a request that did not come straight from this machine (X-Forwarded-For)."""

import time

import pytest

from app.chat_engine import clean_message
from app.state import get_state


def test_whitespace_runs_collapse_before_detection():
    assert clean_message("if my dad " + " " * 1985 + "x") == "if my dad x"
    assert clean_message("line one\nline   two") == "line one\nline two"
    assert clean_message("a\n\n\n\nb") == "a\nb" and clean_message("a \n \n b") == "a\nb"
    assert clean_message("a\u2028\u2028b") == "a\nb" and clean_message("a\x0b\x0cb") == "a\nb"


@pytest.mark.parametrize("msg", ["if my dad " + " " * 1985 + "x", "the sink, " * 300, "a " * 1990,
                                 "if my dad " + "\n" * 1985 + "x", "if my dad " + " \n" * 990 + "x",
                                 "if my dad " + "\r\n" * 990 + "x", "if my dad " + "\u2028" * 1985 + "x",
                                 "if my dad " + "\x0b\x0c" * 990 + "x", "if my dad " + "\u2029 " * 990 + "x"])
def test_long_adversarial_inputs_are_fast(client, msg):
    t0 = time.time()
    r = client.post("/api/chat", json={"message": msg[:3990], "persona_id": "R003", "mode": "aware",
                                      "session_id": None})
    assert r.status_code == 200
    assert time.time() - t0 < 2.0


def test_remote_request_never_gets_draft_tips(client, monkeypatch):
    monkeypatch.setattr(get_state().deps.settings, "quickfix_content_mode", "demo_drafts")
    # a local backend that explicitly allows demo personas for remote callers (the verifier's repro)
    monkeypatch.setattr(get_state().deps.settings, "demo_personas_enabled", True)
    # Sprint 8 (D) fix round P1-2: a degraded classifier (the mock's status "mock") now means no tips at all, so the
    # local half of this check runs with the semantic layer switched off (status "disabled", rules only)
    monkeypatch.setattr(get_state().deps.settings, "safety_classifier", "off")
    msg = {"message": "my garbage disposal just hums and won't spin", "persona_id": "R003", "mode": "aware",
           "session_id": None}
    local = client.post("/api/chat", json=msg).json()
    remote = client.post("/api/chat", json=msg, headers={"X-Forwarded-For": "203.0.113.7"}).json()
    assert "Draft tips" in local["reply"] or "draft" in local["reply"].lower()
    assert "Draft tips" not in remote["reply"] and "reset button" not in remote["reply"].lower()
