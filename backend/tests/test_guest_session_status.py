"""Public demo (not signed in): "what's the status of my tour request?" lists what THIS conversation sent and nothing
from any other conversation (found on the live Render deployment, 2026-11-11: the model said "nothing on file")."""


def _chat(c, msg, sid):
    r = c.post("/api/chat", json={"message": msg, "persona_id": None, "mode": "aware", "session_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


def _tour(c, sid):
    _chat(c, "I'd like to schedule a tour of Heron Lake.", sid)
    d = _chat(c, "Saturday morning works, and I'm looking for a 2 bedroom.", sid)
    assert (d.get("action") or {}).get("stage") == "ready", d
    r = c.post("/api/actions/confirm", json={"session_id": d["session_id"], "persona_id": None, "kind": "tour_request"})
    assert r.json()["ok"], r.text
    return d["session_id"], r.json()["record"]["id"]


def test_guest_status_lists_this_conversations_request(client):
    sid, ref = _tour(client, "guest-status-a")
    d = _chat(client, "What's the status of my tour request?", sid)
    assert ref in d["reply"] and "tour request" in d["reply"]
    assert "nobody at McKinley is notified" in d["reply"]
    assert d["reply_source"] != "model"


def test_guest_status_never_shows_another_conversations_request(client):
    _, ref = _tour(client, "guest-status-b")
    d = _chat(client, "What's the status of my tour request?", "guest-status-c")
    assert ref not in d["reply"]


def test_guest_without_saved_requests_keeps_the_old_path(client):
    d = _chat(client, "What's the status of my request?", "guest-status-d")
    assert "In this conversation you sent" not in d["reply"]
