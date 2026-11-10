"""Sprint 7 fix round: lowering must be monotone-safe. Metamorphic invariant: for danger messages D and harmless
decorations L (casual markers, hedges, other people's smoking, "not joking", device nouns, "separately", a past
clause, a question), decision(L + D) and decision(D + L) >= decision(D) with none < safety_info < care_line <
full_alert. Explicit retractions are not decorations. Development wording only (no holdout text)."""

import pytest

from app.risk.pipeline import assess

RANK = {"none": 0, "safety_info": 1, "care_line": 2, "full_alert": 3}

D = [
    # medical / pronoun / Spanish subjectless
    "my dad collapsed and isn't breathing", "she's on the floor and won't respond to me",
    "his lips are blue and he's gasping", "no me responde y está tirado en el piso", "mi mamá no respira",
    "my wife's face is drooping and her speech is slurred", "he's shaking all over and foaming at the mouth",
    # child / temperature
    "my toddler is climbing over the balcony railing", "my baby is face down in the bathtub",
    "the ac is out and grandpa is confused and stopped sweating", "sin calefacción y mi bebé está fría y morada",
    # self-harm / poison
    "i have my pills counted out and this is goodbye", "i want to die", "voy a tirarme del balcón",
    "my son drank bleach", "i took a whole bottle of sleeping pills",
    # property hazards
    "i smell gas in the kitchen", "the CO alarm is going off and we all have headaches",
    "there's smoke pouring out of the oven", "the kitchen is on fire", "the outlet is sparking and smoking",
    "water is gushing through the ceiling light", "the ceiling is sagging and plaster is falling",
    "we're stuck in the elevator", "someone is breaking in through my window right now",
    "my boyfriend is hitting me", "huele a gas en todo el departamento", "hay humo negro en el pasillo",
    "se reventó una tubería y hay agua por todas partes", "his sleeve caught on the stove",
]
PRE = ["lol", "haha", "jk", "omg", "jaja", "I think", "maybe", "kinda weird but", "I'm not joking,", "no es broma,",
       "separately,", "my neighbor smokes a lot btw.", "the smoke detector is old.", "last year we had a leak.",
       "not sure if this is an emergency but", "creo que"]
POST = ["lol", "haha", "jk", "😂", "💀", "maybe?", "I think", "not joking", "btw my neighbor smokes",
        "the detector is old", "separately, my sink drips", "we had a leak last year", "is this an emergency?",
        "what do i do?", "¿qué hago?", "is this a drill?"]


def rank(msg):
    return RANK[assess(msg, [], None).decision.response]


@pytest.mark.parametrize("msg", D)
def test_danger_base_is_a_full_alert(msg):
    assert rank(msg) == 3, msg


@pytest.mark.parametrize("msg", D)
def test_decorations_never_lower_a_decision(msg):
    base = rank(msg)
    worse = [v for v in [f"{p} {msg}" for p in PRE] + [f"{msg} {s}" for s in POST] if rank(v) < base]
    assert not worse, worse


@pytest.mark.parametrize("msg", ["i smell gas", "my dad isn't breathing", "the kitchen is on fire"])
def test_an_explicit_retraction_is_not_a_decoration(msg):
    # a retraction is handled by the incident state machine across turns (app/risk/incident.py), not here; this
    # only pins that the invariant above excludes it on purpose
    from app.risk.incident import is_retraction
    assert is_retraction("false alarm, i meant my texts", "medical")


def run_turns(turns):
    """Run a conversation through the pipeline + incident state machine (in-memory store); decisions per turn."""
    from app.risk.incident import prior_hazards, step

    class Store:
        def __init__(self):
            self.g = {}

        def last_gate(self, s, mode, p):
            return self.g.get((s, mode, p))

        def log_gate(self, s, mode, p, data):
            self.g[(s, mode, p)] = dict(data)

    store, said, hazards, out = Store(), [], [], []
    for i, msg in enumerate(turns):
        prior = prior_hazards(store, "s", "p", msg, i + 1, list(hazards))
        risk = step(store, "s", "p", msg, assess(msg, said[-3:], None, prior), i + 1)
        if risk.decision.response == "full_alert" and risk.decision.kind:
            hazards.append(risk.decision.kind)
        said.append(msg)
        out.append(risk.decision)
    return out


# Look-alikes from the UX-judge classes (benign senses, contained leaks): decorations must not RAISE them to an alert
LOOK = ["oh shoot, I meant the hall closet", "my oven light burned out", "the dishwasher is leaking onto the floor",
        "the bulb in the hall burned out", "my sink is leaking under the cabinet", "el lavaplatos gotea en el piso",
        "does the unit come with a carbon monoxide detector?", "is the fire drill on thursday?"]
SAFE_DECOR = ["lol", "haha", "maybe", "I think", "separately,", "the detector is old", "btw"]


@pytest.mark.parametrize("msg", LOOK)
def test_decorations_never_raise_a_look_alike_to_an_alert(msg):
    raised = [v for v in [f"{p} {msg}" for p in SAFE_DECOR] + [f"{msg} {p}" for p in SAFE_DECOR] if rank(v) == 3]
    assert rank(msg) < 3 and not raised, raised
