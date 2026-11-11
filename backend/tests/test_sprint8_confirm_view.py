"""Sprint 8: a customer's Send confirmation carries the customer view of the saved record (no staff-only review
metadata such as repeat_history / manager_review / review_queue); a staff caller still gets the full record."""

from tests.test_sprint7_auth import TOKEN, act, chat, token_client  # noqa: F401  (fixture re-export)


def _repeat_ac(c, headers=None):
    r = chat(c, "my AC is broken again, it keeps rattling", persona="R001", session="cv1", headers=headers)
    sid = r["session_id"]
    chat(c, "yes you can come in", persona="R001", session=sid, headers=headers)
    return act(c, "confirm", sid, headers=headers)


def test_customer_confirm_hides_staff_record_fields(token_client):  # noqa: F811
    res = _repeat_ac(token_client)
    assert res["ok"], res
    rec = res["record"]
    assert rec.get("repeat_history") is None and rec.get("manager_review") is None and rec.get("review_queue") is None


def test_staff_confirm_keeps_review_fields(token_client):  # noqa: F811
    res = _repeat_ac(token_client, headers={"X-Staff-Token": TOKEN})
    assert res["ok"], res
    assert res["record"].get("manager_review") is True
    assert (res["record"].get("repeat_history") or {}).get("count", 0) >= 1
