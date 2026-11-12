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


def test_electrical_follow_up_drops_the_repeated_line_but_keeps_a_differently_conditioned_911():
    out, dropped = drop_repeated_reminders(f"{ELECTRIC_STEPS} {FOLLOW}")
    # "call your community's emergency maintenance line" was said unconditionally: the reminder goes. The steps' 911
    # depends on smoke/sparks/heat, so "If anyone feels unwell or is in danger, call 911" is different guidance: kept.
    assert out == (f"{ELECTRIC_STEPS} Your urgent note DEMO-TASK-1023 is saved, but this assistant hasn't sent anyone. "
                   "If anyone feels unwell or is in danger, call 911.")
    assert dropped == ["If you haven't yet, call your community's emergency maintenance line."]


def test_a_conditional_instruction_never_covers_a_reminder():
    text = "Call 911 if water reaches anything electrical or anyone is in danger. If anyone feels unwell or is in " \
           "danger, call 911."
    assert drop_repeated_reminders(text) == (text, [])


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
    english_steps = "Get outside now and call 911."  # an English step never covers a Spanish reminder's wording
    es_follow = t("emergency_follow", "es", ref="DEMO-TASK-1")
    out2, _ = drop_repeated_reminders(f"{english_steps} {es_follow}")
    assert "línea de emergencias de mantenimiento" in out2


def test_follow_up_through_the_api_says_911_once(client):
    def chat(m):
        r = client.post("/api/chat", json={"message": m, "persona_id": "R005", "mode": "aware", "session_id": "dd"})
        assert r.status_code == 200
        return r.json()
    first = chat("the breaker panel smells like burning plastic and the door is hot")
    second = chat("what should I do right now")
    assert first["safety_notice"] and second["safety_notice"]
    for r in (first, second):
        assert r["reply"].lower().count("emergency maintenance line") <= 1, r["reply"]
        assert r["reply"].lower().count("call 911") <= 2, r["reply"]  # at most once per distinct condition


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


# ---- independent safety review (2026-11-12): every approved notice, both languages; negation; source; layout --------
import re  # noqa: E402

from app.emergency import NO_LINE, NOTICE  # noqa: E402
from app.templates import T  # noqa: E402

_PRESENT = {
    "911": re.compile(r"\b911\b"), "988": re.compile(r"\b988\b"),
    "poison": re.compile(r"poison|toxicolog|envenenamiento|1-?800-?222-?1222", re.I),
    "emergency_line": re.compile(r"emergency\s+maintenance\s+line|emergencias?\s+de\s+mantenimiento", re.I),
    "get_out": re.compile(r"\b(?:leave|get (?:everyone )?out|outside|salga|afuera|evac)\w*", re.I),
}


def _present(text):
    return {k for k, rx in _PRESENT.items() if rx.search(text)}


_STEPS = [(f"{k}:{lang}", v[lang], lang) for k, v in NOTICE.items() for lang in ("en", "es") if v.get(lang)]
_STEPS += [(f"emergency_steps:{lang}", T["emergency_steps"][lang], lang) for lang in ("en", "es")
           if T["emergency_steps"].get(lang)]


@pytest.mark.parametrize("name,steps,lang", _STEPS, ids=[s[0] for s in _STEPS])
@pytest.mark.parametrize("follow", ["emergency_follow", "no_line"])
def test_every_approved_notice_keeps_every_instruction_and_its_text(name, steps, lang, follow):
    tail = (t("emergency_follow", lang, ref="DEMO-TASK-1") if follow == "emergency_follow"
            else (NO_LINE.get(lang) or NO_LINE["en"]).format(ref="DEMO-TASK-1"))
    reply = f"{steps} {tail}"
    out, dropped = drop_repeated_reminders(reply)
    assert out.startswith(steps), name  # the approved notice is shown verbatim, first
    assert _present(out) == _present(reply), (name, dropped)  # no kind of instruction disappears
    for d in dropped:
        assert d in REMINDERS


def test_a_negated_mention_never_counts_as_having_said_it():
    text = f"I can't call 911 for you. {FOLLOW}"
    out, dropped = drop_repeated_reminders(text)
    assert "If anyone feels unwell or is in danger, call 911." in out and not dropped


def test_line_breaks_are_kept():
    text = f"{ELECTRIC_STEPS}\n\n{FOLLOW}"
    out, dropped = drop_repeated_reminders(text)
    assert dropped and out.startswith(f"{ELECTRIC_STEPS}\n\n")


def test_model_written_emergency_replies_are_not_deduplicated(client, monkeypatch):
    from app.llm.base import LLMResult, ModelOutput
    from app.state import get_state

    said = (f"{ELECTRIC_STEPS} If you haven't yet, call your community's emergency maintenance line.")

    def fake(system, messages, target):
        return LLMResult(output=ModelOutput(reply=said), provider="mock", requested_model=target.model,
                         model=target.model, parse_mode="json", is_mock=True, stop_reason="end", input_tokens=1,
                         output_tokens=1, latency_ms=1)
    monkeypatch.setattr(get_state().deps.llm, "complete", fake)
    r = client.post("/api/chat", json={"message": "the outlet by my sink sparked and smells burnt", "persona_id":
                                       "R005", "mode": "aware", "session_id": "dd-model"}).json()
    if r["reply_source"] == "model":  # emergency replies are normally fixed templates; if the model wrote it, untouched
        assert r["reply"] == said
