"""Staff/demo routes: guard, contents and redaction. Customer routes stay open (demo identity model)."""

import pytest
from fastapi.routing import APIRoute

STAFF_PATHS = {"/api/prototype/records", "/api/staff/conversations", "/api/staff/conversations/{session_hash}",
               "/api/context/preview"}


def chat(client, msg, session, persona="R001"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def test_every_staff_route_depends_on_the_guard():
    from app.api import actions, chat, evals, gates
    from app.api.staff_guard import require_staff

    def is_guard(deps):
        return any(getattr(d, "dependency", None) is require_staff for d in deps)

    guarded = set()
    for module in (actions, chat, evals, gates):
        router = module.router
        for r in router.routes:
            if isinstance(r, APIRoute) and (is_guard(r.dependencies) or is_guard(router.dependencies)):
                guarded.add(r.path)
    assert STAFF_PATHS <= guarded
    for module in (evals, gates):  # evaluation and gate tools are staff-only too (gate config is public)
        for r in module.router.routes:
            if isinstance(r, APIRoute) and r.path != "/api/gates/config":
                assert r.path in guarded, r.path


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-Server": "proxy"}, {"X-Cluster-Client-IP": "10.0.0.5"}, {"CF-Connecting-IP": "10.0.0.5"},
    {"True-Client-IP": "10.0.0.5"}, {"Host": "localhost.evil.com"}, {"Host": "example.com:8000"},
])
def test_proxied_or_foreign_requests_are_refused(client, headers):
    r = client.get("/api/staff/conversations", headers=headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "STAFF_ONLY"


def test_wrong_token_is_refused_and_right_token_works(client, monkeypatch):
    from pydantic import SecretStr

    from app.state import get_state
    settings = get_state().deps.settings
    monkeypatch.setattr(settings, "staff_api_token", SecretStr("demo-token-for-tests"))
    assert client.get("/api/staff/conversations", headers={"X-Staff-Token": "wrong"}).status_code == 403
    assert client.get("/api/staff/conversations", headers={"X-Staff-Token": "demo-token-for-tests"}).status_code == 200


def test_staff_conversations_list_flags_and_redacts(client):
    chat(client, "I smell gas in the kitchen", "sc1")
    chat(client, "honestly what's the point of anything anymore", "sc2")
    chat(client, "can I talk to a person? my number is 555-201-8890", "sc3")
    rows = client.get("/api/staff/conversations").json()
    flags = {tuple(r["needs_action"]) for r in rows}
    assert any("urgent" in f for f in flags) and any("wellbeing" in f for f in flags)
    assert any("asked_for_person" in f for f in flags)
    assert all("session_id" not in r for r in rows)  # only the one-way hash is exposed
    detail = client.get(f"/api/staff/conversations/{rows[0]['session_hash']}").json()
    assert detail["turns"] and "555-201-8890" not in str(detail)


def test_unknown_conversation_is_404_with_error_envelope(client):
    r = client.get("/api/staff/conversations/0000000000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_cancel_marks_the_card_declined_and_send_it_after_all_restores_it(client):
    chat(client, "the bathroom fan is rattling", "cx1")
    chat(client, "yes you can come in", "cx1")
    res = client.post("/api/actions/cancel", json={"session_id": "cx1", "persona_id": "R001",
                                                   "kind": "maintenance_request"}).json()
    assert res["ok"]
    assert not client.post("/api/actions/confirm", json={"session_id": "cx1", "persona_id": "R001",
                                                         "kind": "maintenance_request"}).json()["ok"]
    assert chat(client, "send it after all", "cx1")["action"]["kind"] == "maintenance_request"
