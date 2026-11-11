"""Sprint 7 safety: the compositional risk frame (app/risk/frame.py), the conservative combination with the phrase
rules (app/risk/detect.py), the R7 policy change (the semantic layer never removes guidance), the classifier v2
contract, notice categories and incident follow-ups. Development wording only (no holdout text)."""

import time

import pytest

from app.emergency import emergency_kind
from app.risk.classifier import SemanticRiskClassifier, parse
from app.risk.detect import detect
from app.risk.frame import analyse, normalize
from app.risk.incident import Incident, classify
from app.risk.models import DeterministicRisk, SemanticResult, SemanticRisk
from app.risk.pipeline import assess
from app.risk.policy import decide


def d(msg, recent=None):
    return assess(msg, recent or [], None).decision


def full(msg, recent=None):
    return d(msg, recent).response == "full_alert"


# ---- normalisation ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [
    ("She's NOT breathng!!!", "shes not breathing!!!"), ("está tirada en el piso", "esta tirada en el piso"),
    ("HE CANT BREATH", "he cant breathe"), ("helppp my mom", "help my mom"), ("lips r blue", "lips are blue"),
    ("unconsious", "unconscious"), ("mi bebé", "mi bebe"), ("isn’t", "isnt"),
])
def test_normalize(raw, want):
    assert normalize(raw) == want


# ---- 1. pronoun-only and Spanish subjectless body states ---------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "she's lying on the kitchen floor and won't respond to me",
    "he went down in the hallway and isn't moving",
    "they aren't breathing normally, little gasps",
    "she won't wake up, i've been shaking her",
    "he's not responding to anything i say",
    "she keeps passing out and her face is grey",
    "no me contesta y está tirado en el baño",
    "no respira bien y tiene los labios morados",
    "está en el suelo y no se mueve, no reacciona",
    "se desmayó y no despierta",
])
def test_pronoun_and_subjectless_states_alert(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == "medical", msg


@pytest.mark.parametrize("msg", [
    "she's not answering my texts about the rent",
    "my roommate isn't responding to me about the utility bill",
    "no me responde los mensajes sobre el contrato",
    "he's lying on the couch watching the game, can maintenance come at 3?",
    "my cat is lying on the floor in the sun",
    "the office still hasn't responded to me",
])
def test_social_or_benign_states_do_not_alert(msg):
    assert not full(msg), msg


# ---- 2. symptom-only medical --------------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "my uncle's lips are turning purple and he's wheezing",
    "her eyes are rolling back and she's twitching all over",
    "my dad's smile is lopsided and his words are slurred",
    "grandma is slumped in her chair and drooling",
    "my son is gurgling and won't open his eyes",
    "the towel on my leg is soaked through and it won't stop bleeding",
    "mi abuela tiene la cara caída de un lado",
    "mi esposo está gris, sudando y se agarra el pecho",
])
def test_symptom_only_reports_alert(msg):
    assert full(msg), msg


# ---- 3. conditional / question framing ----------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "what do i do if my wife can't breathe",
    "if my son isn't waking up should i call someone",
    "is it normal that my baby's lips are blue?",
    "how do i help her, she's not breathing",
    "my daughter swallowed a magnet, is that dangerous?",
    "qué hago si mi mamá no respira",
    "¿es normal que mi hijo esté convulsionando?",
    "mi hija se tragó una pila, ¿qué hago?",
])
def test_live_sign_inside_a_question_alerts(msg):
    assert full(msg), msg


@pytest.mark.parametrize("msg", [
    "what should someone do if a person stops breathing?",
    "what are the signs that someone is having a stroke?",
    "if a kid ever swallows a battery, what should we do?",
    "¿qué hay que hacer si alguien se desmaya?",
    "how would i know if someone has heat stroke?",
])
def test_generic_hypotheticals_do_not_alert(msg):
    assert not full(msg), msg


# ---- 4. child at a height or in water -----------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "my 3 year old is climbing the balcony railing",
    "my son is sitting in the open window on the 4th floor",
    "a little girl is leaning out of a window upstairs",
    "my toddler got out on the balcony and is hanging over the rail",
    "a kid fell into the pool and nobody's watching",
    "my baby is face down in the tub",
    "mi niña se está subiendo a la ventana abierta",
    "un niño se cayó a la alberca y está solo",
])
def test_child_height_or_water_alerts(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind in ("medical", "structural"), msg


@pytest.mark.parametrize("msg", [
    "are the balcony railings tall enough for toddlers?",
    "is the pool fenced and locked at night?",
    "my kids love the pool, what are the hours?",
    "do you have window guards for the kids' bedrooms?",
    "¿la alberca tiene salvavidas?",
])
def test_child_hazard_questions_do_not_alert(msg):
    assert not full(msg), msg


# ---- 5. heat / cold (lead class 2) --------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "the ac has been out for days and my grandpa is confused and stopped sweating",
    "no heat since yesterday and my newborn is cold to the touch and won't feed",
    "it's 100 in here and my mom is dizzy and talking nonsense",
    "my son was playing outside in this heat, now he's vomiting and confused",
    "sin aire acondicionado, mi abuelo está desorientado y muy caliente",
    "no hay calefacción y mi bebé está fría y morada",
    "the heater died and my elderly dad is shivering and confused",
    "no air in here, grandma's skin is hot and dry and she keeps nodding off",
])
def test_exposure_with_body_signs_alerts_medical(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == "medical", msg


@pytest.mark.parametrize("msg", [
    "our heat is out and it's 15 degrees outside, i have a 2 month old",
    "the ac broke and it's 98 degrees, my 85 year old mother lives here",
    "no tenemos calefacción y hace mucho frío, tengo un bebé",
    "no AC during the heat wave and my grandpa uses oxygen",
    "el aire no funciona y mi abuela vive conmigo",
])
def test_exposure_without_symptoms_is_a_calm_line_not_an_alert(msg):
    r = d(msg)
    assert r.response == "care_line" and r.care in ("unwell", "danger"), msg
    assert r.kind is None


# ---- 6. other people's smoking (lead class 1) ---------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "my neighbor smokes on his patio and it drifts into my bedroom",
    "someone keeps smoking weed in the stairwell",
    "the guy below me chain smokes and it comes up through the vents",
    "cigarette smoke comes under my door every night from 3B",
    "el vecino fuma en el balcón y el humo entra a mi casa",
    "huele a marihuana, alguien fuma en el pasillo",
    "people vaping in the laundry room, who do i tell?",
    "my roommate smokes inside even though it's a smoke-free building",
])
def test_neighbour_smoking_is_not_a_fire(msg):
    r = d(msg)
    assert r.response != "full_alert", msg
    assert emergency_kind(msg) is None


@pytest.mark.parametrize("msg", [
    "my neighbor was smoking and now his couch is on fire",
    "someone smoking in the hall dropped a cigarette and there are flames in the trash can",
    "the vecino fuma and now there's black smoke pouring out of his unit",
    "thick smoke is coming out of the vent and the alarm is going off",
])
def test_real_fire_with_a_smoker_still_alerts(msg):
    assert full(msg), msg


# ---- 7. veiled self-harm ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "i gave my cat to my neighbor, i won't need anything after tonight",
    "this is my goodbye. thank you for everything",
    "i've got all my pills counted out on the bed",
    "i'm going up to the roof and i'm not coming down",
    "i just want to go to sleep and never wake up",
    "everyone would be better off without me, i've made my plans",
    "estoy en el puente y ya no aguanto más",
    "nadie me va a extrañar, ya escribí las cartas para mis hijos",
    "voy a tirarme por la ventana",
    "i'm sitting on the edge of the parking garage roof",
])
def test_veiled_self_harm_alerts(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == "self_harm", msg


@pytest.mark.parametrize("msg", [
    "saying goodbye to this apartment next month, how do i return keys?",
    "i'm giving away my plants before the move, anyone want them?",
    "thanks for everything, the repair looks great",
    "i'm done with the application, what's next?",
    "me despido de este departamento el mes que viene",
])
def test_everyday_goodbyes_do_not_alert(msg):
    assert not full(msg), msg


# ---- 8. property hazards composed from source x sign x extent -----------------------------------------------------
@pytest.mark.parametrize("msg,kinds", [
    ("there's a sulfur smell near the water heater", ("gas",)),
    ("the burner was left on with no flame and now everyone has a headache", ("gas", "co")),
    ("we ran the generator in the garage and the kids are throwing up", ("co",)),
    ("el calentador tiene la flama amarilla y a todos nos duele la cabeza", ("co",)),
    ("water is gushing from the wall and it's already ankle deep", ("flood",)),
    ("el agua sale a chorros del techo y no para", ("flood",)),
    ("the balcony floor is pulling away from the building", ("structural",)),
    ("las escaleras se están despegando de la pared", ("structural",)),
    ("a stranger is yanking on my door handle", ("personal_safety",)),
    ("alguien está forzando la cerradura de mi puerta", ("personal_safety",)),
])
def test_property_hazard_frames_alert(msg, kinds):
    r = d(msg)
    assert r.response == "full_alert" and r.kind in kinds, (msg, r.kind)


@pytest.mark.parametrize("msg", [
    "my stove burner won't light but there's no smell",
    "no huele a gas, solo la estufa no prende",
    "the toilet runs all night",
    "there's a hairline crack in the hallway tile",
    "hay una grieta pequeña en la pared, ¿la pueden revisar?",
    "my door handle is loose, can someone tighten it?",
])
def test_property_near_misses_do_not_alert(msg):
    assert not full(msg), msg


# ---- 9. look-alike framings -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "does the unit come with a carbon monoxide detector?",
    "¿tienen detectores de monóxido de carbono?",
    "is the fire drill on thursday? will the alarm be loud?",
    "¿a qué hora es el simulacro de incendio?",
    "has there ever been a fire in this building?",
    "any history of flooding on the ground floor?",
    "there was a grease fire last year, can someone repaint the cabinets?",
    "hace dos años hubo un incendio, ¿ya cambiaron las alarmas?",
    "the news said a gas line exploded in another city",
    "watching a movie where the house burns down",
    "the bathroom fan sparks sometimes, not right now though, it's off",
    "i can't breathe lol that meme",
    "this paperwork is going to give me a stroke",
    "a question about the fire alarm in my unit",
])
def test_look_alikes_get_no_full_alert(msg):
    assert not full(msg), msg
    assert emergency_kind(msg) is None, msg


@pytest.mark.parametrize("msg", [
    "the fire alarm is going off and there's smoke in the hall",
    "our CO detector is screaming and my daughter threw up",
    "is it a drill? there's real smoke coming from 2B",
    "has the fire spread? flames are coming out of the window right now",
])
def test_live_signs_beat_look_alike_framings(msg):
    assert full(msg), msg


# ---- 10. R7: the semantic layer never removes guidance ------------------------------------------------------------
def sem(level="none", cats=(), immediate=False, conf=0.9, **kw):
    return SemanticResult(status="ok", risk=SemanticRisk(risk_level=level, risk_categories=list(cats),
                                                         immediate_danger=immediate, confidence=conf, **kw))


@pytest.mark.parametrize("conf", [0.5, 0.8, 0.95, 1.0])
@pytest.mark.parametrize("det", [DeterministicRisk(care="danger"), DeterministicRisk(care="danger", concern=True),
                                 DeterministicRisk(care="unwell"), DeterministicRisk(care="distress")])
def test_semantic_none_never_removes_a_deterministic_line(det, conf):
    r = decide(det, sem("none", conf=conf), [])
    assert r.response == "care_line" and r.care == det.care


def test_semantic_none_conflict_is_recorded():
    r = decide(DeterministicRisk(care="danger"), sem("none", conf=0.97), [])
    assert r.rule == "R7" and r.conflict and "kept" in r.conflict


def test_semantic_uncertain_without_category_is_never_silence():
    r = decide(DeterministicRisk(), sem("uncertain", conf=0.4), [])
    assert (r.rule, r.response, r.care) == ("R4u", "care_line", "danger")


def test_semantic_uncertain_does_not_replace_safety_info():
    r = decide(DeterministicRisk(mentioned_kind="gas", framing="hypothetical"), sem("uncertain"), [])
    assert r.response == "safety_info"


def test_semantic_can_still_add_an_alert():
    r = decide(DeterministicRisk(), sem("emergency", ["medical"], immediate=True), [])
    assert r.response == "full_alert" and r.rule == "R2"


@pytest.mark.parametrize("status", ["timeout", "error", "bad_output", "unavailable", "rate_limited"])
def test_failed_semantic_is_degraded_not_safe(status):
    r = decide(DeterministicRisk(care="danger"), SemanticResult(status=status), [])
    assert r.response == "care_line" and r.degraded


# ---- 11. classifier v2 contract ------------------------------------------------------------------------------------
def test_v2_fields_parse_and_category_is_merged():
    r = parse('{"risk_level":"emergency","risk_categories":[],"immediate_danger":true,"needs_human":true,'
              '"confidence":0.9,"framing":"report","reason":"x","incident_category":"medical","ongoing":"now",'
              '"subject":"elder"}')
    assert r.incident_category == "medical" and r.risk_categories == ["medical"] and r.subject == "elder"


@pytest.mark.parametrize("cat", ["none", None, "volcano"])
def test_v2_unknown_or_none_category_is_dropped(cat):
    import json
    r = parse(json.dumps({"risk_level": "none", "risk_categories": [], "immediate_danger": False,
                          "needs_human": False, "confidence": 0.9, "framing": "none", "reason": "",
                          "incident_category": cat, "ongoing": "unknown", "subject": "none"}))
    assert r.incident_category is None


@pytest.mark.parametrize("ongoing", ["past", "hypothetical", "negated"])
def test_v2_immediate_danger_that_is_not_ongoing_is_rejected(ongoing):
    with pytest.raises(ValueError):
        parse('{"risk_level":"emergency","risk_categories":["fire_smoke"],"immediate_danger":true,'
              f'"needs_human":true,"confidence":0.9,"framing":"report","reason":"","ongoing":"{ongoing}"}}')


def test_v1_shaped_output_still_parses():
    r = parse('{"risk_level":"urgent","risk_categories":["self_harm"],"immediate_danger":false,"needs_human":true,'
              '"confidence":0.7,"framing":"report","reason":""}')
    assert r.ongoing == "unknown" and r.subject == "unknown"


def test_classifier_hard_deadline_returns_timeout(monkeypatch):
    from app.config import Settings
    from app.llm import LLMGateway, Target
    from app.risk import classifier as clf

    s = Settings(_env_file=None, llm_provider="mock", safety_classifier="auto",
                 safety_classifier_timeout_seconds=0.05)
    gw = LLMGateway(s)
    c = SemanticRiskClassifier(s, gw)
    monkeypatch.setattr(c, "status", lambda: "ready")
    monkeypatch.setattr(c, "target", lambda: Target.parse("openrouter:fake/model"))
    monkeypatch.setattr(gw, "generation_config", lambda t: type("C", (), {"max_tokens": 100, "temperature": 0})())
    monkeypatch.setattr(clf, "MAX_TIMEOUT_SECONDS", 0.05)

    def slow(*a, **k):
        time.sleep(3)

    monkeypatch.setattr(gw, "complete", slow)
    t0 = time.time()
    r = c.classify("my dad is not breathing")
    assert r.status == "timeout" and r.risk is None and time.time() - t0 < 2.9
    assert decide(detect("my dad is not breathing"), r, []).response == "full_alert"


# ---- 12. notice category ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("msg,kind", [
    ("he's not responding and his lips are blue", "medical"),
    ("my boyfriend is choking me", "personal_safety"),
    ("the furnace flame is yellow and we all have headaches and feel sick", "co"),
    ("my grandma fell and hit her head and she isn't answering me", "medical"),
    ("my son drank drain cleaner and he's coughing", "poison"),
])
def test_notice_category(msg, kind):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == kind, (msg, r.kind)


# ---- 13. incident follow-ups ---------------------------------------------------------------------------------------
def inc(kind="medical", third=True):
    return Incident(kind=kind, started_at="t", opened_turn=1, last_seen_turn=1, kinds=[kind], third_party=third)


@pytest.mark.parametrize("msg,kind", [
    ("ahora está despierta pero muy confundida", "medical"),
    ("ya abrió los ojos pero no habla", "medical"),
    ("she's breathing now but really pale", "medical"),
    ("it's getting close to the outlets", "flood"),
    ("the water is reaching the power strip", "flood"),
    ("the cracks are getting bigger", "structural"),
    ("el humo está más cerca", "fire_smoke"),
    ("he's in the other room now", "personal_safety"),
])
def test_follow_ups_keep_the_incident(msg, kind):
    assert classify(msg, inc(kind)) == "follow", msg


@pytest.mark.parametrize("msg,kind", [
    ("false alarm, it was burnt toast", "fire_smoke"),
    ("you misunderstood, i meant my texts", "medical"),
])
def test_sprint6_retractions_still_work(msg, kind):
    assert classify(msg, inc(kind, third=False)) == "retracted"


def test_window_coreference_reads_it_as_the_earlier_object():
    r = d("now it's sagging and making a cracking noise", ["there's a water stain on my bedroom ceiling"])
    assert r.response == "full_alert" and r.kind == "structural"


# ---- 14. layers agree; frame fields are exposed ----------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "no me responde y está tirada en el piso", "my toddler is on the balcony railing",
    "grandma is confused and burning up and stopped sweating, the ac is broken",
])
def test_gate_and_safety_agree(msg):
    det = detect(msg)
    assert det.kind and emergency_kind(msg) == det.kind and det.frame_rule
    fr = analyse(msg)
    assert fr.urgency == "emergency" and fr.ongoing == "now" and fr.category == "medical"


def test_api_frame_alert_opens_no_repair_form(client):
    for msg in ["no me responde y está tirada en el piso", "my toddler is hanging over the balcony railing",
                "the ceiling over my bed is bulging and dripping and pieces are dropping"]:
        r = client.post("/api/chat", json={"message": msg, "persona_id": "R001", "mode": "aware"}).json()
        assert r["safety_notice"], msg
        assert (r.get("action") or {}).get("kind") != "maintenance_request", msg
