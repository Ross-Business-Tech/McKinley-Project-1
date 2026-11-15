"""Object and symptom vocabulary used to topic-gate a resident's history (app/context.py). Not conversation
understanding: the language model interprets messages; these lists only decide which of the person's OWN records are
relevant enough to put in their context."""

import re

MAX_ANALYSED = 600  # bounded, linear time on any input

_THINGS: list[tuple[str, str]] = [
    ("ac", r"\bac\b|\ba/c\b|air ?condition\w*|\bhvac\b|\baire(?: acondicionado)?\b"),
    ("heat", r"\bheat(?:er|ing)?\b|\bfurnace\b|\bradiator\b|calefacci[oó]n"),
    ("water heater", r"\bwater heater\b|\bcalentador\b"), ("hot water", r"\bhot water\b|agua caliente"),
    ("sink", r"\bsinks?\b|fregadero|lavabo"), ("faucet", r"\bfaucets?\b|\btaps?\b|\bgrifo\b"),
    ("toilet", r"\btoilets?\b|\binodoro\b|\bescusado\b"), ("shower", r"\bshowers?\b|\btubs?\b|\bba[ñn]era\b|\bducha\b"),
    ("dishwasher", r"\bdishwasher\b|lavaplatos|lavavajillas"),
    ("fridge", r"\bfridge\b|refrigerator|\bfreezer\b|refrigerador|nevera|\brefri\b"),
    ("oven", r"\boven\b|\bstove\b|\brange\b|\bhorno\b|\bestufa\b"), ("microwave", r"microwave|microondas"),
    ("disposal", r"\bdisposal\b|triturador"), ("washer", r"\bwasher\b|washing machine|\blavadora\b"),
    ("dryer", r"\bdryer\b|\bsecadora\b"), ("window", r"\bwindows?\b|\bventanas?\b"),
    ("door", r"\bdoors?\b|\bpuertas?\b"), ("lock", r"\blocks?\b|deadbolt|cerradura"),
    ("fan", r"\bfans?\b|ventilador"), ("light", r"\blights?\b|\bbulbs?\b|\bluz\b|\bluces\b|\bl[aá]mparas?\b"),
    ("outlet", r"\boutlets?\b|enchufes?"), ("ceiling", r"\bceiling\b|\btecho\b"), ("wall", r"\bwalls?\b|\bpared\b"),
    ("pipe", r"\bpipes?\b|plumbing|tuber[ií]as?|\btubos?\b"), ("drain", r"\bdrains?\b|desag[uü]e"),
    ("pests", r"roach\w*|\bants?\b|\bmice\b|\bmouse\b|pests?\b|bugs?\b|hormigas|cucarachas|ratones"),
    ("detector", r"(?:smoke|co) (?:detector|alarm)|\bdetector\b"), ("blinds", r"\bblinds\b|persianas"),
    ("cabinet", r"\bcabinets?\b|\bcupboards?\b|gabinete|alacena"), ("closet", r"\bcloset\b|cl[oó]set"),
    ("thermostat", r"thermostat|termostato"), ("vent", r"\bvents?\b|\bducts?\b"), ("carpet", r"\bcarpet\b|alfombra"),
    ("mailbox", r"\bmail ?box(?:es)?\b|\bbuz[oó]n\b"), ("gate", r"\bgates?\b|\bport[oó]n\b"),
    ("ice maker", r"ice maker"), ("floor", r"\bfloor(?:ing|boards?)?\b|\bpiso\b"),
    ("doorbell", r"\bdoor ?bell\b|\bintercom\b|\bbuzzer\b|\btimbre\b"), ("peephole", r"\bpeep ?hole\b|\bmirilla\b"),
    ("doorknob", r"\bdoor ?knobs?\b|\bknobs?\b|\bdoor handles?\b|\bmanija\b"),
    ("fixture", r"\btowel (?:bar|rack)\b|\bshelf\b|"
                                                                        r"\bshelves\b|\bmirror\b|\btiles?\b"),
]
_SYMPTOM = re.compile(
    r"\b(?:leak\w*|leaky|drip\w*|broke\w*|busted|bust|cracked|crack\w*|not (?:cold|cool|hot|warm|working|cooling|"
    r"heating|draining|"
    r"turning on|closing|locking|opening|flushing)|won'?t|wont|doesn'?t|does not|isn'?t|is not|stopped|dead|stuck|"
    r"jamm?ed|clog\w*|backed up|backing up|overflow\w*|flood\w*|noise|noisy|loud|buzz\w*|rattl\w*|grind\w*|squeak\w*|"
    r"squeal\w*|hum+(?:s|ing)?|click\w*|bang\w*|knock\w*|whistl\w*|hiss\w*|smell\w*|stinks?|mo[u]?ld|mildew|stain\w*|"
    r"flicker\w*|burn(?:t|ed)? out|died|dies|quit(?: working| on me)?|gave out|conked out|fried|kaput|(?:is|are|went|"
    r"goes|keeps going) (?:also |still |now )?out|out too|loose|wobbl\w*|"
    r"fell (?:off|down)|missing|"
    r"torn|peeling|warm|freezing|too (?:hot|cold)|no (?:hot water|heat|power|water|ac|a/c)|running|keeps|"
    r"infest\w*|chirp\w*|beep\w*|swollen|rot\w*|rust\w*|puddl\w*|wet|soak\w*|"
    r"gotea\w*|fuga|roto|rota|no (?:funciona|sirve|prende|enfr[ií]a|calienta|cierra|abre|jala)|ruido\w*|"
    r"huele|olor|moho|atascad[oa]|tapad[oa]|descompuest[oa])\b", re.I)

def things(text: str) -> set[str]:
    """Every object noun in a text (typed names, EN + ES)."""
    text = (text or "")[:MAX_ANALYSED]
    found = {name for name, pat in _THINGS if re.search(pat, text, re.I)}
    if "water heater" in found:
        found.discard("heat")
    return found



def has_symptom(text: str) -> bool:
    return bool(_SYMPTOM.search(text or ""))
