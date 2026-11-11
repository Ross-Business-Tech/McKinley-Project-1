"""Sprint 6 fix round (authorization): records are scoped by OWNER (principal + persona), chat state by SESSION, and a
stated non-holder gets no account data at the data layer. Assertions are on RESPONSE DATA (references, context fields,
card fields, record owners), never on reply wording. See docs/security/AUTHORIZATION_BOUNDARIES.md."""

import json

import pytest

from app.db import ScopedStore, Store
from app.personas import states_not_account_holder
from app.state import get_state
from tests.test_sprint6_auth import (  # noqa: F401  (hosted fixtures)
    R001_SECRETS,
    act,
    blob,
    chat,
    hosted,
    hosted_settings,
    r001_request,
    refs,
)

MODE = "aware|mock:mock-deterministic-v1"


def card_fields(resp: dict) -> list[dict]:
    return list(((resp.get("action") or {}).get("fields")) or [])


# ---- 1. own records across sessions ---------------------------------------------------------------------------

def test_same_persona_finds_its_own_request_from_an_earlier_session(client):
    ref = r001_request(client, "first-visit")
    r = chat(client, "any update on my requests?", "R001", "second-visit")
    assert ref in refs(r) and "I008" in refs(r)


def test_status_of_an_earlier_session_request_by_its_words(client):
    chat(client, "There's a leak under my kitchen sink", "R001", "early")
    r = chat(client, "Yes, you can enter", "R001", "early")
    assert r["action"]["stage"] == "ready"
    ref = act(client, "confirm", "early", "R001")["record"]["id"]
    later = chat(client, "any update on the leak under my sink?", "R001", "later")
    assert ref in refs(later)
    assert not later["records_created"]  # no duplicate work order


def test_typed_reference_from_an_earlier_session_is_listed_from_the_data_layer(client):
    ref = r001_request(client, "s-one")
    r = chat(client, f"what's the status of {ref}?", "R001", "s-two")
    assert ref in refs(r) or ref in r["reply"]
    assert not r["records_created"]
    assert len(get_state().store.records(persona_id="R001")) == 1  # no duplicate written


# The typed-reference branch in app/actions.py (owned by the conversation engineer) looks only at `mine` (this
# session's records). It needs the one-line call-site change described in the auth fix-round report:
#   rec_t = next((r for r in mine if r["id"].upper() == ref_t), None) or store.own_record(ref_t)  (store is scoped)
# strict xfail: this test starts passing (and the marker must go) once that line is in.
def test_typed_reference_from_an_earlier_session_is_answered_as_found(client):
    ref = r001_request(client, "t-one")
    r = chat(client, f"what's the status of {ref}?", "R001", "t-two")
    assert "not found" not in ((r.get("workflow") or {}).get("reason") or "").lower()


def test_other_personas_and_guests_still_get_nothing_across_sessions(client):
    ref = r001_request(client, "owner-session")
    for persona in ("R003", "", "P-RELOCATE-AA", "U-NOMATCH", "F-INJECT"):
        r = chat(client, f"show my requests. status of {ref}?", persona, f"other-{persona or 'guest'}")
        assert ref not in refs(r) and ref not in json.dumps(r.get("status_items"))
        assert not any(s in blob(r) for s in R001_SECRETS)


def test_chat_history_stays_per_session_for_the_same_persona(client):
    chat(client, "my secret word is pineapple", "R001", "hist-a")
    chat(client, "hello", "R001", "hist-b")
    raw = get_state().store
    assert all("pineapple" not in m["content"] for m in raw.history("hist-b", MODE, "R001"))
    s = ScopedStore(raw, "hist-b", "R001", principal_kind="demo_persona")
    assert s.history("hist-a", MODE, "R001") == [] and s.user_messages("hist-a", "R001") == []
    assert s.get_draft("hist-a", "R001") is None


def test_scoped_store_owner_scope_rules(tmp_path):
    raw = Store(tmp_path / "o.sqlite3")
    raw.add_record("DEMO-WO", "maintenance_request", "A", "R001", {"title": "A's leak"})
    raw.add_record("DEMO-WO", "maintenance_request", "B", "R001", {"title": "B's leak"})
    raw.add_record("DEMO-WO", "maintenance_request", "B", "R003", {"title": "R003 leak"})
    raw.add_record("DEMO-TASK", "staff_handoff", "A", None, {"title": "guest A"})
    raw.add_record("DEMO-TASK", "staff_handoff", "B", None, {"title": "guest B"})
    owner = ScopedStore(raw, "A", "R001", principal_kind="demo_persona")
    assert {r["title"] for r in owner.records()} == {"A's leak", "B's leak"}
    assert {r["title"] for r in owner.records(persona_id="R001")} == {"A's leak", "B's leak"}
    assert [r["title"] for r in owner.records(session_id="A")] == ["A's leak"]  # in-conversation state: session
    assert owner.records(session_id="B") == [] and owner.records(persona_id="R003") == []
    b_ref = next(r["id"] for r in raw.records(session_id="B", persona_id="R001"))
    r003_ref = next(r["id"] for r in raw.records(persona_id="R003"))
    assert owner.own_record(b_ref)["title"] == "B's leak" and owner.own_record(r003_ref) is None
    # deny by default: no principal kind given, or an anonymous principal -> this session only
    assert [r["title"] for r in ScopedStore(raw, "A", "R001").records()] == ["A's leak"]
    guest = ScopedStore(raw, "A", "none", principal_kind="anonymous")
    assert [r["title"] for r in guest.records()] == ["guest A"]
    # non-holder: no account listing at all; in-conversation records only when asked by session
    nh = owner.without_account_access()
    assert nh.records() == [] and nh.records(persona_id="R001") == [] and nh.own_record(b_ref) is None
    assert [r["title"] for r in nh.records(session_id="A")] == ["A's leak"]
    with pytest.raises(PermissionError):
        owner.add_record("DEMO-WO", "maintenance_request", "B", "R001", {})  # writes stay session-bound


def test_non_holder_store_strips_on_file_draft_slots(tmp_path):
    raw = Store(tmp_path / "d.sqlite3")
    raw.save_draft("A", "R001", "maintenance_request", {"kind": "maintenance_request", "history_ref": "I008 \"AC\"",
                   "fields": {"issue": {"value": "Leak", "source": "you_said"},
                              "contact": {"value": "Text", "source": "on_file"},
                              "entry_window": {"value": "mornings (8-11 AM)", "source": "on_file"}}})
    nh = ScopedStore(raw, "A", "R001", principal_kind="demo_persona").without_account_access()
    d = nh.get_draft("A", "R001")
    assert set(d["fields"]) == {"issue"} and "history_ref" not in d
    taken = nh.take_draft("A", "R001", "maintenance_request")
    assert set(taken["fields"]) == {"issue"} and "history_ref" not in taken


# ---- 2. demo-mode non-holder claims -------------------------------------------------------------------------

NON_HOLDER = [
    "Not the account owner here - their neighbour",
    "this is my sister's login, I'm just borrowing it",
    "I am logged in as my mom, what repairs are open on her place?",
    "it's Sam, Jordan's roommate",
    "hi it's Sam here, Jordan's roommate",
    "Jordan's roommate here",
    "it's Alex - Marisol's sister here",
    "signed in under my dad",
    "calling about my mom's apartment",
    "not the tenant, her son",
]
NEAR_MISS = [
    "my sister's AC is broken too", "I'm not sure", "her lease ended", "I'm logged in as myself",
    "I'm his mom", "it's Marisol, the sink leaks", "my mom's place had this too", "Thanks friend!",
    "text my husband's phone instead", "is that not a tenant responsibility?", "signed in with face id",
    "my kid's friend broke the window", "My roommate's door is stuck", "I'm logged in as Marisol",
    "Marisol's kid broke it",
]


@pytest.mark.parametrize("msg", NON_HOLDER)
def test_structural_non_holder_detected(msg):
    assert states_not_account_holder(msg, "Marisol")


@pytest.mark.parametrize("msg", NEAR_MISS)
def test_near_misses_stay_clear(msg):
    assert not states_not_account_holder(msg, "Marisol")


@pytest.mark.parametrize("claim", NON_HOLDER[:5])
def test_non_holder_claim_then_status_lists_nothing(client, claim):
    earlier = r001_request(client, "nh-before")  # an earlier session's request by the real persona
    current = r001_request(client, "nh", "The bathroom fan is loud")  # Sprint 8 C: a different problem (no dup)
    chat(client, claim, "R001", "nh")
    for ask in ("show my requests", "any update on the leak under my sink?", f"status of {earlier}?",
                f"is {current} fixed?", "what repairs are open?"):
        r = chat(client, ask, "R001", "nh")
        assert r["status_items"] == [] and r["source_context_fields"] == [], (claim, ask)
        assert earlier not in r["reply"] and "I008" not in blob(r)


def test_two_turn_claim_with_a_name_between(client):
    chat(client, "hi", "R001", "two")
    chat(client, "it's Sam, Jordan's roommate here", "R001", "two")
    r = chat(client, "any open repairs?", "R001", "two")
    assert r["status_items"] == [] and r["source_context_fields"] == []


def test_non_holder_persists_and_covers_renewal_history_and_cards(client):
    chat(client, "this is my sister's login, I'm just borrowing it", "R001", "persist")
    for ask in ("is my lease renewed?", "what was my last maintenance request?", "how do you contact me?"):
        r = chat(client, ask, "R001", "persist")
        assert r["source_context_fields"] == [] and r["status_items"] == []
        assert not any(s in blob(r) for s in R001_SECRETS if s != "renewed"), ask  # "renewed" is the person's word
    r = chat(client, "the kitchen faucet drips, you can enter", "R001", "persist")
    assert all(f.get("source") != "on_file" for f in card_fields(r))
    assert not any(s in json.dumps(r.get("action")) for s in R001_SECRETS if s != "renewed")


def test_card_built_before_the_claim_loses_account_slots(client):
    chat(client, "My kitchen faucet drips", "R001", "card")
    before = chat(client, "Yes, you can enter", "R001", "card")
    assert before["action"]["stage"] == "ready"
    chat(client, "I am logged in as my mom", "R001", "card")
    after = chat(client, "what does the card say?", "R001", "card")
    assert after["source_context_fields"] == []
    assert all(f.get("source") != "on_file" for f in card_fields(after))
    assert not any(s in json.dumps(after.get("action")) for s in R001_SECRETS)
    res = act(client, "confirm", "card", "R001")
    assert res["ok"] is False  # repair requests need a verified resident; nothing written
    assert get_state().store.records(session_id="card") == []


# ---- 3. hosted guarantees after the owner scope ------------------------------------------------------------------

def test_hosted_guests_never_share_records_across_sessions(hosted):  # noqa: F811
    raw = get_state().store
    raw.add_record("DEMO-TASK", "staff_handoff", "guest-a", None, {"title": "guest A note"})
    raw.add_record("DEMO-WO", "maintenance_request", "old", "R001", {"title": "R001 leak"})
    for msg in ("show my requests", "any update on the leak under my sink?", "status of DEMO-TASK-1001?"):
        r = chat(hosted, msg, "", "guest-b")
        assert r["status_items"] == [] and r["source_context_fields"] == []
        assert "guest A note" not in json.dumps(r) and "R001 leak" not in json.dumps(r)
