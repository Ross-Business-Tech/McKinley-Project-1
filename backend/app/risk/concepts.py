"""Layer 1b (sprint 6): concept-based deterministic detection.

Earlier sprints added one regex per reported sentence; that fixed the reported wording but not paraphrases. These
rules instead combine small, generic VOCABULARIES of meaning ("slots") by proximity:

  person (or child / pet)  +  sign of serious injury / unresponsiveness            -> medical
  person  +  injury mechanism (fell, tumbled, went under)  +  any sign of harm       -> medical
  water body  +  submersion sign                                                    -> medical (drowning)
  child / pet  +  shut inside a vehicle / home  +  heat or an unattended hazard      -> trapped (notice: medical)
  person  +  pinned / crushed under something                                      -> trapped (notice: medical)
  ingestion verb  +  quantity  +  medication / substance                           -> poison (988 added on intent)
  stockpiled medication  +  finality / farewell  +  "last time you'll hear from me" -> self-harm
  entry point broken (glass, window, door)  +  someone present / coming in now      -> personal safety
  partner / ex  +  present-progressive violence (Spanish and English)               -> personal safety
  overhead material falling / floor or deck sinking, leaning, buckling              -> structural
  utility line down / snapped / lying across                                       -> electrical
  water depth or water still rising                                                -> flood
  fire misspellings; something "caught" and is spreading                           -> fire / smoke

They run AFTER the explicit keyword rules in app.emergency (KINDS, CONCEPTS), so explicit wording keeps its specific
kind, and they go through the same framing logic (hypothetical / past / negated / figurative), so "what if a child
went under in the pool?" is safety info, not an alert. Each vocabulary is generic; none is a copy of a test sentence.

`concern()` is the conservative middle tier: words that suggest a person may be hurt or in danger without enough for
an alert. It produces the calm 911 care line, never silence, and it blocks the R7 semantic suppression.
"""

import re

_GAP = r"\W+(?:\w+\W+){0,%d}"


def _near(a: str, b: str, gap: int = 8) -> re.Pattern[str]:
    g = _GAP % gap
    return re.compile(rf"(?:{a}){g}(?:{b})|(?:{b}){g}(?:{a})", re.I)


def _then(a: str, b: str, gap: int = 8) -> re.Pattern[str]:
    return re.compile(rf"(?:{a}){_GAP % gap}(?:{b})", re.I)


# ---- slots ----------------------------------------------------------------------------------------------------
PERSON = (r"\b(?:grand(?:ma|pa|mother|father|son|daughter)|mom|mum|mother|dad|father|husband|wife|partner|roommate|"
          r"neighbou?r|kid|kids|son|daughter|baby|child|children|toddler|infant|friend|boyfriend|girlfriend|man|woman|"
          r"guy|lady|person|brother|sister|cousin|uncle|aunt|tenant|resident|boy|girl|teen\w*|someone|somebody|he|"
          r"she|him|her|they|them)\b|\b(?:mi|el|la|un|una)\s+(?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|abuel[oa]|"
          r"vecin[oa]|pareja|beb[eé]|niñ[oa]|ni[nñ][oa]|señor|señora|hombre|mujer)\b")
CHILD_OR_PET = (r"\b(?:kid|kids|child|children|son|daughter|baby|toddler|infant|little (?:one|boy|girl)|boy|girl|"
                r"\d+ ?(?:year|yr|month)[- ]old|dog|puppy|cat|kitten|pet)\b|\b(?:hij[oa]|beb[eé]|niñ[oa]|ni[nñ][oa]|"
                r"perr[oa]|gat[oa])\b")
# Signs that are serious on their own when attached to a person.
SERIOUS = (r"not (?:breathing|waking)|isn'?t (?:breathing|waking)|stopped breathing|hasn'?t (?:woken|come "
           r"(?:back )?up|surfaced)|won'?t wake|unresponsive|unconscious|limp\b|knocked out|blacked out|out cold|"
           r"bent (?:the )?wrong way|bone (?:is )?(?:sticking|poking|showing)|can'?t (?:move|feel) (?:his|her|their|"
           r"my) (?:legs?|arms?|body)|seizing|convuls\w*|turning (?:blue|purple|gr[ae]y)|(?:lips|face) (?:are |is )?"
           r"(?:blue|purple|gr[ae]y)|no (?:respira|despierta|reacciona)")
# Weak signs ("not answering", "not moving") count only next to a NAMED person, never "they" / "I" ("they're not
# answering my calls"), and never about calls / texts / the door.
WEAK = (r"(?:not|isn'?t) (?:answering|responding|moving)(?! (?:my|his|her|their|the|our) (?:calls?|texts?|phone|"
        r"messages?|emails?|door))|hasn'?t (?:moved|answered|responded)(?! (?:my|his|her|their|the) (?:calls?|texts?|"
        r"phone|messages?|emails?|door))|won'?t (?:answer|respond|move)(?! (?:my|his|her|their|the) (?:calls?|texts?|"
        r"phone|messages?|emails?|door))|no (?:responde|se mueve)")
NAMED = (r"\b(?:grand(?:ma|pa|mother|father|son|daughter)|mom|mum|mother|dad|father|husband|wife|partner|roommate|"
         r"neighbou?r|kid|son|daughter|baby|child|toddler|infant|friend|boyfriend|girlfriend|man|woman|guy|lady|person|"
         r"brother|sister|cousin|boy|girl)\b|\b(?:mi|el|la|un|una)\s+(?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|"
         r"abuel[oa]|vecin[oa]|pareja|beb[eé]|niñ[oa]|señor|señora|hombre|mujer)\b")
MECHANISM = (r"\b(?:fell(?! asleep| in love| behind| for\b| through| apart| short| off the map)|fallen(?! asleep)|"
             r"falls|tumbled|tumbling|tripped|slipped|went down hard|went under|dropped|got hit|hit by "
             r"(?:a )?(?:car|truck)|run over|ran over|crashed|landed (?:on|hard)|knocked (?:down|over)|crushed|"
             r"se cay[oó]|se golpe[oó])\b")
HARM = (SERIOUS + "|" + WEAK + r"|bleed\w*|blood|hurts?|pain|broken|broke (?:his|her|their|my)|crying|"
        r"screaming|scream\w*|moan\w*|groan\w*|can'?t (?:get up|stand|walk|move|breathe)|"
        r"on the (?:floor|ground|concrete|pavement)|head\b|dizzy|confused|throwing up|vomit\w*|duele|sangr\w*")
WATER_BODY = (r"\b(?:pool|deep end|shallow end|hot tub|jacuzzi|bath ?tub|tub|lake|pond|river|retention pond|fountain|"
              r"piscina|alberca|ba[nñ]era|tina)\b")
SUBMERGED = (r"went under|go(?:ne|ing|es)? under|hasn'?t (?:come|came) (?:back )?up|not coming (?:back )?up|"
             r"didn'?t come (?:back )?up|face ?down|under (?:the )?water|underwater|drown\w*|floating|sank|sinking|"
             r"can'?t swim|ahog\w*|se hundi[oó]|bajo el agua|boca abajo")
SHUT_IN = (r"(?:locked|left|stuck|shut|trapped|alone|sleeping|asleep) (?:\w+ )?(?:in|inside)\b|by (?:him|her|them)sel"
           r"(?:f|ves) (?:in|inside)|encerrad[oa]|se qued[oó] (?:encerrad[oa]|adentro|solo|sola)")
VEHICLE = r"\b(?:car|truck|van|suv|vehicle|backseat|back seat|carro|coche|auto|camioneta)\b"
HEAT = (r"\bhot\b|heat|sun\b|sunny|\d{2,3} ?(?:degrees|°)|windows? (?:are |is )?(?:up|closed|rolled up)|sweat\w*|"
        r"calor|caliente|sol\b")
HOME_HAZARD = (r"stove|oven|burner|candle|space heater|bath ?(?:tub)?|water running|tub running|crying|screaming|"
               r"locked out|can'?t get (?:in|back in)|estufa|horno")
PINNED = (r"\b(?:pinned|crushed|stuck|trapped|caught)\W+(?:\w+\W+){0,1}(?:under|beneath|underneath|between)\b|"
          r"\b(?:fell|collapsed|came down|toppled|tipped) (?:on|onto|over on) (?:him|her|them|me|my|his|the (?:kid|"
          r"baby|child))\b|atrapad[oa] (?:debajo|bajo)")
INGEST = (r"\b(?:took|taken|taking|swallowed|swallowing|downed|popped|ate|eaten|chugged|drank|had|overdid|"
          r"se tom[oó]|se trag[oó]|me tom[eé]|tom[eé]|tom[oó])\b")
QUANTITY = (r"\b(?:everything|all (?:of )?(?:my|his|her|the|their)|all|whole (?:bottle|box|pack|packet|sheet|thing)|"
            r"(?:a |the )?(?:bottle|box|handful|bunch|fistful|pile|dozen|lot|ton)s?(?: of)?|too many|way too many|so "
            r"many|a lot of|the rest of|entire|double|triple|\d{2,} |toda[s]? (?:las|la)|un mont[oó]n|muchas)\b")
MEDS = (r"\b(?:pills?|meds|medicine\w*|medication\w*|tablets?|capsules?|prescriptions?|oxy\w*|opioids?|xanax|"
        r"tylenol|advil|ibuprofen|acetaminophen|percocet|vicodin|fentanyl|benzos?|adderall|insulin|"
        r"sleeping (?:pills|aids)|painkillers?|pain (?:meds|pills|killers)|medicine cabinet|edibles?|"
        r"pastillas|medicinas?|medicamentos?)\b")
STOCKPILE = (r"\b(?:saving|saved|stockpil\w*|collecting|hoarding|stashing|stashed|been keeping|counting) (?:up )?"
             r"(?:all )?(?:my |of my |the )?(?:pills|meds|medication|medicine|tablets|pastillas)\b|"
             r"\bjuntando (?:mis )?pastillas\b")
FINALITY = (r"sleep (?:for good|forever|and not wake|and never wake)|never wake up|for good\b|be done (?:for good|with "
            r"it all)|end (?:it|this|things)|no more pain|won'?t (?:have to )?wake up|last time|goodbye|final|"
            r"para siempre|no despertar")
FAREWELL = (r"\b(?:letters?|notes?|messages?|goodbyes?|cartas?)\b\W+(?:\w+\W+){0,4}(?:to|for|para)\W+(?:\w+\W+){0,2}"
            r"(?:family|kids|children|mom|dad|parents|everyone|wife|husband|partner|sister|brother|familia|hijos)")
LAST_WORDS = (r"last time (?:you'?ll|you will|anyone will|anybody will|you) (?:ever )?(?:hear|see|talk)|"
              r"you won'?t (?:hear|see) (?:from )?me (?:again|anymore)|"
              r"won'?t be (?:here|around|alive) (?:tomorrow|by morning|much longer|"
              r"after tonight)|by the time (?:you|anyone|someone) (?:read|see|get)s? this|"
              r"(?:no|nunca) (?:vas|van) a (?:volver a )?saber de m[ií]")
ENTRY_BROKEN = (r"\b(?:glass|window|windows|door|front door|back door|slider|sliding door|lock|deadbolt|ventana|"
                r"puerta|vidrio)\b\W+(?:\w+\W+){0,3}(?:shatter\w*|smash\w*|broke|breaking|break\b|kicked|kicking|"
                r"forced|forcing|pried|prying|bust\w*|crash\w*|rompi\w*|romp\w*|forz\w*)|"
                r"\b(?:shatter\w*|smash\w*|broke|breaking|kicked|kicking|forced|forcing|pried|prying|bust\w*|"
                r"rompi\w*|rompieron|forzaron)\b\W+(?:\w+\W+){0,3}(?:glass|window|windows|door|lock|deadbolt|slider|"
                r"ventana|puerta|vidrio)\b")
PRESENT_INTRUDER = (r"climbing (?:in|through|inside)|coming in|getting in|crawling in|footsteps|someone(?:'s| is)? "
                    r"(?:inside|in (?:here|the house|my (?:unit|apartment|place|home)|the (?:kitchen|living room)))|"
                    r"(?:he|she|they)(?:'s| is| are|'re) (?:inside|in here|in the house|coming (?:in|up))|"
                    r"\bhiding\b|downstairs|upstairs|in the (?:kitchen|living room|hallway)|voices|"
                    r"right now|est[aá]n? (?:entrando|adentro)|pasos|me escondo|escondid[oa]")
PARTNER = (r"\b(?:my )?(?:ex|ex-\w+|partner|boyfriend|girlfriend|husband|wife|roommate|novi[oa]|pareja|esposo|esposa|"
           r"marido|ex ?pareja)\b")
VIOLENCE_NOW = (r"\b(?:is|are|keeps?|keep on|started|starting|won'?t stop) (?:hitting|beating|choking|strangling|"
                r"punching|kicking|slapping|hurting|shoving|attacking|dragging) (?:me|us|her|him|the kids?)\b|"
                r"\bme est[aá] (?:golpeando|pegando|lastimando|ahorcando|empujando|atacando|maltratando)\b|"
                r"\bme (?:sigue|empez[oó] a) (?:golpeando|pegar|golpear|pegando)\b")
OVERHEAD = (r"\b(?:chunks?|pieces?|bits|plaster|drywall|concrete|bricks?|tiles?|beams?|debris|insulation|pedazos|"
            r"trozos|ladrillos)\b(?:\W+(?:\w+\W+){0,3}(?:ceiling|roof|wall|overhang|balcony|facade|techo|pared))?"
            r"\W+(?:\w+\W+){0,3}(?:falling|fell|dropping|dropped|coming down|came down|raining down|cayendo|cayeron)")
STRUCT_PART = (r"\b(?:floor|floors|deck|balcony|stairs|staircase|stairway|steps|porch|landing|beam|beams|posts?|"
               r"joists?|ceiling|roof|walkway|piso|techo|escalera|balc[oó]n|viga)\b")
# Failure words only; "cracking" or "peeling" alone is a repair, not a collapse.
STRUCT_FAIL = (r"\b(?:sank|sinking|sunk|leaning|tilting|buckl\w*|crumbl\w*|giving way|gave way|pulling away|"
               r"separating|caving|caved|sagging|swaying|hundi\w*|inclinad\w*|derrumb\w*)\b")
FELL_ONTO = (r"\b(?:ceiling|roof|overhang|garage ceiling|beam|wall|balcony|techo)\b\W+(?:\w+\W+){0,4}(?:fell|came "
             r"down|collapsed|dropped|cay[oó])\W+(?:\w+\W+){0,1}(?:on|onto|into|sobre|encima)\b")
UTILITY_LINE = (r"\b(?:power|electric\w*|utility|live|high[- ]voltage|overhead)\W+(?:\w+\W+){0,1}(?:lines?|cables?|"
                r"wires?)\b|\b(?:lines?|cables?|wires?)\b\W+(?:\w+\W+){0,3}(?:from|off|on) the (?:pole|tower|"
                r"transformer|post)|\bcables? de (?:luz|electricidad)\b")
LINE_DOWN = (r"\bdown\b|\bdowned\b|snapped|fell|fallen|came down|lying|laying|on the (?:ground|road|sidewalk|car|"
             r"street)|across the|hanging (?:low|down)|sparking|dangling|buzzing|ca[ií]d[oa]s?|en el suelo")
WATER_DEPTH = (r"\b(?:an?|one|two|three|four|several|few|couple(?: of)?) inch(?:es)? of water\b|"
               r"\b(?:water|agua)\b\W+(?:\w+\W+){0,8}(?:(?:still|keeps?|is|keep) (?:rising|coming up|getting higher)"
               r"(?! (?:in )?(?:price|prices|cost|costs|bills?|rates?))|rising fast|"
               r"up to (?:my|our|the) (?:ankles?|knees?|shins?)|sube y sube|sigue subiendo)")
FIRE_MISSPELL = r"\b(?:fyre|fiire|firre|fiyre|faiar|fuyego|fueggo|incendi0)\b"
CAUGHT_SPREADING = (r"\bcaught\b(?! (?:a cold|up|on|my eye|his eye|her eye|the bus|the train|him|her|them|a ride))"
                    r"\W+(?:\w+\W+){0,6}(?:going up|spreading|fast|flames?|burning|smok\w*|growing)|"
                    r"\b(?:going|went|gone) up (?:fast|quick\w*|in seconds)\b")

ELEVATOR = r"\b(?:elevator|lift|ascensor|elevador)\b"
CAR_FAIL = (r"jammed|stuck|stopped|broke down|broken down|frozen|dropped|fell|won'?t (?:open|move)|doors? (?:won'?t|"
            r"will not|don'?t) open|se trab[oó]|atascad[oa]|trabad[oa]|no abre")
OCCUPANT = (r"inside|in it|in there|panick\w*|between floors|trapped|(?:i|we)(?:'m|'re| am| are) in|"
            r"(?:my|our|a|the) \w+ (?:is|are) in|adentro|dentro")

# ---- sprint 6 fix round: intruder in progress, cold exposure, veiled farewell, "not a physical state" ----------
# Someone forcing / prying / climbing through an entry point NOW (present progressive, "keeps trying", "right now").
_ENTRY = (r"\b(?:windows?|doors?|front door|back door|patio door|balcony door|sliding door|slider|screen|lock|locks|"
          r"deadbolt|door ?knob|handle|ventana|puerta|cerradura)\b")
_FORCE = (r"(?:forc\w*|pry\w*|pri(?:ed|es)|kick\w*|jimm\w*|pick\w*|break\w*|smash\w*|bust\w*|climb\w*|crawl\w*|"
          r"rattl\w*|yank\w*|wrench\w*|ram\w*|shoulder\w*|tamper\w*|cutting|cut(?:s)? (?:through|the)|"
          r"(?:get|getting|break|breaking) (?:in|through)|open)")
_PROGRESSIVE = (r"\b(?:is|are|'s|'re|am|keeps?|kept|keep on|still|started|starting|trying to|tries to|try to|"
                r"attempting to|right now)\b")
_SOMEONE = (r"\b(?:someone|somebody|some(?:one|body) i don'?t know|a (?:man|guy|woman|person|stranger|dude)|"
            r"(?:the|this|that) (?:man|guy|woman|person|stranger|dude)|strangers?|intruders?|burglars?|robbers?|"
            r"thie(?:f|"
            r"ves)|alguien|un (?:hombre|tipo|desconocido)|"
            r"unos? (?:hombres|tipos|desconocidos))\b")
FORCING_NOW = (rf"{_SOMEONE}\W+(?:\w+\W+){{0,3}}{_PROGRESSIVE}\W+(?:\w+\W+){{0,2}}{_FORCE}\W+(?:\w+\W+){{0,4}}"
               rf"{_ENTRY}|{_SOMEONE}\W+(?:\w+\W+){{0,3}}(?:at|outside|by|on) (?:my|our|the) (?:\w+ )?(?:windows?|"
               r"doors?|balcony)\W+(?:\w+\W+){0,4}(?:trying to (?:get|come|climb|break) in|trying to open|getting in|"
               r"coming in|climbing in|forcing|prying)|"
               rf"{_SOMEONE}\W+(?:\w+\W+){{0,2}}(?:climb\w*|crawl\w*|com\w+|got|get\w*|break\w*|broke) (?:in )?"
               r"(?:in|through|into) (?:my|our|the) (?:\w+ )?(?:windows?|doors?)|"
               r"\b(?:est[aá]n?|sigue|siguen) (?:tratando|intentando) de (?:abrir|forzar|romper|entrar)|"
               r"\b(?:est[aá]n?) (?:forzando|rompiendo) (?:la|mi|las) (?:puerta|ventana|cerradura)")
# A person inside who should not be there ("a man I don't know is in my living room", "a stranger got in and won't
# leave"). Past-only ("someone got in last year") is framed by the caller; the rule itself needs a home place.
_HOME = (r"(?:my|our|the) (?:apartment|unit|place|home|house|living room|kitchen|bedroom|bathroom|room|hallway|"
         r"closet|basement|garage|bike room|storage(?: room| unit)?|laundry room)|in here|mi (?:casa|apartamento"
         r"|cuarto)")
_UNWANTED = (r"(?:stranger|intruder|burglar|robber|thief|someone (?:i|we) (?:don'?t|do not) know|(?:a |some )?(?"
             r":man|guy|"
             r"woman|person|people) (?:i|we) (?:don'?t|do not|have never|'ve never) (?:know|seen|recogni[sz]e)|"
             r"(?:someone|somebody|a (?:man|guy|woman|person)) (?:who|that) (?:shouldn'?t|should not|doesn'?t|do"
             r"es not) "
             r"(?:be|live)|desconocido|extra[nñ]o)")
_HOME = f"(?:{_HOME})"
_UNWANTED_ALSO = (r"\b(?:someone|somebody|a (?:man|guy|woman|person)|people)\W+(?:\w+\W+){0,4}(?:who|that) (?:sh"
                  r"ouldn'?t|"
                  r"should not|doesn'?t|does not) (?:be|live)\b|\b(?:there'?s|there is|there are) (?:a |some |two |"
                  r"another )?(?:man|guy|men|guys|person|people|someone|somebody|stranger|woman)\W+(?:\w+\W+){0,2}"
                  r"(?:inside|in (?:it|there|here|the|my|our))\b\W+(?:\w+\W+){0,4}(?:right now|now|still)\b")
_UNWANTED = f"(?:{_UNWANTED})"
STRANGER_INSIDE = (rf"\b{_UNWANTED}\W+(?:\w+\W+){{0,5}}(?:in|inside|into|got into|is in|in(?:side)? of) {_HOME}|"
                   rf"(?:in|inside) {_HOME}\W+(?:\w+\W+){{0,4}}{_UNWANTED}|"
                   rf"\b{_UNWANTED}\W+(?:\w+\W+){{0,6}}(?:won'?t leave|refuses to leave|is still here|still inside|"
                   r"hiding)|" + _UNWANTED_ALSO)
# A criminal still present after a property crime ("the thief is still in the bike room with a crowbar").
_CRIMINAL = (r"(?:thie(?:f|ves)|burglars?|robbers?|intruders?|(?:the|that|this|a) (?:guy|man|person|dude|woman) "
             r"(?:who|that) (?:broke|stole|took)|whoever (?:broke|stole)|(?:the|that|this) (?:guy|man|person|dud"
             r"e|woman))")
_STILL_HERE = (r"(?:is|are|'s|'re)? ?still (?:here|there|inside|in (?:the|our|my|his)|hiding|around|on (?:the|our) "
               r"(?:property|floor|roof))|(?:is|are|'s|'re) (?:hiding|inside|lurking|in (?:the|our|my) (?:garage|"
               r"bike room|storage|basement|building|stairwell|hallway|laundry room|unit|apartment))|"
               r"with (?:a|an) (?:crowbar|knife|gun|bat|weapon|hammer|machete|pipe)")
CRIMINAL_PRESENT = rf"\b(?:{_CRIMINAL})\b\W+(?:\w+\W+){{0,3}}(?:{_STILL_HERE})"
FORCING_NOW = f"(?:{FORCING_NOW})"
PRESENT_PERSON = CRIMINAL_PRESENT + "|" + STRANGER_INSIDE + "|" + FORCING_NOW

# Extreme cold + a vulnerable person with a sign of harm -> medical (911, stay with the person).
_VULNERABLE = (r"\b(?:new ?born|infant|baby|babies|bebé|bebe|\d+[- ]?(?:day|week|wk|month|mo)s?[- ]old|preemie|"
               r"elderly|grand(?:ma|pa|mother|father)|my (?:old|elderly|sick) \w+|toddler)\b")
_COLD_CONTEXT = (r"\b(?:no heat|heat(?:'s| is| has| was)?(?: been)? (?:out|off|gone|not working|broken|died)|hea"
                 r"ter (?:died|"
                 r"broke|stopped|isn'?t working|is broken|went out)|furnace (?:died|broke|stopped|isn'?t working|is "
                 r"broken|went out|out)|radiators? (?:is |are )?(?:broken|cold|off|dead)|freezing|below freezing|ice "
                 r"cold|\d{1,2} ?(?:degrees|°)|frigid|sin calefacci[oó]n|helad\w*|mucho fr[ií]o)\b")
_COLD_HARM = (r"\b(?:freezing|ice[- ]cold|icy|so cold|very cold|too cold|cold to the touch|feels? (?:so |really "
              r"|very )?"
              r"cold|shiver\w*|shaking|turning (?:blue|purple|gr[ae]y)|(?:lips|hands|feet|skin|face) (?:are |is |look "
              r"|looks |turning )?(?:blue|purple|gr[ae]y|icy)|barely moving|limp|letharg\w*|(?:really |so |very )sleepy"
              r"|confused|won'?t (?:eat|feed|wake)|not (?:feeding|eating|waking))\b")
COLD_EXPOSURE = _near(_VULNERABLE, _COLD_HARM, 6)

# A veiled farewell (no "die" / "suicide" words): the 988 care line at minimum. Everyday goodbyes are excluded.
VEILED_FAREWELL = re.compile(
    r"\b(?:my|this is my|this will be my|these are my) (?:last|final) (?:message|words|text|post|note|letter)\b(?! "
    r"(?:about|for (?:the|my) (?:repair|request|ticket)|on (?:this|the) (?:repair|ticket)))|"
    r"\b(?:the )?last (?:thing|message|words?) (?:i(?:'ll| will)?|you(?:'ll| will)?) (?:ever )?(?:write|send|say"
    r"|hear)\b|"
    r"\bsay(?:ing)? (?:my )?goodbyes?\b(?! (?:to (?:this|the|my) (?:apartment|place|unit|building|lease|neighbou"
    r"?rhood)|"
    r"(?:next|in|at) ))(?=\W+(?:\w+\W+){0,6}(?:tonight|it'?s time|for good|forever|everyone|everybody|all of you|"
    r"to everyone|before i go)\b)|\bsay(?:ing)? goodbye to (?:everyone|everybody|you all|all of you)\b|"
    r"\b(?:won'?t|will not|wont) (?:be needing|need) (?:the|my|this) (?:apartment|place|unit|stuff|things)\b(?!\W+"
    r"(?:\w+\W+){0,4}(?:mov\w*|lease|transfer\w*|sublet\w*|new place))|"
    r"\b(?:won'?t|will not|wont) have to (?:deal with|worry about|put up with|hear from) me\b|"
    r"\b(?:i'?ve|i have) made (?:my )?peace\b|\bplease (?:give|take care of) my (?:cat|dog|pets?|kids|plants) "
    r"(?:to|for me)\b|\btell my \w+ (?:that )?i love (?:her|him|them)\b", re.I)


def veiled_farewell(text: str) -> bool:
    return bool(VEILED_FAREWELL.search(text))


# "Not a physical state": the speaker refusing to answer, staff not replying to messages, or "passed out the forms".
# Removed before the person + weak-sign rules, so only a person's body state ("my dad isn't responding") counts.
NOT_PHYSICAL = re.compile(
    r"\b(?:i|we)(?:'m|'re| am| are| was| will| won'?t| wont| just| not)*\W*(?:not |no longer |never )?(?:going to )?"
    r"(?:answer\w*|respond\w*|repl\w*)\b(?:\W+(?:\w+\W+){0,4})?|"
    r"\b(?:not|no longer|never) (?:answering|responding|replying)(?: (?:that|this|it|again|anymore|any ?more|more|"
    r"those|these|your|any|questions?)\b)+|"
    r"\b(?:maintenance|office|leasing|landlord|manager|management|staff|front desk|support|super(?:intendent)?|"
    r"property|tech|technician|plumber|electrician|contractor|agent|rep|team|company|you guys|y'?all|nobody|no ?one|"
    r"anyone|the person (?:on the phone|at the (?:desk|office|front))|(?:your|the|their) (?:\w+ )?(?:person|guy|lady|"
    r"people))\W+(?:\w+\W+){0,3}(?:is|are|isn'?t|aren'?t|was|wasn'?t|has|hasn'?t|have|haven'?t|won'?t|wont|keeps?|"
    r"never|still)?\W*(?:not |been |even |ever )*(?:answer\w*|respond\w*|repl\w*|getting back|calling back|picking up)"
    r"\b(?:\W+(?:\w+\W+){0,4})?|"
    r"\b(?:not|isn'?t|wasn'?t|hasn'?t|won'?t|wont|haven'?t|never|stopped) (?:answering|responding|replying|answered|"
    r"responded|replied|answer|respond|reply)\W+(?:\w+\W+){0,3}(?:texts?|calls?|emails?|e-mails?|messages?|phone|"
    # Sprint 6 final (verifier P0-A): "me", "us", "again" and durations are NOT stripped here: "my dad is not
    # responding to me" is a body state. Staff not replying to me/us is covered by the staff branch above.
    r"voicemails?|dms?|questions?|requests?|tickets?)\b|"
    # Sprint 6 final (verifier I3): not responding ABOUT something, or a buyer / seller / date not replying, is social
    r"\b(?:not|isn'?t|is not|hasn'?t|has not|won'?t|wont|stopped|never) (?:been )?(?:respond\w*|repl\w*|answer\w*|"
    r"getting back)(?: to (?:me|us|my \w+|our \w+))?\s+(?:about|regarding|re|over|on the|for the)\b|"
    r"\b(?:who (?:bought|sold|is buying|is selling|rented|is renting|i sold|i bought|i met|i'?m dating)|buyer|seller|"
    r"match|landlord|recruiter|ex)\b[^.?!]{0,40}?\b(?:isn'?t|is not|not|hasn'?t|has not|stopped|never) (?:been )?"
    r"(?:respond\w*|repl\w*|answer\w*)\b(?: to (?:me|us|my \w+))?|"
    r"\bpass(?:ed|ing|es)? out (?:the |some |these |those |all (?:the )?|our |copies of )?(?:paperwork|papers?|forms?|"
    r"flyers?|fliers|leaflets?|cards?|candy|keys|packets?|copies|menus|tickets?|surveys?|notices?|samples|snacks|"
    r"pamphlets?|brochures?|water|masks|lease(?:s| agreements?)?|documents?|info\w*)\b", re.I)


def not_physical(text: str) -> str:
    return NOT_PHYSICAL.sub(" ", text)


# Present-danger signs, used to override "asking about signs" / past-event framing in the same message: a person or
# the speaker with a current symptom, a hazard sign perceived now, or a person / intruder present now.
_SUBJECT = (r"\b(?:i|we|i'?m|we'?re|me|my|our|his|her|he|she|they|it|it'?s|there'?s|everyone|everybody|both of us|the "
            r"(?:whole )?(?:family|house|apartment|kitchen|place|baby|kids?)|mi|nos|estoy|estamos)\b")
_SYMPTOM_NOW = (r"head ?aches?|head (?:hurts|is (?:pounding|killing|throbbing))|dizz\w*|light-?headed|nause\w*|"
                r"throwing up|threw up|vomit\w*|feels? (?:sick|awful|faint|weird)|sick\b(?! of)|drows\w*|"
                r"(?:so |really |very )?sleepy|confus\w*|faint\w*|can'?t (?:lift|move|feel|raise|breathe|talk|speak|"
                r"stand|walk|see)|droop\w*|slurr\w*|numb\w*|eyes (?:are )?(?:burn\w*|sting\w*|water\w*)|"
                r"(?:chest|arm|jaw) (?:pain|hurts|is tight)|grabbing (?:his|her|their|my) chest|sweating|"
                r"short of breath|trouble breathing|wheez\w*|cough\w*|passed out|collapsed|mare\w*|v[oó]mit\w*|"
                r"dolor de cabeza")
_SIGN_NOW = (r"smell\w*|stink\w*|reek\w*|hiss\w*|beep\w*|going off|sounding|smok\w*|spark\w*|flames?|"
             r"in here|right now|huele")
PRESENT_SIGNS = re.compile(rf"{_SUBJECT}\W+(?:\w+\W+){{0,6}}(?:{_SYMPTOM_NOW}|{_SIGN_NOW})\b|"
                           rf"(?:{_SYMPTOM_NOW})\W+(?:\w+\W+){{0,3}}(?:right now|now|in here|todos|tambi[eé]n)\b|"
                           + PRESENT_PERSON, re.I)


def present_signs(text: str) -> bool:
    return bool(PRESENT_SIGNS.search(text))


def cold_exposure(text: str) -> bool:
    return bool(COLD_EXPOSURE.search(text) and re.search(_COLD_CONTEXT, text, re.I))


RULES: list[tuple[str, re.Pattern[str]]] = [
    # self-harm first: the most life-critical kind, and its words overlap with poisoning
    ("self_harm", _near(STOCKPILE, FINALITY, 12)),
    ("self_harm", re.compile(LAST_WORDS, re.I)),
    ("self_harm", _near(FAREWELL, FINALITY + "|" + LAST_WORDS, 14)),
    ("poison", _then(INGEST, rf"(?:{QUANTITY})\W+(?:\w+\W+){{0,3}}(?:{MEDS})", 3)),
    ("personal_safety", _near(ENTRY_BROKEN, PRESENT_INTRUDER, 10)),
    ("personal_safety", _near(PARTNER, VIOLENCE_NOW, 4)),
    ("personal_safety", re.compile(FORCING_NOW, re.I)),  # fix round: forcing / prying / climbing in NOW
    ("personal_safety", re.compile(STRANGER_INSIDE, re.I)),  # someone inside who shouldn't be
    ("personal_safety", re.compile(CRIMINAL_PRESENT, re.I)),  # the thief / intruder still present
    ("trapped", _near(rf"(?:{ELEVATOR})\W+(?:\w+\W+){{0,3}}(?:{CAR_FAIL})", OCCUPANT, 10)),
    ("medical", _near(WATER_BODY, SUBMERGED, 8)),
    ("trapped", _near(PINNED, PERSON + "|can'?t (?:get out|breathe|move)|help", 8)),
    ("trapped", _near(rf"(?:{CHILD_OR_PET})\W+(?:\w+\W+){{0,4}}(?:{SHUT_IN})\W+(?:\w+\W+){{0,3}}(?:{VEHICLE})",
                      HEAT, 12)),
    ("trapped", _near(rf"(?:{CHILD_OR_PET})\W+(?:\w+\W+){{0,4}}(?:{SHUT_IN})", HOME_HAZARD, 12)),
    ("medical", _near(PERSON, SERIOUS, 6)),
    ("medical", _near(NAMED, WEAK, 6)),
    ("medical", _near(rf"(?:{PERSON})\W+(?:\w+\W+){{0,3}}(?:{MECHANISM})", HARM, 10)),
    ("structural", re.compile(OVERHEAD, re.I)),
    ("structural", _near(STRUCT_PART, STRUCT_FAIL, 5)),
    ("structural", re.compile(FELL_ONTO, re.I)),
    ("electrical", _near(UTILITY_LINE, LINE_DOWN, 6)),
    ("flood", re.compile(WATER_DEPTH, re.I)),
    ("fire_smoke", re.compile(FIRE_MISSPELL, re.I)),
    ("fire_smoke", re.compile(CAUGHT_SPREADING, re.I)),
]

# ---- conservative middle tier ----------------------------------------------------------------------------------
_CONCERN = [
    _near(PERSON, MECHANISM, 4),  # "my mom fell", "the kid slipped": possibly hurt
    _near(PERSON, r"hurt|injur\w*|bleed\w*|in pain|can'?t (?:breathe|get up|stand)|not okay|not ok|scream\w* in "
                  r"pain|crying in pain|won'?t stop crying|passed out|herid[oa]|lastimad[oa]", 6),
    re.compile(STOCKPILE, re.I),  # stockpiled medication alone: the 988 line is chosen by the care tier
    _near(ENTRY_BROKEN, r"someone|somebody|stranger|heard|hear|noise|scared|afraid|footsteps|miedo|alguien", 10),
    _near(PARTNER, r"hit(?:s|ting)? (?:me|us|her|him|the kids?)|grabb?\w* (?:me|my|her)|push\w* me|shov\w* me|"
                   r"threat\w*|scared|afraid|miedo|me golpe\w*|me peg\w*", 6),
    _near(WATER_BODY, r"alone|unattended|can'?t find|missing|lost sight", 8),
]
# "she slipped last winter, now she's fine": reassured or clearly past, so no care line from the slots above.
_REASSURED = re.compile(
    r"\b(?:she|he|they|i|we)(?:'s| is| are|'re|'m| am)? (?:totally |completely )?(?:fine|ok|okay|alright|all right|"
    r"not hurt|unhurt)\b|\b(?:no ?one|nobody) (?:was |got |is )?(?:hurt|injured)\b|\blast (?:week|month|year|winter|"
    r"summer|spring|fall|time)\b|\b(?:years?|months?|weeks?) ago\b", re.I)


def concern(text: str) -> bool:
    """Possibly someone hurt or in danger, but not enough for an alert: show the calm 911 line, never silence."""
    return any(p.search(text) for p in _CONCERN) and not _REASSURED.search(text)


def stockpile(text: str) -> bool:
    return bool(re.search(STOCKPILE, text, re.I))
