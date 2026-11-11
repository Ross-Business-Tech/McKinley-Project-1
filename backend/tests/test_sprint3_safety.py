"""Sprint 3: layered safety pipeline (rules -> semantic classifier -> policy -> approved text -> escalation).

Development examples only, written by the implementer. The independent holdout suites live outside the repo and were
never used to write these tests.
"""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.db import Store
from app.emergency import scan
from app.llm import LLMError, LLMGateway
from app.llm.base import LLMResult, ModelOutput
from app.main import app
from app.risk.classifier import SemanticRiskClassifier, parse
from app.risk.detect import detect
from app.risk.models import DeterministicRisk, SemanticResult, SemanticRisk
from app.risk.policy import decide
from app.risk.responses import select
from app.state import build_state, set_state


def sem(level="none", cats=(), immediate=False, conf=0.9, human=False, framing="none"):
    return SemanticResult(status="ok", risk=SemanticRisk(risk_level=level, risk_categories=list(cats),
                                                         immediate_danger=immediate, confidence=conf,
                                                         needs_human=human, framing=framing))


FAILED = SemanticResult(status="timeout", detail="MODEL_TIMEOUT")


# ---------------- policy (layer 3) ----------------

def test_semantic_can_never_suppress_a_deterministic_alert():
    d = decide(DeterministicRisk(kind="gas", framing="report"), sem("none", conf=0.99))
    assert d.response == "full_alert" and d.kind == "gas" and d.rule == "R1"
    assert "never suppressed" in (d.conflict or "")


def test_semantic_can_raise_an_alert_the_rules_missed():
    d = decide(DeterministicRisk(), sem("emergency", ["self_harm"], immediate=True))
    assert d.response == "full_alert" and d.kind == "self_harm" and d.rule == "R2" and d.sources == ["semantic"]
    d = decide(DeterministicRisk(), sem("urgent", ["medical"], immediate=True))
    assert d.response == "full_alert" and d.kind == "medical"


def test_semantic_urgent_without_immediate_danger_gets_category_line_and_staff_check():
    d = decide(DeterministicRisk(), sem("urgent", ["self_harm"]))
    assert d.response == "care_line" and d.care == "distress" and d.needs_human and d.rule == "R4"
    d = decide(DeterministicRisk(), sem("uncertain", ["medical"]))
    assert d.care == "unwell"


def test_classifier_failure_never_defaults_to_safe():
    # The deterministic floor still applies and the decision is marked degraded for staff.
    assert decide(DeterministicRisk(kind="fire_smoke", framing="report"), FAILED).response == "full_alert"
    d = decide(DeterministicRisk(care="danger"), FAILED)
    assert d.response == "care_line" and d.degraded
    assert decide(DeterministicRisk(care="distress"), FAILED).care == "distress"
    assert decide(DeterministicRisk(), FAILED).degraded


def test_only_the_broad_danger_line_can_be_suppressed_and_only_confidently():
    # Sprint 7 (stricter, moved): the first case used to expect "none" (the semantic layer removed the broad 911 line
    # at confidence >= 0.8). The semantic layer can no longer remove deterministic guidance, so the line stays.
    assert decide(DeterministicRisk(care="danger"), sem("none", conf=0.95)).response == "care_line"
    assert decide(DeterministicRisk(care="danger"), sem("none", conf=0.5)).response == "care_line"
    assert decide(DeterministicRisk(care="distress"), sem("none", conf=0.99)).care == "distress"
    assert decide(DeterministicRisk(care="unwell"), sem("none", conf=0.99)).care == "unwell"


def test_hypothetical_hazard_is_safety_info_not_alarm():
    d = decide(DeterministicRisk(mentioned_kind="gas", framing="hypothetical"), FAILED)
    assert d.response == "safety_info" and d.kind == "gas"
    t = select(d, "en")
    assert t.safety_notice is None and t.care_kind == "info" and "Leave now" in (t.care_note or "")


def test_person_danger_earlier_keeps_a_calm_line():
    d = decide(DeterministicRisk(), sem("none", conf=0.99), prior_hazards=["self_harm"])
    assert d.response == "care_line" and d.care == "distress" and d.rule == "R9"
    assert decide(DeterministicRisk(), FAILED, prior_hazards=["gas"]).response == "none"  # property: no


def test_deliberate_overdose_adds_988_to_the_poison_alert():
    det = detect("I took a bunch of my sleeping pills on purpose")
    assert det.kind == "poison" and det.self_harm_intent
    t = select(decide(det, FAILED), "en")
    assert "988" in (t.safety_notice or "") and "911" in (t.safety_notice or "")


# ---------------- layer 1 framing / negation / idioms ----------------

@pytest.mark.parametrize("msg", [
    "There's no smoke, the toast just got a bit dark", "it's a slow drip, not flooding",
    "i never reported a gas leak", "nothing is sparking, the switch is just loose",
    "this commute is killing me", "the rooftop view is fire", "I'm dying to see the two-bedroom",
    "send my note to the office", "can you shoot me an email with the lease",
])
def test_negated_and_figurative_wording_is_not_an_emergency(msg):
    assert scan(msg)[1] != "report", msg


@pytest.mark.parametrize("msg,framing", [
    ("what should I do if I ever smell gas?", "hypothetical"),
    ("in case of a power outage with sparks, who do I call?", "hypothetical"),
    ("we had a small kitchen fire last year, is the extinguisher replaced?", "past"),
])
def test_hypothetical_and_past_hazards_are_framed(msg, framing):
    kind, f = scan(msg)
    assert kind and f == framing


def test_framing_never_downgrades_self_harm_or_threats():
    assert scan("what if I just ended my life")[1] == "report"
    assert scan("last year my ex threatened me and now he is back outside")[1] == "report"


@pytest.mark.parametrize("msg,kind", [
    ("Mi expareja me amenazó con un cuchillo", "personal_safety"),
    ("se reventó la tubería y hay agua por todas partes", "flood"),
    ("mi papá no puede respirar", "medical"),
    ("my grandson took a handful of my blood pressure pills", "poison"),
    ("she's lying on the floor and hasn't moved in a while", "medical"),
    ("I'm such a burden, I already wrote letters for my kids", "self_harm"),
])
def test_meaning_level_concepts(msg, kind):
    assert scan(msg) == (kind, "report"), msg


def test_danger_that_appears_across_turns_is_caught():
    det = detect("now he says his head hurts and he feels dizzy", ["my son sat in the garage with the car running"])
    assert det.kind == "co" and det.via_window
    det = detect("it's happening now", ["what do I do if the outlet starts sparking?"])
    assert det.kind == "electrical" and det.via_window


def test_negated_self_harm_still_gets_988_line():
    det = detect("I'm not suicidal or anything, I'm just so tired")
    assert det.kind is None and det.care == "distress"


# ---------------- layer 2 classifier contract ----------------

def test_classifier_output_contract_is_strict():
    ok = parse('{"risk_level":"urgent","risk_categories":["self_harm","made_up"],"immediate_danger":false,'
               '"needs_human":true,"confidence":0.7,"framing":"report","reason":"x"}')
    assert ok.risk_categories == ["self_harm"]
    with pytest.raises(ValidationError):
        parse('{"risk_level":"catastrophic","risk_categories":[]}')
    with pytest.raises(ValueError):
        parse("I think it's fine")


class FakeProvider:
    name = "openrouter"

    def __init__(self, content=None, error=None, model="test/risk-model"):
        self.content, self.error, self.model, self.calls = content, error, model, []

    def complete(self, system, messages, target, cfg, schema=None, schema_name="mckinley_reply"):
        self.calls.append(schema_name)
        if self.error:
            raise self.error
        return LLMResult(output=ModelOutput(reply=""), provider="openrouter", requested_model=target.model,
                         model=self.model, stop_reason="stop", input_tokens=10, output_tokens=10, latency_ms=5,
                         parse_mode="json", extra={"content": self.content})


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1",
                    openrouter_api_key="test-not-a-real-key", db_path=tmp_path / "s3.sqlite3",
                    safety_classifier_target="openrouter:test/risk-model", **kw)


def test_classifier_statuses(tmp_path):
    s = _settings(tmp_path)
    content = json.dumps({"risk_level": "none", "risk_categories": [], "immediate_danger": False,
                          "needs_human": False, "confidence": 0.9, "framing": "none", "reason": ""})
    c = SemanticRiskClassifier(s, LLMGateway(s, {"openrouter": FakeProvider(content)}))
    assert c.classify("hi").status == "ok"
    c = SemanticRiskClassifier(s, LLMGateway(s, {"openrouter": FakeProvider("not json")}))
    assert c.classify("hi").status == "bad_output"
    err = LLMError("MODEL_TIMEOUT", "slow", retryable=True)
    c = SemanticRiskClassifier(s, LLMGateway(s, {"openrouter": FakeProvider(error=err)}))
    assert c.classify("hi").status == "timeout"
    c = SemanticRiskClassifier(s, LLMGateway(s, {"openrouter": FakeProvider(content, model="other/model")}))
    assert c.classify("hi").status == "error"  # MODEL_SWITCHED is never accepted as a classification
    s2 = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", openrouter_api_key=None,
                  db_path=tmp_path / "x.sqlite3", safety_classifier_target="openrouter:test/risk-model")
    assert SemanticRiskClassifier(s2, LLMGateway(s2)).classify("hi").status == "unavailable"
    s3 = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1", db_path=tmp_path / "y.db")
    assert SemanticRiskClassifier(s3, LLMGateway(s3)).classify("hi").status == "mock"


@pytest.fixture
def semantic_client(tmp_path, workbook):
    def make(content=None, error=None):
        s = _settings(tmp_path)
        state = build_state(settings=s, gateway=LLMGateway(s, {"openrouter": FakeProvider(content, error)}),
                            workbook=workbook, store=Store(s.db_path))
        set_state(state)
        return TestClient(app)
    yield make
    set_state(None)  # type: ignore[arg-type]


def _chat(c, msg, session, persona="R001"):
    return c.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                     "session_id": session}).json()


def test_end_to_end_semantic_alert_creates_urgent_note_and_staff_route(semantic_client):
    c = semantic_client(json.dumps({"risk_level": "emergency", "risk_categories": ["self_harm"],
                                    "immediate_danger": True, "needs_human": True, "confidence": 0.8,
                                    "framing": "report", "reason": "possible plan"}))
    r = _chat(c, "I've sorted out who gets my cat. thanks for everything", "sem1")
    assert r["safety_notice"] and "988" in r["safety_notice"] and r["emergency_kind"] == "self_harm"
    assert r["risk"]["decision"]["rule"] == "R2" and r["handoff"]["team"] == "management"
    assert r["records_created"] and r["records_created"][0]["status"] == "urgent_queued"


def test_end_to_end_semantic_timeout_keeps_rules_and_is_visible(semantic_client):
    c = semantic_client(error=LLMError("MODEL_TIMEOUT", "slow", retryable=True))
    r = _chat(c, "I smell gas in the hallway", "sem2")
    assert r["safety_notice"] and r["risk"]["semantic"]["status"] == "timeout"
    assert any(s["step"] == "2b_safety" and "semantic=timeout" in s["detail"] for s in r["pipeline"])


# ---------------- engine behaviour with the mock (no classifier) ----------------

def test_hypothetical_question_gets_info_not_an_urgent_note(client):
    r = _chat(client, "what should I do if I ever smell gas?", "hyp1")
    assert r["safety_notice"] is None and r["care_kind"] == "info" and "Leave now" in r["care_note"]
    assert not r["records_created"] and r["action"] is None
    assert r["risk"]["semantic"]["status"] == "mock"


def test_safety_line_persists_after_person_says_they_are_fine(client):
    r = _chat(client, "I want to kill myself", "persist1")
    assert r["safety_notice"] and "988" in r["safety_notice"]
    r = _chat(client, "I'm fine. stop showing me that hotline stuff", "persist1")
    assert r["care_kind"] == "distress" and "988" in r["care_note"]


def test_person_emergency_handoff_team_matches_the_saved_note(client):
    r = _chat(client, "my dad collapsed and he is not breathing", "team1")
    assert r["handoff"]["team"] == "management" and r["records_created"][0]["team"] == "management"


def test_distress_care_line_recommends_a_human_check(client):
    r = _chat(client, "honestly what's the point of anything anymore", "dist1")
    assert r["care_kind"] == "distress" and r["recommended_handoff"] and r["handoff"]["category"] == "safety_emergency"
    assert r["handoff"]["status"] == "recommended_not_sent"


def test_new_danger_words_after_a_person_danger_alert_alert_again():
    d = decide(DeterministicRisk(care="danger"), FAILED, prior_hazards=["personal_safety"])
    assert d.response == "full_alert" and d.kind == "personal_safety" and d.rule == "R9e"
    d = decide(DeterministicRisk(care="danger"), FAILED, prior_hazards=["self_harm"])
    assert d.response == "care_line" and d.care == "distress"  # self-harm keeps the 988 line instead


def test_generic_emergency_text_never_claims_a_note_in_any_language():
    """Consolidation audit B2: unknown-kind alerts use steps-only text; the note sentence is added only when saved."""
    from app.risk.models import RiskDecision
    from app.templates import t
    for lang in ("en", "es"):
        steps = t("emergency_steps", lang)
        assert "911" in steps and "nota" not in steps.lower() and "note" not in steps.lower()
        txt = select(RiskDecision(response="full_alert", kind="other", rule="R2"), lang).safety_notice or ""
        assert "911" in txt and "nota urgente" not in txt and "urgent note" not in txt
