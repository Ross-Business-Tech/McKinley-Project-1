"""Sprint 6 safety: concept-slot detection, incident-specific notices, the narrowed R7 exception, the conservative
middle tier and the semantic classifier's contract. Development examples written by the Sprint 6 safety engineer from
category descriptions (not holdout data, not copied from earlier sprint reports). Every rule has positive AND negative
cases."""

import json

import pytest

from app.config import Settings
from app.emergency import possible_risk, scan
from app.llm import LLMError, LLMGateway
from app.llm.base import LLMResult, ModelOutput
from app.risk.category import refine
from app.risk.classifier import MAX_TIMEOUT_SECONDS, SemanticRiskClassifier, parse
from app.risk.detect import detect
from app.risk.models import DeterministicRisk, SemanticResult, SemanticRisk
from app.risk.pipeline import assess
from app.risk.policy import decide
from app.risk.responses import select


def alert(msg):
    d = assess(msg, [], None).decision
    return d.kind if d.response == "full_alert" else None


def sem(level="none", cats=(), immediate=False, conf=0.95):
    return SemanticResult(status="ok", risk=SemanticRisk(risk_level=level, risk_categories=list(cats),
                                                         immediate_danger=immediate, confidence=conf))


# ---- 1. concept slots: positives (kind = notice kind after selection) --------------------------------------------
CONCEPT_POS = [
    ("medical", "my uncle tumbled down the porch steps and isn't responding"),
    ("medical", "the lifeguard is gone and a girl went under in the deep end"),
    ("medical", "a toddler is floating face down in the hot tub"),
    ("medical", "my baby is shut in the car in the sun and I can't get the door open"),
    ("medical", "the dog was left locked in a van with the windows up and it's 95 degrees"),
    ("medical", "the wardrobe toppled onto my son and he's stuck under it"),
    ("medical", "mi hija se quedó encerrada en el coche y hace mucho calor"),
    ("poison", "my uncle swallowed a handful of his blood pressure pills"),
    ("poison", "she took the whole bottle of tylenol an hour ago"),
    ("self_harm", "I've been stockpiling my meds so I can sleep forever"),
    ("self_harm", "by the time anyone reads this I'll be gone"),
    ("personal_safety", "somebody just smashed the back door glass and I hear footsteps downstairs"),
    ("personal_safety", "my husband is beating me right now"),
    ("personal_safety", "mi ex me está golpeando"),
    ("structural", "bits of concrete are dropping from the parking deck overhang"),
    ("structural", "the balcony is tilting away from the wall"),
    ("structural", "the garage ceiling came down on my car"),
    ("electrical", "a utility line snapped and is lying across the driveway"),
    ("flood", "there are two inches of water in the hallway and it keeps rising"),
    ("fire_smoke", "fiire in unit 4, everyone get out"),
    ("fire_smoke", "the curtains caught from the heater and it's spreading"),
    ("trapped", "the lift jammed between floors and we're in it"),
]
# Same words, no active danger: never a full alert.
CONCEPT_NEG = [
    "she fell asleep on the couch watching tv",
    "they're not answering my calls about the lease",
    "the kids are in the pool all day, what are the pool hours?",
    "I took a bunch of photos of the cabinet for the inspection",
    "I took all my vitamins",
    "I'm saving my receipts for the deposit refund",
    "the deck needs new paint, it's cracking a little",
    "water is rising in price lol",
    "my partner is hitting the gym later",
    "my roommate keeps hitting snooze",
    "my mom slipped on the ice last winter, now she's fine",
    "the lift is slow but it works",
    "I wrote a note to my family about the move",
    "this is the last time I'll ask about parking",
    "the cable guy left the wire on the floor",
    "what if a child went under in the pool? is there a lifeguard?",
]


@pytest.mark.parametrize("kind,msg", CONCEPT_POS)
def test_concept_slots_alert_with_the_right_notice(kind, msg):
    assert alert(msg) == kind


@pytest.mark.parametrize("msg", CONCEPT_NEG)
def test_concept_look_alikes_do_not_alert(msg):
    assert alert(msg) is None


def test_hypothetical_concept_is_safety_info_not_an_alert():
    d = assess("what should I do if a kid ever goes under in the pool?", [], None).decision
    assert d.response == "safety_info"


# ---- 2. look-alike fixes in emergency.py (positive + negative) -----------------------------------------------------
@pytest.mark.parametrize("msg", ["can I get a carbon monoxide detector installed in the bedroom?",
                                 "I need a new smoke alarm, mine expired", "what are the signs of carbon monoxide?",
                                 "this rent increase almost gave me a heart attack",
                                 "my car got broken into last month, any update?"])
def test_lookalike_requests_are_not_alerts(msg):
    assert alert(msg) is None


@pytest.mark.parametrize("kind,msg", [("co", "my new CO detector is going off and my head hurts"),
                                      ("co", "the carbon monoxide alarm I installed is beeping nonstop"),
                                      ("medical", "I think my dad is having a heart attack"),
                                      ("personal_safety", "someone broke into my apartment and is still inside")])
def test_the_real_thing_still_alerts(kind, msg):
    assert alert(msg) == kind


# ---- 3. incident-specific notice selection (layer 4a) ---------------------------------------------------------------
@pytest.mark.parametrize("detected,msg,expected", [
    ("trapped", "my baby is locked in the car and it's really hot out", "medical"),
    ("trapped", "my toddler locked himself in the bathroom and won't answer", "medical"),
    ("trapped", "I'm stuck in the elevator between floors", "trapped"),
    ("trapped", "estoy atrapado en el elevador", "trapped"),
    ("personal_safety", "my mom tripped and is on the floor screaming that her hip hurts", "medical"),
    ("personal_safety", "he hit me and I fell, my arm hurts", "personal_safety"),
    ("fire_smoke", "hay humo saliendo del enchufe", "electrical"),
    ("fire_smoke", "the outlet is on fire", "fire_smoke"),
    ("medical", "we're running a generator inside and my wife feels faint and dizzy", "co"),
    ("medical", "my dad fell next to the heater and is bleeding", "medical"),
])
def test_refine_picks_the_existing_notice_that_fits(detected, msg, expected):
    assert refine(detected, msg)[0] == expected


def test_hot_car_alert_uses_the_medical_notice_never_the_elevator_text():
    d = assess("my baby is locked in the car and it's really hot out", [], None).decision
    assert (d.kind, d.detected_kind) == ("medical", "trapped") and d.notice_reason
    text = select(d, "en").safety_notice
    assert "elevator" not in text.lower() and "911" in text
    es = select(assess("mi hijo se quedó encerrado en el carro y hace mucho calor", [], None).decision, "es")
    assert "elevador" not in es.safety_notice.lower() and "911" in es.safety_notice


def test_semantic_trapped_alert_is_refined_too():
    class C:
        def classify(self, m, r):
            return sem("emergency", ["trapped"], immediate=True)
    d = assess("my little girl is in the car and I can't get her out, it's so hot", [], C()).decision  # type: ignore
    assert d.response == "full_alert" and d.kind == "medical"


def test_every_category_maps_to_an_approved_notice():
    from app.emergency import NOTICE
    from app.risk.models import RISK_CATEGORIES
    for cat in RISK_CATEGORIES:
        for lang in ("en", "es"):
            assert NOTICE[cat][lang]
        kind, _ = refine(cat, "")
        assert kind in NOTICE


# ---- 4. R7: the semantic layer can no longer remove a person-in-danger line ----------------------------------------
def test_r7_suppression_still_applies_to_broad_vocabulary():
    # Sprint 7 (stricter, moved): this pinned the old "R7-suppressed" exception. The semantic layer can no longer
    # remove deterministic guidance, so even broad vocabulary keeps the 911 line; the conflict is recorded instead.
    d = decide(DeterministicRisk(care="danger"), sem("none", conf=0.95), [])
    assert d.rule == "R7" and d.response == "care_line" and d.care == "danger" and d.conflict


def test_r7_suppression_blocked_for_a_person_in_danger_sign():
    det = detect("my grandma slipped in the kitchen")
    assert det.care == "danger" and det.concern and not det.kind
    d = decide(det, sem("none", conf=0.99), [])
    assert d.rule == "R7" and d.response == "care_line" and d.care == "danger"


def test_r7_concern_flag_is_not_set_by_vocabulary_alone():
    det = detect("the smoke detector cover is cracked")
    assert not det.concern


# ---- 5. conservative middle tier: possible danger without a category -> 911 care line, never silence --------------
@pytest.mark.parametrize("msg", ["my grandma slipped in the kitchen", "my kid got hurt on the playground equipment",
                                 "someone smashed my window and I heard a noise", "I've been saving up my pills",
                                 "my son is near the pond alone"])
def test_uncertain_danger_gets_a_care_line(msg):
    d = assess(msg, [], None).decision
    assert d.response in ("care_line", "full_alert")


@pytest.mark.parametrize("msg", ["my window is broken, can someone fix it?",
                                 "the back door lock broke yesterday",
                                 "my mom slipped on the ice last year but she's fine",
                                 "nobody was hurt, the tile fell"])
def test_repairs_and_reassured_past_events_get_no_concern_line(msg):
    from app.emergency import person_concern
    assert not person_concern(msg)


def test_stockpiled_pills_alone_gets_the_988_line():
    assert possible_risk("I've been saving up my pills") == "distress"
    assert possible_risk("I'm saving my receipts") is None


# ---- 6. semantic classifier contract -------------------------------------------------------------------------------
def _sem_json(**kw):
    base = {"risk_level": "none", "risk_categories": [], "immediate_danger": False, "needs_human": False,
            "confidence": 0.9, "framing": "none", "reason": ""}
    base.update(kw)
    return json.dumps(base)


def test_self_contradictory_output_is_rejected_not_guessed():
    with pytest.raises(ValueError):
        parse(_sem_json(risk_level="none", immediate_danger=True))
    assert parse(_sem_json(risk_level="urgent", immediate_danger=True)).risk_level == "urgent"


class FakeProvider:
    name = "openrouter"

    def __init__(self, content=None, error=None):
        self.content, self.error, self.cfgs = content, error, []

    def complete(self, system, messages, target, cfg, schema=None, schema_name="mckinley_reply"):
        self.cfgs.append(cfg)
        if self.error:
            raise self.error
        return LLMResult(output=ModelOutput(reply=""), provider="openrouter", requested_model=target.model,
                         model=target.model, stop_reason="stop", input_tokens=1, output_tokens=1, latency_ms=3,
                         parse_mode="json", extra={"content": self.content})


def _clf(tmp_path, provider, **kw):
    s = Settings(_env_file=None, llm_provider="mock", llm_model="mock-deterministic-v1",
                 openrouter_api_key="test-not-a-real-key", db_path=tmp_path / "s6.sqlite3",
                 safety_classifier_target="openrouter:test/risk-model", **kw)
    return SemanticRiskClassifier(s, LLMGateway(s, {"openrouter": provider}))


def test_classifier_timeout_is_bounded_and_never_retried(tmp_path):
    p = FakeProvider(_sem_json())
    _clf(tmp_path, p, safety_classifier_timeout_seconds=60).classify("hi")
    assert p.cfgs[0].timeout_seconds == MAX_TIMEOUT_SECONDS and p.cfgs[0].max_retries == 0


def test_classifier_inconsistent_output_is_bad_output_and_degraded(tmp_path):
    r = _clf(tmp_path, FakeProvider(_sem_json(risk_level="none", immediate_danger=True))).classify("hi")
    assert r.status == "bad_output"
    d = decide(detect("I smell gas"), r, [])
    assert d.response == "full_alert" and d.degraded


@pytest.mark.parametrize("err", ["MODEL_TIMEOUT", "MODEL_RATE_LIMITED", "PROVIDER_ERROR"])
def test_classifier_failure_never_lowers_a_rules_alert(tmp_path, err):
    r = _clf(tmp_path, FakeProvider(error=LLMError(err, "x", retryable=True))).classify("he's not breathing")
    assert r.status != "ok"
    d = decide(detect("my dad collapsed and he's not breathing"), r, [])
    assert d.response == "full_alert" and d.degraded


def test_semantic_none_cannot_remove_a_concept_alert():
    det = detect("a little boy went under in the deep end and hasn't come up")
    assert det.kind == "medical"
    d = decide(det, sem("none", conf=0.99), [])
    assert d.response == "full_alert" and d.rule == "R1" and d.conflict


def test_semantic_layer_may_add_an_alert_the_rules_missed():
    det = detect("he's turned a weird color and I can't get a word out of him")
    d = decide(det, sem("emergency", ["medical"], immediate=True), [])
    assert d.response == "full_alert" and d.rule == "R2"


def test_scan_framing_still_applies_to_concepts():
    assert scan("last year a kid went under in the pool here")[1] == "past"
    assert alert("what if my baby got locked in the car?") is None
