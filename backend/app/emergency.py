"""Deterministic emergency detection and per-hazard safety text (I-17 / I-18 TEAM DRAFTS, not McKinley-approved).

Runs on every message, for every audience, before identity, drafts or any model. Errs on the side of treating a
message as an emergency: a false alarm costs a phone call, a miss can cost a life. The safety text never tells the
person to do anything risky and never claims anyone was dispatched. McKinley maintenance and risk/legal must
approve the list and the wording (docs/WORKFLOW_TRACEABILITY.md, I-17/I-18).
"""

import re
import unicodedata

# Ordered: the first match wins, so the most life-critical kinds come first.
_W = r"(?:\w+\W+){0,6}"  # up to six words in between
KINDS: list[tuple[str, re.Pattern[str]]] = [
    ("self_harm", re.compile(
        r"kill(ing)? my ?self|suicid|end (my|it all|my own) ?(life)?\b|want to die|wanna die|don'?t want to (live|be "
        r"alive|be here anymore)|hurt(ing)? my ?self|no reason to live|matarme|quitarme la vida|suicidar|"
        r"quiero morir|tự tử|muốn chết|(don'?t|dont|do not) (want|wanna) (to )?(be here|exist|wake up|go on)|"
        r"better off (dead|without me)|no quiero (vivir|estar aqu[ií])", re.I)),
    ("poison", re.compile(
        r"swallow\w*\W+(?:\w+\W+){0,6}(clean\w*|bleach|chemical\w*|pills?|medicine|poison|detergent|pod|battery|"
        r"batteries)|\bpoison(ed|ing)?\b|overdos|trag[oó]\W+(?:\w+\W+){0,4}(cloro|limpia\w*|pastillas|veneno)", re.I)),
    ("trapped", re.compile(
        r"stuck in (the|an|my) (elevator|lift)|(elevator|lift)\W+(?:\w+\W+){0,4}stuck|trapped (in|inside|under)|"
        r"atrapad[oa] en el (elevador|ascensor)", re.I)),
    ("structural", re.compile(
        rf"\b(ceiling|roof|floor|wall|balcony|stairs?|deck)\W+{_W}(collaps\w*|fell (in|down)|falling (in|down)|sag\w*|"
        r"cav(ed|ing) in|caving)|collapsed (ceiling|roof|balcony)|techo se (cay[oó]|derrumb)", re.I)),
    ("medical", re.compile(
        r"chest pains?|heart attack|(not|isn'?t|stopped|can'?t|cannot) breath(e|ing)|unconscious|unresponsive|"
        r"passed out|\bcollapsed\b|overdos|seizure|\b(having|had) a stroke\b(?! of)|bleeding (a lot|badly|heavily|"
        r"won'?t stop)|choking|"
        r"dolor (en el|de) pecho|no respira|inconsciente|se desmay|đau ngực|không thở", re.I)),
    ("personal_safety", re.compile(
        r"break(ing)? ?in\b|breaking into|broke into|broken into|(trying|tried) to (get|break) in|intruder|"
        r"someone (is )?(in|inside) my (apartment|unit|home|place)|threat(en|ening)|stalk(ing|er)|"
        r"domestic (violence|abuse)|abus(e|ing|ive) (me|partner)|(hit|hitting|beat|beating|hurt|hurting) "
        r"(me|her|him|them|someone|a child|the kids?)\b|(screaming|yelling)\W+(?:\w+\W+){0,8}(hit|hurt|help)|"
        r"(don'?t|do not|no longer) feel safe\b(?! (walking|at night))|\b(has|with|pulled) a (gun|knife)|"
        r"\bweapon|attack(ed|ing)? me|"
        r"me (amenaza|golpea|quiere hacer daño)|entraron a (mi|robar)|no me siento segur", re.I)),
    ("gas", re.compile(
        rf"(smel+\w*|odou?r|olor|huel\w*|stink\w*|reek\w*|whiff|leak\w*|hiss\w*|mùi|rò rỉ)\W+{_W}"
        r"(ga+s+|propane|natural gas|gasolina)\b|"
        rf"\b(ga+s+|propane)\b\W+{_W}(smel+\w*|leak\w*|odou?r|hiss\w*|stink\w*)|fuga de gas|olor a gas|huele a gas|"
        r"khí ga|mùi ga|غاز|煤气|燃气|瓦斯|rotten egg|\bgaz\b|gaz kokusu|odeur de gaz|zapach gazu", re.I)),
    ("co", re.compile(
        r"carbon monoxide|mon[oó]xido|\bco\b ?(alarm|detector|monitor)|(alarm|detector) (for|de) (co|mon[oó]xido)",
        re.I)),
    ("fire_smoke", re.compile(
        r"\bfire\b(?! ?(alarm test|drill|place|pit|extinguisher|department|works|fighter|d\b))|\bflames?\b|"
        r"on fire|\bburning\b(?! question)|burnt? (smell|plastic|rubber)|smells? (like |of )?(burn|smoke)|"
        r"\bsmok(e|ing|y|in'?)\b(?! ?(detector|alarm)\b(?!.{0,30}(going off|sounding|won'?t stop|keeps going)))|"
        r"(smoke|fire) (alarm|detector)s? (is |are )?(going off|sounding|won'?t stop|keeps going)|"
        r"\bhumo\b|\bfuego\b|incendio|quemando|cháy|khói|حريق|دخان|着火|火灾|冒烟", re.I)),
    ("electrical", re.compile(
        r"\bspark(s|ed|in'?)?\b|\bsparking\b|chispa|(exposed|bare|loose|hanging|hangin'?) wires?|"
        r"wires?\W+(?:\w+\W+){0,3}(hanging|hangin'?|exposed|sticking out|coming out)|"
        r"(panel|breaker|outlet|socket|switch|wire|wiring|cord|plug|fuse box)\W+(?:\w+\W+){0,8}"
        r"(hot|buzz\w*|burn\w*|melt\w*|smok\w*|scorch\w*|sizzl\w*)|"
        r"(water|leak\w*|drip\w*)\W+(?:\w+\W+){0,10}(light|fixture|outlet|socket|electric\w*|wiring|panel)\b|"
        r"\b(light|fixture|outlet|socket)\W+(?:\w+\W+){0,10}(water|leak\w*|drip\w*)|electrocut|shock(ed|ing)? me",
        re.I)),
    ("flood", re.compile(
        r"\bflood(ing|ed|s)?\b(?! ?(zone|insurance|plain|light))|water (is )?(pouring|everywhere|gushing|spraying|"
        r"coming in|pouring in|all over)|(pipe|line|hose) (has )?(burst|broke|exploded|split)|burst (pipe|line)|"
        r"\bgushing\b|overflow\w*\W+(?:\w+\W+){0,8}(hallway|everywhere|floor|won'?t stop|another room|downstairs)|"
        r"inund\w*|agua por todas partes|se rompi[oó] (una|la) (tuber[ií]a|ca[ñn]er[ií]a)|tuber[ií]a rota|ngập",
        re.I)),
]

_SPACED = re.compile(r"\b[A-Za-z]([ .*_\-])(?:[A-Za-z]\1){1,}[A-Za-z]\b")  # one separator style per word
_POLICY_OR_FIGURATIVE = re.compile(
    r"smoking (allowed|policy|permitted|area|section)|(no|non)[- ]?smoking|smoke[- ]free|allow smoking|can i smoke|"
    r"knife (block|set|drawer)|stroke of (luck|genius)|burning (to|question)|burn(s|ing)? (food|the food|toast|rice|"
    r"dinner)|feel safe (walking|at night|in the parking)|well[- ]lit|just kidding|jk\b|fire (pit|place|sale|drill)",
    re.I)
_BENIGN_CHIRP = re.compile(r"(smoke|co) (alarm|detector).{0,40}(chirp|beep)\w*.{0,40}batter|batter\w*.{0,40}"
                           r"(smoke|co) (alarm|detector)", re.I)


def _prepare(message: str) -> str:
    text = unicodedata.normalize("NFKC", message)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    # "s m e l l gas", "f.i.r.e" -> "smell gas", "fire"
    return _SPACED.sub(lambda m: re.sub(r"[ .*_\-]", "", m.group(0)), text)


def emergency_kind(message: str) -> str | None:
    """Hazard kind for an acute emergency, or None. Low-battery chirps are the one explicit non-emergency."""
    text = _prepare(message)
    if re.search(r"(smoke|co) (alarm|detector)", text, re.I) and re.search(r"dizz|headache|nause|head hurts|sick",
                                                                          text, re.I):
        return "co"  # alarm + symptoms = treat as carbon monoxide
    if _POLICY_OR_FIGURATIVE.search(text):
        text = _POLICY_OR_FIGURATIVE.sub(" ", text)
    if _BENIGN_CHIRP.search(text) and not re.search(r"smoke (is|coming)|fire|flame|head|dizz|nause", text, re.I):
        return None
    for kind, pat in KINDS:
        if pat.search(text):
            return kind
    return None


QUEUE_NOTE = {
    "en": " An urgent note is saved in the staff queue, but this prototype can't page or call anyone, so please "
          "make that call yourself.",
    "es": " Dejé una nota urgente para el personal, pero este prototipo no puede avisar ni llamar a nadie, así que "
          "por favor haga usted esa llamada.",
}

HEADING = {
    "self_harm": {"en": "You can call or text 988 now", "es": "Puede llamar o enviar un mensaje al 988 ahora"},
    "default": {"en": "If anyone is in danger, call 911 now", "es": "Si hay peligro, llame al 911 ahora"},
}

# I-18 TEAM DRAFT safety text per hazard. Spanish = draft translation; needs review by a fluent staff member.
NOTICE: dict[str, dict[str, str]] = {
    "gas": {
        "en": "Leave now. Don't use light switches, phones or flames inside. Once you're outside, call 911 or your gas "
              "company, then your community's emergency maintenance line.",
        "es": "Salga ahora. No use interruptores, teléfonos ni llamas adentro. Ya afuera, llame al 911 o a la compañía "
              "de gas y después a la línea de emergencias de mantenimiento.",
    },
    "co": {
        "en": "Get everyone, including pets, outside into fresh air now and call 911. Don't go back in until "
              "responders say it's safe. Headache, dizziness or nausea can be signs of carbon monoxide.",
        "es": "Salga con todos, incluidas las mascotas, al aire libre ahora y llame al 911. No vuelva a entrar hasta "
              "que los servicios de emergencia lo indiquen. Dolor de cabeza, mareo o náuseas pueden ser señales de "
              "monóxido de carbono.",
    },
    "fire_smoke": {
        "en": "Get out now and call 911. Close doors behind you, don't use elevators, and don't go back inside.",
        "es": "Salga ahora y llame al 911. Cierre las puertas al salir, no use elevadores y no vuelva a entrar.",
    },
    "electrical": {
        "en": "Stay away and don't touch it, especially if there's water nearby. If you see smoke, sparks or heat, "
              "leave and call 911. Then call your community's emergency maintenance line.",
        "es": "Aléjese y no lo toque, sobre todo si hay agua cerca. Si ve humo, chispas o calor, salga y llame al 911. "
              "Después llame a la línea de emergencias de mantenimiento.",
    },
    "flood": {
        "en": "Stay away from water near outlets, lights or appliances. Call your community's emergency maintenance "
              "line now. Call 911 if water reaches anything electrical or anyone is in danger.",
        "es": "Aléjese del agua cerca de enchufes, luces o aparatos. Llame ahora a la línea de emergencias de "
              "mantenimiento. Llame al 911 si el agua llega a algo eléctrico o alguien corre peligro.",
    },
    "structural": {
        "en": "Move away from that area and keep others out. If anyone is hurt or trapped, call 911. Then call your "
              "community's emergency maintenance line.",
        "es": "Aléjese de esa área y no deje que otros entren. Si alguien está herido o atrapado, llame al 911. "
              "Después llame a la línea de emergencias de mantenimiento.",
    },
    "personal_safety": {
        "en": "If you're in danger, call 911 now. Go somewhere safe and lock the door if you can. If you can't talk, "
              "many areas let you text 911. The National Domestic Violence Hotline is also open day and night.",
        "es": "Si está en peligro, llame al 911 ahora. Vaya a un lugar seguro y cierre con llave si puede. Si no puede "
              "hablar, en muchas zonas puede enviar un mensaje de texto al 911.",
    },
    "poison": {
        "en": "Call 911 now if the person is hard to wake, having trouble breathing or having a seizure. Otherwise"
              " call "
              "the Poison Help line now; it's free and open day and night. Don't make them vomit, and keep the product "
              "container to read from.",
        "es": "Llame al 911 ahora si la persona no despierta bien, le cuesta respirar o tiene convulsiones. Si no,"
              " llame "
              "ya a la línea de ayuda contra envenenamientos; es gratis y atiende día y noche. No la haga vomitar y "
              "tenga a mano el envase del producto.",
    },
    "trapped": {
        "en": "Press the elevator's emergency call button and stay calm; don't try to force the doors. If anyone is "
              "hurt, panicking or the car is filling with smoke, call 911.",
        "es": "Presione el botón de emergencia del elevador y mantenga la calma; no intente forzar las puertas. Si "
              "alguien está herido o hay humo, llame al 911.",
    },
    "medical": {
        "en": "Call 911 now. Stay with the person if it's safe; the 911 dispatcher will tell you what to do.",
        "es": "Llame al 911 ahora. Quédese con la persona si es seguro; el operador del 911 le dirá qué hacer.",
    },
    "self_harm": {
        "en": "I'm really glad you told me. You can call or text 988 to reach the Suicide & Crisis Lifeline, any "
              "time, day or night. If you might act on these thoughts right now, call 911.",
        "es": "Me alegra mucho que me lo haya dicho. Puede llamar o enviar un mensaje de texto al 988 para hablar con "
              "la Línea de Prevención del Suicidio y Crisis, a cualquier hora (hay ayuda en español). Si cree que "
              "podría hacerse daño ahora mismo, llame al 911.",
    },
}

LABEL = {"poison": "Possible poisoning", "trapped": "Trapped (elevator)",
         "gas": "Gas smell or leak", "co": "Carbon monoxide", "fire_smoke": "Fire or smoke",
         "electrical": "Electrical hazard", "flood": "Flooding or burst pipe", "structural": "Structural danger",
         "personal_safety": "Personal safety", "medical": "Medical emergency", "self_harm": "Self-harm risk"}

# For messages in languages the prototype has no templates for: always lead with the universal emergency line.
MULTILINGUAL_LINE = "If this is an emergency, call 911. Si es una emergencia, llame al 911."


def notice(kind: str, lang: str = "en") -> str:
    return NOTICE[kind].get(lang) or NOTICE[kind]["en"]


def heading(kind: str | None, lang: str = "en") -> str:
    h = HEADING["self_harm" if kind == "self_harm" else "default"]
    return h.get(lang) or h["en"]
