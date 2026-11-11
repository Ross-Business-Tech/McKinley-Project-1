"""Layer 1c (sprint 7): compositional risk frame.

Earlier layers match whole phrases ("my dad is not breathing"). Whole CLASSES of reports were missed because a
phrase needs every one of its words: a symptom with no canonical hazard word, a pronoun instead of a named person,
a Spanish sentence with no subject at all, a live report phrased as a question, a typo. This layer instead reads a
message as a frame built from independent, bilingual lexicons and combines them:

    WHO        self / adult / child / elder / pet / pronoun (incl. the Spanish dropped subject) / generic
    STATE      body or behaviour states with a severity tier
                 critical  alone is enough: not breathing, unresponsive, won't wake, seizing, blue lips, choking,
                           bleeding heavily, face drooping, collapsed, face down in water ...
                 weak      needs a subject AND a second sign: on the floor, not moving, not answering me ...
                 body      heat / cold / illness signs: confused, not sweating, hot to the touch, ice cold, ...
    HAZARD     a child at a height (railing, window ledge, roof edge) or in water; heat / cold exposure context;
               an ingestion (verb + substance)
    FRAMING    per sentence: now | past | hypothetical (generic subject or an event verb inside "if") | media |
               drill | policy question | joking | negated.  A STATIVE sign about a SPECIFIC subject inside a
               conditional or a question still counts as now ("if my dad can't breathe what do I do",
               "is it normal that my wife is shaking and won't respond").

Output: separate fields for the incident category, urgency, ongoing status and the notice template, so the policy
does not have to infer them from one label. The frame only ADDS caution in app.risk.detect: it can turn a miss into
an alert or a care line, or turn a deterministic "hypothetical" into a report when the sign is live. The framings it
can apply to an existing rule match (media, drill, policy question, device noun) never apply to self-harm or personal
safety, and never when the message also has a live state or sign. Text is normalised first (accents, apostrophes,
repeated letters, common typos), so lexicons are written once, without accents, for English and Spanish.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from app.risk.concepts import not_physical
from app.risk.neutralize import _COMPLETED
from app.risk.neutralize import _LIVE as _LIVE_TIME

# ---- normalisation ------------------------------------------------------------------------------------------------
_TYPO = {
    "breathng": "breathing", "breating": "breathing", "brething": "breathing", "breahting": "breathing",
    "breathin": "breathing", "breatheing": "breathing", "breaathing": "breathing", "brathing": "breathing",
    "unconsious": "unconscious", "unconcious": "unconscious", "unconscous": "unconscious", "unconsciuos": "unconscious",
    "uncoscious": "unconscious", "unresponsve": "unresponsive", "unresposive": "unresponsive",
    "respondin": "responding", "respondng": "responding", "repsonding": "responding", "answerin": "answering",
    "movin": "moving", "wakin": "waking", "bleedin": "bleeding", "chokin": "choking", "shakin": "shaking",
    "seizng": "seizing", "siezing": "seizing", "seizeing": "seizing", "seziure": "seizure", "siezure": "seizure",
    "collasped": "collapsed", "colapsed": "collapsed", "fainted": "fainted", "passd": "passed",
    "flor": "floor", "foor": "floor", "groud": "ground", "bathrom": "bathroom", "inconciente": "inconsciente",
    "inconsiente": "inconsciente", "respira": "respira", "desmallo": "desmayo", "desmallada": "desmayada",
    "desmallado": "desmayado", "convulcionando": "convulsionando", "convulsiando": "convulsionando",
    "r": "are", "u": "you", "ur": "your", "cuz": "because", "bc": "because", "rn": "right now", "pls": "please",
    "plz": "please", "nt": "not", "isn": "isnt", "dosnt": "doesnt", "wont": "wont",
}
_LAUGH = re.compile(r"\b(?:lol+|lmao+|lmfao|haha\w*|hehe\w*|jk|jaja\w*|xd)\b|\U0001F602|\U0001F923|\U0001F480|"
                    r"\U0001F606|\U0001F605", re.I)


def normalize(text: str) -> str:
    """Lowercase, no accents, no apostrophes ("isn't" -> "isnt", "está" -> "esta"), letters repeated 3+ times
    collapsed ("helppp" -> "help"), common typos and texting forms mapped to their word, "can't breath" -> breathe."""
    t = unicodedata.normalize("NFKC", text or "")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[’‘`']", "", t)
    t = re.sub(r"([a-z])\1{2,}", r"\1", t)
    t = re.sub(r"[a-z]+", lambda m: _TYPO.get(m.group(0), m.group(0)), t)
    t = re.sub(r"\b(cant|cannot|can not|couldnt|unable to|struggling to|hard to|trouble) breath\b", r"\1 breathe", t)
    return re.sub(r"[ \t]+", " ", t)


# ---- WHO ----------------------------------------------------------------------------------------------------------
_CHILD = (r"kids?|child|children|son|daughter|toddlers?|little (?:one|boy|girl|guy|brother|sister)|boy|girl|"
          r"\d+ ?(?:year|yr|month|mo|week|wk)s?[- ]?old|babys?|babies|infant|newborn|grandson|granddaughter|"
          r"nino|nina|ninos|hijo|hija|hijos|bebe|nene|nena|chiquit[oa]|niet[oa]|criatura|nephew|niece|sobrin[oa]")
_ELDER = r"grandma|grandpa|grandmother|grandfather|granny|nana|abuel[oa]|abuelit[oa]|elderly \w+|old (?:man|woman|lady)"
_ADULT = (r"mom|mum|mother|dad|father|husband|wife|partner|roommate|room mate|neighbou?r|friend|boyfriend|girlfriend|"
          r"man|woman|guy|lady|person|brother|sister|cousin|uncle|aunt|tenant|resident|coworker|fiance|fiancee|"
          r"co-worker|colleague|boss|patient|guest|visitor|classmate|teammate|caregiver|"
          r"esposo|esposa|marido|mama|mami|papa|papi|vecin[oa]|pareja|amig[oa]|herman[oa]|senor|senora|hombre|"
          r"mujer|ti[oa]|prim[oa]|novi[oa]|companer[oa]|suegr[oa]")
_PET = r"dog|puppy|cat|kitten|pet|perr[oa]|perrit[oa]|gat[oa]|gatit[oa]|mascota"
_PRONOUN = r"he|she|hes|shes|him|her|they|theyre|them|his|ella|el (?=esta|no|se)"
_GENERIC = (r"someone|somebody|anyone|anybody|a person|people|a (?:kid|child|baby|toddler)|kids|children|alguien|"
            r"una persona|la gente|un nino|una nina|un bebe|cualquiera")
_SELF = r"i|im|ive|id|ill|me|myself|we|were|us|our|both of us|all of us|everyone|everybody|yo|estoy|me siento|tengo|"
_SELF += r"estamos|nosotros|todos"
# Possessives lose their apostrophe in normalize() ("husband's" -> "husbands"), so every role also matches with "s".
WHO = {
    "child": re.compile(rf"\b(?:{_CHILD})s?\b"),
    "elder": re.compile(rf"\b(?:{_ELDER})s?\b"),
    "adult": re.compile(rf"\b(?:{_ADULT})s?\b"),
    "pet": re.compile(rf"\b(?:{_PET})s?\b"),
    "pronoun": re.compile(rf"\b(?:{_PRONOUN})\b"),
    "self": re.compile(rf"\b(?:{_SELF})\b"),
}
_SPECIFIC = re.compile(rf"\b(?:my|our|his|her|their|the|mi|mis|su|nuestr[oa])\s+(?:\w+\s+)?(?:{_CHILD}|{_ELDER}|"
                       rf"{_ADULT}|{_PET})s?\b|\b(?:{_PRONOUN})\b")
_GENERIC_RE = re.compile(rf"\b(?:{_GENERIC})\b")

# ---- STATE (critical / weak / body) --------------------------------------------------------------------------------
_NEG = r"(?:not|isnt|arent|wasnt|no|stopped|hasnt|havent|cant|cannot|wont|doesnt|didnt|never)"
CRITICAL = re.compile(
    r"\bburn(?:ed|t) (?:his|her|their|my) (?:\w+ ){0,2}?(?:badly|bad|really bad|so bad)\b|\bse quemo (?:\w+ ){0,3}?"
    r"(?:feo|mucho|grave|horrible)\b|"
    r"\bworst headache (?:of (?:my|his|her|their) life|ever|ive ever had|hes ever had|shes ever had)\b|"
    r"\bel peor dolor de cabeza\b|"
    # sprint 8: indirect breathing / stroke / fainting signs (EN + ES)
    r"\bwheez\w* (?:and|but) (?:\w+ )?(?:cant|cannot|unable to|can barely|isnt able to) (?:talk|speak)\b|"
    r"\b(?:asthma|allergic|anaphylactic) (?:attack|reaction)\b(?:\W+\w+){0,6}?\W+(?:inhaler|epipen|epi pen|"
    r"medicine|meds)\b(?:\W+\w+){0,2}?\W+(?:isnt|is not|not|wont|doesnt|arent) (?:\w+ )?(?:working|helping)\b|"
    r"\b(?:cant|cannot|can not|unable to|cant seem to) (?:get|catch|take) (?:any|enough|a|his|her|their|my) "
    r"(?:\w+ )?(?:air|breath)\b|\bno (?:le|me) entra (?:el )?aire\b|\b(?:le|me) falta (?:el )?aire\b|"
    r"\bse (?:le )?(?:esta )?ahoga\b|\bse esta asfixiando\b|"
    r"\b(?:cant|cannot|unable to) (?:lift|raise|move) (?:his|her|their|my) (?:\w+ )?(?:arm|leg|hand)\b|"
    r"\bno (?:puede|puedo) (?:levantar|mover) (?:el|la|su) (?:brazo|pierna|mano)\b|"
    r"\b(?:words|speech|talking)\b(?:\W+\w+){0,3}?\W+(?:coming out wrong|garbled|jumbled|all mixed up|"
    r"dont make sense|not making sense)\b|\bhabla (?:enredad[oa]|arrastrando)\b|"
    r"\b(?:keeps?|kept) (?:passing out|fainting|blacking out)\b|\bse (?:sigue|vuelve a) desmay\w*|"
    r"\b(?:oxygen|o2|spo2|sats?|saturation|pulse ?ox\w*|oximeter|oximetro|oxigeno|saturacion)\b(?:\W+\w+){0,4}?\W+"
    r"(?:[1-8]\d)\b(?!\s*(?:degrees|grados|years|anos|f\b|dollars|bucks))|"
    r"\b(?:skin|piel)\b(?:\W+\w+){0,4}\W+(?:peeling off|falling off|coming off|melting|blister\w*|se (?:esta )?(?:caye"
    r"ndo|"
    r"cae|despegando)|derritiendo|ampoll\w*)\b|\b(?:severe|bad|deep|third[- ]degree|second[- ]degree) burns?\b|"
    r"\bquemadura (?:grave|fuerte|profunda)\b|\b(?:burn\w*|scald\w*|boiling|hirviendo|quem\w*|hot oil|aceite)\b(?:\W+"
    r"\w+)"
    r"{0,8}?\W+(?:blister\w*|ampollas?|peeling|skin (?:is )?(?:white|black|charred))\b|\bno se (?:despierta|despierte)"
    r"\b|"
    r"\b(?:not|isnt|arent|stopped|quit|hasnt been|cant|cannot|can barely|barely|struggling to|having trouble|"
    r"trouble|hard to|unable to) (?:\w+ )?breath(?:e|ing)\b|\bno (?:esta )?respir(?:a|e|ando)\b|"
    r"\bno (?:puede|pueda) respirar\b|\bno (?:esta )?breath\w*|\b(?:not|isnt|no esta) breathing (?:well|right|good|"
    r"bien|normal\w*)\b|\bgasping\b|\bgurgl\w*|\bbreathing (?:weird|funny|strange|shallow|slow|really "
    r"slow|wrong|is weird|is slow|is shallow)|\brespira (?:muy )?(?:raro|mal|poquito|lento)\b|"
    r"\b(?:wont|not|isnt|doesnt|hasnt) (?:respond\w*|answer\w*|react\w*) (?:to (?:me|us|anything|anyone|"
    r"his name|her name|touch)|at all)\b|\bunresponsive\b|\bunconscious\b|\binconsciente\b|\bout cold\b|\bknocked out"
    r"\b|\bblacked out\b|"
    r"\b(?:wont|cant|can not|couldnt|unable to|not|isnt|hasnt|never) (?:\w+ )?(?:wake|waking|woken|come to|came to)\b|"
    r"\bno (?:despierta|despierte|reacciona|reaccione|vuelve en si)\b|"
    r"\b(?:seizing|seizure|convuls\w*|fitting|having a fit|jerking|twitching all over)\b|"
    r"\beyes (?:\w+ )?(?:rolled|rolling) (?:back|up)\b|\bojos en blanco\b|\bfoam\w* (?:at|from|in) (?:the |his |her "
    r"|their )?mouth\b|\bespuma (?:en|por) la boca\b|"
    r"\b(?:lips|face|skin|fingers|fingertips|nails|mouth|cara|labios|piel)\b(?:\W+\w+){0,3}\W+(?:blue|purple|gr[ae]y|"
    r"azul\w*|morad\w*)\b|\b(?:turning|turned|going|gone|se (?:puso|esta poniendo)) (?:blue|purple|gr[ae]y|azul|"
    r"morad[oa])\b|\bmottled\b|\b(?:is|are|looks?|went|esta|se ve) (?:\w+ (?:and )?){0,2}(?:blue|purple|"
    r"azul|morad[oa])\b|"
    r"\b(?:choking|chokes|se esta ahogando|ahogandose)\b|"
    r"\b(?:face|mouth|smile|cara|boca|sonrisa)\b(?:\W+\w+){0,3}\W+(?:droop\w*|lopsided|crooked|uneven|caid[oa]|"
    r"torcid[oa]|chuec[oa])\b|\bcrooked (?:smile|face|mouth)\b|"
    r"\b(?:cant|cannot|unable to) (?:raise|lift) both (?:of )?(?:his |her |their |my )?arms\b(?! (?:above|over))|"
    r"\b(?:one side|un lado)\b(?:\W+\w+){0,4}\W+(?:droop\w*|numb|limp|cay[oa]|caido)\b|\bslurr\w*|"
    r"\bbleeding (?:\w+ )?(?:a lot|badly|heavily|everywhere|so much|nonstop|wont stop|like crazy)\b|"
    r"\b(?:wont|doesnt|isnt) stop bleeding\b|\bblood (?:is )?(?:everywhere|spurting|pouring|gushing|soaking)\b|"
    r"\bsoak\w* through\b|\bsangr\w* mucho\b|\bmucha sangre\b|\bno (?:para|deja) de sangrar\b|"
    r"\bcollapsed\b|\bcollapses\b|\bse desplom\w*|\bse desmay\w*|\bdesmayad[oa]\b|\bpassed out\b|\bfainted\b|"
    r"\b(?:went|is|goes|going|gone) limp\b|\blimp\b|\bfloppy\b|\bslumped\b|\bmotionless\b|"
    r"\bface ?down\b|\bboca abajo\b|\bclutching (?:his|her|their|my) chest\b|\bse agarra el pecho\b|"
    r"\b(?:chest|pecho)\b(?:\W+\w+){0,3}\W+(?:pain|hurts|crushing|tight|pressure|dolor|duele|aprieta)\b|"
    r"\b(?:dolor|duele|presion)\b(?:\W+\w+){0,4}?\W+(?:pecho)\b|\b(?:swollen|swelling|closing)\b(?:\W+\w+){0,2}\W+"
    r"(?:throat|tongue|lips)\b|\b(?:hinchando|hinchandose|cerrando|inflamando)\b(?:\W+\w+){0,2}?\W+(?:garganta|"
    r"lengua|labios|cara)\b|\b(?:throat|tongue|garganta|lengua)\b(?:\W+\w+){0,3}\W+(?:swell\w*|closing|"
    r"hinchad\w*|cerrando)\b")
# Stative critical signs: an ongoing condition. Inside a conditional with a specific subject they mean "now" ("if my
# dad can't breathe"); the EVENT forms ("if he stops breathing", "if she has a seizure") stay hypothetical.
_STATIVE = re.compile(
    r"\b(?:not|isnt|arent|cant|cannot|barely|struggling to|having trouble|unable to|no (?:esta|puede|pueda)?) ?"
    r"(?:\w+ )?(?:breath(?:e|ing)|respir\w*)\b|\bno (?:respira|respire|despierta|despierte|reacciona|reaccione|"
    r"responde|responda)\b|\b(?:isnt|is not|not|wont|cant|hasnt) (?:\w+ )?(?:waking|wake|woken|responding|respond|"
    r"moving|answering)\b|\bis (?:choking|seizing|having a seizure|convulsing|bleeding|blue|purple|unconscious|"
    r"unresponsive|limp|gasping)\b|\b(?:lips|face|skin) (?:are |is |look |looks )?(?:blue|purple|gr[ae]y)\b|"
    r"\besta (?:temblando|convulsionando|morad[oa]|inconsciente|tirad[oa])\b|\beste (?:temblando|convulsionando)\b|"
    r"\b(?:unresponsive|unconscious|inconsciente|choking|gasping|seizing|convulsing|face ?down|boca abajo)\b")
WEAK = re.compile(
    r"\b(?:not|isnt|arent|wont|hasnt|doesnt|cant get (?:him|her|them) to|never) (?:\w+ )?(?:responding|respond|"
    r"answering|answer|moving|move|moved|talking|talk|opening (?:his|her|their) eyes|open (?:his|her|their) eyes)\b|"
    r"\bno (?:me )?(?:responde|responda|contesta|conteste|se mueve|se mueva|habla|abre los ojos)\b|"
    r"\b(?:lying|laying|lies|lays|sprawled|passed|down|collapsed|slumped|curled up) (?:\w+ )?(?:on|in) (?:the|my|"
    r"our|his|her) (?:\w+ )?(?:floor|ground|pavement|concrete|sidewalk|grass|tile|stairs|tub|shower)\b|"
    r"\b(?:on|in) the (?:\w+ )?(?:floor|ground) (?:and |, )?(?:not|wont|cant)\b|"
    r"\b(?:hes|shes|theyre|is|are|esta|still) (?:\w+ )?(?:on|in) the (?:\w+ )?(?:floor|ground)\b|"
    r"\b(?:tirad[oa]|acostad[oa]|caid[oa]) en (?:el|la) (?:piso|suelo|bano|ducha|cocina)\b|"
    r"\b(?:esta|sigue|estan) (?:\w+ )?en el (?:piso|suelo)\b|"
    r"\bjust (?:dropped|fell over|went down)\b|\b(?:fell|fallen|se cayo|se cayeron|tripped|slipped|se resbalo|se trope"
    r"zo|resbalo|tropezo)\b|\bdropped (?:to "
    r"the floor|like a)\b|\bwent down\b|"
    r"\bcant get up\b|\bcant stand\b|\bwont get up\b|\bno se (?:levanta|para|mueve|incorpora)\b|"
    r"\bno (?:puede|pueda) (?:levantarse|pararse|moverse|caminar)\b|\bno se (?:puede|pueda) (?:levantar|parar|mover)\b"
    r"|\bwheez\w*|"
    r"\bpale\b|\bpalid[oa]\b|\bclammy\b|\bsweaty\b|\bsweating\b|\bsudando\b|\bgr[ae]y\b|\bgris\b|"
    r"\b(?:decaid[oa]|aletargad[oa]|sin fuerzas|lethargic|listless)\b|"
    r"\bshaking (?:really |so |very )?(?:hard|badly|uncontrollably)\b|\btemblando\b|\btiembla\b|"
    r"\bwont (?:respond|answer) to (?:me|us|anything)\b|\bcant feel (?:his|her|their|my) (?:arm|leg|face|legs|arms)\b")
BODY = re.compile(
    r"\bconfus\w*|\bnot making sense\b|\btalking (?:nonsense|gibberish|weird|funny|crazy)\b|\bdisoriented\b|"
    r"\bout of it\b|\bnot (?:herself|himself|themselves)\b|\bacting (?:strange|weird|odd|drunk|confused)\b|"
    r"\b(?:not|isnt|stopped|quit|no longer) sweating\b|\bno (?:esta )?suda\w*|\bdry (?:and hot|hot) skin\b|"
    r"\b(?:skin is (?:\w+ )?(?:hot and )?dry|dry skin)\b|\bnodding off\b|\bkeeps? (?:falling asleep|passing out)\b|"
    r"\bflushed\b|\b(?:hasnt|not|no) (?:peed|peeing|wet (?:a )?diapers?)\b|\bstopped making sense\b|"
    r"\bfeverish\b|\bhigh fever\b|\bfiebre (?:muy )?alta\b|\bmucha fiebre\b|\bno (?:quiere )?(?:comer|tomar|"
    r"beber|mamar|lactar)\b|"
    r"\b(?:confused|dizzy|weak) and (?:very |so |really )?(?:hot|cold)\b|\bhot to the touch\b|\bburning (?:hot|up)\b|"
    r"\b(?:hes|shes|he feels|she feels|skin|forehead|body) (?:is |feels )?"
    r"(?:so |"
    r"really |very )?hot\b|\bon fire to the touch\b|"
    r"\b(?:very|really|super|so|bright) red\b|\b(?:esta|muy) (?:roj[oa]|calient[ea]|ardiendo)\b|\bardiendo\b|"
    r"\bdizz\w*|\blight ?headed\b|\bmarea\w*|\bvomit\w*|\bthrowing up\b|\bthrew up\b|\bpuk\w*|"
    r"\b(?:about to|going to|gonna|feel like i(?:m| am)? (?:going to|gonna)) (?:pass out|faint|black out)\b|"
    r"\bme voy a desmayar\b|\bwont (?:drink|eat|feed)\b|\bnot (?:drinking|eating|feeding)\b|\bno (?:quiere )?(?:come|t"
    r"oma|bebe)\b|"
    r"\b(?:so|really|very|super) (?:sleepy|drowsy|tired|weak)\b|\bcan barely (?:wake|keep|stay|stand)\b|"
    r"\bhard to wake\b|\bletharg\w*|\bsomnolient\w*|\bcold (?:to the touch|and blue|and pale)\b|"
    r"\b(?:hes|shes|is|are|feels?|felt|skin|hands|feet|body) (?:so |really |very |ice |icy |freezing )?cold\b(?! (?:in|"
    r"out|outside|inside|here|there|weather|today|tonight))|\bis freezing\b(?! (?:in|out|outside|inside|here))|"
    r"\b(?:esta|se siente|la siento|lo siento) (?:muy )?(?:fri[oa]|helad[oa])\b|\bshiver\w*|"
    r"\b(?:shaking|temblando)\b|\bmorad[oa]\b|\bblue\b|\bweak\b|\bdebil\b|\bconfundid[oa]\b|\bdesorientad[oa]\b|"
    r"\bno (?:tiene sentido|dice nada coherente)\b|\bhabla (?:raro|incoherente)\b|\bheadache\b|\bnause\w*")

# Spanish has no subject pronoun: a 3rd-person verb on the state is the subject ("no me responde", "esta tirada").
# Sprint 8: an odd state after an ingestion ("está muy raro", "acting weird"), and a change in mental status that is a
# possible sign on its own for another person (calm line only: "my dad seems really out of it today")
_ODD = re.compile(r"\b(?:acting|actuando) (?:\w+ )?(?:weird|strange|odd|funny|raro|rara|extrano|extrana)\b|"
                  r"\b(?:esta|anda|se ve) (?:muy |bien )?(?:rar[oa]|dormid[oa]|adormilad[oa]|somnolient[oa]|"
                  r"extran[oa])\b|\b(?:really|very|so|super) (?:drowsy|sleepy|out of it)\b|\bdrowsy\b")
# Sprint 8: "i don't know if my dad is breathing", "no sé si respira": a live, uncertain report, never a conditional
_UNSURE_ALIVE = re.compile(r"\b(?:dont|do not|cant|cannot|not sure|unsure|no se|no estoy segur[oa]|no puedo saber)\b"
                           r"(?:\W+\w+){0,3}?\W+(?:if|whether|si)\b(?:\W+\w+){0,4}?\W+(?:breathing|breathes|alive|"
                           r"has a pulse|respira|respirando|vivo|viva|tiene pulso)\b|\b(?:cant|cannot|no puedo) "
                           r"(?:find|feel|encontrar|sentir) (?:a |his |her |their |el |su )?(?:pulse|heartbeat|"
                           r"pulso)\b")
# final round (pre-existing P0): stroke signs. A numb / weak / dead limb or face WITH a companion sign (suddenly,
# can't lift it, one side, drooping, slurred, confused); "my arm went numb from sleeping on it" is not one.
_LIMB_NUMB = re.compile(r"\b(?:cant|cannot|can no longer) feel (?:my|his|her|their) (?:\w+ )?(?:arm|leg|hand|face|"
                        r"side)\b|"
                        r"\b(?:cant|cannot|unable to) (?:move|feel|use|lift) (?:the |his |her |my |their )?(?:left |r"
                        r"ight "
                        r"|one )side\b|\bno (?:puede|puedo) mover (?:el|su|mi) lado\b|"
                        r"\bno (?:siento|siente) (?:el|la|mi|su) (?:brazo|pierna|mano|cara)\b|"
                        r"\b(?:arm|leg|hand|face|side|brazo|pierna|mano|cara|lado)s?\b(?:\W+\w+){0,3}?\W+(?:numb|dead|"
                        r"limp|weak|heavy|droopy|tingly|dormid[oa]|entumid[oa]|adormecid[oa]|debil|pesad[oa]|caid[oa]"
                        r")\b|"
                        r"\b(?:numb|numbness|weak|weakness|entumid\w*|adormecid\w*|durmio)\b(?:\W+\w+){0,3}?\W+(?:arm|"
                        r"leg|hand|face|side|brazo|pierna|mano|cara|lado)\b")
_STROKE_COMP = re.compile(r"\b(?:suddenly|all of a sudden|out of nowhere|cant (?:lift|move|raise|feel|hold)|wont (?:l"
                          r"ift|"
                          r"move)|droop\w*|slurr\w*|one side|left|right|confus\w*|cant (?:talk|speak)|de repente|"
                          r"izquierd[oa]|derech[oa]|no (?:puede|lo puede|la puede) (?:levantar|mover)|no habla bien|"
                          r"arrastra\w*)\b")
# final round (holdout class b): an overdose quantity, also inside a question ("what happens if i took 15 xanax")
_TOOK_QTY = re.compile(r"\b(?:took|taken|popped|downed|swallowed|tomo|tome|me tome|trague|se tomo)\b(?:\W+\w+){0,3}?"
                       r"\W+(?:[1-9]\d+(?!\s?(?:mg|ml|mcg|milligrams?|miligramos?)\b)|a handful|handful|whole|all (?:"
                       r"of )?(?:my|the|her|his)|too many|entire|a bunch|"
                       r"double|triple|todas|toda la|un punado|demasiad[oa]s)\b")
# last round (pre-existing P0): an infant with a fever AND lethargy / limpness / not feeding is a medical alert
_INFANT = re.compile(r"\b(?:baby|babies|babys|infant|newborn|preemie|\d+ ?(?:month|week|day)s?[- ]old|bebe|recien nac"
                     r"id[oa]|"
                     r"nene|nena)\b")
_FEVER = re.compile(r"\b(?:fever\w*|feverish|burning up|hot to the touch|temperature of|temp (?:of|is)|1(?:0[0-9])(?:"
                    r"\.\d)? ?"
                    r"(?:f|degrees)?|3[89](?:\.\d)? ?(?:c|grados)?|fiebre|calentura|ardiendo)\b")
_INFANT_SIGN = re.compile(r"\b(?:lethargic|listless|limp|floppy|wont (?:feed|eat|drink|nurse|take (?:a|her|his|the) "
                          r"bottle)|not (?:feeding|eating|nursing|drinking)|hard to wake|wont wake|barely (?:moving|a"
                          r"wake)|"
                          r"decaid[oa]|aletargad[oa]|no (?:quiere )?(?:comer|mamar|tomar|lactar|come|toma)|no se desp"
                          r"ierta|"
                          r"sin fuerzas|flojit[oa]|no reacciona)\b")
_LIMB_BENIGN = re.compile(r"\b(?:slept on|sleeping on|from sleeping|from the cold|from typing|after (?:the gym|working "
                          r"out|lifting|yoga)|dormi encima|por dormir|dentist|novocaine|anesthesia|anestesia)\b")
_MENTAL = re.compile(r"\b(?:confus\w*|out of it|not making sense|disoriented|confundid[oa]|desorientad[oa])\b"
                     r"(?! (?:about|by|with|over|on|regarding|why|what|how|when|where|which|sobre|con|por|de) )")
_ES_THIRD = re.compile(r"\b(?:esta|este|se (?:puso|desmayo|desplomo|cayo|esta)|no (?:me )?(?:responde|responda|"
                       r"contesta|respira|reacciona|despierta|se mueve)|tiene (?:los|la|el))\b")

# ---- HAZARD -------------------------------------------------------------------------------------------------------
_HEIGHT = (r"balcony|balcon|railing|rail|railings|barandal|baranda|barandilla|window ?(?:sill|ledge)|ledge|"
           r"cornisa|window|ventana|roof|rooftop|techo|azotea|edge|borde|stair ?well|landing")
_HEIGHT_ACT = (r"climb\w*|hanging|hangs|dangling|leaning (?:out|over)|lean\w* out|halfway out|sitting (?:on|in)|"
               r"sits on|standing (?:on|at)|stands on|perched|on the edge|over the (?:rail\w*|edge)|got (?:onto|on|up "
               r"on|out on)|crawl\w* (?:out|onto)|out (?:on|onto) the|pushed out|fell out|fell (?:from|off|out of)|"
               r"se cayo (?:de|del|por)|about to fall|could fall|"
               r"subiendo|se (?:esta )?(?:subiendo|subio|asoma\w*)|asomad[oa]|colgad[oa]|colgando|sentad[oa] en|"
               r"parad[oa] en|trepando|se va a caer|a punto de caer")
_WATER = r"pool|piscina|alberca|bath|bathtub|tub|tina|banera|lake|pond|lago|estanque|hot tub|jacuzzi|river|rio"
_WATER_ACT = (r"no sale|resbal\w*|slipped (?:in|into|under)|fell in|fell into|went in|in the water|under ?water|under t"
              r"he water|face ?down|boca abajo|"
              r"went under|not coming up|sinking|se cayo (?:a|en)|se esta ahogando|bajo el agua|"
              r"en el agua|drown\w*|ahog\w*|floating|flotando")
_UNWATCHED = (r"nobody (?:is )?(?:watching|with)|no one (?:is )?(?:watching|with)|alone|by (?:him|her|them)self|"
              r"unattended|unsupervised|nadie (?:lo|la|los)? ?(?:esta )?(?:cuidando|mirando|viendo)|sol[oa]")
CHILD_HEIGHT = re.compile(rf"\b(?:{_HEIGHT})\b(?:\W+\w+){{0,8}}?\W+(?:{_HEIGHT_ACT})|(?:{_HEIGHT_ACT})(?:\W+\w+)"
                          rf"{{0,6}}?\W+(?:{_HEIGHT})\b")
CHILD_EDGE = re.compile(r"\b(?:is|are|esta|got|gets|climbed|se subio)\s+(?:up\s+)?(?:on|onto|on top of|sobre|en|al|a "
                        r"la)\s+(?:the |el |la |a )?(?:\w+ )?(?:railing|rail|ledge|sill|edge|roof|barandal|baranda|cor"
                        r"nisa|"
                        r"azotea|techo|borde)\b")
CHILD_WATER = re.compile(rf"\b(?:{_WATER})\b(?:\W+\w+){{0,8}}?\W+(?:{_WATER_ACT})|(?:{_WATER_ACT})(?:\W+\w+)"
                         rf"{{0,6}}?\W+(?:{_WATER})\b")
UNWATCHED_IN_WATER = re.compile(rf"(?:{_UNWATCHED})\b(?:\W+\w+){{0,8}}?\W+(?:in the (?:water|pool)|en el agua|en la "
                                rf"piscina)|(?:in the (?:water|pool)|en el agua|en la piscina|fell in|se cayo)"
                                rf"(?:\W+\w+){{0,8}}?\W+(?:{_UNWATCHED})")
EXPOSURE = re.compile(
    r"\b(?:ac|a/c|air|air conditioning|aircon|heat|heating|heater|furnace|cooling)\s+(?:just |completely )?(?:quit|die"
    r"d|"
    r"gave out|stopped working|wont turn on|isnt cooling|isnt working|is not working)\b|\bno (?:cooling|heating)\b|"
    r"\bse (?:descompuso|averio|apago|rompio|murio)\s+(?:el|la)\s+(?:aire|calefaccion|calentador|clima|minisplit)\b|"
    r"\b(?:aire|calefaccion|calentador|clima)\b(?:\W+\w+){0,2}?\W+(?:no (?:sirve|enfria|calienta|prende|funciona)|se "
    r"(?:descompuso|averio|apago))\b|"
    r"\b(?:no|without) (?:ac|a/c|air|air conditioning|aircon|heat|heating|power)\b|\b(?:ac|a/c|air|air conditioning|ai"
    r"rcon|"
    r"cooling|heat|heating|heater|furnace|boiler|radiators?)(?: has| is|s| has been| was| been)? (?:\w+ )?(?:broken|"
    r"out|off|dead|died|down|not working|stopped|gone|busted)\b|\bheat ?wave\b|\b(?:9\d|1[0-2]\d) ?(?:degrees|f)?"
    r" (?:in here|inside|in the (?:apartment|unit|house))\b|\bits (?:9\d|1[0-2]\d)\b|\b(?:so|really|super|"
    r"extremely|insanely) hot (?:in here|inside)\b|\bin (?:this|the) heat\b|\b(?:outside|out) in the (?:sun|heat)\b|"
    r"\bplaying outside\b|\bfreezing (?:in here|inside|cold)\b|\bbelow freezing\b|\b(?:[0-4]\d) ?(?:degrees|f) "
    r"(?:in here|inside)\b|\bsin (?:aire|calefaccion|luz)\b|\b(?:el )?aire (?:acondicionado )?no (?:funciona|sirve|"
    r"prende)\b|\bno (?:hay|tenemos) (?:aire|calefaccion|luz)\b|\bcalefaccion no (?:funciona|sirve)\b|"
    r"\bhace (?:mucho |muchisimo |demasiado )?(?:calor|frio)\b|\bmucho (?:calor|frio)\b")
INGEST = re.compile(r"\b(?:swallow\w*|ate|eaten|eating|eats|drank|drunk|drinking|drinks|chewed|chewing|bit into|"
                    r"licked|got into|se (?:traga|come|toma|bebe)|traga|"
                    r"put (?:a |an |some )?\w+ in (?:his|her|their) mouth|se (?:trago|comio|tomo|bebio|metio)|trago|"
                    r"comio|bebio|ingirio)\b")
SUBSTANCE = re.compile(r"\b(?:prescriptions?|script|refills?|receta|bottle of (?:\w+ )?(?:pills|meds|tablets|"
                       r"advil|tylenol)|batter(?:y|ies)|button battery|coin battery|magnets?|pods?|"
                       r"laundry \w+|detergent|bleach|"
                       r"drain cleaner|drano|cleaner|cleaning \w+|chemicals?|antifreeze|rat poison|poison|pesticide|"
                       r"bug spray|lye|pills?|tablets?|meds|medicine|medication|edibles?|weed|nicotine|vape (?:juice|"
                       r"liquid)|pila|pilas|bateria|baterias|iman|imanes|cloro|lejia|detergente|veneno|pastillas?|"
                       r"medicin\w*|limpiador\w*|quimic\w*|jabon|"
                       # fix round: common medicines and household chemicals (EN + ES)
                       r"tylenol|advil|aspirin|ibuprofen|acetaminophen|paracetamol|xanax|valium|ambien|benadryl|"
                       r"oxycodone|oxycontin|oxys|percocet|vicodin|adderall|insulin|antidepressants?|sleeping pills|"
                       r"melatonin|zoloft|"
                       r"prozac|lithium|klonopin|clonazepam|seroquel|gabapentin|lighter fluid|gasoline|gasolina|"
                       r"kerosene|queroseno|paint thinner|thinner|aguarras|lamp oil|windshield (?:fluid|washer fluid)|"
                       r"mouthwash|nail polish remover|acetone|acetona|hand sanitizer|rubbing alcohol|essential oils?|"
                       r"ammonia|amoniaco|raticida|insecticida|veneno para ratas|weed killer|herbicida|fertilizer|"
                       r"motor oil|aceite de motor|lavavajillas|suavizante|blanqueador|vitamins?|vitaminas?|"
                       r"iron pills|gummy vitamins|vitamin gummies|melatonin gummies)\b")
# fix round: Spanish "tomó / bebió" is also "I take": only with a third-person subject ("mi hija tomó cloro")
_TOMO = re.compile(rf"\b(?:{_CHILD}|{_ELDER}|{_ADULT}|el|ella|alguien)s?\s+(?:\w+\s+){{0,2}}?(?:se\s+)?(?:tomo|bebio|"
                   rf"trago|comio|tomaron|bebieron|tragaron)\b")
# fix round: a child, baby, elder or pet shut in a vehicle (a hot car is a medical emergency, never a care line)
_IN_CAR = re.compile(rf"\b(?:{_CHILD}|{_ELDER}|{_PET})s?\b(?:\W+\w+){{0,3}}?\W+(?:locked|stuck|trapped|shut|left "
                     rf"(?:alone )?|alone|encerrad[oa]s?|atrapad[oa]s?|dejad[oa]s?|olvidad[oa]s?|sol[oa]s?)\s+"
                     rf"(?:\w+\s+)?"
                     rf"(?:in|inside|en|dentro del?)\s+(?:the |a |my |our |his |her |el |la |mi |un )?(?:hot |locked |"
                     rf"parked )?(?:car|vehicle|truck|van|suv|minivan|carro|coche|auto|camioneta)\b")
_LEFT_IN_CAR = re.compile(rf"\b(?:deje|left|forgot|olvide)\s+(?:a\s+)?(?:my|mi|the|el|la|our)?\s*(?:{_CHILD}|{_PET})s?"
                          rf"\s+(?:\w+\s+){{0,2}}?(?:in|en|inside|dentro del?)\s+(?:the |el |la |mi |my )?(?:hot )?"
                          rf"(?:car|carro|"
                          rf"coche|auto|truck|camioneta)\b")
_IN_CAR_NOT = re.compile(r"\b(?:stroller|car ?seat|bag|toys?|phone|keys|wallet|stuff|things|groceries|carriola|"
                         r"llaves|juguetes?|bolsa)\b")
_PET_TOXIC = re.compile(r"\b(?:chocolate|grapes?|raisins?|xylitol|gum|onions?|garlic|lilies|lily|antifreeze|uvas?|"
                        r"cebolla)\b")
_INGEST_CHILD = re.compile(rf"\b(?:{_CHILD}|{_ELDER}|{_PRONOUN})\b")
# Sprint 8: an UNKNOWN substance swallowed ("se tomó algo", "drank something under the sink"): with a body sign in
# the same message (or the next one, app.risk.detect) it is a poisoning report.
_SOMETHING = re.compile(r"\b(?:swallow\w*|ate|eaten|drank|drunk|took|taken|got into|se (?:trago|comio|tomo|bebio|"
                        r"metio)|trago|comio|tomo|bebio|ingirio)\b(?:\W+\w+){0,2}?\W+(?:something|anything|stuff|"
                        r"some(?:thing)? (?:from|under|in|out of)|algo|alguna cosa|unas? cosas?)\b")


def unknown_ingestion(t: str) -> bool:
    """A person swallowed something unknown or a product / medicine (normalised text)."""
    return bool(_SOMETHING.search(t) or (INGEST.search(t) and SUBSTANCE.search(t)))

# ---- property hazards: SOURCE x SIGN x EXTENT (no person needed) ---------------------------------------------------
_APPLIANCE = (r"stove|oven|range|burner|cooktop|dryer|water heater|heater|furnace|boiler|meter|gas line|pipe|grill|"
              r"fireplace|estufa|horno|calentador|boiler|caldera|medidor|tuberia de gas|secadora|parrilla")
_ODOUR = r"smell\w*|stink\w*|reek\w*|odou?r|stench|whiff|huele|olor|apesta"
_GAS_DESC = r"rotten egg\w*|eggs?|sulfur|sulphur|skunk|propane|natural gas|gas\b|huevo\w*|azufre|zorrillo"
_HISS = r"hiss\w*|siseo|silbido|silba|whoosh\w*|sise\w*"
_LEFT_ON = (r"left on|on all (?:night|day)|been on (?:for|all)|no flame|without (?:a )?flame|didnt light|unlit|"
            r"sin flama|sin llama")
_SYMPTOM = (r"head(?:ache| is (?:spinning|pounding|killing)| hurts)|dizz\w*|light ?headed|nause\w*|throwing up|"
            r"threw up|"
            r"vomit\w*|puk\w*|so sleepy|drows\w*|wont wake|cant wake|confus\w*|faint\w*|passed out|feel(?:s|ing)? "
            r"(?:sick|weird|off|awful)|dolor de cabeza|duele (?:la )?cabeza|mare\w*|vomit\w*|nausea\w*|somnolient\w*|d"
            r"esmay\w*")
_FUEL = (r"generator|charcoal|grill (?:inside|indoors|in the)|bbq inside|oven (?:open|door open|on) (?:for|to) (?:heat|"
         r"warm)|(?:open|opened|left) the oven (?:for|to)|car (?:running|on|idling) in (?:the )?garage|kerosene|propan"
         r"e "
         r"heater|space heater|water heater flame|flame (?:is |looks )?(?:yellow|orange|lazy|floppy)|yellow flame|"
         r"furnace|boiler|fireplace|generador|carbon|brasero|anafre|parrilla (?:adentro|dentro)|horno (?:abierto|prend"
         r"ido)"
         r"|calentador|caldera|chimenea|para calentar\w*|(?:flama|llama) (?:amarilla|naranja)")
_WATER_FLOW = (r"raining|overflow\w*|desbord\w*|leaking fast|no para de salir|shooting|spraying|gushing|pouring|rushing"
               r"|bursting|burst|streaming|flooding|sale a chorros|a chorros|"
               r"brotando|saliendo|entrando|cayendo|chorreando")
_WATER_EXTENT = (r"getting worse|in (?:two|three|four|several|multiple|\d+) (?:places|spots)|pulgadas|centimetros|"
                 r"sin parar|no para|ya hay|everywhere|all over|cant stop|wont stop|doesnt stop|filling|up to|inches|a"
                 r"nkles?|knees?|into the "
                 r"(?:hall|hallway|living|bedroom|next)|no para|por todos lados|por todas partes|muchisima|mucha agua|"
                 r"ya llego|tobillos|rodillas")
_STRUCT = (r"boards|deck boards|ceiling|roof|floor|floors|deck|balcony|stairs|staircase|steps|porch|beam|beams|joists?|"
           r"wall|walls|"
           r"walkway|railing|foundation|techos?|pisos?|pared(?:es)?|escaleras?|balcon(?:es)?|vigas?|barandal(?:es)?")
_STRUCT_FAIL = (r"snapp\w*|snapped|sway\w*|groan\w*|dipping|dipped|pulled loose|pulling loose|came loose|coming loose|"
                r"ripped (?:off|away)|despegand\w*|desprend\w*|sank|sinking|sunk|leaning|tilting|tilted|buckl\w*|crumb"
                r"l\w*|giving way|gave way|pulling away|"
                r"separat(?:ing|ed|es) (?:from|away)|caving|caved|sagging|sags|bulg\w*|dropped|dropping|collaps\w*|com"
                r"ing down|came down|"
                r"falling (?:apart|down|off|in)|cracking (?:loud|and|sound)|hundi\w*|inclinad\w*|derrumb\w*|"
                r"separand\w*|cayendo|se (?:cae|cayo|vino abajo)|vencid\w*|abombad\w*")
_ACTOR = (r"someone|somebody|a (?:man|guy|woman|person|stranger|dude)|(?:the|that|this|some) (?:man|guy|woman|"
          r"person|stranger|dude)|strangers?|intruders?|my ex|ex|alguien|un (?:hombre|tipo|senor|desconocido)|"
          r"una (?:mujer|persona)|mi ex(?:esposo|novio|pareja)?")
_FORCE = (r"jiggl\w*|rattl\w*|yank\w*|pry\w*|pried|kick\w*|bang\w*|pound\w*|forc\w*|try\w* (?:to )?(?:open|get in|"
          r"break)|tries (?:to )?(?:open|get)|turning|twist\w*|pull\w* on|pushing on|picking|tratando de (?:abrir|entr"
          r"ar|"
          r"forzar)|intentando (?:abrir|entrar|forzar)|forzando|golpeando|pateando|abriendo")
_ENTRY_OBJ = (r"door|doors|door ?handle|door ?knob|handle|knob|lock|locks|deadbolt|window|windows|slider|sliding door|"
              r"patio door|screen|puerta|ventana|cerradura|manija|perilla|chapa")


def _near_re(a: str, b: str, gap: int = 8) -> re.Pattern[str]:
    g = rf"(?:\W+\w+){{0,{gap}}}?\W+"
    return re.compile(rf"\b(?:{a})\b{g}(?:{b})\b|\b(?:{b})\b{g}(?:{a})\b")


GAS_FRAME = [_near_re(_ODOUR, _GAS_DESC, 6), _near_re(_HISS, _APPLIANCE + "|" + _ODOUR, 8),
             _near_re(_LEFT_ON, _ODOUR + "|" + _SYMPTOM, 12)]
CO_FRAME = [_near_re(_FUEL, _SYMPTOM, 14)]
FLOOD_FRAME = [_near_re(r"water|agua|it|inodoro|toilet|tub|sink|lavabo|tina", _WATER_FLOW, 4),
               _near_re(_WATER_FLOW, _WATER_EXTENT, 10)]
STRUCT_FRAME = [_near_re(_STRUCT, _STRUCT_FAIL, 6)]
ENTRY_FRAME = [_near_re(_ACTOR, _FORCE, 5), _near_re(_FORCE, _ENTRY_OBJ, 4)]


_FABRIC = (r"shirt|sleeve|sleeves|hair|clothes|clothing|dress|pants|robe|apron|skirt|jacket|blanket|towel|curtains?|"
           r"oven mitt|camisa|manga|pelo|cabello|ropa|vestido|toalla|cortinas?")
_IGNITE = r"caught|catching|went up|lit up|se prendi\w*|se encendi\w*|agarro fuego"
_HEAT_SRC = (r"stove|burner|candle|fireplace|heater|grill|gas range|cooktop|lighter|estufa|vela|chimenea|calentador|"
             r"parrilla")
FABRIC_FIRE = [_near_re(_FABRIC, _IGNITE, 3), _near_re(_IGNITE, _HEAT_SRC, 5)]


WATER_ELEC = [_near_re(r"water|agua|leak\w*|puddle|drip\w*|gotea\w*", r"reaching|touching|getting (?:close )?to|"
                       r"close to|"
                        r"next to|near|around|onto|into|under|behind|toward|towards|heading for|llegando a|llega a|"
                        r"cerca de|hacia|junto a|al lado de|pegad[oa] a|by|beside|en", 4),
              re.compile(r"\b(?:outlets?|plugs?|power ?strips?|cords?|extension cords?|wires?|wiring|electrical panel|"
                         r"panel|breaker\w*|fuse ?box|enchufes?|tomacorrientes?|cables?|regletas?)\b")]


# Spanish "llamas" = flames only in a fire context (not "you call", not the animal)
_ES_PLACE = (r"cocina|ventana|ventanas|puerta|sala|cuarto|recamara|habitacion|departamento|apartamento|casa|edificio|"
             r"pasillo|balcon|techo|pared|horno|estufa|sarten|cortinas?|sofa|sillon|cama|basura|bote|enchufe|contacto|"
             r"secadora|carro|coche|garaje|cochera|escalera|closet|bano|microondas|tostador|lavanderia|ropa|arriba|"
             r"abajo|unidad|vecino|vecina|edificio|terraza|patio|cuarto de al lado")
# Spanish flames / burning: a fire verb, or "llamas" WITH a place that should not burn (not "you call", the animal,
# a toy, or a fireplace / candle burning normally). Burning a PERSON ("está ardiendo" = fever) is not a fire.
_FIRE_ES = re.compile(
    rf"\b(?:hay|salen|sale|saliendo|veo|vi|se ven|echando|echa|entre)\s+(?:unas |muchas |grandes |las )?llamas\s+"
    rf"(?:en|de|del|por|desde|saliendo de)\s+(?:el |la |los |las |mi |su |un |una |nuestr\w+ )?(?:\w+ )?"
    rf"(?:{_ES_PLACE})\b|"
    rf"\bllamas\s+(?:en|de|del|por|saliendo de|que salen de)\s+(?:el |la |los |las |mi |su |un |una )?(?:\w+ )?"
    rf"(?:{_ES_PLACE})\b|\b(?:{_ES_PLACE})\b(?:\W+\w+){{0,3}}?\W+(?:esta |estan )?(?:echando|con|en) llamas\b|"
    rf"\b(?:esta|estan|se esta|se estan|sigue|siguen)\s+(?:ardiendo|incendiando|quemando)\s+(?:el|la|los|las|mi|su)\s+"
    rf"(?:{_ES_PLACE})\b|\b(?:el|la|los|las|mi|su)\s+(?:{_ES_PLACE})\s+(?:\w+ )?(?:esta|estan|se esta|sigue)\s+"
    rf"(?:ardiendo|incendiando|quemando)\b|\b(?:se (?:prendio|prendieron|incendio|esta quemando)|prendi\w* fuego|"
    rf"agarr\w* fuego|se (?:le |les )?prendio fuego)\b")
_NOT_FIRE_ES = re.compile(r"\b(?:zoo\w*|granja|farm|alpacas?|animal\w*|peluche|juguetes?|tienda|lana|wool|chimenea|"
                          r"fogata|velas?|estufa de lena|asador|bonit\w*|me llamas|te llamas|"
                          r"nos llamas|"
                          r"(?:tu|usted) (?:me )?llamas|llamas (?:a|al|por telefono|mas tarde|manana))\b")


# Something heavy fell / collapsed ON a person ("se le cayó la repisa encima a mi hijo", "the dresser fell on her")
FELL_ON_PERSON = re.compile(
    rf"\b(?:{_CHILD}|{_ELDER}|{_ADULT}|{_PRONOUN})s?\s+(?:is |are |got |was |s )?(?:pinned|trapped|stuck|crushed)"
    rf"(?:\s+(?:under|beneath|underneath|by|between))?\b|\b(?:pinned|trapped|stuck|crushed)\s+(?:under|beneath|"
    rf"underneath)\b|\b(?:atrapad[oa]|aplastad[oa]|prensad[oa])s?\b|"
    rf"\b(?:fell|falls|collapsed|came down|toppled|tipped|tipped over|toppled over|landed|crashed)\s+(?:on|onto|on top "
    rf"of)\s+"
    rf"(?:my |the |his |her |a |our )?"
    rf"(?:\w+ )?(?:{_CHILD}|{_ELDER}|{_ADULT}|{_PRONOUN})s?\b|\bse (?:le |les |me )?(?:cay[oó]|cayeron|vino abajo|"
    rf"desplom[oó])\b(?:\W+\w+){{0,5}}?\W+(?:encima|sobre)\b(?:\W+\w+){{0,4}}?\W+(?:{_CHILD}|{_ELDER}|{_ADULT}|"
    rf"[eé]l|ella)\b")


_BP = re.compile(r"\b(?:bp|blood pressure|presion|tension|cuff|monitor)\b(?:\W+\w+){0,4}?\W+(\d{2,3})\s*(?:over|"
                 r"/|sobre)\s*"
                 r"(\d{2,3})\b")
_HR = re.compile(r"\b(?:heart ?rate|pulse|hr|bpm|heartbeat|ritmo cardiaco|pulso|frecuencia cardiaca|latidos)\b"
                 r"(?:\W+\w+){0,4}?\W+(\d{2,3})\b|\b(\d{2,3})\s*bpm\b")
_SYMPTOM_RE = re.compile(r"\b(?:headache|dolor de cabeza|duele (?:mucho )?(?:la cabeza|el pecho)|chest|pecho|"
                         r"dizz\w*|mare\w*|faint\w*|pass out|desmay\w*|"
                         r"confus\w*|vision|blurry|short of breath|cant breathe|sweat\w*|nause\w*|vomit\w*|numb\w*|"
                         r"pounding|racing|palpitat\w*)\b")


def _vital_danger(s: str) -> bool:
    """Sprint 7: a blood pressure >= 180 systolic (or >= 120 diastolic) or a heart rate >= 150 or <= 40."""
    for m in _BP.finditer(s):
        sys_, dia = int(m.group(1)), int(m.group(2))
        if sys_ >= 180 or dia >= 120 or (sys_ <= 80 and dia <= 50):
            return True
    for m in _HR.finditer(s):
        v = int(m.group(1) or m.group(2))
        if v >= 150 or 20 <= v <= 40:
            return True
    return False


_HEAD_HIT = re.compile(r"\b(?:hit|struck|bumped|banged|smacked|whacked|slammed|cracked|landed on|fell on|golpe\w*|pego|"
                       r"se pego|se golpeo)\b(?:\W+\w+){0,4}?\W+(?:head|heads|forehead|skull|cabeza|frente)\b|"
                       r"\b(?:head|heads|cabeza)\b(?:\W+\w+){0,3}?\W+(?:hit|injury|wound|trauma|golpe)\b")
_HEAD_SIGN = re.compile(r"\b(?:drows\w*|sleepy|wont stay awake|keeps falling asleep|confus\w*|vomit\w*|throwing up|"
                        r"threw up|dizzy|not making sense|unequal pupils|somnolient\w*|adormilad\w*|confundid\w*|"
                        r"vomit\w*|mareado|mareada|sangre del oido|bleeding from (?:the|her|his) ear)\b")


# fix round: "i tried to put it out but it's spreading", "no puedo apagarlo": a live fire with no fire word
_CANT_PUT_OUT = re.compile(r"\b(?:tried to|trying to|try to|cant|cannot|couldnt|unable to) (?:\w+ )?put (?:it|the fire|"
                           r"the flames|them) out\b|\b(?:fire|flames?|grease|pan|stove|oven|burner|it)\b"
                           r"(?:\W+\w+){0,2}?\W+(?:wont|doesnt|isnt) (?:go|going) out\b"
                           r"(?! (?:of|with|tonight|today|anymore|to))|\bno (?:puedo|pude|podemos) "
                           r"apagar\w*|\bno se (?:apaga|quiere apagar)\b")


def _hazard(s: str) -> tuple[str, str] | None:
    """Property / intruder hazards composed from a source, a sign and an extent."""
    if FELL_ON_PERSON.search(s):
        return "medical", "something heavy fell on a person"
    if _CANT_PUT_OUT.search(s):
        return "fire_smoke", "a fire the person cannot put out"
    if _FIRE_ES.search(s) and not _NOT_FIRE_ES.search(s):
        return "fire_smoke", "flames (Spanish) in a fire context"
    if all(p.search(s) for p in WATER_ELEC) and re.search(r"\b(?:water|agua|leak\w*|puddle|drip\w*|"
                                                          r"gotea\w*)\b(?:\W+\w+)"
                                                          r"{0,6}?\W+(?:reaching|touching|getting|close|next|near|"
                                                          r"around|onto|into|under|behind|toward|towards|heading|"
                                                          r"llegando|llega|cerca|hacia|junto|lado|pegad[oa]|by|"
                                                          r"beside|en)\b"
                                                          r"(?:\W+\w+){0,4}?\W+(?:outlets?|plugs?|power ?strips?|cords"
                                                          r"?|"
                                                          r"wires?|wiring|panel|breaker\w*|fuse ?box|enchufes?|"
                                                          r"tomacorrientes?|cables?|regletas?)\b", s):
        return "electrical", "water reaching something electrical"
    if all(p.search(s) for p in FABRIC_FIRE):
        return "fire_smoke", "clothing or fabric caught on a heat source"
    if all(p.search(s) for p in ENTRY_FRAME):
        return "personal_safety", "someone forcing an entry point"
    if CO_FRAME[0].search(s):
        return "co", "fuel-burning source with symptoms"
    if any(p.search(s) for p in GAS_FRAME):
        return "gas", "gas smell / hiss / unlit burner"
    if all(p.search(s) for p in FLOOD_FRAME):
        return "flood", "water flowing with an uncontrolled extent"
    if STRUCT_FRAME[0].search(s):
        return "structural", "a structural part failing"
    return None


# ---- self-harm (veiled) -------------------------------------------------------------------------------------------
_SH_FAREWELL = re.compile(
    r"\b(?:writing|sending|this is|here is|heres) my (?:last|final) (?:message|text|note|letter|words)\b|"
    r"\bescrib\w* (?:las |unas |mis )?cartas (?:para|a)\b|\b(?:carta|cartas|nota|notas|mensaje) de despedida\b|"
    r"\bgoodbye (?:letters?|notes?)\b|\bthis is (?:my )?(?:goodbye|farewell)\b|\b(?:my|a) (?:final"
    r" |last )?goodbye\b|\b(?:said|say|saying|said all) "
    r"(?:my )?goodbyes?\b|"
    r"\b(?:wrote|written|writing|left) (?:\w+ )?(?:letters?|notes?) (?:for|to) (?:my|the|everyone)\b|"
    r"\besta es mi despedida\b|\bme despido\b|\bdespedirme\b|\badios para siempre\b|\bgoodbye forever\b|"
    r"\bthank(?:s| you) for everything\b(?=.*\b(?:goodbye|bye|done|end|last)\b)|\bdeje (?:unas )?cartas\b")
_SH_FINAL = re.compile(
    r"\b(?:wont|will not|not going to) (?:be needing|need) (?:\w+ ){0,2}(?:anything|anymore|after|it|them)\b|"
    r"\bafter tonight\b|\bnot coming (?:back|down|home)\b|\bi(?:m| am) done\b(?! with (?:the|my|this) (?:form|"
    r"lease|application|request|apartment))|\bdont want to do this anymore\b|\bcant do this anymore\b|"
    r"\b(?:fall )?(?:asleep|sleep) and (?:not|never) (?:have to )?wake\b|\bnot (?:have to )?wake up (?:again|ever)\b|"
    r"\bno (?:volver a )?despertar\w*|\bdormirme y no despertar\b|\bya tengo todo listo\b|\bya no quiero seguir\b|"
    r"\bdisappear (?:tonight|forever)\b|"
    r"\bits (?:all )?over for me\b|\bthe end for me\b|\bmade my (?:plans|decision|peace)\b|\bnunca mas\b|"
    r"\bno quiero (?:volver a )?despertar\w*|\b(?:esta noche|hoy) me voy\b|\bme voy (?:esta noche|para siempre|hoy)\b|"
    r"\b(?:im|i am) (?:leaving|going|gone) (?:tonight|for good|forever)\b|\bno puedo mas\b|\bya no puedo\b|\bdont want"
    r" to wake up\b|\bafter (?:this"
    r"|the) (?:weekend|week|month)\b|\b"
    r"by (?:tomorrow|morning|monday)\b|\bya no voy a estar\b|"
    r"\bno voy a estar (?:aqui|mas|manana)\b|\b(?:wont|will not|not going to) be (?:here|around|alive) (?:tomorrow|any"
    r"more|"
    r"much longer|for (?:it|that|long)|by)\b|\b(?:dont think|not sure|doubt) i(?:ll| will)? be (?:around|here|alive)\b|"
    r"\bi dont care\b(?! (?:what|which|when|how|about the|if (?:you|they|it)))|\bits (?:really |too )?deep\b|\bya no a"
    r"guanto\b|\bno aguanto mas\b|\bno point anymore\b|"
    r"\btheres no point\b|\bya no tiene sentido\b|\b(?:dont|cant|do not) see (?:a|any) way out\b|\bno (?:veo|hay|tengo"
    r") "
    r"salida\b|\btonight (?:i(?:m| am| will|ll)? )?(?:going to |gonna )?(?:fix\w*|end\w*|do\w*|finish\w*|take care of|"
    r"taking care of) (?:that|it|this|thats|its)\b|"
    r"\bno (?:pienso|voy a) bajar\b|\bnot (?:going|planning) to come down\b")
_SH_METHOD = re.compile(
    r"\b(?:pills|meds|pastillas|tablets) (?:\w+ ){0,3}(?:counted|lined up|ready|on the table|in front of me|aqui|"
    r"listas)\b|\b(?:counted|lined) (?:out|up) (?:\w+ ){0,2}(?:pills|meds)\b|\b(?:rope|noose|razor|blade|gun|cuerda|"
    r"soga|navaja|pistola)\b|\b(?:roof|rooftop|ledge|bridge|parking garage|top floor|azotea|puente|cornisa)\b|"
    r"\btengo (?:las|mis) pastillas\b|\b(?:la |una )?(?:cuerda|soga) (?:\w+ )?(?:lista|preparada|colgada|amarrada)\b|"
    r"\btengo (?:la|una) (?:cuerda|soga|navaja|pistola)\b|\bahorca\w*|\bcolgarme\b|\bcortarme\b|\btirarme\b")
_SH_INJURY = re.compile(r"\b(?:been|keep|started) cutting\b(?! (?:the|my|a|an|some|grass|hair|wood|back|"
    r"down|coupons|class|it)\b)|\bcutting (?:myself|again)\b|\bcut myself\b|"
    r"\b(?:burn|burned|burning|hurt|hurting) myself\b|(?<!se )\bme (?:corto|corte|lastimo|quemo)\b(?! (?:con|cocinando"
    r"|sin querer|por accidente))")
# Explicit intent with a means: enough on its own ("me voy a tirar del balcon", "i'm going to jump off the roof").
_SH_INTENT = re.compile(
    r"\b(?:tonight|today|this weekend|esta noche|hoy)\b(?:\W+\w+){0,5}?\W+(?:end|ending|acabar con|terminar con) "
    r"(?:it all|everything|my life|todo|mi vida)\b|\b(?:im|i am)? ?(?:going to|gonna|will|ll) end (?:it all|"
    r"everything|my life)\b|\bvoy a (?:acabar|terminar) con (?:todo|mi vida)\b|"
    r"\b(?:cuerda|soga|rope|noose)\s+(?:\w+\s+)?(?:lista|preparada|colgada|amarrada|ready|set up|tied|hanging)\b|"
    r"\bpara (?:ahorcarme|colgarme|matarme|cortarme|tirarme|aventarme|morirme)\b|"
    r"\b(?:voy a|me voy a|quiero)\s+(?:ahorcarme|colgarme|cortarme las venas|matarme)\b|"
    r"\bme (?:corte|corto|cortaba|abri) (?:las |la )?(?:venas|munecas|muneca)\b|\bcut (?:open )?(?:my|both) "
    r"(?:wrists?|veins)\b|\bslit my wrists?\b|"
    r"\b(?:voy a|me voy a|quiero|i(?:m| am) (?:going|gonna) to|im gonna|i will|ill|about to)\s+(?:tirarme|aventarme|"
    r"tirar|aventar|lanzarme|jump|step off|throw myself)\b|\b(?:jump|jumping|step off|tirarme|aventarme)\s+(?:off|from|"
    r"de|del|desde|por)\s+(?:the |a |my |el |la |un |una )?(?:\w+ )?(?:balcon\w*|roof|rooftop|bridge|ledge|window|vent"
    r"ana|"
    r"puente|azotea|edificio|building|garage)\b")
_SH_GIVING = re.compile(r"\b(?:gave|giving|give) (?:away )?(?:my|all my) (?:\w+ )?(?:dog|cat|pets?|things|stuff|"
                        r"belongings|plants)\b(?! (?:to the shelter because|back))|\bregal\w* (?:mis|mi) (?:cosas|perr"
                        r"[oa]|gat[oa])\b")
_SH_BURDEN = re.compile(
    r"\bnadie me (?:va a )?extran\w*|\bno one (?:will|would) (?:even )?(?:miss me|notice)\b|\bnobody (?:will|would) "
    r"(?:even )?(?:miss me|notice)\b|\b(?:would|will|d) be (?:better|quieter|easier|happier|fine|lighter) "
    r"without me\b|\bestarian mejor sin mi\b|\bbetter off (?:if i (?:just )?(?:disappeared|was gone|wasnt here)|withou"
    r"t me)\b|"
    r"\b(?:soy|im) (?:una carga|a burden)\b|\bnadie (?:me )?(?:quiere|necesita)\b|\bno one (?:cares|needs me)\b|"
    r"\b(?:not going to|wont|will not|wont ever) be a (?:problem|burden|bother) (?:for|to) (?:anyone|anybody|you|"
    r"everyone)\b|\bya no (?:voy a )?(?:ser|molestar) (?:una carga|a nadie)\b")
_SH_CLOSURE = re.compile(r"\bthank(?:s| you) for everything\b|\bgracias por todo\b|\btake care of (?:yourself|"
                         r"everyone|my \w+)\b|\bi love you all\b|\btell (?:my \w+|everyone|them) (?:that )?i love\b|"
                         r"\bcuiden a\b|\blos quiero (?:a todos|mucho)\b|\bforgive me\b|\bperdonenme\b|"
                         r"\b(?:just )?want(?:ed)? (?:someone|somebody|you|anyone) to know\b|\bthats all\b|"
                         r"\bmake sure my \w+ (?:gets?|is|are) (?:fed|ok|okay|taken care|looked after)\b|"
                         r"\bthats it\b|\bdont (?:try to )?(?:stop|find) me\b|\bno me busquen\b")
_SH_EXCLUDE = re.compile(r"\bgoodbyes? to (?:this|the|my|our|that) (?:old )?(?:apartment|place|unit|building|"
                         r"neighbou?rhood|city|town|area|house|home|lease|job|office|team|pool|gym)\b|\b(?:moving|move"
                         r" out|moved|lease|new (?:place|apartment|job|city)|relocat\w*|transfer\w*|"
                         r"mudanza|mudo|mudamos|me mudo)\b")
_BODYPART = re.compile(r"\b(?:lips|face|skin|fingers?|fingertips|nails|chest|eyes|mouth|throat|tongue|arm|arms|leg|"
                       r"legs|head|neck|labios|cara|piel|boca|ojos|pecho|garganta|lengua|brazo|cabeza|una?s)\b")
_AFTERMATH = re.compile(r"\b(?:repaint|paint|fix|replace|repair|clean\w*|patch|inspect|look at|check|repar\w*|"
                        r"arregl\w*|pint\w*|limpi\w*|revis\w*|cambi\w*)\b")
_LIVE_HAZARD = re.compile(r"\b(?:right now|again|spreading|pouring|coming (?:out|in|from|under)|going off|flames?|"
                          r"smoke (?:is|coming)|burning now|on fire|sparking|hissing|ahora mismo|otra vez)\b")
_SELF_REF = re.compile(r"\b(?:i|im|ive|me|my|myself|yo|me|mi|estoy|tengo|quiero)\b")

# ---- framing ------------------------------------------------------------------------------------------------------
_SENT = re.compile(r"(?<=[.!?;])\s+|\n+")
_IF = re.compile(r"\b(?:if|what if|in case|when|si|en caso de que|cuando)\b")
_EVENT_HYPO = re.compile(r"\b(?:ever|were to|happens? to|gets|starts|stops|has an?|had an?|chokes|falls|collapses|"
                         r"faints|passes out|goes (?:limp|blue|under)|swallows|drinks|eats|alguna vez|llegara a|"
                         r"le da|empieza|deja de)\b")
_QUESTION = re.compile(r"\?|^\s*(?:is|are|does|do|should|can|could|what|how|when|where|who|why|will|would|es|que|como|"
                       r"cuando|donde|debo|puedo|hay)\b")
_PAST = re.compile(r"\b(?:last (?:year|month|week|summer|winter|spring|fall|time|christmas)|(?:years?|months?|weeks?) "
                   r"ago|a (?:while|few (?:months|years|weeks)) (?:ago|back)|back in|in (?:19|20)\d\d|used to|when "
                   r"(?:he|she|i|we|they) (?:was|were) (?:little|young|a baby|younger)|once (?:had|when)|el ano pasado|"
                   r"hace (?:\w+ )?(?:anos|meses|semanas|ano|mes)|cuando (?:era|eramos) (?:nin[oa]|chic[oa])|"
                   r"(?:had|tuvo|tuve) (?:a|an|un|una) \w+ (?:last|in|hace|el ano))\b")
_NOWISH = re.compile(r"\b(?:now|right now|still|currently|again|todavia|ahora|sigue|ya mismo|at the moment)\b")
_SIGNS_Q = re.compile(r"\b(?:signs?|symptoms?|warning signs?) (?:of|for|that)\b|\bwhat does (?:a |an )?\w+ look like\b|"
                      r"\bhow (?:do|can|would|will) (?:i|you|we|someone) (?:know|tell|recogni[sz]e|spot)\b|"
                      r"\b(?:senales|sintomas) de\b|\bcomo (?:se|sabes?|saber) (?:si|cuando)\b")
_MEDIA = re.compile(r"\b(?:watching|watched|reading|read|saw|seen) (?:a |an |the |this )?(?:show|movie|film|series|"
                    r"episode|documentary|video|clip|novel|book|story|article|post|news|tiktok|reel)|\b(?:show|movie|"
                    r"film|novel|book|episode|documentary|podcast|game|article|story|the news|noticias|pelicula|serie|"
                    r"novela|libro)\b(?:\W+\w+){0,4}\W+(?:where|about|said|says|with|in which|donde|sobre|dijo|dice)\b|"
                    r"\bin (?:another|a different|some other) (?:city|state|building|town|country)\b")
_DRILL = re.compile(r"\b(?:drill|drills|simulacro|simulacros|practice evacuation|testing the (?:\w+ )?(?:alarms?|"
                    r"detectors?|sprinklers?)|alarm test|(?:alarm|detector|sprinkler)s? (?:test|testing|inspection)|"
                    r"prueba de (?:alarma|incendio)s?|cpr class|first aid class|safety class|training)\b")
_POLICY_Q = re.compile(
    r"(?:^|[.?!]\s*)\s*(?:does|do|is|are|will|can|could)\b(?:\W+\w+){0,6}\W+(?:come with|have|has|include\w*|provide\w"
    r"*|equipped|"
    r"allowed|permitted|installed|up to code|fenced|code|required|available|safe for|childproof\w*|policy|gated|"
    r"locked|secured?|supervised|lifeguards?|covered|accessible|safe)\b|"
    r"\b(?:what(?:s| is)|whats) the (?:policy|rule|procedure|protocol|plan)\b|\b(?:policy|rules?) (?:on|about|for)\b|"
    r"\b(?:tienen|tiene|hay|incluye\w*|se permite\w*|permiten|esta permitido)\b(?:\W+\w+){0,4}\W+(?:detector\w*|"
    r"alarma\w*|extintor\w*|salvavidas|rociador\w*|barandal\w*|reja\w*|cerca)\b|\bis there an? (?:aed|"
    r"defibrillator|extinguisher|sprinkler)\b")
_HISTORY_Q = re.compile(r"\b(?:history of|ever (?:been|had)|has there (?:ever )?been|have there (?:ever )?been|any "
                        r"(?:past|previous|prior)|in the past|ha habido|hubo (?:alguna vez )?(?:un|una|algun)|alguna v"
                        r"ez "
                        r"(?:hubo|ha habido))\b")
_HABITUAL_NOT_NOW = re.compile(r"\b(?:sometimes|every (?:now and then|once in a while|so often)|occasionally|"
                               r"once in a while|a veces|de vez en cuando)\b(?=.*\b(?:not (?:right )?now|its off|not a"
                               r"t "
                               r"the moment|not happening now|ahora no|no ahorita)\b)")
_DEVICE = re.compile(
    r"\b(?:fire|smoke|co|carbon monoxide|gas|heat) (?:alarms?|detectors?|extinguishers?|sprinklers?|doors?|exits?|"
    r"escapes?|lanes?|drills?|stick|tv|bill|company|meter|line hookup|stove|range|grill|hazards?|risks?|safety|"
    r"codes?|inspections?|insurance|marshal)\b|\b(?:detector|alarma|simulacro|salida|puerta|"
    r"extintor)\w* de (?:humo|incendio|gas|monoxido(?: de carbono)?)\b")
_LIVE_DEVICE = re.compile(r"\b(?:going off|went off|goes off|sounding|beeping|blaring|screeching|screaming|shrieking|"
                          r"wailing|ringing|alarming|red light|flashing red|wont stop|keeps "
                          r"(?:going|beeping|sounding)|flashing|reading|says co|shows|sonando|suena|pitando)\b")


@dataclass
class RiskFrame:
    who: list[str] = field(default_factory=list)  # roles found: self / child / elder / adult / pet / pronoun
    states: list[str] = field(default_factory=list)  # tiers found: critical / weak / body
    hazards: list[str] = field(default_factory=list)  # height / water / exposure / ingestion / farewell ...
    category: str | None = None  # incident category for the notice (medical / poison / self_harm / ...)
    urgency: str = "none"  # emergency | possible | none
    ongoing: str = "unknown"  # now | past | hypothetical | media | drill | policy | joking | unknown
    template: str | None = None  # approved notice kind (before app.risk.category.refine)
    live_conditional: bool = False  # a stative sign about a specific subject inside "if" / a question
    look_alike: str | None = None  # media | drill | policy | device: framing that may downgrade a rule match
    reason: str = ""
    care_hint: str | None = None  # the calm line for a "possible" frame: danger (911) / unwell / distress

    @property
    def alert(self) -> bool:
        return self.urgency == "emergency" and self.ongoing in ("now", "unknown")

    @property
    def possible(self) -> bool:
        return self.urgency == "possible" or (self.urgency == "emergency" and not self.alert
                                              and self.ongoing not in ("media", "drill", "policy", "joking"))


_SOCIAL = re.compile(
    r"\b(?:not|isnt|wont|hasnt|doesnt|never|stopped)\s+(?:been\s+)?(?:responding|respond|answering|answer|replying|"
    r"reply|talking|talk)(?:\s+to\s+(?:me|us|my|our)\b)?(?:\s+(?:\w+\s+){0,2})?(?:texts?|calls?|messages?|emails?|"
    r"phone|dms?|about|regarding|on|over|for|since|in (?:days|weeks)|after)\b|"
    r"\bno (?:me )?(?:responde|contesta|conteste|responda)\s+(?:\w+\s+){0,2}(?:mensajes?|textos?|llamadas?|"
    r"correos?|whatsapp|telefono|sobre|acerca|por)\b|\b(?:office|leasing|management|maintenance|landlord|staff|"
    r"manager|super)\b(?:\W+\w+){0,4}\W+(?:not|isnt|wont|hasnt|never|no)\s+(?:\w+\s+)?(?:respond\w*|answer\w*|"
    r"repl\w*|contesta|responde)\b")


def _sentences(t: str) -> list[str]:
    return [s for s in _SENT.split(t) if s and s.strip()] or [t]


def _who(s: str) -> list[str]:
    roles = [r for r, p in WHO.items() if p.search(s)]
    if _ES_THIRD.search(s) and "pronoun" not in roles:
        roles.append("pronoun")
    return roles


# fix round: whitespace-led alternatives start only at the beginning of a whitespace run ((?<!\s)): linear
_FCLAUSE = re.compile(r"[,;:]+|(?<!\s)\s+-+\s+|\b(?:but|because|although|though|pero|porque|aunque)\b|"
                      r"(?<!\s)\s+(?=(?:and\s+)?(?:we|i|there|it|they|he|she)\s+(?:had|was|were|used to|did|got|"
                      r"once)\b)")
_ANY_SIGN = [CRITICAL, WEAK, BODY]


def _framing(s: str, whole: str, has_stative: bool) -> str:
    """Clause-local framing (fix round): if any clause that holds a sign reads as now, the sentence is now, so an
    added past clause or "not sure if this is an emergency, but" never re-frames a live sign."""
    clauses = [c for c in _FCLAUSE.split(s) if c and c.strip()]
    # a signs question or a media frame scopes its whole sentence ("what are the signs of a stroke, like face
    # drooping?"); past and "if" clauses are local
    if len(clauses) > 1 and not _SIGNS_Q.search(s) and not (_MEDIA.search(s) and not _NOWISH.search(s)):
        signed = [c for c in clauses if any(p.search(c) for p in _ANY_SIGN) or _hazard(c) or CHILD_HEIGHT.search(c)
                  or (INGEST.search(c) and SUBSTANCE.search(c)) or _SOMETHING.search(c)
                  or CHILD_WATER.search(c) or CHILD_EDGE.search(c)]
        if any(_framing_one(c, whole, bool(_STATIVE.search(c)) or has_stative) == "now" for c in signed):
            return "now"
    return _framing_one(s, whole, has_stative)


def _framing_one(s: str, whole: str, has_stative: bool) -> str:
    """now | past | hypothetical | media for one clause or sentence."""
    if _MEDIA.search(s) and not _NOWISH.search(s):
        return "media"
    if _PAST.search(s) and not _NOWISH.search(s):
        return "past"
    if _SIGNS_Q.search(s) and not (_SPECIFIC.search(s) and has_stative and not _GENERIC_RE.search(s)):
        return "hypothetical"  # "what are the warning signs of a stroke, like face drooping?"
    if _IF.search(s) and not re.match(r"^\s*(?:when|cuando)\b", s):
        specific = bool(_SPECIFIC.search(s)) and not _GENERIC_RE.search(s)
        if specific and has_stative and not _EVENT_HYPO.search(s):
            return "now"  # "if my dad can't breathe what do I do": a live report inside a conditional
        return "hypothetical"
    return "now"  # sprint 7 fix round: a laugh marker never changes the framing of a live sign


def analyse(message: str, recent: list[str] | None = None) -> RiskFrame:
    """Frame of the LAST message. `recent` adds hazard CONTEXT only (heat / cold exposure), never a state."""
    # late import: app.emergency imports app.risk.concepts
    from app.emergency import clean_for_frame, describes_current_situation, scan
    t = normalize(clean_for_frame(message))
    t = not_physical(_SOCIAL.sub(" , ", t))
    ctx = normalize(" . ".join((recent or [])[-2:]))
    f = RiskFrame()
    live_fire = bool(_LIVE_DEVICE.search(t) and re.search(r"\bsmok|\bflame|\bfire\b(?! drill)", t))
    if _DRILL.search(t) and not (CRITICAL.search(t) or live_fire or _LIVE_HAZARD.search(t)):
        f.look_alike = "drill"
    elif _MEDIA.search(t) and not _NOWISH.search(t):
        f.look_alike = "media"
    elif _QUESTION.search(t) and _POLICY_Q.search(t) and not (CRITICAL.search(t) or WEAK.search(t)):
        f.look_alike = "policy"
    elif (_SIGNS_Q.search(t) and not _SPECIFIC.search(t) and not _LIVE_HAZARD.search(t)
          and all(_SIGNS_Q.search(x) or not scan(x)[0] for x in _sentences(t))
          and (t.strip().endswith("?") or not describes_current_situation(message))):
        f.look_alike = "signs"  # "what are the signs that someone is having a stroke?" (no specific person)
    elif _QUESTION.search(t) and _HISTORY_Q.search(t) and not (CRITICAL.search(t) or _LIVE_HAZARD.search(t)):
        f.look_alike = "past"  # "has there ever been a fire in building A?", "any history of flooding?"
    elif _HABITUAL_NOT_NOW.search(t):
        f.look_alike = "past"  # "the fan sparks sometimes, not right now, it's off": a repair, not a live hazard
    elif _PAST.search(t) and (_AFTERMATH.search(t) or "?" in t) and not (CRITICAL.search(t) or _LIVE_HAZARD.search(t)):
        f.look_alike = "past"  # "there was a kitchen fire last month and the cabinets still smell, can you repaint?"
    elif _DEVICE.search(t) and not _LIVE_DEVICE.search(t) and not re.search(
            r"\b(?:smok\w*|flames?|burn\w*|smell\w*|huele|humo|llamas|fuego|spark\w*|chispa\w*|hiss\w*)\b",
            _DEVICE.sub(" ", t)):
        f.look_alike = "device"

    exposure = bool(EXPOSURE.search(t) or EXPOSURE.search(ctx))
    best: tuple[int, str, str, str, bool] | None = None  # (score, category, sentence, reason, live_conditional)
    for s in _sentences(t):
        roles = _who(s)
        crit, weak, body = CRITICAL.findall(s), WEAK.findall(s), BODY.findall(s)
        for name, found in (("critical", crit), ("weak", weak), ("body", body)):
            if found and name not in f.states:
                f.states.append(name)
        for r in roles:
            if r not in f.who:
                f.who.append(r)
        person = [r for r in roles if r != "pet"]
        cand: list[tuple[int, str, str]] = []
        if crit and (person or _BODYPART.search(s)):
            cand.append((3, "medical", "critical body state"))
        n_weak = len(set(weak))
        if person and n_weak >= 2:
            cand.append((3, "medical", "a person with two signs (e.g. on the floor and not responding)"))
        if person and n_weak >= 1 and len(set(body)) >= 1 and not (roles == ["self"]):
            cand.append((3, "medical", "a person with a sign and a body state"))
        if exposure and person and (len(set(body)) + n_weak >= 2 or crit):
            cand.append((3, "medical", "heat or cold exposure with body signs"))
        if person and len(set(body)) >= 2 and roles != ["self"] and re.search(
                r"\bconfus|not making sense|nonsense|disoriented|out of it|confundid|desorientad|incoherente|"
                r"slurr", s) and exposure:
            cand.append((3, "medical", "confusion with heat or cold"))
        if re.search(rf"\b(?:{_CHILD})\b", s) and (CHILD_HEIGHT.search(s) or CHILD_EDGE.search(s)):
            cand.append((3, "medical", "a child at a height (railing, window, roof edge)"))
            f.hazards.append("height")
        if (re.search(rf"\b(?:{_CHILD}|{_ELDER}|{_ADULT}|{_PRONOUN}|{_GENERIC})\b", s)
                and (CHILD_WATER.search(s) or UNWATCHED_IN_WATER.search(s))):
            cand.append((3, "medical", "a person in the water (fell in, face down, unwatched)"))
            f.hazards.append("water")
        if (_IN_CAR.search(s) and not _IN_CAR_NOT.search(_IN_CAR.search(s).group(0))) or _LEFT_IN_CAR.search(s):
            cand.append((3, "trapped", "a child, elder or pet shut in a vehicle"))
        if (INGEST.search(s) or _TOMO.search(s)) and SUBSTANCE.search(s) and (_INGEST_CHILD.search(s) or "self" in
                                                                               roles or person):
            cand.append((2, "poison", "a person swallowed a product or medicine"))
            f.hazards.append("ingestion")
        young_old = bool(re.search(rf"\b(?:{_CHILD}|{_ELDER})s?\b", s))
        if _SOMETHING.search(s) and (person or "self" in roles or _ES_THIRD.search(s)) and (
                crit or weak or _ODD.search(s) or (body and young_old)):
            # a child / elder with any body sign; an adult or the speaker needs a stronger sign ("i ate something
            # and feel sick" is not a poisoning alert)
            cand.append((3, "poison", "a person swallowed something unknown and has a body sign"))
            f.hazards.append("ingestion")
        if "pet" in roles and INGEST.search(s) and (
                SUBSTANCE.search(s) or _PET_TOXIC.search(s)):
            cand.append((1, "poison", "a pet swallowed something harmful (calm line; the notices are for people)"))
        mild = all(re.match(r"vitamin|vitamina|gummy|melatonin", x) for x in SUBSTANCE.findall(s))
        if _INFANT.search(s) and _FEVER.search(s) and _INFANT_SIGN.search(s):
            cand.append((3, "medical", "an infant with a fever and lethargy or not feeding"))
        if _TOOK_QTY.search(s) and SUBSTANCE.search(s) and (person or "self" in roles) and not (
                mild and not re.search(r"\b(?:[1-9]\d+|whole|entire|bottle|frasco|bote)\b", s)):
            # ("i took all my vitamins" is a daily routine; a whole bottle of them is not)
            cand.append((3, "poison", "a quantity of a medicine taken (overdose)"))
        if _LIMB_NUMB.search(s) and _STROKE_COMP.search(s) and not _LIMB_BENIGN.search(s) and (person or
                                                                                         "self" in roles):
            cand.append((3, "medical", "one-sided numbness or weakness with a stroke sign"))
        if _UNSURE_ALIVE.search(s) and (re.search(r"\b(?:breath\w*|respir\w*)\b", s) or any(
                r in roles for r in ("child", "elder", "adult"))):  # not "my plant", "this watch app"
            cand.append((3, "medical", "the speaker cannot tell whether someone is breathing / alive"))
        if _vital_danger(s):
            cand.append((3 if (crit or weak or body or _SYMPTOM_RE.search(s)) else 1, "medical",
                         "a measured vital sign in a danger range"
                         + (" with a symptom" if (crit or weak or body) else "")))
        if _HEAD_HIT.search(s) and (_HEAD_SIGN.search(s) or crit):
            cand.append((3, "medical", "a head injury with drowsiness / confusion / vomiting"))
        hz = _hazard(s)
        if hz:
            cand.append((3, hz[0], hz[1]))
            f.hazards.append(hz[0])
        if not cand and person and roles != ["self"] and (weak or len(set(body)) >= 2 or _MENTAL.search(s)):
            cand.append((1, "medical", "a person with a possible sign"))
        if not cand:
            continue
        score, cat, why = max(cand, key=lambda c: c[0])
        stative = bool(_STATIVE.search(s)) or (cat == "medical" and "height" in f.hazards) or bool(hz) or (
            cat == "poison" and bool(re.search(r"\b(?:swallowed|ate|drank|se trago|trago|se comio|se tomo)\b", s)))
        framing = _framing(s, t, stative)
        if framing == "hypothetical" and _IF.search(s) and (_SPECIFIC.search(s) or re.search(
                r"\b(?:i|ive|me|yo)\b", s)) and not _GENERIC_RE.search(s) and (
                _COMPLETED.search(s) or _LIVE_TIME.search(s)):
            # fix round (P1-1): "is it bad if my daughter drank bleach a few minutes ago", "what if my husband's lips
            # are turning blue": a completed event, an observed appearance or a recent time is a live report
            framing = "now"
        if _UNSURE_ALIVE.search(s) and framing == "hypothetical" and not _GENERIC_RE.search(s):
            framing = "now"  # "i don't know if he's breathing" is a live report, not a conditional
        if framing in ("hypothetical",) and _QUESTION.search(s) and _SPECIFIC.search(s) and stative and not \
                _EVENT_HYPO.search(s) and not _GENERIC_RE.search(s):
            framing = "now"
        live_cond = framing == "now" and bool(_IF.search(s) or _QUESTION.search(s))
        rank = score * 10 + {"now": 5, "hypothetical": 2, "past": 1}.get(framing, 0)
        if best is None or rank > best[0]:
            best = (rank, cat, framing, why, live_cond)
    if exposure:
        f.hazards.append("exposure")
        if best is None and re.search(rf"\b(?:{_CHILD}|{_ELDER}|{_ADULT})s?\b|\b(?:pregnant|embarazada|sick|enferm[oa]|"
                                      rf"oxygen|oxigeno|disabled|wheelchair|ms|multiple sclerosis|copd|asthma\w*|heart "
                                      rf"condition|medical condition|dialysis|chemo\w*|diabet\w*|recien nacid\w*|"
                                      rf"silla de ruedas|discapacidad|asma|\d{{2}} (?:years? old|anos)|"
                                      rf"de (?:[6-9]\d|1[01]\d)"
                                      rf"(?: anos)?)\b", t):
            # Lead class 2: no heat / no AC with a vulnerable person and NO symptom: urgent repair + the calm
            # "unwell" line (911 if anyone feels very unwell), not the medical person-in-danger alert.
            f.category, f.urgency, f.ongoing, f.care_hint = "medical", "possible", "now", "unwell"
            f.reason = "heat or cold exposure with a vulnerable person, no symptom described"
            return f

    sh = _self_harm(t)
    if sh:
        level, why = sh
        if level == "emergency":
            best = (99, "self_harm", "now", why, False)
        elif best is None or best[0] < 20:
            f.category, f.template, f.urgency, f.ongoing, f.reason = "self_harm", "self_harm", "possible", "now", why
            f.hazards.append("farewell")
            return f
    if best is None:
        return f
    rank, cat, framing, why, live_cond = best
    f.category = f.template = cat
    f.ongoing = framing
    f.urgency = "emergency" if rank >= 20 else "possible"
    f.live_conditional = live_cond
    f.reason = why
    return f


_SPAN_SENTENCE = {"drill": _DRILL, "media": _MEDIA, "policy": _POLICY_Q, "signs": _SIGNS_Q, "past": re.compile(
    rf"(?:{_PAST.pattern})|(?:{_HISTORY_Q.pattern})|\b(?:sometimes|occasionally|once in a while|a veces|"
    rf"de vez en cuando|"
    rf"not (?:right )?now|its off)\b")}


def without_lookalike(message: str, look_alike: str | None) -> str:
    """The message with the look-alike phrase removed: the sentences that carry the drill / media / policy / signs /
    past framing, and every device noun ("smoke detector", "fire alarm"). Lowering a rule match is allowed only when
    THIS remainder has no hazard of its own (sprint 7 fix round: lowering must be monotone-safe)."""
    t = normalize(message)
    pat = _SPAN_SENTENCE.get(look_alike or "")
    if pat is not None and look_alike not in ("drill", "policy"):
        t = " . ".join(x for x in _sentences(t) if not pat.search(x))
    # drill / policy: only the drill words and device nouns go ("... ceiling light, is this a drill?" keeps the flood)
    return _DRILL.sub(" ", _DEVICE.sub(" ", t))


def _self_harm(t: str) -> tuple[str, str] | None:
    if _SH_EXCLUDE.search(t) and not _SH_METHOD.search(t):
        return None
    groups = [n for n, p in (("farewell", _SH_FAREWELL), ("final", _SH_FINAL), ("method", _SH_METHOD),
                             ("giving", _SH_GIVING), ("burden", _SH_BURDEN), ("closure", _SH_CLOSURE),
                             ("injury", _SH_INJURY))
              if p.search(t)]
    if re.search(r"\b(?:cartas?|notas?|mensajes?) de despedida\b|\bgoodbye (?:letters?|notes?)\b|\bsuicide note\b", t):
        return "emergency", "a goodbye letter"
    if _SH_INTENT.search(t) or re.search(
            r"\b(?:im|i am|estoy)\s+(?:standing|sitting|perched|parad[oa]|sentad[oa])\s+(?:at|on|en)\s+(?:the )?(?:edg"
            r"e|"
            r"ledge|railing|borde|orilla)\s+(?:of|de)\s+(?:the |a |el |la )?(?:\w+ )?(?:roof|rooftop|bridge|building|p"
            r"arking "
            r"(?:deck|garage|structure)|balcon\w*|azotea|puente|edificio)\b", t):
        return "emergency", "self-harm intent with a means"
    if groups == ["closure"]:
        return None  # "thanks for everything" alone is a polite sign-off
    if not groups or not _SELF_REF.search(t) and "farewell" not in groups:
        return None
    if groups == ["method"]:
        if re.search(r"\b(?:im|i am|estoy)\s+(?:\w+ )?(?:on|at|in|en)\s+(?:the |a |el |la )?(?:\w+ )?(?:bridge|ledge|"
                     r"roof|rooftop|puente|azotea|cornisa)\b|\bcutting\b|\bcut myself\b|myself\b", t):
            return "possible", "possible self-harm sign: at a height or self-injury"
        return None  # "the roof", "a rope" alone: not a self-harm sign
    if len(groups) >= 2 or "final" in groups and re.search(r"\b(?:asleep|sleep|wake|despertar|dormir)", t):
        return "emergency", "veiled self-harm: " + " + ".join(groups)
    return "possible", "possible self-harm sign: " + groups[0]
