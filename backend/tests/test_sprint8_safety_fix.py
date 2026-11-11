"""Sprint 8 fix round (agent A): findings of the independent verifier, red-team, resident simulator and UI judge,
fixed by class. Development wording written by agent A (no holdout text). Mock provider, offline."""

import time
import uuid

import pytest

from app.risk.pipeline import assess
from app.risk.ui_state import safety_ui

RANK = {"none": 0, "safety_info": 1, "care_line": 2, "full_alert": 3}


def d(msg, recent=None):
    return assess(msg, recent or [], None).decision


def rank(msg):
    return RANK[d(msg).response]


def chat(client, msg, session, persona="R003"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def run_turns(turns):
    from tests.test_sprint7_safety_invariants import run_turns as rt
    return rt(turns)


def ui(dec):
    from app.risk.responses import select
    st = select(dec, "en")
    return safety_ui(dec, alert_shown=bool(st.safety_notice), care_kind=st.care_kind)


# ---- P0-1: a "yes" after safety information for a question becomes the full alert (rule R5f) ----------------------
QUESTIONS = ["If my dad can't breathe, what should I do?", "if my wife won't wake up who do i call?",
             "qué hago si mi abuelo no reacciona", "what should we do if someone collapses?",
             "what do i do if i smell gas?", "si mi hijo se traga una pila, ¿qué hago?"]
YES = ["yes", "yeah it is", "it is happening", "sí", "he is, please help", "she isn't", "yes right now",
       "sí, ahora mismo", "yep", "he's not breathing", "she won't wake up", "no responde"]


@pytest.mark.parametrize("q", QUESTIONS)
@pytest.mark.parametrize("a", YES)
def test_affirmation_after_a_safety_question_is_a_full_alert(q, a):
    first, second = run_turns([q, a])
    assert first.response in ("safety_info", "care_line"), (q, first.rule)
    assert second.response == "full_alert" and second.kind, (q, a, second.rule)


@pytest.mark.parametrize("a", ["no, just asking", "no", "not right now, just in case", "solo pregunto",
                               "hypothetically", "no, he's fine", "nope, thanks"])
def test_a_denial_clears_the_pending_question(a):
    first, second, third = run_turns(["If my dad can't breathe, what should I do?", a, "yes"])
    assert second.response != "full_alert" and third.response != "full_alert", (a, second.rule, third.rule)


def test_the_pending_question_expires():
    out = run_turns(["If my dad can't breathe, what should I do?", "what time is the pool open?",
                     "is the gym open late?", "yes"])
    assert out[-1].response != "full_alert"


def test_a_past_mention_leaves_nothing_pending():
    out = run_turns(["we had a small kitchen fire last year, all fine now", "yes"])
    assert out[-1].response != "full_alert"


def test_confirmation_through_the_api_writes_the_urgent_note(client):
    s = uuid.uuid4().hex
    r1 = chat(client, "If my mother can't breathe, what do I do?", s)
    assert r1["safety_state"] == "concern"
    r2 = chat(client, "yes, right now", s)
    assert r2["safety_state"] == "active" and r2["safety_notice"] and r2["emergency_kind"] == "medical"
    assert r2["risk"]["decision"]["rule"] in ("R5f", "R1")
    assert any(rec["kind"] == "staff_handoff" for rec in r2["records_created"])
    r3 = chat(client, "ok", s)  # an active incident now: a quiet turn keeps a calm line
    assert r3["safety_state"] in ("active", "concern")


def test_spanish_confirmation_through_the_api(client):
    s = uuid.uuid4().hex
    chat(client, "si mi papá no respira, ¿qué hago?", s)
    r = chat(client, "sí", s)
    assert r["safety_state"] == "active" and r["emergency_kind"] == "medical"


# ---- P1-1: a live situation inside "is it bad if ..." is a report, not a hypothetical ------------------------------
@pytest.mark.parametrize("msg", [
    "what do i do if my son swallowed a battery, he did it 5 minutes ago",
    "is it bad if my daughter drank some bleach a few minutes ago? she's coughing",
    "is it dangerous if my roommate has been unresponsive for a few minutes?",
    "how worried should i be if my friend took a handful of pills and is drowsy",
    "is it an emergency if my neighbor collapsed in the lobby",
    "what if my husband's lips are turning blue?",
    "is it serious if my mom fell and hit her head just now",
    "qué hago si mi hijo se tragó una pila hace unos minutos",
    "¿es grave si mi hija tomó cloro hace un rato? está tosiendo",
    "es una emergencia si mi abuelo se desmayó en el pasillo",
])
def test_live_situation_inside_a_question_is_an_alert(msg):
    assert rank(msg) == 3, (msg, d(msg).rule)


@pytest.mark.parametrize("msg", [
    "what should i do if a kid swallows a coin?", "is it bad if someone faints from the heat?",
    "what happens if a person drinks bleach?", "qué pasa si alguien se desmaya?",
])
def test_generic_versions_stay_information(msg):
    assert rank(msg) < 3, (msg, d(msg).rule)


# ---- pre-existing P0: household chemical / poison swallowed ("tomó", "drank") ------------------------------------
@pytest.mark.parametrize("msg", [
    "mi hija tomó cloro", "mi hijo tomó veneno para ratas", "my son drank lighter fluid",
    "mi hija tomó cloro hace unos minutos y está tosiendo", "my toddler drank some gasoline from the garage",
    "mi niño bebió thinner", "my daughter swallowed nail polish remover", "el bebé tomó suavizante de ropa",
    "my grandpa drank windshield washer fluid by mistake", "mi esposo tomó raticida",
])
def test_household_chemical_ingestion_is_poison(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == "poison", (msg, r.rule, r.kind)


@pytest.mark.parametrize("msg", ["yo tomo pastillas para la presión", "yo tomo cloro para limpiar el baño",
                                 "i bought lighter fluid for the grill", "can i store gasoline in my storage unit?",
                                 "where do i throw away old paint thinner?"])
def test_household_chemical_near_misses(msg):
    assert rank(msg) < 3, msg


# ---- pre-existing P1: a child / elder / pet shut in a vehicle ---------------------------------------------------
@pytest.mark.parametrize("msg", [
    "my 2 year old is locked in the hot car", "the baby is stuck in the car and it's really hot",
    "my dog is locked inside the car in the parking lot", "grandma is trapped in the car and can't get out",
    "mi hijo está encerrado en el carro", "dejé a mi bebé en el coche y se cerró",
    "a kid is locked in a car in the garage", "mi perrito está atrapado en el auto",
])
def test_shut_in_a_vehicle_is_an_alert(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind in ("medical", "trapped"), (msg, r.rule)


@pytest.mark.parametrize("msg", ["i locked my keys in the car",
                                 "my son is waiting in the car while i grab the package",
                                 "my dog loves riding in the car",
                                 "can my dog ride in the car to the vet?", "dejé las llaves en el carro"])
def test_vehicle_near_misses(msg):
    assert rank(msg) < 3, msg


# ---- contacts: self-overdose quantity adds 988 -----------------------------------------------------------------
@pytest.mark.parametrize("msg", ["I just swallowed a whole bottle of my sleeping pills", "i took all my xanax",
                                 "i took 40 tylenol", "me tomé todas mis pastillas"])
def test_self_overdose_quantity_adds_988(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.also_988 or r.kind == "self_harm", (msg, r.rule, r.kind)
    hrefs = [c["href"] for c in ui(r)[1]]
    assert "tel:988" in hrefs and "sms:988" in hrefs and "tel:911" in hrefs


@pytest.mark.parametrize("msg", ["my son swallowed a whole bottle of vitamins", "my toddler ate 20 vitamin gummies"])
def test_a_child_overdose_is_poison_without_988(msg):
    r = d(msg)
    assert r.response == "full_alert" and r.kind == "poison" and not r.also_988, (msg, r.rule)


@pytest.mark.parametrize("msg", ["I cut myself deep", "i cut myself and it won't stop bleeding",
                                 "me corté las muñecas"])
def test_self_cut_has_988_and_911(msg):
    hrefs = [c["href"] for c in ui(d(msg))[1]]
    assert {"tel:988", "sms:988", "tel:911"} <= set(hrefs), (msg, hrefs)


# ---- educational hazard questions are concern, not active ------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "Is carbon monoxide dangerous?", "how do I know if I have a gas leak?", "is natural gas toxic?",
    "can a space heater explode?", "how dangerous is a grease fire?", "¿es peligroso el monóxido de carbono?",
    "how can I tell if there's carbon monoxide?", "is bleach poisonous?",
])
def test_educational_hazard_questions_are_not_alerts(msg):
    r = d(msg)
    state, contacts = ui(r)
    assert state in ("concern", "normal") and (state == "normal" or contacts), (msg, r.rule, r.response)


@pytest.mark.parametrize("msg", [
    "is carbon monoxide dangerous? the alarm is going off and i feel dizzy", "is the gas smell in here dangerous?",
    "is it dangerous that i smell gas right now?", "¿es peligroso? huele a gas en la cocina",
])
def test_a_perceived_hazard_with_a_question_stays_an_alert(msg):
    assert rank(msg) == 3, (msg, d(msg).rule)


# ---- a small hazard already under control in the same message: concern, and the repair can follow --------------
@pytest.mark.parametrize("msg", [
    "small grease fire, I put it out, everyone is fine", "the pan caught fire but we smothered it, all good",
    "the toaster caught fire, i put it out", "the outlet sparked so i turned the breaker off",
    "se prendió el sartén, ya lo apagué, todos bien", "a towel caught fire on the stove, the fire is out now",
    "the toaster oven caught fire, i unplugged it and it's out now", "hubo un fuego pequeño en la estufa, lo apagué",
])
def test_controlled_small_hazard_is_concern(msg):
    r = d(msg)
    assert r.response == "safety_info", (msg, r.rule, r.response)


@pytest.mark.parametrize("msg", [
    "i tried to put it out but it's spreading", "i put it out but there's still smoke everywhere",
    "i can't put the fire out", "no puedo apagarlo", "i turned off the stove but i still smell gas",
    "we put it out but my son burned his hand badly",
])
def test_not_controlled_stays_an_alert(msg):
    assert rank(msg) == 3, (msg, d(msg).rule)


def test_after_a_controlled_fire_a_repair_opens(client):
    s = uuid.uuid4().hex
    r1 = chat(client, "small grease fire, I put it out, everyone is fine", s)
    assert r1["safety_state"] == "concern"
    r2 = chat(client, "can you send someone to look at the stove hood?", s)
    assert r2["safety_state"] == "normal" and (r2.get("action") or {}).get("kind") == "maintenance_request"


# ---- concern is never empty -----------------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "I got a little shock when I touched the outlet", "the light switch zapped me", "i felt a jolt from the dryer",
    "me dio un toque el enchufe", "got shocked plugging in the lamp", "me dio una descarga el interruptor",
    "no heat, 40 degrees, newborn", "my grandma has no AC and it's 95 inside",
])
def test_concern_always_has_a_line_and_contacts(msg):
    # never silent and never empty (an existing electrical alert for "zapped me" is kept, not lowered)
    r = d(msg)
    state, contacts = ui(r)
    assert state in ("concern", "active") and contacts, (msg, r.rule, r.response)


@pytest.mark.parametrize("msg", ["my son got shocked and isn't responding", "i got shocked and my arm is numb and "
                                 "my chest hurts", "a wire shocked my dad and he collapsed"])
def test_a_shock_with_a_body_sign_is_an_alert(msg):
    assert rank(msg) == 3, (msg, d(msg).rule)


def test_every_concern_on_the_dev_wording_has_contacts():
    from tests.test_sprint8_safety import NEW_D
    msgs = [*NEW_D, "my grandma slipped", "i feel dizzy today", "what if there's a fire?", "my dad seems out of it",
            "everyone would be better off without me", "the hallway smells a bit like smoke"]
    for m in msgs:
        state, contacts = ui(d(m))
        assert state == "normal" or contacts, m


# ---- false alarm: a little water contained in an appliance --------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "a little water at the bottom of my dishwasher", "my dishwasher has a little water pooled at the bottom, is that a "
    "flood?", "there's some water in the washer after the cycle, is that normal?", "a little water under the fridge",
    "la lavadora tiene un poco de agua, ¿es una inundación?", "a small puddle of water under the sink, is that a leak?",
    "some water in the drip pan of the ac", "un poco de agua debajo del refri",
])
def test_contained_appliance_water_is_not_an_alert(msg):
    assert rank(msg) < 3, (msg, d(msg).rule)


@pytest.mark.parametrize("msg", [
    "a little water under the dishwasher and it's spreading toward the outlet", "my dishwasher is gushing water",
    "the dishwasher overflowed and water is all over the kitchen", "my 2 year old drank some of the drano under the "
    "sink", "el agua de la lavadora va hacia el enchufe",
])
def test_contained_water_near_misses_stay_alerts(msg):
    assert rank(msg) == 3, (msg, d(msg).rule)


# ---- category: "something" alone no longer means poison ---------------------------------------------------------
def test_something_alone_does_not_pick_the_poison_notice():
    from app.risk.category import refine
    assert refine("poison", "something is wrong, she's turning blue")[0] == "medical"
    assert refine("poison", "she swallowed something and is turning blue")[0] == "poison"


# ---- regex timing: linear on long whitespace ----------------------------------------------------------------------
@pytest.mark.parametrize("msg", ["if my dad" + " " * 20000 + "x", "a" + " " * 20000 + "- b",
                                 "my\t" * 5000 + "dad can't breathe", ("if he fell , and " * 2000)])
def test_clause_regexes_are_linear(msg):
    from app.risk.frame import _FCLAUSE
    from app.risk.neutralize import _CLAUSE, _COND_END, spans
    t = time.perf_counter()
    _COND_END.search(msg)
    _CLAUSE.split(msg)
    _FCLAUSE.split(msg)
    spans(msg)
    assert time.perf_counter() - t < 1.0
