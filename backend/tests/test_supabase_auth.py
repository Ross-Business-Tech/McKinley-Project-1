"""Supabase sign-in: token checks, the invite list, and what a signed-in person can and cannot reach.

No network: tokens are signed with a throwaway key made here, and the published-keys fetch is a stub."""

import json
import sqlite3
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import manage_users
from app.auth import AuthError
from app.config import Settings
from app.db import Store
from app.llm import LLMGateway
from app.main import app
from app.state import build_state, set_state
from app.supabase_auth import SupabaseVerifier

URL = "https://abcdefgh.supabase.co"
ISS = f"{URL}/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
JWK = {**json.loads(jwt.algorithms.ECAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "alg": "ES256", "use": "sig"}
JWKS = {"keys": [JWK]}
DROP = object()


def make_token(email="resident@example.com", sub="user-1", key=KEY, kid="k1", alg="ES256", **over):
    now = int(time.time())
    payload = {"aud": "authenticated", "iss": ISS, "sub": sub, "email": email, "role": "authenticated",
               "iat": now, "exp": now + 3600, "app_metadata": {"provider": "email"}}
    payload.update(over)
    payload = {k: v for k, v in payload.items() if v is not DROP}
    return jwt.encode(payload, key, algorithm=alg, headers={"kid": kid} if kid else None)


def verifier(fetch=lambda url: JWKS, secret=None, clock=time.monotonic):
    s = Settings(_env_file=None, supabase_url=URL, supabase_jwt_secret=SecretStr(secret) if secret else None)
    return SupabaseVerifier(s, fetch_jwks=fetch, clock=clock)


# ---------------------------------------------------------------- the token check
def test_a_genuine_token_is_accepted_and_the_email_is_lowercased():
    claims = verifier().verify(make_token(email="Resident@Example.COM"))
    assert (claims.user_id, claims.email) == ("user-1", "resident@example.com")


@pytest.mark.parametrize("bad", [
    {"exp": 1},  # expired long ago
    {"aud": "someone-else"},
    {"iss": "https://evil.example.com/auth/v1"},
    {"exp": DROP},
    {"sub": DROP},
    {"role": "anon"},  # the public anon key is not a person
    {"role": "service_role"},
    {"is_anonymous": True},
    {"email": DROP},
    {"email": "not-an-email"},
    {"app_metadata": {"provider": "google"}},  # only the emailed code is switched on
    {"app_metadata": {}},
])
def test_tokens_with_wrong_or_missing_claims_are_refused(bad):
    with pytest.raises(AuthError) as e:
        verifier().verify(make_token(**bad))
    assert e.value.status == 401 and e.value.code == "INVALID_TOKEN"


def test_garbage_and_forged_tokens_are_refused():
    v = verifier()
    for token in ("", "not.a.jwt", make_token(key=OTHER_KEY)):  # signed by someone else's key under the same kid
        with pytest.raises(AuthError) as e:
            v.verify(token)
        assert e.value.code == "INVALID_TOKEN"


def test_alg_none_and_unlisted_algorithms_are_refused():
    now = int(time.time())
    payload = {"aud": "authenticated", "iss": ISS, "sub": "u", "email": "a@example.com", "role": "authenticated",
               "exp": now + 600, "app_metadata": {"provider": "email"}}
    unsigned = jwt.encode(payload, None, algorithm="none")
    hs512 = jwt.encode(payload, "x" * 64, algorithm="HS512")
    for token in (unsigned, hs512):
        with pytest.raises(AuthError):
            verifier(secret="x" * 64).verify(token)


def test_a_shared_secret_token_only_counts_when_that_legacy_secret_is_configured():
    secret = "legacy-shared-secret-" + "z" * 32
    token = make_token(key=secret, alg="HS256", kid=None)
    assert verifier(secret=secret).verify(token).email == "resident@example.com"
    with pytest.raises(AuthError):
        verifier().verify(token)  # no secret configured: an HS256 token can never be trusted
    with pytest.raises(AuthError):
        verifier(secret="a-different-secret-" + "q" * 32).verify(token)


def test_unknown_key_ids_cannot_make_the_backend_hammer_supabase():
    calls, now = [], [1000.0]

    def fetch(url):
        calls.append(url)
        return JWKS
    v = verifier(fetch=fetch, clock=lambda: now[0])
    v.verify(make_token())
    assert len(calls) == 1 and calls[0] == f"{ISS}/.well-known/jwks.json"
    stranger = make_token(kid="rotated")
    for _ in range(5):  # within the minimum gap: refused without another fetch
        with pytest.raises(AuthError):
            v.verify(stranger)
    assert len(calls) == 1
    now[0] += 31  # a legitimately rotated key is picked up after the gap
    with pytest.raises(AuthError):
        v.verify(stranger)
    assert len(calls) == 2


def test_when_supabase_keys_cannot_be_fetched():
    def down(url):
        raise OSError("connection refused: internal detail")
    with pytest.raises(AuthError) as e:
        verifier(fetch=down).verify(make_token())
    assert e.value.status == 503 and e.value.code == "AUTH_UNAVAILABLE" and "internal" not in e.value.message

    state = {"up": True}

    def flaky(url):
        if state["up"]:
            return JWKS
        raise OSError("down")
    now = [0.0]
    v = verifier(fetch=flaky, clock=lambda: now[0])
    assert v.verify(make_token()).email == "resident@example.com"
    state["up"] = False
    now[0] += 5000  # the cached keys are stale and the refresh fails: keep using the keys we have
    assert v.verify(make_token()).email == "resident@example.com"


# ---------------------------------------------------------------- the invite list
def test_invite_list_store_rules(tmp_path):
    s = Store(tmp_path / "p.sqlite3")
    assert s.profile_for_email("a@example.com") is None
    s.upsert_profile("A@Example.com", "resident", "R001")
    p = s.profile_for_email("a@EXAMPLE.com")
    assert p["role"] == "resident" and p["persona_id"] == "R001" and p["user_id"] is None and not p["disabled"]
    assert s.claim_profile("a@example.com", "u1") is True
    assert s.claim_profile("a@example.com", "u1") is True  # the same account again
    assert s.claim_profile("a@example.com", "u2") is False  # a different account under the same email
    assert s.claim_profile("nobody@example.com", "u1") is False
    s.upsert_profile("a@example.com", "resident", "R003")  # re-inviting clears the remembered account on purpose
    assert s.profile_for_email("a@example.com")["user_id"] is None
    assert s.set_profile_disabled("a@example.com", True) and s.profile_for_email("a@example.com")["disabled"]
    assert [r["email"] for r in s.profiles()] == ["a@example.com"]
    assert s.remove_profile("a@example.com") and not s.remove_profile("a@example.com")
    with pytest.raises(sqlite3.IntegrityError):  # the table itself only accepts the two roles
        s.upsert_profile("b@example.com", "admin", None)


def test_manage_users_tool(tmp_path, workbook, capsys):
    s = Settings(_env_file=None, db_path=tmp_path / "m.sqlite3", data_path=tmp_path / "missing.xlsx")
    store = Store(s.db_path)
    # the resident id is checked against the synthetic data; none is loaded here, so it refuses
    assert manage_users.main(["add", "--email", "a@example.com", "--role", "resident", "--persona", "R001"],
                             settings=s, store=store) == 2
    assert "Could not check" in capsys.readouterr().err
    assert manage_users.main(["add", "--email", "a@example.com", "--role", "resident", "--persona", "R001",
                              "--no-check"], settings=s, store=store) == 0
    assert manage_users.main(["add", "--email", "a@example.com", "--role", "resident"], settings=s, store=store) == 2
    assert manage_users.main(["add", "--email", "s@example.com", "--role", "staff", "--persona", "R001"],
                             settings=s, store=store) == 2
    assert manage_users.main(["add", "--email", "s@example.com", "--role", "staff"], settings=s, store=store) == 0
    assert manage_users.main(["disable", "--email", "a@example.com"], settings=s, store=store) == 0
    assert store.profile_for_email("a@example.com")["disabled"]
    assert manage_users.main(["remove", "--email", "ghost@example.com"], settings=s, store=store) == 1
    capsys.readouterr()
    assert manage_users.main(["list"], settings=s, store=store) == 0
    out = capsys.readouterr().out
    assert "a@example.com" in out and "DISABLED" in out and "s@example.com" in out
    with pytest.raises(SystemExit):
        manage_users.main(["add", "--email", "nonsense", "--role", "staff"], settings=s, store=store)


def test_the_resident_id_is_checked_against_the_synthetic_data(tmp_path, workbook, capsys):
    s = Settings(_env_file=None, db_path=tmp_path / "m2.sqlite3", data_path=tmp_path / "missing.xlsx")
    store = Store(s.db_path)
    import app.manage_users as mu
    mu.load_residents = lambda settings, st: (workbook, None)  # the fixture workbook stands in for the seed data
    assert mu.main(["add", "--email", "a@example.com", "--role", "resident", "--persona", "R001"],
                   settings=s, store=store) == 0
    assert mu.main(["add", "--email", "b@example.com", "--role", "resident", "--persona", "R777"],
                   settings=s, store=store) == 2
    assert "not a resident" in capsys.readouterr().err


# ---------------------------------------------------------------- the API
@pytest.fixture
def api(settings, workbook):
    """A backend with sign-in switched on. A staff token is set so "this machine = staff" can't mask the sign-in."""
    settings.supabase_url = URL
    settings.staff_api_token = SecretStr("t" * 32)
    store = Store(settings.db_path)
    state = build_state(settings=settings, gateway=LLMGateway(settings), workbook=workbook, store=store)
    state.verifier = SupabaseVerifier(settings, fetch_jwks=lambda url: JWKS)
    set_state(state)
    store.upsert_profile("resident@example.com", "resident", "R001")
    store.upsert_profile("staff@example.com", "staff", None)
    with TestClient(app) as c:
        c.store = store  # type: ignore[attr-defined]
        yield c
    set_state(None)  # type: ignore[arg-type]


def bearer(email="resident@example.com", sub=None, **over):
    return {"Authorization": f"Bearer {make_token(email=email, sub=sub or email, **over)}"}


def me(api, headers=None):
    r = api.get("/api/me", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_me_reports_each_kind_of_visitor(api):
    assert me(api) == {"auth_enabled": True, "status": "anonymous", "role": None, "persona_id": None}
    assert me(api, bearer()) == {"auth_enabled": True, "status": "signed_in", "role": "resident",
                                 "persona_id": "R001"}
    assert me(api, bearer("staff@example.com"))["role"] == "staff"
    assert me(api, bearer("stranger@example.com"))["status"] == "not_invited"
    assert me(api, {"Authorization": "Bearer junk"})["status"] == "invalid_token"
    assert me(api, bearer(exp=1))["status"] == "invalid_token"
    api.store.set_profile_disabled("resident@example.com", True)
    assert me(api, bearer())["status"] == "not_invited"


def test_a_resident_invite_without_a_linked_resident_gets_nothing(api):
    api.store.upsert_profile("orphan@example.com", "resident", None)
    assert me(api, bearer("orphan@example.com"))["status"] == "not_invited"


def test_the_same_email_from_a_different_supabase_account_is_not_let_in(api):
    assert me(api, bearer(sub="account-A"))["status"] == "signed_in"
    assert me(api, bearer(sub="account-B"))["status"] == "not_invited"
    assert me(api, bearer(sub="account-A"))["status"] == "signed_in"


def test_a_deployment_without_sign_in_ignores_tokens(client):
    r = client.get("/api/me", headers=bearer()).json()
    assert r == {"auth_enabled": False, "status": "no_auth", "role": None, "persona_id": None}


def chat(api, message, headers=None, **kw):
    body = {"message": message, "persona_id": None, "mode": "aware", "session_id": "s1", **kw}
    return api.post("/api/chat", json=body, headers=headers or {})


def test_a_bad_token_never_blocks_a_message(api):
    for headers in ({"Authorization": "Bearer junk"}, bearer(exp=1), bearer("stranger@example.com")):
        r = chat(api, "I smell gas in my kitchen", headers, session_id=f"g-{id(headers)}")
        assert r.status_code == 200
    assert api.store.session_binding("g-" + str(id(headers)))[0] == "anonymous"


def test_a_signed_in_resident_is_that_resident_and_the_browser_cannot_choose_another(api):
    r = chat(api, "My AC stopped cooling again. This has happened multiple times.", bearer(), persona_id="R003")
    assert r.status_code == 200, r.text
    assert api.store.session_binding("s1") == ("authenticated_resident", "R001")
    body = r.json()
    assert body["action"]["kind"] == "maintenance_request"  # R001's own history, never R003's


def test_a_signed_in_resident_can_save_a_request_and_nobody_else_can_touch_the_draft(api):
    h = bearer()
    chat(api, "My AC stopped cooling again. This has happened multiple times.", h)
    assert chat(api, "Yes, you can enter", h).json()["action"]["stage"] == "ready"
    confirm = {"session_id": "s1", "persona_id": None, "kind": "maintenance_request"}
    # the same session without the sign-in is a different principal: refused, and the draft stays
    denied = api.post("/api/actions/confirm", json=confirm)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "SESSION_PERSONA_MISMATCH"
    other = api.post("/api/actions/confirm", json=confirm, headers=bearer("staff@example.com"))
    assert other.status_code == 403
    ok = api.post("/api/actions/confirm", json=confirm, headers=h).json()
    assert ok["ok"] and ok["record"]["id"].startswith("DEMO-WO-")


def test_signing_out_mid_conversation_starts_a_new_one_not_a_leak(api):
    chat(api, "My AC stopped cooling again. This has happened multiple times.", bearer())
    r = chat(api, "What is my request status?")  # same session id, no sign-in
    assert r.status_code == 200
    assert r.json()["session_id"] != "s1"  # a fresh server-issued conversation
    assert "AC" not in r.json()["reply"]


def test_staff_routes_need_a_staff_sign_in_or_the_staff_token(api):
    path = "/api/evals/cases"
    assert api.get(path).status_code == 403
    assert api.get(path, headers=bearer()).status_code == 403  # a resident is not staff
    assert api.get(path, headers=bearer("stranger@example.com")).status_code == 403
    assert api.get(path, headers={"Authorization": "Bearer junk"}).status_code == 403
    assert api.get(path, headers=bearer("staff@example.com")).status_code == 200
    assert api.get(path, headers={"X-Staff-Token": "t" * 32}).status_code == 200
    assert api.get(path, headers={"X-Staff-Token": "wrong"}).status_code == 403
    api.store.set_profile_disabled("staff@example.com", True)
    assert api.get(path, headers=bearer("staff@example.com")).status_code == 403


def test_staff_overrides_and_diagnostics_follow_the_staff_sign_in(api):
    override = {"mode": "baseline"}
    assert chat(api, "hello", bearer(), **override).status_code == 403
    assert chat(api, "hello", bearer("staff@example.com"), **override).status_code == 200
    # the response keeps its shape, but staff-only fields are blanked for residents (app/api/views.py)
    assert chat(api, "hello there", bearer()).json()["prompt_version"] == ""
    assert chat(api, "hello there", bearer("staff@example.com")).json()["prompt_version"] != ""


def test_a_staff_sign_in_does_not_turn_chat_into_a_resident_account(api):
    chat(api, "Any update on my repair?", bearer("staff@example.com"))
    assert api.store.session_binding("s1") == ("anonymous", "none")


def test_health_shows_staff_facts_only_to_staff(api):
    assert api.get("/api/health").json()["database"] == ""
    assert api.get("/api/health", headers=bearer()).json()["database"] == ""
    assert api.get("/api/health", headers=bearer("staff@example.com")).json()["database"] == "sqlite"


def test_the_token_never_appears_in_any_response(api):
    h = bearer()
    token = h["Authorization"].split(" ")[1]
    for r in (api.get("/api/me", headers=h), api.get("/api/health", headers=h), chat(api, "hello", h)):
        assert token not in r.text


def test_cors_allows_the_authorization_header(api):
    r = api.options("/api/chat", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                                          "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200 and "authorization" in r.headers["access-control-allow-headers"].lower()


# ---------------------------------------------------------------- settings
def _hosted(**kw):
    base = dict(_env_file=None, app_env="hosted", cors_origins="https://site.onrender.com",
                staff_api_token=SecretStr("abcdefghijklmnop0123456789XYZ"),
                database_url=SecretStr("postgresql://u:p@h:5432/d"))
    base.update(kw)
    return Settings(**base)


def test_hosted_mode_checks_the_supabase_address():
    assert not any("SUPABASE_URL" in p for p in _hosted(supabase_url=URL).hosted_problems())
    assert not any("SUPABASE_URL" in p for p in _hosted().hosted_problems())
    for bad in ("http://abcdefgh.supabase.co", f"{URL}/rest/v1", "abcdefgh.supabase.co"):
        assert any("SUPABASE_URL" in p for p in _hosted(supabase_url=bad).hosted_problems()), bad
    assert _hosted(supabase_url=URL + "/").supabase_origin == URL  # a pasted trailing slash is harmless
