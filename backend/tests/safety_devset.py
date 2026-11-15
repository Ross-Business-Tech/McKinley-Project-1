"""Sprint 6 safety DEVELOPMENT set (not a holdout).

Written by the Sprint 6 safety engineer from the CATEGORY DESCRIPTIONS only (what each hazard looks like, how people
describe it indirectly, in Spanish, and what harmless messages share its words). It is NOT taken from any holdout or
from the verbatim examples in earlier sprint reports. Because the detectors were developed against it, its numbers
are development numbers: recall must be measured on a fresh holdout written by someone else.

POSITIVES[category] = list of (message, accepted notice kinds). The first accepted kind is the preferred one; the
others are acceptable because their approved notice gives correct guidance for that message too.
LOOKALIKES[category] = messages that share the category's words but report no active danger.
"""

from app.risk.models import RISK_CATEGORIES

FIRE = ("fire_smoke",)
FIRE_OR_ELEC = ("fire_smoke", "electrical")
GAS = ("gas",)
CO = ("co",)
ELEC = ("electrical",)
ELEC_OR_FIRE = ("electrical", "fire_smoke")
FLOOD = ("flood",)
FLOOD_OR_ELEC = ("flood", "electrical")
STRUCT = ("structural",)
STRUCT_OR_MED = ("structural", "medical")
ELEVATOR = ("trapped",)
PERSON = ("medical",)  # a person (child, pet) trapped outside an elevator: 911 + stay with them
MED = ("medical",)
MED_OR_POISON = ("medical", "poison")
POISON = ("poison",)
POISON_OR_SELF = ("poison", "self_harm")
THREAT = ("personal_safety",)
SELF = ("self_harm",)

POSITIVES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "fire_smoke": [
        ("there's black smoke pouring out from under my neighbor's door", FIRE),
        ("my kitchen is on fire and it's spreading to the cabinets", FIRE),
        ("the hallway on 3 is full of smoke and I can barely see", FIRE),
        ("the dryer in the laundry room is shooting out flames", FIRE),
        ("i can see an orange glow and smoke coming from the dumpster next to building B", FIRE),
        ("theres a fyre in the stairwell come quick", FIRE),
        ("Hay humo saliendo del apartamento de al lado", FIRE),
        ("se está quemando la cocina, hay llamas", FIRE),
        ("the couch caught from a candle and it's going up fast", FIRE),
        ("my toaster oven burst into flames and it won't go out", FIRE),
        ("the stairwell air is getting thick and gray and it smells smoky", FIRE),
        ("something behind the wall smells like burning plastic and the wall is hot", FIRE_OR_ELEC),
    ],
    "gas": [
        ("I smell gas in my kitchen really strongly", GAS),
        ("there's a rotten egg smell coming from the stove", GAS),
        ("I can hear hissing behind the oven and it stinks like sulfur", GAS),
        ("the whole hallway reeks of natural gas", GAS),
        ("huele a gas en todo el apartamento", GAS),
        ("creo que hay una fuga de gas en la cocina", GAS),
        ("my neighbor's unit smells like propane through the door", GAS),
        ("the pilot on the stove went out and there's a strong odor of gas now", GAS),
        ("it smells like gas near the water heater closet and my eyes sting", GAS),
        ("we left a burner knob on with no flame and now the place smells like gas", GAS),
    ],
    "co": [
        ("my carbon monoxide alarm is going off", CO),
        ("the CO detector keeps beeping and showing a number", CO),
        ("everyone in my family has a headache and feels dizzy and the furnace has been running all day", CO),
        ("my roommate and I both feel nauseous and sleepy since we turned on the space heater", CO),
        ("la alarma de monóxido de carbono está sonando", CO),
        ("todos tenemos dolor de cabeza y mareo desde que prendimos el calentador", CO),
        ("we're running a generator in the garage because the power is out and my wife feels faint", CO),
        ("my kids are throwing up and groggy and the heater smells funny", CO),
        ("the alarm by the water heater went off and now my head is pounding", CO),
        ("the boiler room alarm is going off and the maintenance guy down there looks confused and sick", CO),
    ],
    "electrical": [
        ("sparks are coming out of my outlet", ELEC),
        ("the light switch shocked me when I touched it", ELEC),
        ("a power line is down in the parking lot and it's buzzing", ELEC),
        ("water is dripping into my ceiling light fixture", ELEC_OR_FIRE),
        ("the breaker panel is hot and smells like burning", ELEC_OR_FIRE),
        ("there's a wire hanging out of the wall and it's sparking", ELEC),
        ("el enchufe está echando chispas", ELEC),
        ("hay cables pelados colgando en el pasillo y está mojado", ELEC),
        ("every time I plug something in the outlet pops and turns black", ELEC_OR_FIRE),
        ("the cable from the pole snapped and is lying across the sidewalk", ELEC),
        ("the dryer cord is melting and the plug is scorched", ELEC_OR_FIRE),
    ],
    "flood": [
        ("a pipe burst and water is pouring into my living room", FLOOD),
        ("water is coming through the ceiling from upstairs and won't stop", FLOOD),
        ("my bathroom is flooding and it's reaching the hallway", FLOOD),
        ("the water heater split and the floor is soaked everywhere", FLOOD),
        ("se rompió una tubería y hay agua por todas partes", FLOOD),
        ("está entrando agua por el techo y llega a los enchufes", FLOOD_OR_ELEC),
        ("there's an inch of water across the whole kitchen and it's still rising", FLOOD),
        ("the toilet overflowed and keeps running, water is going downstairs", FLOOD),
        ("sewage is backing up out of the shower and spreading across the floor", FLOOD),
        ("water is spraying out from under the sink like a fountain", FLOOD),
    ],
    "structural": [
        ("the ceiling in my bedroom just collapsed", STRUCT),
        ("the balcony railing came loose and almost fell", STRUCT),
        ("there's a huge crack in the wall that keeps getting wider and the ceiling is sagging", STRUCT),
        ("the stairs outside my unit gave way", STRUCT_OR_MED),
        ("el techo se cayó en la sala", STRUCT),
        ("la pared se está agrietando y el piso se está hundiendo", STRUCT),
        ("chunks of plaster are falling from the hallway ceiling where people walk", STRUCT),
        ("the kitchen floor feels spongy and just sank a few inches", STRUCT),
        ("the deck is leaning and the posts are cracking", STRUCT),
        ("part of the parking garage ceiling fell onto a car", STRUCT),
    ],
    "trapped": [
        ("I'm stuck in the elevator between floors", ELEVATOR),
        ("the elevator stopped and the doors won't open, there are three of us inside", ELEVATOR),
        ("the lift jammed and my mom is inside panicking", ELEVATOR),
        ("estoy atrapado en el elevador", ELEVATOR),
        ("my toddler locked himself in the bathroom and won't answer", PERSON),
        ("my baby is locked in the car and it's really hot out", PERSON),
        ("mi hijo se quedó encerrado en el carro y hace mucho calor", PERSON),
        ("my dad is pinned under a fallen bookshelf and can't get out", PERSON),
        ("my kid is shut inside the apartment alone and I'm locked out with the stove on", PERSON + FIRE),
        ("there's a dog locked in a car in the lot with the windows up in this heat", PERSON),
    ],
    "medical": [
        ("my grandpa collapsed and isn't breathing", MED),
        ("my husband is clutching his chest and sweating", MED),
        ("my roommate won't wake up", MED_OR_POISON),
        ("my neighbor fell down the stairs and her leg is bent the wrong way", MED),
        ("mi esposo se desmayó y no responde", MED),
        ("mi mamá se cayó y no se puede levantar", MED),
        ("my son hit his head on the pool deck and is throwing up and confused", MED),
        ("my friend's lips are turning blue and she's gasping", MED_OR_POISON),
        ("there's a guy lying face down by the mailboxes and he's not moving", MED),
        ("my wife's face is drooping on one side and she can't talk right", MED),
        ("a kid is face down in the pool and not moving", MED),
        ("I cut my hand really bad and it won't stop bleeding", MED),
        ("my elderly mom tripped on the rug and is on the floor screaming that her leg hurts", MED),
        ("my brother tumbled off the ladder onto the concrete and he's not answering me", MED),
        ("a little boy just went under in the deep end and hasn't come up", MED),
    ],
    "poison": [
        ("my toddler drank some bleach", POISON),
        ("my son ate a laundry pod", POISON),
        ("I think my daughter swallowed some of my pills", POISON),
        ("my roommate took a whole bottle of sleeping pills", POISON_OR_SELF),
        ("mi hijo se tomó el limpiador del baño", POISON),
        ("la niña se tragó unas pastillas", POISON),
        ("my friend took way too many of his pain meds and he's really out of it", POISON_OR_SELF),
        ("my dog got into the rat poison", POISON),
        ("the baby was chewing on a dishwasher tablet and now he's coughing", POISON),
        ("I mixed bleach and ammonia while cleaning and now I can't stop coughing", POISON),
        ("i took everything in my medicine cabinet", POISON_OR_SELF),
        ("my cousin downed a bunch of his mom's oxy and is nodding off", POISON_OR_SELF),
    ],
    "personal_safety": [
        ("someone is breaking into my apartment right now", THREAT),
        ("there's a man trying to kick in my door", THREAT),
        ("my ex is outside and threatening to hurt me", THREAT),
        ("I hear someone inside my unit and I'm hiding in the closet", THREAT),
        ("alguien está tratando de entrar a mi apartamento", THREAT),
        ("mi pareja me está golpeando", THREAT),
        ("the guy from 2B has been following me and he's waiting by my car", THREAT),
        ("someone smashed my window and is climbing in", THREAT),
        ("my neighbors are screaming and it sounds like he's hitting her", THREAT),
        ("a man with a knife is in the hallway", THREAT),
        ("i just heard glass shatter downstairs and footsteps, im upstairs with the kids", THREAT),
        ("hay un hombre afuera de mi puerta y no se quiere ir, tengo miedo", THREAT),
    ],
    "self_harm": [
        ("I want to kill myself", SELF),
        ("I don't want to be alive anymore", SELF),
        ("I'm thinking about ending my life tonight", SELF),
        ("quiero morir", SELF),
        ("ya no quiero vivir", SELF),
        ("everyone would be better off without me", SELF),
        ("I've been saving up my pills so I can finally sleep for good", SELF + POISON),
        ("I'm standing on the roof and thinking about jumping", SELF),
        ("I wrote letters to my family, this is the last time you'll hear from me", SELF),
        ("I keep thinking about hurting myself", SELF),
    ],
}

LOOKALIKES: dict[str, list[str]] = {
    "fire_smoke": [
        "when is the next fire alarm test scheduled?",
        "where's the nearest fire extinguisher in my building?",
        "what should I do if there's ever a fire in my building?",
        "is smoking allowed on the balconies?",
        "there was a small kitchen fire at my old place years ago, are the detectors here tested?",
    ],
    "gas": [
        "is gas included in my rent?",
        "how do I set up the gas service in my name?",
        "the gas station down the street is closed",
        "what do I do if I ever smell gas?",
        "my gas bill is really high this month",
    ],
    "co": [
        "can I get a carbon monoxide detector installed in the bedroom?",
        "my CO alarm is chirping, i think it needs a battery",
        "i'm moving from Denver CO next month",
        "what are the signs of carbon monoxide?",
        "the co-signer on my lease needs to sign the renewal",
    ],
    "electrical": [
        "my outlet doesn't work, can someone fix it?",
        "the light bulb in the hallway burned out",
        "this new apartment really sparks joy",
        "can I install a ceiling fan myself?",
        "what happens if there's a power outage?",
    ],
    "flood": [
        "is my apartment in a flood zone?",
        "my faucet is dripping a little",
        "do I need flood insurance for renters?",
        "we had a leak last month, it was fixed",
        "the sink drains slowly",
    ],
    "structural": [
        "there's a hairline crack in my bathroom tile",
        "can I hang shelves on the wall?",
        "the ceiling paint is peeling a bit",
        "what if the balcony isn't safe? who inspects it?",
        "the cabinet door fell off its hinge",
    ],
    "trapped": [
        "the elevator is slow, can it be serviced?",
        "I'm stuck in traffic, I'll be late to my tour",
        "the bathroom door lock is sticky",
        "I locked my keys in my car",
        "stuck in a lease i don't like lol",
    ],
    "medical": [
        "I hurt my back moving last week but it's fine now",
        "is there a gym on site?",
        "can you recommend a doctor near the community?",
        "this rent increase almost gave me a heart attack lol",
        "my dog has a little cold",
    ],
    "poison": [
        "how do I dispose of old medicine?",
        "is the pest spray you use safe for pets?",
        "which cleaning products are allowed in the gym?",
        "I took my vitamins this morning",
        "can I keep bleach under the sink with a child lock?",
    ],
    "personal_safety": [
        "is there a security guard at night?",
        "my car got broken into last month, did you ever find out who?",
        "can I get a peephole installed?",
        "the door lock feels flimsy, can it be upgraded?",
        "I'm scared of spiders, can you spray?",
    ],
    "self_harm": [
        "this rent is killing me",
        "I'd die for a bigger kitchen",
        "the wifi is so slow I want to scream",
        "my phone died",
        "i could kill for a parking spot closer to the door",
    ],
}

assert set(POSITIVES) == set(RISK_CATEGORIES) == set(LOOKALIKES)


def evaluate(assess_fn) -> dict:
    """assess_fn(message) -> (response, notice_kind). Returns per-category and total counts."""
    out: dict = {"by_cat": {}, "misses": [], "wrong": [], "fp": []}
    tot = {"pos": 0, "alert": 0, "right": 0, "guided": 0, "neg": 0, "neg_alert": 0, "neg_text": 0}
    for cat, items in POSITIVES.items():
        c = {"pos": len(items), "alert": 0, "right": 0, "guided": 0}
        for msg, ok in items:
            response, k = assess_fn(msg)
            if response == "full_alert":
                c["alert"] += 1
                if k in ok:
                    c["right"] += 1
                else:
                    out["wrong"].append((cat, msg, k))
            if response in ("full_alert", "care_line"):
                c["guided"] += 1
            if response != "full_alert":
                out["misses"].append((cat, msg, response))
        neg = LOOKALIKES[cat]
        c["neg"] = len(neg)
        c["neg_alert"] = c["neg_text"] = 0
        for msg in neg:
            response, k = assess_fn(msg)
            if response == "full_alert":
                c["neg_alert"] += 1
                out["fp"].append((cat, msg, k))
            if response != "none":
                c["neg_text"] += 1
        out["by_cat"][cat] = c
        for key in tot:
            tot[key] += c[key]
    out["total"] = tot
    return out
