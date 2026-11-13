
from tests.test_context import AC_MSG, RENEWAL_MSG


def test_health_and_models_hide_secrets(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["provider"] == "mock" and h["data_loaded"]
    models = client.get("/api/models")
    assert models.status_code == 200
    text = models.text.lower()
    assert "sk-" not in text and "openrouter_api_key" not in text and "base_url" not in text
    by_key = {m["key"]: m for m in models.json()}
    assert by_key["mock:mock-deterministic-v1"]["is_mock"]
    assert by_key["openrouter:google/gemma-4-31b-it:free"]["status"] == "NEEDS_API_KEY"


def test_personas(client):
    ps = client.get("/api/personas").json()
    assert {"P-RELOCATE-AA", "P-BROWSE-FL", "U-NOMATCH", "R001"} <= {p["id"] for p in ps}


def test_chat_aware_vs_baseline(client):
    a = client.post("/api/chat", json={"message": AC_MSG, "persona_id": "R001", "mode": "aware",
                                       "session_id": "s1"}).json()
    b = client.post("/api/chat", json={"message": AC_MSG, "persona_id": "R001", "mode": "baseline",
                                       "session_id": "s1"}).json()
    assert a["is_mock"] and a["provider"] == "mock" and a["model"] == "mock-deterministic-v1"
    assert a["recommended_handoff"] and a["handoff_is_recommendation_only"]
    assert a["source_context_fields"] and b["source_context_fields"] == []
    assert a["prompt_version"].startswith("mckinley-v0.2") and b["prompt_version"].startswith("baseline-v1")
    assert {c["code"] for c in a["output_checks"]} >= {"terminology", "no_false_action_claim", "structured_output"}


def test_aware_policy_gate_forces_handoff(client):
    r = client.post("/api/chat", json={"message": "I smell gas in my kitchen", "persona_id": "U-NOMATCH",
                                       "mode": "aware"}).json()
    assert r["recommended_handoff"] and r["handoff_category"] == "safety_emergency"


def test_chat_validation_and_errors(client):
    assert client.post("/api/chat", json={"message": "", "mode": "aware"}).status_code == 422
    assert client.post("/api/chat", json={"message": "x", "mode": "other"}).status_code == 422
    assert client.post("/api/chat", json={"message": "x", "mode": "aware", "extra": 1}).status_code == 422
    r = client.post("/api/chat", json={"message": "x", "mode": "aware", "target": "openrouter:evil/model"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNKNOWN_TARGET"
    r = client.post("/api/chat", json={"message": "x", "mode": "aware",
                                       "target": "openrouter:google/gemma-4-31b-it:free"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "NEEDS_API_KEY"


def test_session_separation(client, settings):
    from app.db import Store
    store = Store(settings.db_path)
    client.post("/api/chat", json={"message": RENEWAL_MSG, "persona_id": "R003", "mode": "aware",
                                   "session_id": "A"})
    assert store.history("A", "aware|mock:mock-deterministic-v1", "R003")
    assert store.history("B", "aware|mock:mock-deterministic-v1", "R003") == []
    assert store.history("A", "baseline|mock:mock-deterministic-v1", "R003") == []


def test_configured_key_never_returned(settings, workbook):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.db import Store
    from app.llm import LLMGateway
    from app.main import app
    from app.state import build_state, set_state

    settings.openrouter_api_key = SecretStr("sk-or-v1-SUPERSECRET")
    set_state(build_state(settings=settings, gateway=LLMGateway(settings), workbook=workbook,
                          store=Store(settings.db_path)))
    with TestClient(app) as c:
        for path in ("/api/health", "/api/models", "/api/personas"):
            assert "SUPERSECRET" not in c.get(path).text
        assert {m["key"]: m for m in c.get("/api/models").json()}[
            "openrouter:google/gemma-4-31b-it:free"]["ready"]
    set_state(None)  # type: ignore[arg-type]
