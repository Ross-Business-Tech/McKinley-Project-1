"""Small API helpers shared by the test modules."""


def chat(client, msg, session, persona="R003", **extra):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session, **extra}).json()


def press_send(client, session, kind, persona="R003"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}
