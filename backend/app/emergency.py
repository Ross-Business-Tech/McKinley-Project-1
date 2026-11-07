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
        r"kill(ing)? my ?self|suicid|\bend (my (own )?life|it all)\b|want to die|wanna die|don'?t want to (live|be "
        r"alive|be here anymore)|hurt(ing)? my ?self|no reason to live|matarme|quitarme la vida|suicidar|"
        r"quiero morir|tự tử|muốn chết|(don'?t|dont|do not) (want|wanna) (to )?(be here|exist|wake up|go on)|"
        r"better off (dead|without me)|\bending (it all|my life|things)\b|\bend (it|things) all\b|want to (end it|"
        r"disappear)|"
        r"ganas de morir|"
        r"no quiero (vivir|estar aqu[ií])", re.I)),
    ("poison", re.compile(
        r"(drank|drunk|ate|eaten|got into)\W+(?:\w+\W+){0,6}(clean\w*|bleach|chemical\w*|pills?|medicine|"
        r"poison|detergent|pods?|magnets?|batter(y|ies)|antifreeze)|se tom[oó]\W+(?:\w+\W+){0,3}(cloro|"
        r"limpiador|pastillas)|swallow\w*\W+(?:\w+\W+){0,6}magnets?|"
        r"swallow\w*\W+(?:\w+\W+){0,6}(clean\w*|bleach|chemical\w*|pills?|medicine|poison|detergent|pod|battery|"
        r"batteries)|\bpoison(ed|ing)?\b|overdos|trag[oó]\W+(?:\w+\W+){0,4}(cloro|limpia\w*|pastillas|veneno)", re.I)),
    ("trapped", re.compile(
        r"stuck in (the|an|my) (elevator|lift)|(elevator|lift) stopped|(locked|stuck|trapped) in\W+(?:\w+\W+){0,4}"
        r"(can'?t|cannot) get out|can'?t get out of (the|my) (elevator|lift|room|bathroom)|(elevator|"
        r"lift)\W+(?:\w+\W+){0,4}stuck|trapped (in|inside|under)|"
        r"atrapad[oa] en el (elevador|ascensor)", re.I)),
    ("structural", re.compile(
        r"(railing|handrail|balcony)\W+(?:\w+\W+){0,4}(loose|broke|broken|gave way|came off|came loose|wobbl\w*)|"
        r"almost fell (off|out|over|from)|"
        rf"\b(ceiling|roof|floor|wall|balcony|stairs?|deck)\W+{_W}(collaps\w*|fell (in|down)|falling (in|down)|sag\w*|"
        r"cav(ed|ing) in|caving)|collapsed (ceiling|roof|balcony)|techo se (cay[oó]|derrumb)", re.I)),
    ("medical", re.compile(
        r"(fell|fallen|has fallen)\W+(?:\w+\W+){0,4}(can'?t|cannot|unable to) (get up|move)|hit (his|her|my|their)"
        r" head|"
        r"allergic reaction|anaphyla|epi-?pen|(face|lips?|tongue|throat)\W+(?:\w+\W+){0,2}(swell\w*|closing)|"
        r"stung\W+(?:\w+\W+){0,8}(allergic|swell\w*)|se cay[oó] y no (se )?puede (levantar|mover)|"
        r"chest pains?|heart attack|(not|isn'?t|stopped|can'?t|cannot) breath(e|ing)|unconscious|unresponsive|"
        r"passed out|\bcollapsed\b|overdos|seizure|\bstroke\b(?! of (luck|genius))|face (is )?droop\w*|slurr\w*|"
        r"can'?t feel (her|his|my|their) (arm|leg|face)|bleeding (a lot|badly|heavily|"
        r"won'?t stop)|choking|"
        r"dolor (en el|de) pecho|no respira|inconsciente|se desmay|đau ngực|không thở", re.I)),
    ("personal_safety", re.compile(
        r"break(ing)? ?in\b|\bbroke (?:in|into)\b|breaking into|broke into|broken into|(trying|tried) to (get|break)"
        r" in|intruder|"
        r"someone (is )?(in|inside) my (apartment|unit|home|place)|threat(en|ening)|stalk(ing|er)|"
        r"domestic (violence|abuse)|abus(e|ing|ive) (me|partner)|(hit|hitting|beat|beating|hurt|hurting) "
        r"(me|her|him|them|someone|a child|the kids?)\b|(screaming|yelling)\W+(?:\w+\W+){0,8}(hit|hurt|help)|"
        r"(don'?t|do not|no longer) feel safe\b|\bgun(s|shots?|fire)?\b|shots? fired|\bknife\b|"
        r"(kill|hurt) me\b|following me|stranger (is )?in (my|the) (apartment|unit|home)|"
        r"won'?t leave\W+(?:\w+\W+){0,4}scared|i'?m scared|"
        r"\bweapon|attack(ed|ing)? me|"
        r"me (amenaza|golpea|quiere hacer daño)|entraron a (mi|robar)|no me siento segur", re.I)),
    ("gas", re.compile(
        rf"(smel+\w*|odou?r|olor|huel\w*|stink\w*|reek\w*|whiff|leak\w*|hiss\w*|mùi|rò rỉ)\W+{_W}"
        r"(ga+s+|propane|natural gas|gasolina)\b|"
        rf"\b(ga+s+|propane)\b\W+{_W}(smel+\w*|leak\w*|odou?r|hiss\w*|stink\w*)|fuga de gas|olor a gas|huele a gas|"
        r"pilot light\W+(?:\w+\W+){0,4}smel\w*|smel\w*\W+(?:\w+\W+){0,6}pilot light|huevo podrido|khí ga|mùi ga|غاز|"
        r"煤气|燃气|瓦斯|rotten"
        r" egg|\bgaz\b|gaz kokusu|odeur de gaz|zapach gazu", re.I)),
    ("co", re.compile(
        r"carbon mon\w*|mon[oó]xid\w*|monixide|\bco (thing|sensor)|\bco\b ?(alarm|detector|monitor)|(alarm|detector)"
        r" (for|de) (co|mon[oó]xido)",
        re.I)),
    ("fire_smoke", re.compile(
        r"\bfire\b(?! ?(alarm test|drill|place|pit|extinguisher|department|works|fighter|d\b))|\bflames?\b|"
        r"on fire|\bburning\b(?! question)|burnt? (smell|plastic|rubber)|smells? (like |of )?(burn|smoke)|"
        r"smell\w*\W+(?:\w+\W+){0,2}(?:burnt|burning|smoky)|"
        r"\bsmok(e|ing|y|in'?)\b(?! ?(detector|alarm)\b(?!.{0,30}(going off|sounding|won'?t stop|keeps going)))|"
        r"(smoke|fire) (alarm|detector)s? (is |are )?(going off|sounding|won'?t stop|keeps going)|"
        r"\bhumo\b|\bfuego\b|incendio|quemando|quemado|cháy|khói|حريق|دخان|着火|火灾|冒烟", re.I)),
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

# ---- second layer: meaning from word COMBINATIONS (person + state, substance + ingestion, symptom + source) ----
# Catches understated or indirect reports that never name the hazard. Still deterministic and still a floor, not a
# guarantee; run after KINDS so explicit wording keeps its specific kind.
_PERSON = (r"(?:my|the|a|our|his|her)\s+(?:\w+\s+){0,2}(?:grand(?:ma|pa|mother|father)|mom|mum|mother|dad|father|"
           r"husband|"
           r"wife|partner|roommate|room mate|neighbou?r|kid|son|daughter|baby|child|toddler|friend|boyfriend|"
           r"girlfriend|"
           r"man|woman|guy|lady|person|brother|sister|tenant|someone)|\bsomeone\b|\b(?:he|she|they)(?:'s| is| are)?\b|"
           r"\bmi\s+(?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|abuel[oa]|vecin[oa]|pareja|beb[eé])")
# Strong signs stand alone; weak ones ("not answering", "won't move") need a named person nearby, never just
# "I" or "they" ("I'm not answering more questions", "they're not answering my calls" are not emergencies).
_UNRESPONSIVE = (r"won'?t (?:wake|open (?:his|her|their) eyes)|wont wake|(?:not|isn'?t|isnt|stopped) (?:waking|"
                 r"breathing)|breathing (?:weird|funny|strange|shallow|slow)|turning (?:blue|purple|gr[ae]y)|out cold|"
                 r"can'?t wake|no (?:reacciona|despierta)")
_WEAK_UNRESP = (r"won'?t (?:answer|respond|move)|wont (?:answer|respond|move)|(?:not|isn'?t|isnt) (?:moving|"
                r"responding|answering)|lying (?:there|on the floor|in the|outside)|no (?:responde|se mueve)")
_NAMED_PERSON = (r"\b(?:grand(?:ma|pa|mother|father)|mom|mum|mother|dad|father|husband|wife|partner|roommate|"
                 r"neighbou?r|kid|son|daughter|baby|child|toddler|friend|boyfriend|girlfriend|man|woman|guy|lady|"
                 r"person|brother|sister|tenant|resident)\b|\bmi\s+(?:esposo|esposa|hij[oa]|mam[aá]|pap[aá]|"
                 r"abuel[oa]|vecin[oa]|pareja|beb[eé])")
_CARDIAC = (r"(?:left )?arm (?:hurts|is numb|pain|went numb)\W+(?:\w+\W+){0,8}(?:chest|sweat)|(?:sweat\w*|gr[ae]y|pale)"
            r"\W+(?:\w+\W+){0,8}(?:left )?arm (?:hurts|pain|numb)|chest (?:is )?(?:tight|pressure|hurts|crushing)|"
            r"can'?t catch (?:his|her|my|their) breath|gasping|lips (?:are )?(?:blue|turning)")
_BLEED = (r"spurt\w*|bleeding (?:everywhere|a lot|so much|nonstop|non-stop)|won'?t stop bleeding|blood everywhere|"
          r"lots? of blood|deep cut|cut (?:my|his|her) (?:hand|arm|leg|wrist)\W+(?:\w+\W+){0,6}(?:bad|deep|won'?t|"
          r"spurt|blood)|sangr\w+ mucho|mucha sangre")
_INGEST = (r"drank|drunk|drink|ate|eaten|eating|swallow\w*|chew\w*|lick\w*|got into|ingest\w*|put (?:it|some) in "
           r"(?:his|her) mouth|se (?:comi[oó]|tom[oó]|trag[oó]|bebi[oó])|comi[oó]|bebi[oó]")
_SUBSTANCE = (r"drano|drain cleaner|bleach|clean(?:er|ing (?:stuff|product|spray))\w*|chemical\w*|laundry pod|pods?\b|"
              r"pills?|tablets?|pastillas|medic\w*|meds\b|rat (?:bait|poison)|bait|poison\w*|pesticide|insecticide|"
              r"bug spray|roach|ant (?:bait|trap)|the stuff (?:the |that )?(?:pest|exterminator|bug)\w*|sprayed|"
              r"antifreeze|detergent|button batter\w*|batter(?:y|ies)|magnets?|lye|weed killer|cloro|veneno|"
              r"limpiador|lej[ií]a|cigarette|vape (?:juice|liquid)|nicotine")
_FUMES = (r"mix\w* (?:the )?(?:bleach|cleaners|chemicals)\W+(?:\w+\W+){0,4}(?:and|with) (?:ammonia|vinegar|"
          r"another|other)|bleach and ammonia|(?:fumes|chemical smell)\W+(?:\w+\W+){0,10}(?:cough\w*|can'?t breathe|"
          r"eyes (?:burn|sting)|dizz\w*)")
_SYMPTOM = (r"head ?aches?|head (?:hurts|is (?:pounding|killing))|pounding head|dizz\w*|light-?headed|nause\w*|"
            r"throwing up|vomit\w*|drows\w*|sleepy|confus\w*|faint\w*|letharg\w*|feel (?:sick|weird|off)|"
            r"mare\w*|dolor de cabeza|n[aá]use\w*|v[oó]mit\w*|somnolien\w*")
_HEAT = (r"furnace|heater|heat(?:ing)?(?:'s| is| was| has)?(?: been)? (?:on|running|blasting|cranked)|turned (?:the"
         r" )?heat (?:on|up)|boiler|"
         r"water heater|generator|fireplace|gas stove|stove|oven|car (?:running|on)|garage|exhaust|calefacci\w*|"
         r"calentador|estufa|caldera")
_SELF_HARM2 = (r"\bkms\b|\bunalive|want(?:s|ed)? (?:it all|everything|this|things|my life) to (?:end|stop|be over)|"
               r"nothing (?:left )?to live for|(?:take|swallow|overdose on|down) (?:all|a bunch|the whole bottle|"
               r"every one) (?:of )?(?:my |the |her |his )?(?:pills|meds|medication|tablets)|better off (?:if i"
               r" (?:was|were)(?:n'?t| not) (?:here|around|alive)|without me|if i (?:died|was dead|disappeared))|\bend"
               r" (?:my|his|her|their) (?:own )?life|wants? to (?:die|end (?:it|his life|her life|"
               r"their life|everything))|(?:won'?t|wont|will not) be (?:around|here|alive) (?:next|much longer|"
               r"anymore|by)|nobody (?:would|will) (?:even )?(?:notice|care|miss me)|(?:if|when) i(?:'m| am| was|"
               r" were) "
               r"gone|goodbye (?:note|letter|message)|suicide note|(?:pills|meds) (?:lined up|saved up|ready|counted)|"
               r"(?:jump|jumping) (?:off|from) (?:the|a|my)\W+(?:\w+\W+){0,3}(?:roof|bridge|garage|balcony|building|"
               r"window|ledge|overpass)|(?:thinking|thought) (?:of|about) (?:jumping|ending (?:it|things|my)|killing|"
               r"not waking up)|(?:no|ya no) quiero seguir|nicht mehr leben|will sterben|me quiero morir|quiero "
               r"morirme|hurt (?:himself|herself|themselves)|(?:cutting|cut) myself|"
               r"(?:can'?t|cant) (?:do this|go on|take (?:it|this)) anymore\W+(?:\w+\W+){0,10}(?:pills|end|die|gone|"
               r"jump|note|over|goodbye)")
_THREAT_ACTOR = (r"\b(?:my |an? |the |some )?(?:ex|ex-\w+|boyfriend|girlfriend|husband|wife|partner|man|guy|"
                 r"stranger|someone|somebody|person|people|neighbou?r)\b|pareja|esposo|novio|un hombre|alguien")
_THREAT_ACT = (r"bang\w* on (?:my|the) (?:door|window)|pound\w* on (?:my|the) door|kick\w* (?:in )?(?:my|the) door|"
               r"trying (?:the|my|every|all the) (?:door|doors|handles?|door handles?)|outside my (?:door|window|unit)"
               r"\W+(?:\w+\W+){0,6}(?:yell|threat|bang|scream|get me|won'?t leave)|watching (?:me|my (?:unit|apartment|"
               r"place|door))|follow\w* me|chok\w*|strangl\w*|hit (?:me|my)|hits me|punch\w* me|slap\w* me|beat (?:me|"
               r"up)|get me|hurt me|kill me|coming back (?:tonight|later|again)|(?:said|says|saying) (?:he|she)(?:'ll| "
               r"will| is going to) (?:get|hurt|kill)|me pega|me golpe\w*|me amenaz\w*|tengo miedo")
_STRUCT2 = (r"(?:ceiling|roof|wall)\W+(?:\w+\W+){0,3}(?:came|fell|caved|crashed) (?:down|in)|part of (?:the|my)"
            r" (?:ceiling|"
            r"roof|wall|floor) (?:came|fell|collapsed|caved)|crack\w*\W+(?:\w+\W+){0,8}(?:bowing|bulging|sagging|"
            r"widening|spreading|getting bigger)|bowing (?:down|in|out)|pull\w* away from (?:the )?(?:building|wall)|"
            r"about to (?:give out|collapse|fall|cave)|g[ai]ve way|tree (?:fell|came down|crashed) (?:on|through|into)|"
            r"hole in (?:the|my) (?:roof|ceiling)|hole above|se est[aá] cayendo el techo|grieta")
_ELEC2 = (r"\bzapp\w*|\bshocked\b|electric (?:shock|current)|(?:outlet|socket|switch|plug|panel|"
          r"breaker)\W+(?:\w+\W+){0,8}"
          r"(?:pop\w*|bang|black mark|scorch\w*|crackl\w*|warm|hot to the touch|burn\w*)|(?:pop\w*|"
          r"bang)\W+(?:\w+\W+){0,6}"
          r"(?:outlet|socket|panel|breaker)|fray\w*\W+(?:\w+\W+){0,6}(?:copper|wire|cord)|copper (?:is )?(?:showing|"
          r"exposed)|buzz\w* (?:inside|in|behind) the wall|flicker\w*\W+(?:\w+\W+){0,8}(?:buzz\w*|crackl\w*|burn\w*)")
_FLOOD2 = (r"\b\d+ (?:inch|inches|in\.?|cm) of water|ankle[- ]deep|knee[- ]deep|soak\w* (?:the|my) (?:carpet|floor|"
           r"rug|bed)|leaking into my (?:unit|apartment|place) (?:really |so )?(?:fast|bad)|water\W+(?:\w+\W+){0,2}"
           r"(?:pouring|gushing|streaming|flowing|rushing|coming|leaking fast) (?:in )?(?:through|from|out of) the "
           r"(?:ceiling|light)|overflow\w*\W+(?:\w+\W+){0,8}(?:under the door|into the|out of the)"
           r"|(?:agua|water)\W+(?:\w+\W+){0,8}(?:llega a|por debajo|under the door|into the (?:hall|bedroom|living))|"
           r"se est[aá] saliendo el agua|rising water|water keeps (?:rising|coming)")
_GAS2 = (r"sulfur|sulphur|rotten[- ]?eggs?|huevo|skunk\W+(?:\w+\W+){0,8}(?:stove|oven|water heater|furnace|kitchen|"
         r"burner|closet)|(?:smells?|smelling|odou?r)\W+(?:\w+\W+){0,3}(?:funky|weird|strange|off|"
         r"funny)\W+(?:\w+\W+){0,8}"
         r"(?:stove|burner|oven|water heater|furnace)|(?:stove|burner|oven|range)\W+(?:\w+\W+){0,8}(?:hiss\w*|"
         r"left on (?:for|all|overnight))|hiss\w*\W+(?:\w+\W+){0,8}(?:stove|burner|gas line|meter)|"
         r"(?:burner|knob|stove)\W+(?:\w+\W+){0,5}left on\W+(?:\w+\W+){0,8}(?:smell|smells)|huele"
         r" raro\W+(?:\w+\W+){0,6}"
         r"(?:cocina|estufa|huevo)")
_FIRE2 = (r"black (?:stuff|smoke)\W+(?:\w+\W+){0,4}(?:pour\w*|coming|out of)|pour\w* out of the (?:dryer|vent|oven|"
          r"microwave)\W+(?:\w+\W+){0,6}(?:smell|black)|(?:went|go(?:ing)?) up in flames|grease\W+(?:\w+\W+){0,6}"
          r"(?:went up|caught|flar\w*|ignit\w*)|\bcharred\b|\bablaze\b|(?:caught|catch\w*) fire|set (?:the )?\w+ on"
          r" fire|"
          r"\bsmoldering\b|\bsmouldering\b")
_TRAPPED2 = (r"(?:locked|stuck|trapped) (?:himself|herself|themselves|myself|in)\W+(?:\w+\W+){0,8}(?:isn'?t|not|won'?t|"
             r"can'?t)\W+(?:\w+\W+){0,1}(?:answer\w*|respond\w*|open|get out)|(?:locked|stuck|trapped) in (?:my|the|"
             r"his|"
             r"her) (?:bedroom|bathroom|room|closet|unit)|door (?:handle|knob)\W+(?:\w+\W+){0,4}(?:broke|came off)\W+"
             r"(?:\w+\W+){0,6}(?:locked|stuck|trapped)|atorad[oa]|atrapad[oa]|encerrad[oa]")


def _near(a: str, b: str, gap: int = 12) -> re.Pattern[str]:
    """a then b, or b then a, within `gap` words."""
    w = rf"\W+(?:\w+\W+){{0,{gap}}}"
    return re.compile(rf"(?:{a}){w}(?:{b})|(?:{b}){w}(?:{a})", re.I)


CONCEPTS: list[tuple[str, re.Pattern[str]]] = [
    ("self_harm", re.compile(_SELF_HARM2, re.I)),
    ("poison", _near(_INGEST, _SUBSTANCE, 8)),
    ("poison", re.compile(_FUMES, re.I)),
    ("trapped", re.compile(_TRAPPED2, re.I)),
    ("medical", _near(_PERSON, _UNRESPONSIVE, 10)),
    ("medical", _near(_NAMED_PERSON, _WEAK_UNRESP, 8)),
    ("medical", re.compile(_UNRESPONSIVE + "|" + _CARDIAC + "|" + _BLEED, re.I)),
    ("personal_safety", _near(_THREAT_ACTOR, _THREAT_ACT, 10)),
    ("co", _near(_SYMPTOM, _HEAT, 14)),
    ("co", re.compile(r"(?:co |carbon |little |the )?detector\W+(?:\w+\W+){0,8}(?:beep\w* (?:4|four) times|flash\w* "
                      r"red|red light)", re.I)),
    ("structural", re.compile(_STRUCT2, re.I)),
    ("fire_smoke", re.compile(_FIRE2, re.I)),
    ("electrical", re.compile(_ELEC2, re.I)),
    ("flood", re.compile(_FLOOD2, re.I)),
    ("gas", re.compile(_GAS2, re.I)),
]

# Danger vocabulary: high recall, low severity. Not enough for the full alert or an urgent note, but enough that
# the reply leads with "if anyone is hurt or in danger, call 911". Measured separately from full-alert recall.
_DANGER = re.compile(
    r"\b(?:burn(?:t|ing|ed)?|scorch\w*|smok(?:e|ing|y)|glow\w*|crackl\w*|flames?|fumes?|sulfur|propane|gas|"
    r"spark\w*|zap\w*|shock\w*|tingl\w*|electrocut\w*|live wires?|power lines?|downed line|"
    r"sewage|flood\w*|gush\w*|pouring|(?:through|from) the ceiling|ceiling (?:is )?(?:leak\w*|drip\w*)|"
    r"collaps\w*|caved?|cave-in|bulg\w*|sagg\w*|spongy|gave way|give out|snapp?ed|fell off|fallen|fell down|"
    r"brick|masonry|crack\w* (?:wall|ceiling|beam)|"
    r"hurt|injur\w*|bleed\w*|blood|broken (?:arm|leg|bone|hip|wrist)|bone|bent (?:the )?wrong way|unconscious|"
    r"faint\w*|seizure|stroke|slurr\w*|droop\w*|chest|breath\w*|chok\w*|hard to wake|won'?t wake|not waking|"
    r"blood sugar|diabet\w*|overdos\w*|poison\w*|swallow\w*|ingest\w*|edibles?|"
    r"gun|shoot\w*|knife|stab\w*|threat\w*|stalk\w*|intruder|break(?:ing)? in|broke in|hiding|scared|afraid|"
    r"someone (?:is )?in my|following (?:me|us|residents)|"
    r"trapped|stuck in|can'?t get out|won'?t open|locked in|"
    r"rope|goodbye|giving away|sleep forever|no way out|end it|despedí|lo hago|"
    r"humo|fuego|incendio|sangr\w*|herid\w*|inconsciente|atrapad\w*|miedo|pistola|cuchillo)\b", re.I)
_DANGER_NOT = re.compile(r"sparks? joy|gas (bill|station|company|stove (is|works) fine)|fire (lane|exit|drill|alarm "
                         r"test|extinguisher)|chest of drawers|burning question|smoke[- ]free|no smoking|"
                         r"bone dry|broke (?:the )?bank", re.I)
_SELF_HARM_HINT = re.compile(r"\brope\b|goodbye (?:to|letter|note)|giving away (?:my|all)|sleep forever|no way out|"
                             r"won'?t need (?:it|them|anything) (?:soon|anymore)|despedí de todos|esta noche lo hago|"
                             r"not (?:be )?(?:around|here) (?:much longer|anymore)", re.I)

# Third tier: not enough to call it an emergency, too much to say nothing. The reply keeps going but leads with a
# calm safety line (no urgent note, no alarm). "distress" adds 988; "unwell" adds 911-if-worse.
_DISTRESS = re.compile(
    r"what'?s the point(?: of (?:anything|living|trying|it all|going on|me|life)| anymore|\W*$)|no point (?:in living|"
    r"anymore|in anything)|(?:can'?t|cant) (?:do this|go on|take (?:it|this))(?: like this)? anymore|"
    r"(?:can'?t|cant) go on like this|give up on (?:everything|life)|(?:feel|feeling|i'?m|im) (?:so |really )?hopeless|"
    r"(?:i'?m|im) (?:so )?done with (?:everything|life)|(?:won'?t|wont) (?:be around|matter)|"
    r"everything is falling apart|ya no puedo m[aá]s|no aguanto m[aá]s", re.I)
_UNWELL = re.compile(_SYMPTOM.replace(r"confus\w*|", "").replace(r"feel (?:sick|weird|off)|", "")
                     + r"|can'?t breathe well|short of breath", re.I)


CARE_NOTE = {
    "distress": {"en": "If things feel like too much right now, you can call or text 988 any time to talk with"
                       " someone. "
                       "If you're in danger, call 911.",
                 "es": "Si siente que todo es demasiado ahora, puede llamar o enviar un mensaje al 988 a cualquier"
                       " hora "
                       "para hablar con alguien. Si está en peligro, llame al 911."},
    "unwell": {"en": "If anyone feels very unwell or it gets worse, call 911.",
               "es": "Si alguien se siente muy mal o empeora, llame al 911."},
    "danger": {"en": "If anyone is hurt or in danger right now, call 911. If something in your home is unsafe, stay "
                     "away from it and call your community's emergency maintenance line.",
               "es": "Si alguien está herido o en peligro ahora, llame al 911. Si algo en su casa no es seguro, "
                     "aléjese y llame a la línea de emergencias de mantenimiento."},
}
REFUSE_LEAD = {
    "en": "I understand. I can't send anyone from here, and nobody has been sent. Staying could be dangerous, so "
          "please follow these steps now: ",
    "es": "Entiendo. Desde aquí no puedo enviar a nadie y no se ha enviado a nadie. Quedarse podría ser peligroso, "
          "así que por favor siga estos pasos ahora: ",
}


def possible_risk(message: str) -> str | None:
    """'distress' / 'unwell' / None for messages that are not a clear emergency (use when emergency_kind is None)."""
    text = _prepare(message)
    if _DISTRESS.search(text) or _SELF_HARM_HINT.search(text):
        return "distress"
    if _DANGER.search(_DANGER_NOT.sub(" ", text)):
        return "danger"
    if _UNWELL.search(text):
        return "unwell"
    return None


_SPACED = re.compile(r"\b[A-Za-z]([ .*_\-])(?:[A-Za-z]\1){1,}[A-Za-z]\b")  # one separator style per word
_POLICY_OR_FIGURATIVE = re.compile(
    r"smoking (allowed|policy|permitted|area|section)|(no|non)[- ]?smoking|smoke[- ]free|allow smoking|can i smoke|"
    r"(?:schedul\w*|when is|book)\W+(?:\w+\W+){0,4}(?:inspection|test(?:ing)?)|(?:fire|smoke|co|carbon monoxide)"
    r" (?:alarm|detector)s? (?:inspection|test(?:ing)?|check)|are there (?:any )?(?:co|smoke|carbon monoxide|fire)"
    r" (?:detectors|alarms)|(?:detectors|alarms) in (?:every|each|all) (?:unit|apartment)s?|"
    r"(?:smoke |fire |co )?(?:detector|alarm)\W+(?:\w+\W+){0,3}going off\W+(?:\w+\W+){0,2}(?:when|while|whenever|"
    r"every time) (?:i|we) (?:cook|shower|make|burn toast)|"
    r"fire lane|fire exit|fire door|sparks? joy|(?:can|should) i (?:mix|use)\W+(?:\w+\W+){0,4}(?:bleach|"
    r"ammonia|vinegar)|"
    r"knife (block|set|drawer)|stroke of (luck|genius)|burning (to|question)|burn(s|ing)? (food|the food|toast|rice|"
    r"dinner)|well[- ]lit|just kidding|jk\b|fire (pit|place|sale|drill)|smoking hot",
    re.I)
_BENIGN_CHIRP = re.compile(r"(smoke|co|carbon monoxide) (alarm|detector).{0,40}(chirp|beep|batter)\w*.{0,40}"
                           r"(batter|chirp)|batter\w*.{0,40}(smoke|co|carbon monoxide) (alarm|detector)", re.I)


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
    # "Is the parking lot well lit? I don't feel safe walking" asks about lighting; it is not a threat in progress.
    threat = re.search(r"following|stranger|\bex\b|someone|scared|threat|gun|knife|hit|hurt|kill|break", text, re.I)
    if not threat and "?" in text and re.search(r"feel safe (walking|at night|in the parking)", text, re.I):
        text = re.sub(r"feel safe", " ", text, flags=re.I)
    if _BENIGN_CHIRP.search(text) and not re.search(r"smoke (is|coming)|fire|flame|head|dizz|nause", text, re.I):
        return None
    for kind, pat in KINDS:
        if pat.search(text):
            return kind
    for kind, pat in CONCEPTS:
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
