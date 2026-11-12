"""Emergency follow-ups say each instruction once (app/safety_dedupe.py); approved steps are never touched."""

import pytest

from app.safety_dedupe import REMINDERS, drop_repeated_reminders
from app.templates import t

CO_STEPS = ("Get everyone, including pets, outside into fresh air now and call 911. Don't go back in until responders "
            "say it's safe. Headache, dizziness or nausea can be signs of carbon monoxide.")
ELECTRIC_STEPS = ("Stay away and don't touch it, especially if there's water nearby. If you see smoke, sparks or heat, "
                  "leave and call 911. Then call your community's emergency maintenance line.")
FOLLOW = t("emergency_follow", "en", ref="DEMO-TASK-1023")


def test_reminders_come_from_the_approved_template():
    assert len(REMINDERS) == 4 and all("911" in r or "mantenimiento" in r or "maintenance" in r for r in REMINDERS)


def test_co_follow_up_keeps_steps_first_and_the_maintenance_reminder():
    out, dropped = drop_repeated_reminders(f"{CO_STEPS} {FOLLOW}")
    assert out.startswith("Get everyone, including pets, outside")  # still leads with getting outside
    assert CO_STEPS in out  # approved steps verbatim
    assert out.count("911") == 1 and "emergency maintenance line" in out  # not in the CO steps: kept
    assert dropped == ["If anyone feels unwell or is in danger, call 911."]


def test_electrical_follow_up_drops_both_repeats_and_keeps_steps():
    out, dropped = drop_repeated_reminders(f"{ELECTRIC_STEPS} {FOLLOW}")
    assert out == f"{ELECTRIC_STEPS} Your urgent note DEMO-TASK-1023 is saved, but this assistant hasn't sent anyone."
    assert len(dropped) == 2 and out.count("911") == 1


def test_follow_up_without_steps_keeps_every_reminder():
    out, dropped = drop_repeated_reminders(FOLLOW)
    assert out == FOLLOW and not dropped


@pytest.mark.parametrize("text", [CO_STEPS, ELECTRIC_STEPS, "Call 911 now. Call 911 if it gets worse."])
def test_non_template_sentences_are_never_removed(text):
    assert drop_repeated_reminders(text) == (text, [])


def test_spanish_follow_up():
    steps = "Salga ahora y llame al 911. Luego llame a la línea de emergencias de mantenimiento."
    out, dropped = drop_repeated_reminders(f"{steps} {t('emergency_follow', 'es', ref='DEMO-TASK-1')}")
    assert out.count("911") == 1 and len(dropped) == 2 and out.startswith(steps)


def test_follow_up_through_the_api_says_911_once(client):
    def chat(m):
        r = client.post("/api/chat", json={"message": m, "persona_id": "R005", "mode": "aware", "session_id": "dd"})
        assert r.status_code == 200
        return r.json()
    first = chat("the breaker panel smells like burning plastic and the door is hot")
    second = chat("what should I do right now")
    assert first["safety_notice"] and second["safety_notice"]
    for r in (first, second):
        assert r["reply"].lower().count("call 911") <= 1, r["reply"]
        assert r["reply"].lower().count("emergency maintenance line") <= 1, r["reply"]


def test_red_alert_notice_state_and_contacts_are_untouched(client, monkeypatch):
    """Only the reply text is deduplicated: the approved notice, safety state and contacts are identical with the
    dedupe switched off."""
    from app import safety_dedupe

    def run(session):
        out = []
        for m in ("the breaker panel smells like burning plastic and the door is hot", "what should I do right now"):
            r = client.post("/api/chat", json={"message": m, "persona_id": "R005", "mode": "aware",
                                               "session_id": session}).json()
            out.append((r["safety_notice"], r["safety_state"], r["safety_contacts"], r["safety_heading"]))
        return out

    with_dedupe = run("dd-on")
    monkeypatch.setattr(safety_dedupe, "drop_repeated_reminders", lambda reply: (reply, []))
    without = run("dd-off")
    assert with_dedupe == without and all(n for n, *_ in with_dedupe)
