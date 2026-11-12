"""Deterministic emergency detection and per-hazard safety text (I-17 / I-18 TEAM DRAFTS, not McKinley-approved).

Runs on every message, for every audience, before identity, drafts or any model. Errs on the side of treating a
message as an emergency: a false alarm costs a phone call, a miss can cost a life. The safety text never tells the
person to do anything risky and never claims anyone was dispatched. McKinley maintenance and risk/legal must
approve the list and the wording (docs/workflows/traceability.md, I-17/I-18).
"""

import re
import unicodedata

from app.risk.concepts import PRESENT_PERSON as _PRESENT_PERSON_RE
from app.risk.concepts import RULES as CONCEPT_RULES
from app.risk.concepts import cold_exposure as _cold_exposure
from app.risk.concepts import concern as _concern
from app.risk.concepts import not_physical as _not_physical
from app.risk.concepts import present_signs as _present_signs
from app.risk.concepts import stockpile as _stockpile
from app.risk.concepts import veiled_farewell as _veiled_farewell

# Ordered: the first match wins, so the most life-critical kinds come first.
_W = r"(?:\w+\W+){0,6}"  # up to six words in between
KINDS: list[tuple[str, re.Pattern[str]]] = [
    ("self_harm", re.compile(
        r"kill(ing)? my ?self|suicid|\bend (my (own )?life|it all)\b|want to die|wanna die|don'?t want to (live|be "
        r"alive|be here anymore)|hurt(ing)? my ?self|no reason to live|matarme|quitarme la vida|suicidar|"
        r"quiero morir|tự tử|muốn chết|(don'?t|dont|do not) (want|wanna) (to )?(be here|exist|wake up|go on)|"
        r"better off (dead|without me)|\bending (it all|my life|things)\b|\bend (it|things) all\b|want to (end it|"
        r"disappear)|"
        r"ganas de morir|me (?:voy a|quiero) matar|quiero matarme|acabar con (?:mi vida|todo)|no vale la pena vivir|"
        r"no quiero (vivir|estar aqu[ií])", re.I)),
    ("poison", re.compile(
        r"(drank|drunk|ate|eaten|got into)\W+(?:\w+\W+){0,6}(clean\w*|bleach|chemical\w*|pills?|medicine|"
        r"poison|detergent|pods?|magnets?|batter(y|ies)|antifreeze)|se tom[oó]\W+(?:\w+\W+){0,3}(cloro|"
        r"limpiador|pastillas)|swallow\w*\W+(?:\w+\W+){0,6}magnets?|"
        r"swallow\w*\W+(?:\w+\W+){0,6}(clean\w*|bleach|chemical\w*|pills?|medicine|poison|detergent|pod|battery|"
        r"batteries)|\bpoison(ed|ing)?\b|overdos|trag[oó]\W+(?:\w+\W+){0,4}(cloro|limpia\w*|pastillas|veneno)|"
        r"(?:took|taken|swallowed|downed|popped|tom[eé]|se tom[oó])\W+(?:like |maybe |about )?(?:all|a bunch|a handful|"
        r"a lot|way too many|too many|the whole bottle|\d+|twenty|thirty|forty|fifty|muchas|demasiadas|todas)\W+"
        r"(?:\w+\W+){0,4}(?:pills|meds|medication|tablets|pastillas|xanax|tylenol|advil|ibuprofen|oxy\w*|percocet)|"
        r"(?:pills|meds|medication|tablets|pastillas)\W+(?:\w+\W+){0,6}(?:with|and|con) (?:alcohol|vodka|wine|beer|"
        r"liquor|whiskey|tequila|drinks)|sobredosis", re.I)),
    ("trapped", re.compile(
        r"stuck in (the|an|my) (elevator|lift)|(elevator|lift) stopped|(locked|stuck|trapped) in\W+(?:\w+\W+){0,4}"
        r"(can'?t|cannot) get out|can'?t get out of (the|my) (elevator|lift|room|bathroom)|(elevator|"
        r"lift)\W+(?:\w+\W+){0,4}stuck|trapped (in|inside|under)|"
        r"atrapad[oa] en el (elevador|ascensor)", re.I)),
    ("structural", re.compile(
        # fix round (P2): a loose / wobbly railing alone is a repair (calm 911 line + form); it is an emergency when
        # it broke, came off or gave way, or with a danger sign (someone almost fell, leaning on it, a child near it)
        r"(railing|handrail|balcony)\W+(?:\w+\W+){0,4}(broke|broken|gave way|came off|came loose|snapped|"
        r"fell (?:off|down)|collaps\w*)|"
        r"(railing|handrail)\W+(?:\w+\W+){0,4}(loose|wobbl\w*|moves|shak\w*)\W+(?:\w+\W+){0,10}(almost fell|nearly "
        r"fell|about to (?:give|fall|come off|break)|could fall|leaning on|lean on|kid|child|toddler|baby|"
        r"fell|falling|pulling (?:out|away))|"
        r"(almost fell|nearly fell|leaning on|lean on)\W+(?:\w+\W+){0,8}(railing|handrail)\W+(?:\w+\W+){0,4}"
        r"(loose|wobbl\w*|moves|shak\w*)|"
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
        r"dolor (en el|de) pecho|no respira|inconsciente|se desmay|đau ngực|không thở|"
        r"(?:barely|struggling to|hard to|trouble|having trouble) breath\w*|can'?t get (?:enough )?air|"
        r"chest (?:feels? |is )?(?:heavy|tight|tightness|pressure|crushing)|bone (?:is )?(?:sticking out|showing)|"
        r"(?:fell|fallen) (?:down|off|from)\W+(?:\w+\W+){0,6}(?:can'?t|cannot|won'?t) (?:move|get up|walk|stand)|"
        r"convulsi\w+|ataque (?:al coraz[oó]n|card[ií]aco)|sangra(?:ndo)? mucho|no (?:puede|puedo) respirar|"
        r"se (?:peg[oó]|golpe[oó]) (?:en )?la cabeza", re.I)),
    ("personal_safety", re.compile(
        r"break(ing)? ?in\b|\bbroke (?:in|into)\b|breaking into|broke into|broken into|(trying|tried) to (get|break)"
        r" in|intruder|"
        r"someone (is )?(in|inside) my (apartment|unit|home|place)|threat(en|ening)|stalk(ing|er)|"
        r"domestic (violence|abuse)|abus(e|ing|ive) (me|partner)|(hit|hitting|beat|beating|hurt|hurting) "
        r"(me|her|him|them|someone|a child|the kids?)\b|(screaming|yelling)\W+(?:\w+\W+){0,8}(hit|hurt|help)|"
        r"(don'?t|do not|no longer) feel safe\b|\bgun(s|shots?|fire)?\b|shots? fired|\bknife\b|"
        r"(kill|hurt) me\b|following me|stranger (is )?in (my|the) (apartment|unit|home)|"
        r"won'?t leave\W+(?:\w+\W+){0,4}scared|i'?m scared (?:for my life|he|she|they|of (?:him|her|them|my (?:ex|"
        r"partner|"
        r"husband|wife|boyfriend|girlfriend)))|"
        r"\bweapon|attack(ed|ing)? me|"
        r"me (amenaza|golpea|quiere hacer daño)|entraron a (mi|robar)|no me siento segur|"
        r"tiene (?:un|una) (?:arma|pistola|cuchillo)|me (?:quiere|va a) (?:matar|pegar|lastimar)|"
        r"alguien (?:est[aá] )?(?:entr[oó]|tratando de entrar|intentando entrar)|"
        r"me est[aá] (?:siguiendo|amenazando|pegando)|violencia dom[eé]stica", re.I)),
    ("gas", re.compile(
        rf"(smel+\w*|odou?r|olor|huel\w*|stink\w*|reek\w*|whiff|leak\w*|hiss\w*|mùi|rò rỉ)\W+{_W}"
        r"(ga+s+|propane|natural gas|gasolina)\b|"
        rf"\b(ga+s+|propane)\b\W+{_W}(smel+\w*|leak\w*|odou?r|hiss\w*|stink\w*)|fuga de gas|olor a gas|huele a gas|"
        r"pilot light\W+(?:\w+\W+){0,4}smel\w*|smel\w*\W+(?:\w+\W+){0,6}pilot light|huevo podrido|khí ga|mùi ga|غاز|"
        r"煤气|燃气|瓦斯|rotten"
        r" egg|\bgaz\b|gaz kokusu|odeur de gaz|zapach gazu", re.I)),
    ("co", re.compile(
        r"carbon mon\w*|mon[oó]xid\w*|monixide|\bco (thing|sensor)|\bco\b ?(alarm|detector|monitor)|(alarm|detector)"
        r" (for|de) (co|mon[oó]xido)|"
        # sprint 5.1 (E-1): "CO" abbreviated next to the device or its display ("the alarm says CO", "it shows CO on
        # the detector", "CO level is 80"). "co" must stand alone: not "co-signer", "co.", "& co".
        r"(?:alarm|detector|monitor|sensor|display|screen)\w*\W+(?:\w+\W+){0,4}(?:says?|said|reads?|shows?|showing|"
        r"display\w*|flash\w*|blink\w*)\W+(?:\w+\W+){0,2}co\b(?![-'.&]\w)|"
        r"(?:says?|reads?|shows?|showing|display\w*|flash\w*)\W+(?:\w+\W+){0,1}co\b(?![-'.&]\w)\W+(?:\w+\W+){0,4}"
        r"(?:alarm|detector|monitor|sensor|display|screen)|"
        r"\bco\b(?![-'.&]\w)\W+(?:\w+\W+){0,3}(?:on|in) (?:the|my|our) (?:\w+ )?(?:alarm|detector|monitor|sensor|"
        r"display|screen)|\bco (?:levels?|reading|ppm|warning|alert)\b",
        re.I)),
    ("fire_smoke", re.compile(
        r"\bfire\b(?! ?(alarm test|drill|place|pit|extinguisher|department|dept\b|works|fighter|d\b|station|"
        r"house|escape|lane|marshal|truck|engine|crew|m[ae]n\b))|\bflames?\b|"
        r"on fire|\bburning\b(?! question)|burnt? (smell|plastic|rubber)|smells? (like |of )?(burn|smoke)|"
        r"smell\w*\W+(?:\w+\W+){0,2}(?:burnt|burning|smoky)|"
        r"\bsmok(e|ing|y|in'?)\b(?! ?(detector|alarm)\b(?!.{0,30}(going off|sounding|won'?t stop|keeps going)))|"
        r"(smoke|fire) (alarm|detector)s? (is |are )?(going off|sounding|won'?t stop|keeps going)|"
        r"\bhumo\b|\bfuego\b|incendio|quemando|quemado|cháy|khói|حريق|دخان|着火|火灾|冒烟|"
        r"(?:room|kitchen|hallway|apartment|unit|air|place)\W+(?:\w+\W+){0,3}(?:is |getting |all )?(?:hazy|smoky)",
        re.I)),
    ("electrical", re.compile(
        r"\bspark(s|ed|in'?)?\b|\bsparking\b|chispa|(exposed|bare|loose|hanging|hangin'?) wires?|"
        r"wires?\W+(?:\w+\W+){0,3}(hanging|hangin'?|exposed|sticking out|coming out)|"
        r"(panel|breaker|outlet|socket|switch|wire|wiring|cord|plug|fuse box)\W+(?:\w+\W+){0,8}"
        r"(hot|buzz\w*|burn\w*|melt\w*|smok\w*|scorch\w*|sizzl\w*)|"
        r"(water|leak\w*|drip\w*)\W+(?:\w+\W+){0,4}(?:in|into|from|out of|through|on|onto|near|around|behind|over)"
        r" (?:the |my |a |an )?(?:\w+ )?(light|fixture|outlet|socket|electric\w*|wiring|panel|breaker)s?\b|"
        r"\b(light|fixture|outlet|socket|panel|breaker)s?\W+(?:\w+\W+){0,3}(?:is |are )?(?:leaking|dripping|full of "
        r"water|filling with water|wet|soaked)|electrocut|shock(ed|ing)? me|"
        r"chispea|cables? (?:expuestos?|pelados?|sueltos?)|(?:enchufe|tomacorriente)\W+(?:\w+\W+){0,3}(?:echa|"
        r"est[aá]|sale)\W+(?:\w+\W+){0,1}(?:humo|chispas|caliente)|me dio (?:la )?corriente|descarga el[eé]ctrica",
        re.I)),
    ("flood", re.compile(
        r"\bflood(ing|ed|s)?\b(?! ?(zone|insurance|plain|light))|water (is )?(pouring|everywhere|gushing|spraying|"
        r"coming in|pouring in|all over)|(pipe|line|hose) (has )?(burst|broke|exploded|split)|burst (pipe|line)|"
        r"\bgushing\b|overflow\w*\W+(?:\w+\W+){0,8}(hallway|everywhere|won'?t stop|another room|downstairs)|"
        r"inund\w*|agua por todas partes|se rompi[oó] (una|la) (tuber[ií]a|ca[ñn]er[ií]a)|tuber[ií]a rota|ngập|"
        r"revent[oó] (?:una|la) (?:tuber[ií]a|ca[ñn]er[ií]a)|agua\W+(?:\w+\W+){0,2}(?:entrando|saliendo|cayendo) "
        r"(?:por|del) (?:el )?techo",
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
            r"throwing up|vomit\w*|drows\w*|sleepy|confus\w*|faint\w*|letharg\w*|"
            r"feel (?:sick(?! of| and tired)|weird|off)|"
            r"mare\w*|dolor de cabeza|n[aá]use\w*|v[oó]mit\w*|somnolien\w*")
_HEAT = (r"furnace|heater|heat(?:ing)?(?:'s| is| was| has)?(?: been)? (?:on|running|blasting|cranked)|turned (?:the"
         r" )?heat (?:on|up)|boiler|"
         r"water heater|generator|fireplace|gas stove|stove|oven|car (?:running|on)|garage|exhaust|calefacci\w*|"
         r"calentador|estufa|caldera")
_SELF_HARM2 = (r"\bkms\b|\bunalive|want(?:s|ed)? (?:it all|everything|this|things|my life) to (?:end|stop|be over)|"
               r"nothing (?:left )?to live for|(?:take|swallow|overdose on|down) (?:all|a bunch|the whole bottle|"
               r"every one) (?:of )?(?:my |the |her |his )?(?:pills|meds|medication|tablets)|better off (?:if i"
               r" (?:was|were)(?:n'?t| not) (?:here|around|alive)|without me|if i (?:died|was dead|disappeared))|\bend"
               r"(?:ed|ing|s)? (?:my|his|her|their) (?:own )?life|wants? to (?:die|end (?:it|his life|her life|"
               r"their life|everything))|(?:won'?t|wont|will not) be (?:around|here|alive) (?:next|much longer|"
               r"anymore|by)|nobody (?:would|will) (?:even )?(?:notice|care|miss me)|(?:if|when) i(?:'m| am| was|"
               r" were) "
               r"gone\b(?! (?:on|for|to|away|out|during|over|at|this|next|from))|goodbye (?:note|letter|message)|suici"
               r"de note|(?:pills|meds) (?:lined up|saved up|ready|counted)|"
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
               r"up)|(?:\'ll|will|going to|gonna|coming to) get me|hurt me|kill me|coming back (?:tonight|later|"
               r"again)|(?:said|says|saying) (?:he|she)(?:'ll| "
               r"will| is going to) (?:get|hurt|kill)|me pega|me golpe\w*|me amenaz\w*|tengo miedo")
_STRUCT2 = (r"(?:ceiling|roof|wall)\W+(?:\w+\W+){0,3}(?:came|fell|caved|crashed) (?:down|in)|part of (?:the|my)"
            r" (?:ceiling|"
            r"roof|wall|floor) (?:came|fell|collapsed|caved)|crack\w*\W+(?:\w+\W+){0,8}(?:bowing|bulging|sagging|"
            r"widening|spreading|getting bigger)|bowing (?:down|in|out)|pull\w* away from (?:the )?(?:building|wall)|"
            r"about to (?:give out|collapse|fall|cave)|g[ai]ve way|tree (?:fell|came down|crashed) (?:on|through|into)|"
            r"hole in (?:the|my) (?:roof|ceiling)|hole above|se est[aá] cayendo el techo|"
            # sprint 7: a crack alone is a repair; only a crack that grows / opens is structural danger
            r"grieta\W+(?:\w+\W+){0,4}(?:creciendo|cada vez m[aá]s|se (?:est[aá] )?abriendo|enorme|se agranda)")
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

# ---- sprint 3: meaning-level concepts (generic vocabularies, combined; not copies of any test sentence) ----
# Self-harm without the words "suicide/kill/die": a burden/hopelessness idea next to a finality/method idea.
_BURDEN = (r"(?:i'?m|i am|feel like (?:i'?m|i am)|being) (?:just |such )?(?:a |an )?(?:burden|waste of space)|better "
           r"off without me|(?:everyone|they|my (?:family|kids|mom|dad|wife|husband)) (?:would|will|'d) be (?:better|"
           r"fine|happier|okay)(?: off)? without me|(?:won'?t|will not|wont) be (?:a |anyone'?s )?(?:problem|burden|"
           r"bother) (?:for )?(?:you |anyone )?(?:much )?(?:longer|anymore|soon)|(?:tired|exhausted|sick) of (?:being "
           r"alive|existing|living)|(?:don'?t|do not|can'?t) see (?:a|any) (?:future|way out)|nothing (?:left )?to "
           r"live for|no (?:one|body) (?:would|will) (?:even )?(?:miss|notice)|easier (?:for everyone )?if i (?:weren'"
           r"?t"
           r"|wasn'?t|was not|were not) (?:here|around|alive)|soy una carga|sin m[ií] (?:estar[ií]an|todos) mejor|"
           r"no (?:veo|tengo) (?:salida|futuro)")
_FINAL = (r"(?:my )?last (?:night|day|week) (?:here|alive|on earth)|(?:last|final) (?:goodbye|message|words|note)|"
          r"one last time|after (?:tonight|i'?m gone|i die|my death|i'?m dead)|for after\b|(?:won'?t|will not|wont) "
          r"need (?:the apartment|this apartment|the lease|my (?:stuff|things)|anything) (?:anymore|after|soon|much "
          r"longer)|say(?:ing)? (?:my )?goodbyes?|(?:wrote|writing|written|left) (?:a |my )?(?:goodbye )?(?:letters?|"
          r"notes?) (?:to|for)|giv(?:e|ing) away (?:my|all)|rehom\w*|new home for my|affairs in order|(?:made|have|got|"
          r"making) a plan|decided (?:to end|how|when|it'?s time)|end (?:it|things|everything)\b|make it (?:all )?"
          r"stop|(?:not|never) (?:wake|waking) up|(?:not|never) (?:coming|come) back|(?:gone|disappear\w*) (?:for "
          r"good|forever)|(?:stockpil|sav|hoard)\w* (?:up )?(?:my |the )?(?:pills|meds|medication)|(?:bought|got) "
          r"(?:a )?(?:rope|gun)|me despido|despedirme|ya no voy a estar|\brope\b|bridge|ledge")
_HEIGHT_ALONE = (r"(?:go|going|walk|head|climb)\w* (?:up )?(?:to|on) (?:the )?(?:roof|rooftop|top floor|bridge|ledge|"
                 r"parking (?:garage|deck) roof)\W+(?:\w+\W+){0,8}(?:alone|by myself|and not|won'?t|not come|for the "
                 r"last|one last)")
_METHOD = (r"(?:keep|kept|been) (?:looking at|staring at|holding|thinking about) (?:the |a |my )?(?:knife|knives|rope|"
           r"pills|gun|razor|blade)|(?:rope|noose|razor|blade|pills|gun) (?:is |are )?(?:ready|set up|tied|in my|next "
           r"to)|"
           r"how many (?:pills|tablets|of (?:my|these|the) (?:pills|meds))\W+(?:\w+\W+){0,6}(?:to (?:die|not wake|sleep"
           r" forever|end)|would it take|is (?:too many|enough|lethal|fatal))|(?:lethal|fatal) dose|enough (?:pills|me"
           r"ds)"
           r" to")
_GONE = (r"(?:when|after|once|if) i(?:'m (?:not around|gone|not here|no longer here)|'ll be gone| pass away| die)"
         r"(?: anymore)?"
         r"\b(?! (?:on|for|to|away|out|during|over|at|of|from|this|next))|(?:not|won't be) (?:around|here|alive) "
         r"(?:anymore|much longer)|(?:pass away|die) soon")
_GONE_PLAN = (r"planning|plan\b|tonight|soon|this week|already|arrang\w*|sorted|found someone|take (?:my|care of my)|"
              r"have to deal|won't have to|so (?:my|the) (?:family|kids|sister|brother|mom|dad|parents|roommate)|"
              r"deposit|rent early|for after|my stuff|my things|my (?:dog|cat|pets?)")
# Sprint 8 (verifier P0-B): a wish or plan to take MORE medicine than prescribed ("I want to take the whole bottle",
# "thinking of taking the rest", "wish I could take them all", "quiero tomarme todo el frasco") is self-harm intent,
# also after a routine dose ("I took 2 tylenol for my headache but I want to take the whole bottle").
OD_INTENT = re.compile(
    # only with a medicine word somewhere in the message ("take the rest of the week off" is not an overdose)
    r"^(?=[\s\S]*\b(?:pills?|tablets?|meds|medicines?|medications?|tylenol|advil|ibuprofen|aspirin|xanax|sleeping|"
    r"prescriptions?|pastillas?|medicinas?|frasco)\b)[\s\S]*?"
    r"\b(?:want(?:s|ed)?|wanna|thinking (?:about|of)|wish(?: i could)?|going to|gonna|plan(?:ning)? (?:to|on)|might|"
    r"about to|tempted to|could just|feel like|quiero|pienso|voy a|tengo ganas de)\b[^.?!]{0,40}?"
    r"\b(?:tak(?:e|ing)|"
    r"swallow(?:ing)?|down(?:ing)?|tomar(?:me)?|tragar(?:me)?)\b[^.?!]{0,30}?\b(?:the rest|the whole|whole bottle|all "
    r"(?:of )?(?:them|it|my|the|those)|them all|everything|the (?:entire )?bottle|todo|todas|el resto|el frasco)\b",
    re.I)


_INTENT = (r"(?:roof|rooftop|top (?:floor|of (?:the|a|my) (?:\w+ ){0,2}(?:garage|building|bridge|parking structure|"
           r"tower))|bridge|ledge|overpass|balcony)\W+(?:\w+\W+){0,10}(?:not coming (?:back|down|home)|never coming "
           r"back|step off|jump\w*|let go|for the last time|one last time)|how easy it (?:would|'d) be to (?:just )?"
           r"(?:step off|jump|fall|end|let go|disappear|not|stop)|this is (?:my|the) last (?:message|text|time)\W+"
           r"(?:\w+\W+){0,12}(?:thank|goodbye|bye|love|sorry|forgive|take care)|(?:happier|better|easier|fine|okay)"
           r" (?:off )?if i (?:just )?(?:wasn't|weren't|was not|were not|was gone|were gone|disappeared|died|didn't "
           r"exist)(?: here| around| alive)?|\bi(?:'ll|'m going to|'m gonna)? end (?:it|things|everything|my life)"
           r" (?:all )?(?:tonight|today|now|soon|this week)\b|(?:tonight|today)\W+(?:\w+\W+){0,2}i(?:'ll)? end "
           r"(?:it|things|everything)\b|terminar con todo|acabar con todo|quitarme de en medio")
_PASSIVE_SI = (r"(?:want|wanna|like) to (?:go to )?sleep and (?:never|not) wake up|"
               r"wish i (?:wouldn'?t|didn'?t|could(?:n'?t)? just|would(?:n'?t)?) (?:wake up|exist|be here|disappear)|"
               r"(?:hope|wish) i (?:don'?t|never) wake up|(?:wouldn'?t|would not) mind (?:if i )?(?:dying|not waking|"
               r"never waking)|ojal[aá] no despertar|quisiera desaparecer")
_OVERWHELM = (r"can'?t stop crying|crying (?:all|every|non ?stop)\w*|so overwhelmed|(?:i'?m|im|i am) falling apart|"
              r"breaking down|breaking point|(?:can'?t|cannot) cope|me siento (?:tan |muy )?sol[oa]|nadie me (?:quiere|"
              r"extra[ñn]a)|estoy (?:muy |tan )?(?:deprimid[oa]|desesperad[oa])")
# Overdose / poisoning described by signs rather than an ingestion verb.
_OD_SIGNS = (r"pinpoint pupils|narcan|naloxone|(?:lips|fingertips|fingers?|nails) (?:are |look |turned |turning )?(?:b"
             r"lue|"
             r"purple|gr[ae]y)|(?:snoring|gurgling|rattling)\W+(?:\w+\W+){0,8}(?:won'?t|can'?t|not) (?:wake|respond)|"
             r"nodding off\W+(?:\w+\W+){0,8}(?:won'?t|can'?t|not|breath\w*)")
_CHEM = r"bleach|ammonia|cleaners?|chemicals?|fumes|spray\w*|pesticide|exterminator|bug bomb|fogger|insecticide|vinegar"
_CHEM_HARM = (r"coughing (?:a lot|nonstop|and)|chok\w*|can'?t breathe|hard to breathe|trouble breathing|eyes (?:are )?"
              r"(?:burn|"
              r"sting)\w*|dizz\w*|vomit\w*|throwing up|faint\w*|passed out")
# Threats and violence without "kill/hurt me".
_AT_DOOR = (r"\b(?:he|she|they|someone|somebody|my ex|a man|a guy|a stranger|a woman)(?:'s| is| are|'re)? (?:standing |"
            r"waiting |sitting |still |back |banging )?(?:outside|at|by|in front of) my (?:door|window|unit|apartment|"
            r"car)\b\W+(?:\w+\W+){0,8}(?:right now|now|again|won'?t leave|scared|afraid|help)|(?:scared|afraid|terrifi"
            r"ed)"
            r"\W+(?:\w+\W+){0,6}(?:he|she|they|someone)(?:'s| is| are|'re)? (?:standing |waiting |still )?(?:outside|a"
            r"t)"
            r" my (?:door|window)|(?:est[aá]|sigue) (?:afuera|fuera|en la puerta) de mi (?:puerta|casa|apartamento)")
_VIOLENCE = (r"\b(?:he|she|they|my (?:ex|partner|husband|wife|boyfriend|girlfriend|roommate|dad|mom)|someone)\b\W+"
             r"(?:\w+\W+){0,4}(?:grabbed|choked|strangled|shoved|pushed|slapped|punched|hit|kicked|threw \w+ at|pinned|"
             r"dragged) (?:me|my|us|the kids?)\b|(?:i'?ll|i will|gonna|going to|is going to) (?:stab|shoot|kill|cut|"
             r"strangle|choke|beat|hurt|burn|bury|slit|end) (?:you|u|her|him|them|your)\b|me (?:peg[oó]|golpe[oó]|"
             r"amenaz[oó]|ahorc\w*|empuj[oó])|(?:dijo|dice|amenaz[oó]) (?:que )?(?:me )?(?:va a|con) (?:matar|"
             r"hacer daño|matarme)|(?:you'?ll|i'?ll make you|you will) (?:regret|pay for) (?:it|this)")
# Medical events described by signs.
_MED_SIGNS = (r"(?:lying|laying|lies|collapsed) (?:there|on the (?:floor|ground|bathroom floor|kitchen floor)|face ?do"
              r"wn)"
              r"\W+(?:\w+\W+){0,8}(?:not moving|hasn'?t moved|won'?t move|motionless|isn'?t moving|not answering|won'?"
              r"t "
              r"answer)|motionless|hasn'?t moved (?:in|for)|(?:pain|ache|pressure)\W+(?:\w+\W+){0,4}(?:jaw|left arm|ar"
              r"m "
              r"and chest|chest and arm)|(?:sweat\w*|clammy)\W+(?:\w+\W+){0,8}(?:chest|left arm|jaw)|(?:chest|left arm|"
              r"jaw)\W+(?:\w+\W+){0,8}(?:sweat\w*|clammy)|(?:can'?t|cannot|won'?t) (?:talk|speak) (?:right|properly|"
              r"clearly)|words (?:are |came out )?(?:jumbled|wrong|garbled)|no puede hablar bien|habla raro|"
              r"(?:cara|boca) (?:ca[ií]da|torcida)|confundid[oa]\W+(?:\w+\W+){0,6}(?:no puede hablar|habla)")
# Fire described without fire words.
_FIRE3 = (r"(?:pan|pot|grease|oil|stove|stovetop|oven|toaster|microwave|dryer|curtains?|trash|candle|blanket)\W+"
          r"(?:\w+\W+){0,6}(?:caught|flar\w*|went up|is growing|getting bigger|spreading|keeps growing|glowing orange|"
          r"orange glow)|(?:flames?|glow)\W+(?:\w+\W+){0,4}(?:getting bigger|spreading|growing|reaching)|"
          r"(?:it|something) caught\b(?! (?:a cold|up|on|my eye|the bus|the train))")
_TRAPPED3 = (r"(?:kid|child|son|daughter|baby|toddler|grand\w+|dog|mom|dad|someone)\W+(?:\w+\W+){0,6}(?:locked|stuck|"
             r"trapped) (?:in|inside)|(?:can'?t|cannot|won'?t) (?:open|unlock) the (?:door|bathroom|bedroom)\W+"
             r"(?:\w+\W+){0,8}(?:inside|in there|kid|child|baby|son|daughter|water|bath)|(?:elevador|ascensor)\W+"
             r"(?:\w+\W+){0,6}(?:se par[oó]|se detuvo|parado|detenido|atorado|no abre)|(?:i'?m|we'?re|we are|i am|"
             r"people (?:are )?|someone(?:'s| is)?) (?:inside|in) (?:the|it|this|an) (?:elevator|lift)\W+(?:\w+\W+){0,"
             r"8}"
             r"(?:stopped|stuck|won'?t|not moving|between)|(?:elevator|lift)\W+(?:\w+\W+){0,8}(?:between floors|won'?t"
             r" (?:open|move)|doors? (?:won'?t|will not) open)")
_WATER3 = (r"water heater\W+(?:\w+\W+){0,6}(?:burst|split|broke|gave out|exploded|spraying|gushing|dumping|emptying|"
           r"everywhere|popped|flooding)|(?:sewage|raw sewage|toilet water|poop water|aguas negras)\W+(?:\w+\W+){0,6}"
           r"(?:everywhere|spreading|all over|coming up|backing up|into the|over the|on the floor)|(?:water|agua)\W+"
           r"(?:\w+\W+){0,6}(?:coming|pouring|running|dripping|raining|out of|through|from)\W+(?:\w+\W+){0,3}"
           r"(?:lamp|ceiling fan|smoke detector|light|fixture|outlet|socket)")
_STRUCT3 = (r"(?:pedazos|trozos|partes|pieces|chunks) (?:del|de la|of the) (?:techo|pared|ceiling|wall)\W+(?:\w+\W+){0"
            r",4}"
            r"(?:cayendo|caen|falling|fell|coming down)|el techo\W+(?:\w+\W+){0,4}(?:cayendo|cay[oó]|derrumb\w*|se vin"
            r"o "
            r"abajo)")
_CO_SIGNS = (r"soot|yellow (?:flame|burner)|lazy flame|flame (?:is |looks )?(?:yellow|orange|floppy|lazy)|"
             r"(?:everyone|we all|the (?:whole )?family|all of us)\W+(?:\w+\W+){0,4}(?:sick|headaches?|dizzy|nause\w*)")

# ---- sprint 5.1: indirect reports from the resident simulator (own development wording; see tests) ----
# E-2: a young child (or someone) swallowed an unknown thing / a household product; the product named on its own
# with a sign of harm ("the dishwasher pod stuff, he's coughing").
_SMALL_CHILD = (r"toddler|baby|infant|little one|(?:my |the |our )(?:\d+ ?(?:year|yr|month)[- ]old|kid|son|"
                r"daughter|child)")
_UNKNOWN_SWALLOW = (r"(?:swallow\w*|got into|put \w+ in (?:his|her|their) mouth|chew\w* on|lick\w*)\W+(?:\w+\W+){0,4}"
                    r"(?:something|some (?:stuff|liquid|powder)|whatever)|(?:swallow\w*|ate|eaten|drank|got into|"
                    r"chew\w* on|lick\w*)\W+(?:\w+\W+){0,4}(?:(?:from )?(?:under|below) the (?:kitchen |"
                    r"bathroom )?sink|"
                    r"from the (?:cleaning |cleaner )?(?:cabinet|cupboard))")
_HOUSEHOLD = (r"(?:dishwasher|laundry|detergent|tide) ?(?:pods?|tabs?|tablets?|stuff|soap|liquid|packets?)|"
              r"drain cleaner|"
              r"drano|bleach|lye|oven cleaner|toilet (?:bowl )?cleaner|rat poison|antifreeze|button batter\w*|"
              r"from under the sink|under the sink stuff")
_SWALLOW_HARM = (r"cough\w*|chok\w*|gag\w*|vomit\w*|throw\w* up|threw up|puk\w*|drool\w*|foaming|wheez\w*|"
                 r"(?:mouth|throat|lips) (?:is |are )?(?:burn\w*|red|swollen)|crying (?:and|a lot)|won'?t stop crying")
# E-3: a person fell and is calling out / hurt; or a person heard calling for help.
_PERSON_FELL = (r"(?:" + _PERSON + r"|\b(?:she|he|they)\b)\W+(?:\w+\W+){0,3}(?:fell|fallen|took a (?:bad )?fall|"
                r"has had a fall|slipped|tripped|went down)\b")
_FALL_SIGN = (r"calling (?:out|for help|help)|cr(?:y|ies|ying) (?:out|for help)|(?:yell|scream|shout|call)\w* (?:out )?"
              r"(?:for )?help|moan\w*|groan\w*|hurt|in pain|bleed\w*|on the floor|on the ground|can'?t (?:get up|"
              r"stand|move|reach)|hasn'?t (?:gotten|got) up|won'?t get up|not getting up|help me")
_CALLING_HELP = (r"(?:\b(?:she|he|they|someone|somebody|a (?:woman|man|person|lady|guy|kid|child))(?:'s| is| are|'re)?|"
                 + _NAMED_PERSON + r")\W+(?:\w+\W+){0,3}(?:calling|crying|yelling|screaming|shouting|"
                 r"begging)\W+(?:out\W+)?"
                 r"(?:for )?help\b(?! (?:desk|line|center|centre|button|page|article|ticket))")
# E-6: someone testing doors at night.
_DOOR_TRY = (r"(?:trying|tried|testing|jiggl\w*|rattl\w*|twist\w*|pull\w* on|turning|checking)\W+(?:\w+\W+){0,1}"
             r"(?:(?:the|our|every|each|all the|people'?s|neighbou?rs'?|residents'?)\s+)?"
             r"(?:door ?handles|door ?knobs|doorknobs|handles|doors|locks)\b|(?:trying|tried|testing|jiggl\w*|rattl\w*)"
             r"\W+(?:every|each|all the) (?:door|handle|lock|unit)")


def _near(a: str, b: str, gap: int = 12) -> re.Pattern[str]:
    """a then b, or b then a, within `gap` words."""
    w = rf"\W+(?:\w+\W+){{0,{gap}}}"
    return re.compile(rf"(?:{a}){w}(?:{b})|(?:{b}){w}(?:{a})", re.I)


CONCEPTS: list[tuple[str, re.Pattern[str]]] = [
    ("self_harm", re.compile(_SELF_HARM2, re.I)),
    ("self_harm", _near(_BURDEN, _FINAL, 20)),
    ("self_harm", re.compile(_HEIGHT_ALONE + "|" + _METHOD + "|" + _INTENT, re.I)),
    ("self_harm", OD_INTENT),
    ("self_harm", _near(_GONE, _GONE_PLAN, 20)),
    ("poison", re.compile(_OD_SIGNS, re.I)),
    ("poison", _near(_CHEM, _CHEM_HARM, 10)),
    ("personal_safety", re.compile(_VIOLENCE + "|" + _AT_DOOR, re.I)),
    ("medical", re.compile(_MED_SIGNS, re.I)),
    ("trapped", re.compile(_TRAPPED3, re.I)),
    ("flood", re.compile(_WATER3, re.I)),
    ("structural", re.compile(_STRUCT3, re.I)),
    ("co", _near(_CO_SIGNS, _SYMPTOM + "|" + _HEAT + "|furnace|boiler|vomit\\w*|throwing up", 14)),
    ("fire_smoke", re.compile(_FIRE3, re.I)),
    ("poison", _near(_INGEST, _SUBSTANCE, 8)),
    ("poison", _near(_SMALL_CHILD, _UNKNOWN_SWALLOW, 6)),
    ("poison", _near(_HOUSEHOLD, _SWALLOW_HARM, 10)),
    ("medical", _near(_PERSON_FELL, _FALL_SIGN, 10)),
    ("medical", re.compile(_CALLING_HELP, re.I)),
    ("personal_safety", _near(_THREAT_ACTOR, _DOOR_TRY, 8)),
    ("poison", re.compile(_FUMES, re.I)),
    ("trapped", re.compile(_TRAPPED2, re.I)),
    ("medical", _near(_PERSON, _UNRESPONSIVE, 10)),
    ("medical", _near(_NAMED_PERSON, _WEAK_UNRESP, 8)),
    ("medical", re.compile(_UNRESPONSIVE + "|" + _CARDIAC + "|" + _BLEED, re.I)),
    ("personal_safety", _near(_THREAT_ACTOR, _THREAT_ACT, 10)),
    ("personal_safety", re.compile(r"\b(?:he|she|they)(?:'ll| will| is going to| are going to|'s going to|'re going to"
                                   r"| said he'd| said she'd) (?:get|hurt|kill|shoot|stab|beat) me\b", re.I)),
    ("co", _near(_SYMPTOM, _HEAT, 14)),
    ("co", re.compile(r"(?:co |carbon |little |the )?detector\W+(?:\w+\W+){0,8}(?:beep\w* (?:4|four) times|flash\w* "
                      r"red|red light)", re.I)),
    ("structural", re.compile(_STRUCT2, re.I)),
    ("fire_smoke", re.compile(_FIRE2, re.I)),
    ("electrical", re.compile(_ELEC2, re.I)),
    ("flood", re.compile(_FLOOD2, re.I)),
    ("gas", re.compile(_GAS2, re.I)),
]
# Sprint 6: concept-slot rules (app/risk/concepts.py) run after every explicit rule above, through the same framing.
CONCEPTS.extend(CONCEPT_RULES)

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
# Sprint 7 fix round (UX judge): benign senses of danger words: an interjection ("oh shoot"), a consumable that
# burned out (a bulb, the oven light), being burnt out (tired). A live sign elsewhere in the message still counts.
_DANGER_NOT = re.compile(r"\b(?:oh|aw|ah|ahh|dang|well) shoot\b|^\W*shoot\b(?!\s+(?:me|him|her|them|us|at|someone))|"
                         r"\bshoot[,!.]|\b(?:bulbs?|light ?bulbs?|lights?|lamps?|nightlight|oven light|fridge light|"
                         r"fuses?|candles?)\W+(?:\w+\W+){0,4}burn(?:ed|t) out\b|\bburn(?:ed|t) out (?:bulbs?|lights?)"
                         r"\b|"
                         r"\b(?:i'?m|feel|feeling|so) (?:so |really |totally )?burn(?:ed|t) out\b|sparks? joy|gas (bil"
                         r"l|station|company|stove (is|works) fine)|fire (lane|exit|drill|alarm "
                         r"test|extinguisher)|chest of drawers|burning question|smoke[- ]free|no smoking|"
                         r"bone dry|broke (?:the )?bank|smoke (?:detector|alarm)s? (?:repair|battery|batteries|replace"
                         r"ment|replaced|"
                         r"install\w*|check|test|inspection|cover)|(?:repair|replace|fix|install|send)\w* (?:the |my |"
                         r"a )?"
                         r"smoke (?:detector|alarm)|(?:scared|afraid|terrified) of (?:spiders?|bugs?|heights|the d"
                         r"ark|mice|roaches|"
                         r"dogs?|clowns|needles|snakes|flying|public speaking)|burn(?:t|ed) (?:toast|food|popcorn|rice"
                         r"|dinner)|shoot(?:ing)? "
                         r"(?:me |you |us |them )?(?:an? |the |over )?"
                         r"(?:email|text|message|note|line|star|photos?|pics?|video|quick)|shooting stars?|photo ?shoo"
                         r"ts?|"
                         r"flood (?:zone|insurance|plain|map|risk)|gas (?:service|account|utility|included|hook ?up|se"
                         r"t ?up|"
                         r"turned on|in my name|provider|meter reading)|set(?:ting)? up (?:the |my )?gas|(?:no ?one|no"
                         r"body|"
                         r"no one) (?:is |was |got |has been )?(?:hurt|injured)|(?:incluye|incluido|incluida)\W+(?:\w+"
                         r"\W+)"
                         r"{0,3}gas|gas\W+(?:\w+\W+){0,3}(?:incluido|incluida)|(?:smoke|co|carbon monoxide) (?:alarm|"
                         r"detector)s?\W+(?:\w+\W+){0,6}(?:chirp\w*|low batter\w*|batter(?:y|ies))", re.I)
_SELF_HARM_HINT = re.compile(r"\brope\b|goodbye (?:to(?! (?:this|the|my|our) (?:apartment|place|unit|building|lease|"
                             r"neighbou?rhood|city|town|area|old \w+)\b)|letter|note)|giving away (?:my|all)|"
                             r"sleep forever|no way out|"
                             r"(?:rather|want to|wanna) (?:just )?(?:not exist|disappear|be dead|not wake up)|"
                             r"(?:no|any) reason to (?:keep going|go on|live|stay)|how (?:i would|to) do it|"
                             r"\bcutting (?:again|myself)|hurting myself|self[- ]harm|(?:won'?t|wont) be (?:alive|here|"
                             r"around)|not (?:be )?alive|end it all|kill myself|overdos\w*|"
                             r"sentido (?:a la|de la) vida|desaparecer para siempre|no quiero existir|hacerme da[ñn]o|"
                             r"won'?t need (?:it|them|anything) (?:soon|anymore)|despedí de todos|esta noche lo hago|"
                             r"not (?:be )?(?:around|here) (?:much longer|anymore)|suicid\w*|want(?:ed)? to die|"
                             r"wanna die|better off (?:dead|without me)|burden|" + _PASSIVE_SI + "|" + _BURDEN + "|"
                             + _GONE, re.I)

# Third tier: not enough to call it an emergency, too much to say nothing. The reply keeps going but leads with a
# calm safety line (no urgent note, no alarm). "distress" adds 988; "unwell" adds 911-if-worse.
_DISTRESS = re.compile(
    r"what'?s the point(?: of (?:anything|living|trying|it all|going on|me|life)| anymore|\W*$)|no point (?:in living|"
    r"anymore|in anything)|(?:can'?t|cant) (?:do this|go on|take (?:it|this))(?: like this)? anymore|"
    r"(?:can'?t|cant) go on like this|give up on (?:everything|life)|(?:feel|feeling|i'?m|im) (?:so |really )?hopeless|"
    r"(?:i'?m|im) (?:so )?done with (?:everything|life)|(?:won'?t|wont) (?:be around|matter)|"
    r"everything is falling apart|nothing matters|it doesn'?t matter anyway|tired of (?:living|everything|life)|"
    r"ya no puedo m[aá]s|no aguanto m[aá]s|feels? (?:so |really |completely )?hopeless|so stressed (?:that )?i "
    r"can'?t (?:sleep|eat|breathe)|panic attacks?|" + _OVERWHELM, re.I)
_UNWELL = re.compile(_SYMPTOM.replace(r"confus\w*|", "").replace(r"feel (?:sick(?! of| and tired)|weird|off)|", "")
                     + r"|can'?t breathe well|short of breath", re.I)
_NEGATED_SELF_HARM = re.compile(
    r"(?:not|never been|i'?m not|im not) (?:really )?suicidal|not (?:going|gonna|trying) to (?:hurt|kill) myself|"
    r"(?:no|nunca) (?:me voy a|quiero) (?:matar|hacer daño)|no (?:estoy|soy) suicida", re.I)
# Possibly someone in danger, but not enough for the full alert: the 911 line, never silence.
_DANGER_HINT = re.compile(
    # fix round (P2): a loose / wobbly railing alone is a repair with the calm 911 line, not a full alert
    r"\b(?:railing|handrail|guard ?rail)s?\W+(?:\w+\W+){0,4}(?:loose|wobbl\w*|shak\w*|moves)\b|"
    r"(?:crash|scream\w*|thud|bang\w*|yell\w*)\W+(?:\w+\W+){0,10}(?:then )?(?:silence|quiet|nothing|stopped)|"
    r"(?:has|have|kept|still has) (?:a |the )?key\w*\W+(?:\w+\W+){0,12}(?:coming in|came in|let (?:him|her|them)sel\w* "
    r"in|moved|in my (?:apartment|unit|place)|when i'?m (?:not home|out|away|asleep))|(?:things|stuff) (?:keep )?"
    r"(?:moved|moving|missing) (?:around )?in my (?:apartment|unit|place)|"
    # sprint 5.1 (E-6): a neighbour who may need a welfare check (door left open / not seen, plus a bad smell)
    r"(?:(?<!\bmy )(?<!\bour )door (?:has been|was|is|been|left|standing) (?:\w+ )?open|haven'?t (?:seen|"
    r"heard from) (?:him|her|them|my "
    r"neighbou?r|the (?:\w+ )?neighbou?r)|mail (?:is )?piling up|packages piling up|(?:hasn'?t|not) (?:answered|"
    r"answering) (?:the|her|his|their) door)\W+(?:\w+\W+){0,12}(?:(?:smell\w*|stench|odou?r|stink\w*)\W+(?:\w+\W+){0,3}"
    r"(?:awful|terrible|horrible|really bad|so bad|rotten|rotting|decay\w*|like something died|foul|nasty)|(?:awful|"
    r"terrible|horrible|rotten|rotting|foul|nasty|really bad|dead) (?:smell|stench|odou?r|stink))", re.I)


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
# Hazard mentioned as a question/hypothetical or a past event: the same approved steps, calmly, without the alarm.
INFO_LEAD = {"en": "If that happens: ", "es": "Si eso pasa: "}
# Added to any alert where the person may have harmed themselves on purpose (e.g. deliberate overdose).
ALSO_988 = {"en": " If this was on purpose or you're thinking about hurting yourself, you can also call or text 988.",
            "es": " Si fue a propósito o está pensando en hacerse daño, también puede llamar o enviar un mensaje "
                  "al 988."}
REFUSE_LEAD = {
    "en": "I understand. I can't send anyone from here, and nobody has been sent. Staying could be dangerous, so "
          "please follow these steps now: ",
    "es": "Entiendo. Desde aquí no puedo enviar a nadie y no se ha enviado a nadie. Quedarse podría ser peligroso, "
          "así que por favor siga estos pasos ahora: ",
}


def person_concern(message: str) -> bool:
    """Sprint 6: the care line came from a sign that a PERSON may be hurt or in danger (concept slots or the welfare /
    break-in hints), not just from broad hazard vocabulary. Such a line is never removed by the semantic layer (R7)."""
    text = _clean(_prepare(message))
    return bool(_concern(text) or _DANGER_HINT.search(text))


def possible_risk(message: str) -> str | None:
    """'distress' / 'danger' / 'unwell' / None for messages that are not a clear emergency."""
    raw = _prepare(message)
    # Someone who brings up self-harm only to deny it ("I'm not suicidal, but...") still gets the calm 988 line.
    if _NEGATED_SELF_HARM.search(raw) or (_LAUGH.search(raw) and _kind_of(raw) == "self_harm"):
        return "distress"
    text = _clean(raw)
    if _DISTRESS.search(text) or _SELF_HARM_HINT.search(text) or _stockpile(text) or _veiled_farewell(text):
        return "distress"
    if _DANGER.search(_DANGER_NOT.sub(" ", text)) or _DANGER_HINT.search(text) or _concern(text):
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
    r"fire lane|fire exit|fire door|fire escape|fire station|inspecci[oó]n de (?:los )?detectores(?: de humo)?|"
    r"detectores? de humo|(?:test|check|inspect)\w*\W+(?:\w+\W+){0,2}(?:co|carbon monoxide|"
    r"smoke|fire) (?:detectors?|alarms?)|sparks? joy|(?:can|should) i (?:mix|use)\W+(?:\w+\W+){0,4}(?:bleach|"
    r"ammonia|vinegar)|"
    r"knife (block|set|drawer)|stroke of (luck|genius)|burning (to|question)|burn(s|ing)? (food|the food|toast|rice|"
    r"dinner)|well[- ]lit|just kidding|jk\b|fire (pit|place|sale|drill)|smoking hot|"
    r"smoke machine|fog machine|haze machine|"
    # sprint 6: asking for a detector (new, extra, replacement) is a maintenance request, not an alarm sounding
    r"(?:get|install\w*|replac\w*|buy|add|put in|new|another|extra|spare|expired|old)\W+(?:\w+\W+){0,3}(?:co|"
    r"carbon monoxide|smoke|fire) (?:detectors?|alarms?)(?!\W+(?:\w+\W+){0,4}(?:going off|beep\w*|sounding|"
    r"won'?t stop|went off))|(?:co|carbon monoxide|smoke) (?:detectors?|alarms?) (?:installed|replaced|put in)",
    re.I)
# sprint 6: a past break-in of a car / storage / mailbox is property crime, not a person in danger now. Fix round: the
# exemption never applies when the same message describes someone present now ("...and the guy is still in our
# garage"); see _kind_of.
_PAST_PROPERTY_CRIME = re.compile(
    r"(?:car|truck|vehicle|bike|storage(?: unit)?|mailbox|locker|garage)\W+(?:\w+\W+){0,2}(?:got |was |been |were )?"
    r"(?:broken into|broke into|stolen)\W+(?:\w+\W+){0,4}(?:last|ago|yesterday|over the weekend|the other)\w*", re.I)
# Everyday idioms that use hazard words ("this rent is killing me", "the view is fire", "dying to see it").
_FIGURATIVE = re.compile(
    r"\b(?:rent|prices?|fees?|bills?|commute|noise|traffic|stairs|heat|humidity|wait(?:ing)?|process|paperwork|"
    r"(?:my|this|these|that|the) (?:\w+ )?(?:back|feet|job|boss|work|wait|place|price|process|form|stairs|fees|neighbo"
    r"u?r|"
    r"music|dog|kids?|commute|class(?:es)?)|work|deadlines?|you guys|y'?all|it|this|that)\s+(?:is|are|'s|was|will|would"
    r"|gonna|going to|literally|honestly|seriously|\s)*\s*(?:kill(?:ing)?|murder(?:ing)?) me\b|"
    r"dying (?:to|for)\b|to die for|dead (?:tired|serious|set|on|end)|killer (?:view|deal|price|location|amenities|"
    r"kitchen|pool)|killing it|kill for (?:a|an|this|that)|"
    r"(?:is|are|looks?|sounds?|was|so|straight|lowkey|actually|kinda|honestly) fire\b(?! (?:in|on|at|from|coming|"
    r"alarm|is|was))|\bfire ?(?:tv|stick|tablet|hd|emoji|engine red|red|orange)\b|kindle fire|this place is fire|"
    r"\b(?:ceasefire|cease fire)\b|blow(?:ing)? up my phone|blew up my phone|out of gas|gas (?:money|prices|mileage)|"
    r"smoke break|drowning in (?:work|bills|paperwork|debt|emails)|bomb (?:deal|view|place|apartment)|"
    r"break(?:ing)? the bank|(?:i'?m|im) (?:so )?dead\b(?! (?:serious))(?=.{0,20}(?:lol|lmao|haha|😂|🤣|💀))|"
    r"(?:heart|this) attack of (?:cuteness|nostalgia)|"
    # sprint 6: "the bill almost gave me a heart attack"
    r"(?:almost |nearly |about to |going to |gonna )?(?:gave|give|giving|gives) me (?:a )?(?:heart attack|stroke)\b",
    re.I)
# Sprint 7: "this paperwork is going to give me a stroke" / "i'm about to have a heart attack" is hyperbole, but only
# when NO body symptom is described (fix round P0: "I think I might have a stroke, my face is numb on one side").
_MODAL_HYPERBOLE = re.compile(r"\b(?:about to|going to|gonna|could|might|will|i'?ll) have (?:a |an )?(?:stroke|heart "
                              r"attack|aneurysm|breakdown|meltdown)\b", re.I)
_BODY_SYMPTOM = re.compile(r"\b(?:numb\w*|tingl\w*|droop\w*|slurr\w*|face|arm|chest|jaw|vision|blurr\w*|dizz\w*|"
                           r"head ?ache|headache|pain|hurts?|weak\w*|can'?t (?:feel|move|speak|talk|see|breathe|lift)|"
                           r"sweat\w*|short of breath|faint\w*|confus\w*|vomit\w*|nause\w*|pressure|tight\w*|"
                           r"entumid\w*|dolor|mare\w*|pecho|brazo|cara)\b", re.I)
# Negated hazards ("no smoke", "it's not sparking", "I don't smell gas"); only the negated phrase is removed.
_NEGATED = re.compile(
    r"\bnothing (?:is |was |'s )?(?:sparking|smoking|burning|on fire|leaking gas)\b|"
    # fix round: the hazard sign has stopped ("the smell is gone", "the hissing stopped"); a negation never clears
    # an active incident by itself (app/risk/incident.py decides that)
    r"\b(?:the )?(?:gas )?(?:smell|odou?r|stench|hissing|sparking)(?:'s| is| has| has been)? (?:completely |finally |"
    r"all )?(?:gone|stopped|cleared|went away|gone away|faded)\b|"
    r"\bnot (?:a |any )?(?:flood\w*|fire|on fire|smok\w+|sparking|sparks|gas(?: leak| smell)?|an emergency|emergency|"
    r"burning)\b|"
    r"\bnever (?:reported|said|mentioned|told you|claimed)\W+(?:\w+\W+){0,3}(?:gas|fire|smoke|leak|emergency)\w*|"
    # Sprint 10 (simulator safety miss): in "oh no smoke coming from the outlet", "oh no" is an exclamation
    r"(?<!\boh )(?<!\bohh )(?<!\boh, )"
    r"\b(?:no|not any|without(?: any)?|zero|never (?:saw|smelled|had))\s+(?:\w+\s+)?(?:signs? of\s+)?(?:smoke|fire|"
    r"flames?|sparks?|sparking|gas(?: smell| leak)?|smell of gas|burning(?: smell)?|water on the floor|flooding|blood|"
    r"injur\w+|beeping)\b|"
    r"\bnot (?:the|my|our) (?:smoke|fire|co)(?: (?:one|alarm|detector))?\b(?! (?:is|was|coming|everywhere|"
    r"pouring|filling))|"
    r"\b(?:there'?s|there is|it'?s|it is|i'?m|i am|that'?s|that is|its|im)\s+not\s+(?:a |any |really )?(?:smoke|fire|"
    r"on fire|gas(?: leak)?|an emergency|emergency|flooding|sparking|shocked|smoking|beeping|suicidal|leaking gas)\b|"
    r"\b(?:i |we )?(?:don'?t|do not|didn'?t|did not)\s+(?:smell|see|hear|notice)\s+(?:any |anything like )?(?:gas|smoke"
    r"|fire|sparks?|burning)\b|"
    r"\b(?:isn'?t|is not|aren'?t|are not|wasn'?t|was not)\s+(?:\w+\s+)?(?:beeping|sparking|smoking|on fire|leaking"
    r" gas|going off)\b|"
    r"\bno (?:hay|había|veo|huele a|huele|se huele|siento olor a)\s+(?:\w+\s+)?(?:humo|fuego|olor a gas|gas|chispas)\b"
    r"|\bsin (?:humo|fuego|chispas)"
    r"\b",
    re.I)
# Framing: a hazard named only in a question/hypothetical, a school project, or a clearly past event.
_HYPO = re.compile(
    r"\b(?:what (?:should|do|would|can) (?:i|we|you|someone|people) do (?:if|in case)|what if\b|in case (?:of|there"
    r"(?:'?s| is| was))|if (?:i|we|you|someone|there|a|the|my)\b(?:\s+\w+){0,2}\s+(?:ever|were to|happen\w* to)\b|if "
    r"there (?:is|was|were|'?s) ever|if (?:i|we) ever|hypothetically|for future reference|how (?:do|would|can|will) "
    r"(?:i|you|we) (?:know|tell) if|is it (?:dangerous|safe|normal|bad) (?:if|when|to)|should i (?:worry|be worried)"
    r" if|what happens (?:if|when)|what(?:'?s| is) the (?:procedure|protocol|plan|policy) (?:for|if|in case)|"
    r"(?:project|homework|essay|report|presentation|class|research|paper) (?:about|on)|for (?:a|my) (?:class|school|"
    r"project)|(?:the |my )?lease (?:says|states)|qu[eé] (?:hago|debo hacer|hacer|pasa) si|en caso de|"
    # sprint 6: asking how to recognise a hazard is a safety question, not a report
    r"what are (?:the )?(?:signs|symptoms|warning signs) of|how (?:do|can|would) (?:i|you|we) (?:recogni[sz]e|spot"
    r"|detect)|cu[aá]les son (?:los )?s[ií]ntomas de)", re.I)
_PAST = re.compile(r"\b(?:last (?:year|month|summer|winter|spring|fall|time)|years? ago|months? ago|a while (?:ago|bac"
                   r"k)|"
                   r"back in (?:19|20)\d\d|in (?:19|20)\d\d|(?:the|that) (?:fire|flood|leak) (?:we|there) (?:had|was)|"
                   r"used to|el a[ñn]o pasado|hace (?:a[ñn]os|meses))\b", re.I)
_NOW = re.compile(r"\b(?:now|right now|still|currently|tonight|today|this (?:morning|evening|afternoon)|at the moment|"
                  r"just now|is happening|happening again|(?:smells?|leaking|sparking|smoking|burning) again|keeps?|"
                  r"ahora|todav[ií]a|otra vez|ya mismo)\b", re.I)
_LAUGH = re.compile(r"\b(?:lol|lmao|lmfao|haha\w*|jk|jaja\w*)\b|😂|🤣|💀|😭", re.I)
# Never downgraded by framing: a hypothetical or past mention of these can still be a disclosure.
_NEVER_DOWNGRADE = {"self_harm", "personal_safety"}
_BENIGN_CHIRP = re.compile(r"(smoke|co|carbon monoxide) (alarm|detector).{0,40}(chirp|beep|batter)\w*.{0,40}"
                           r"(batter|chirp)|batter\w*.{0,40}(smoke|co|carbon monoxide) (alarm|detector)|"
                           # sprint 5.1 (E-9): a fire alarm's low-battery chirp is maintenance, not a fire
                           r"fire (alarm|detector)s?\W+(?:\w+\W+){0,6}(?:low[- ]?batter\w*|chirp\w*|"
                           r"needs? (?:a )?(?:new )?"
                           r"batter\w*)|(?:low[- ]?batter\w*|chirp\w*)\W+(?:\w+\W+){0,6}fire (alarm|detector)", re.I)
# Hazard words that still mean a real fire / CO even when the message also mentions a chirp or battery.
_CHIRP_BUT_DANGER = re.compile(r"smoke (is|coming)|\bsmok\w*\b(?! ?(?:alarm|detector|one))|hazy|"
                               r"\bfire\b(?! ?(?:alarm|detector))|flame|head|dizz|nause|going off|"
                               r"won'?t stop (?:beeping|sounding|going)|burn|smell", re.I)


_CONTRACTIONS = [(re.compile(rf"\b{a}\b", re.I), b) for a, b in (
    (r"i am", "i'm"), (r"im", "i'm"), (r"ive", "i've"), (r"do not", "don't"), (r"dont", "don't"),
    (r"will not", "won't"), (r"wont", "won't"), (r"can not", "can't"), (r"cannot", "can't"), (r"cant", "can't"),
    (r"was not", "wasn't"), (r"is not", "isn't"), (r"isnt", "isn't"), (r"were not", "weren't"),
    (r"would not", "wouldn't"), (r"did not", "didn't"), (r"didnt", "didn't"), (r"i will", "i'll"),
    (r"it is", "it's"), (r"there is", "there's"), (r"that is", "that's"))]


def _prepare(message: str) -> str:
    text = unicodedata.normalize("NFKC", message)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.replace("’", "'").replace("‘", "'")
    # "s m e l l gas", "f.i.r.e" -> "smell gas", "fire"
    text = _SPACED.sub(lambda m: re.sub(r"[ .*_\-]", "", m.group(0)), text)
    for pat, rep_ in _CONTRACTIONS:
        text = pat.sub(rep_, text)
    return text


def _strip_figurative(text: str) -> str:
    text = _FIGURATIVE.sub(" ", text)
    if not _BODY_SYMPTOM.search(text):
        text = _MODAL_HYPERBOLE.sub(" ", text)
    return text


def _strip_negated(text: str) -> str:
    return _NEGATED.sub(" ", text)


# Sprint 7: body heat is not a fire ("burning up", "his skin is burning hot", "ardiendo en fiebre").
# Fix round (P0): scoped to fever / temperature wording. "On fire" and "caught" are never removed ("he is on fire",
# "her sleeve caught on the stove" are fires).
_BODY_HEAT = re.compile(r"\bburning hot\b|\b(?:confused|hot|sick|sweaty|feverish|red|flushed|dizzy|clammy|weak)\s+"
                        r"(?:and\s+)?burning up\b|\b(?:he|she|they|baby|kid|child|son|daughter|toddler|grandma|grandpa"
                        r"|mom|dad|i)(?:'s| is| are|"
                        r"'re|'m| am)? (?:really |so |just )?burning up\b(?! (?:in|inside))|\bburning up with (?:a )?f"
                        r"ever\b|"
                        r"\b(?:skin|forehead|body)\W+(?:\w+\W+){0,2}(?:is |feels |felt )(?:so |really |very )?burning("
                        r"?: hot)?"
                        r"\b(?! (?:smell|down|in))|\bburning (?:with )?fever\b|\bardiendo (?:en|de) fiebre\b|"
                        r"\bfever\W+(?:\w+\W+){0,3}burning\b", re.I)
# Sprint 7 (lead class 1): smoke from OTHER people's habits (a neighbour smoking cigarettes or weed, smoke drifting in
# from the hallway) is a nuisance for the office, not a fire. Removed only when nothing in the message describes a
# fire: flames, "fire", black / thick smoke pouring or filling, an alarm going off, a burning smell, sparks.
_HABIT_SMOKE = re.compile(
    r"\b(?:cigarettes?|cigs?|cigars?|weed|pot\b|marijuana|cannabis|joints?|blunts?|vap(?:e|es|ing)|hookah|tobacco|"
    r"second[- ]?hand smoke|cigarrillos?|cigarros?|mota|marihuana|tabaco|porro)\b|"
    r"\b(?:neighbou?rs?|someone|somebody|people|they|guy|guys|tenants?|roommates?|upstairs|downstairs|next door|"
    r"vecin\w*|alguien|la gente)\b\W+(?:(?!unit|apartment|door|vent|kitchen|building|house|place|oven|dryer|stove|"
    r"room|hallway|wall|outlet|panel|car|attic|roof)\w+\W+){0,3}(?:smok(?:e|es|ing)|chain ?smok\w*|light(?:s|ing)? up|"
    r"fuma\w*)\b", re.I)
_REAL_FIRE_SIGN = re.compile(r"\b(?:fill(?:ed|ing|s)? (?:up )?with|full of|thick with|lleno de|llena de)"
                             r"\W+(?:\w+\W+){0,1}"
                             r"(?:smoke|humo)\b|\b(?:smoke|humo)\W+(?:\w+\W+){0,3}(?:pour\w*|billow\w*|fill\w*|"
                             r"everywhere|coming (?:out|from|under|in)|out of|getting (?:thick|worse|bigger)|thick|bla"
                             r"ck|negro|sale|"
                             r"saliendo|por todas partes)|\borange (?:light|glow)\b|"
                             r"\b(?:sale|saliendo|hay)\W+(?:\w+\W+){0,1}(?:humo|smoke)\b|\bsmoke\W+(?:\w+\W+){0,6}gett"
                             r"ing (?:thick|worse)|\b(?:the|my|our|his|her|a) (?!neighbou?r|"
                             r"guy|man|woman|roommate|tenant)\w+ (?:is|are|'s) (?:now )?smoking\b|\bsmoking now\b|"
                             r"\b(?:fell|falls|fallen) asleep (?:while )?smoking\b|\bcaught\b|"
                             r"\bfire\b(?! (?:alarm|exit|door|lane|code|hazard|department|dept))|\bflames?\b|"
                             r"\bon fire\b|\b(?:black|thick|heavy|gr[ae]y) smoke\b|smoke (?:is )?(?:pouring|billowing|"
                             r"filling|everywhere|coming out of (?:the|my|our) (?:vent|outlet|wall|ceiling|oven|dryer)"
                             r")|"
                             r"(?:alarm|detector)s? (?:is |are )?(?:going off|sounding|went off)|burn(?:ing|t) "
                             r"(?:smell|plastic|rubber)|smells? (?:like |of )?burn|\bsparks?\b|\bllamas?\b|\bfuego\b|"
                             r"\bincendio\b|can'?t (?:breathe|see)", re.I)
_SMOKE_WORD = re.compile(r"\b(?:smok(?:e|ing|y|es)|humo|fumes?)\b", re.I)


_ATTRIBUTED_SMOKE = re.compile(r"\b(?:cigarette|cig|cigar|weed|pot|marijuana|vape|vaping|tobacco|hookah|"
                               r"second[- ]?hand|"
                               r"their|his|her)\s+(?:smoke|smoking)\b|\bhumo (?:de|del) (?:cigarr\w*|tabaco|marihuana|"
                               r"vecino)\b", re.I)


def _strip_habit_smoke(text: str) -> str:
    """Only when no present smoke / fire sign remains once the smoke attributed to the habit ("cigarette smoke
    coming under my door") is set aside: "my neighbor smokes and now the hallway is full of smoke" stays a fire."""
    if _HABIT_SMOKE.search(text) and not _REAL_FIRE_SIGN.search(_ATTRIBUTED_SMOKE.sub(" ", text)):
        return _SMOKE_WORD.sub(" ", text)
    return text


def clean_for_frame(message: str) -> str:
    """The message with negated, figurative, not-physical, body-heat and other people's smoking phrases removed, for
    the compositional frame (app/risk/frame.py), so both layers read the same meaning."""
    return _clean(_prepare(message))


# Fix round (P0 false alarm): "balcony door", "deck light", "porch gate" name hardware, not the structure: a door that
# won't latch is a repair. The compound becomes the hardware noun alone before any rule runs.
_HARDWARE_COMPOUND = re.compile(r"\b(?:balcony|patio|deck|porch|closet|stair(?:well|case)?|roof|ceiling|wall|floor|"
                                r"balc[oó]n|techo|pared)\s+(door|doors|window|windows|light|lights|lamp|fan|gate|"
                                r"screen|lock|slider|latch|handle|knob|hinge|vent|outlet|tile|tiles|puerta|ventana|"
                                r"luz|l[aá]mpara|ventilador|cerradura)\b", re.I)


# Final round (P0 false alarm): a body-state verb with an OBJECT subject is a broken object, not a person ("the closet
# shelf collapsed", "the cabinet handle fell off"). Kept when it fell / collapsed ON someone; ceilings, roofs, floors,
# balconies are not in the list and stay structural.
_OBJECT_FELL = re.compile(
    r"\b((?:shelf|shelves|shelving|rack|cabinet|cupboard|closet door|(?<!next )door|handle|knob|curtain rod|rod|"
    r"blinds?|tv|mirro"
    r"r|"
    r"picture|frame|towel (?:bar|rack)|hook|light fixture|fixture|ceiling fan|table|chair|bed ?frame|bunk|couch|tent|"
    r"boxes|box|pile|stack|organizer|bracket|drawer|lid|cover|vent cover|grab bar|toilet seat|repisa|estante|"
    r"gabinete|puerta|manija|cortinero|espejo|cuadro|mueble|silla|mesa|cajón|cajon))\s+(?:just |completely |totally |"
    r"kind of |sort of )?(?:collapsed|fell (?:off|down|apart)|came off|broke off|se (?:cay[oó]|cayeron|desplom[oó]|"
    r"rompi[oó]))\b(?!\s+(?:on|onto|over|on top of|encima|sobre)\b)", re.I)


# Spanish word order: the verb first ("se cayó la repisa", "se desprendió la manija") or the object with a "del ..."
# complement ("la puerta del closet se cayó"). Kept when it fell ON someone ("se le cayó la repisa encima a mi hijo").
_OBJ_ES = (r"repisas?|estantes?|gabinetes?|puertas?|manijas?|perillas?|cortineros?|toalleros?|espejos?|cuadros?|"
           r"muebles?|sillas?|mesas?|caj[oó]n|cajones|persianas?|cortinas?|ganchos?|tapas?|rejillas?|lamparas?|l[aá]mparas?|"
           r"ventiladores?|bisagras?|jaladeras?|barras?|tablas?|literas?")
_OBJECT_FELL_ES = re.compile(
    rf"\bse (?:cay[oó]|cayeron|desprendi[oó]|desprendieron|despeg[oó]|rompi[oó]|zaf[oó]|solt[oó]|vino abajo)"
    rf"\s+(?:el|la|"
    rf"los|las|un|una|mi|mis)\s+((?:{_OBJ_ES}))\b(?![^.?!]{{0,40}}\b(?:encima|sobre|a mi|al ni[nñ]o|a la ni[nñ]a|a mi "
    rf"\w+))|\b((?:{_OBJ_ES}))(?:\s+(?:del?|de la)\s+\w+)?\s+se (?:cay[oó]|cayeron|desprendi[oó]|despeg[oó]|"
    rf"rompi[oó]|zaf[oó]|solt[oó])\b(?![^.?!]{{0,40}}\b(?:encima|sobre|a mi))", re.I)


# Final round (structural): "collapsed / fell off / came off / gave out" is a PERSON body state only when its noun
# subject is a person; a building part (ceiling, roof, floor, balcony, stairs, wall...) stays structural; any other
# noun subject is a broken object ("my bookcase collapsed", "the bracket in my den collapsed") = a repair. "On / onto
# <someone>" is never rewritten.
_NOUN_SUBJECT_VERB = re.compile(
    r"\b(?:the|my|a|an|our|this|that|his|her|their|one of (?:the|my|our))\s+((?:[\w'-]+\s+){0,5}?)([\w'-]+)\s+"
    r"(?:just |completely |totally |suddenly |kind of |sort of )?(collapsed|fell off|fell apart|came off|came apart|"
    r"gave out|gave way)\b(?!\s+(?:on|onto|over|on top of)\b)", re.I)
_PERSONISH = re.compile(_PERSON + r"|\b(?:i|me|we|us)\b|\b(?:grand\w+|mom|mum|dad|wife|husband|son|daughter|kid|baby|"
                        r"child|toddler|friend|roommate|neighbou?r|tenant|man|woman|guy|lady|boy|girl|brother|sister|"
                        r"uncle|aunt|cousin|partner|boyfriend|girlfriend|someone|somebody|person|dog|cat|"
                        # sprint 8: more people nouns ("my coworker collapsed" is a person, not a broken object)
                        r"co-?workers?|colleagues?|boss|nephew|niece|patient|classmate|teammate|elderly|senior|"
                        r"visitor|guest|stranger|caregiver|nurse|teacher|student|fianc[eé]e?|husband)'?s?\b", re.I)
_BUILDING_PART = re.compile(r"\b(?:ceilings?|roofs?|floors?|balcon(?:y|ies)|stairs|staircase|stairway|steps|"
                            r"walls?|decks?|"
                            r"porch|building|foundation|beams?|joists?|garage|parking (?:deck|garage|structure)|"
                            r"structure|overhang|awning|chimney|walkway|landing|railing|ceiling tiles?)\b", re.I)


def _object_subject(m: re.Match[str]) -> str:
    np_ = (m.group(1) or "") + m.group(2)
    head = re.split(r"\b(?:in|on|at|of|from|by|near|under|inside|behind|next to)\b", np_, maxsplit=1, flags=re.I)[0]
    if _PERSONISH.search(np_) or _BUILDING_PART.search(head):
        return m.group(0)
    return m.group(0)[: m.start(3) - m.start(0)] + "broke"


def _clean(text: str) -> str:
    """Figurative, negated and "not a physical state" phrases removed (the speaker refusing to answer, staff not
    replying, "passed out the forms"); sprint 7: body heat and other people's smoking habits."""
    text = _HARDWARE_COMPOUND.sub(lambda m: m.group(1), text)
    text = _OBJECT_FELL.sub(lambda m: m.group(1) + " broke", text)
    text = _NOUN_SUBJECT_VERB.sub(_object_subject, text)
    text = _OBJECT_FELL_ES.sub(lambda m: (m.group(1) or m.group(2)) + " roto", text)
    # final round: body heat is a FEVER, not a fire, but the person and the sign are kept ("my baby is burning up and
    # limp" was read as "my and limp": no person, no alert)
    return _strip_habit_smoke(_BODY_HEAT.sub(_as_fever, _not_physical(_strip_negated(_strip_figurative(text)))))


def _as_fever(m: re.Match[str]) -> str:
    return re.sub(r"burning(?: up| hot)?|ardiendo", "feverish", m.group(0), flags=re.I)


# Sprint 5.1 (journey j-safe-indirect-co): an alarm sounding + (a heat source OR several people) + symptoms = CO, even
# without the words "CO" / "carbon monoxide". Symptoms the person puts down to something else ("a headache from
# work", "sick of this") are not counted.
_SYMPTOM_ELSEWHERE = re.compile(
    r"(?:head ?aches?|head hurts|dizz\w*|nause\w*|sick|tired|foggy)\W+(?:\w+\W+){0,2}(?:from|because of|after) "
    r"(?:work|school|class|stress|studying|my (?:job|shift|boss|workout)|the gym|drinking|last night|crying|the "
    r"screen)|\bhangover|sick of\b|sick and tired|\b(?:a|my) cold\b|the flu\b|allerg\w*", re.I)
_ALARM_SOUNDING = re.compile(
    r"(?:\balarms?\b|detector|sensor|monitor|something|thing|it)\W+(?:\w+\W+){0,4}(?:beep\w*|going off|went off|"
    r"goes off|sounding|blar\w*|screech\w*|shriek\w*|ringing|won'?t stop)|\bbeep(?:ing|s|ed)?\b(?! (?:when|while|"
    r"whenever|every time) (?:i|we) (?:cook|shower))", re.I)
_NOT_A_HOME_ALARM = re.compile(r"\b(?:car|clock|phone|microwave|oven timer|timer|watch|security system) ?alarms?\b|"
                               r"alarm clock|microwave|timer|my phone", re.I)
_SEVERAL = re.compile(
    r"\bwe(?:'re| are)? (?:all|both)\b|\ball of us\b|\b(?:everyone|everybody)\b(?! in the building)|\bthe (?:whole )?"
    r"family\b|\bboth\b|\b(?:the|my|our) (?:kids|children|roommates|parents)\b|\b(?:\w+ )?(?:and|&) (?:i|me)\b|"
    r"\bme and\b|\b(?:wife|husband|partner|roommate|kid|son|daughter|mom|dad|baby)\W+(?:\w+\W+){0,6}(?:too|also|"
    r"as well)\b|\b(?:wife|husband|partner|roommate|son|daughter|mom|dad) and (?:my |our |the )?(?:wife|husband|"
    r"partner|roommate|son|daughter|kids?|mom|dad|baby)\b", re.I)
_CO_SYMPTOM = re.compile(_SYMPTOM + r"|fogg\w*|brain fog|out of it|groggy|woozy|spacey|loopy|feel(?:s|ing)? weird|"
                         r"head (?:is )?(?:pounding|throbbing)", re.I)
_HEAT_SOURCE = re.compile(_HEAT + r"|space heater|heat(?:ing)? (?:unit|system)|basement|utility (?:room|closet)",
                          re.I)
_REAL_FIRE = re.compile(r"\bsmok(?:e|ing|y)\b(?! ?(?:alarm|detector))|\bflames?\b|\bfire\b(?! ?(?:alarm|"
                        r"detector))|\bburning\b", re.I)


def _indirect_co(text: str) -> bool:
    sym = _SYMPTOM_ELSEWHERE.sub(" ", text)
    if not (_ALARM_SOUNDING.search(text) and _CO_SYMPTOM.search(sym)) or _REAL_FIRE.search(text):
        return False
    if _NOT_A_HOME_ALARM.search(text) and not re.search(r"detector|sensor", text, re.I):
        return False
    return bool(_HEAT_SOURCE.search(text) or _SEVERAL.search(sym))


# Sprint 5.1 (judge re-score): an UPPERCASE standalone "CO" / "C.O." (as an alarm display shows it) plus a person
# feeling unwell = carbon monoxide, even without "alarm" in the same message. Case-sensitive on purpose: "co-op",
# "c/o", "Co." (company), "CO2", Colorado ("Denver, CO", "moving to CO") are excluded.
_CO_UPPER = re.compile(r"(?<![\w/.&-])(?:CO|C\.O\.?)(?![\w/&'-]|\.\s*[A-Z]|\.\w)")
_COLORADO = re.compile(r"(?:\b(?:in|to|from|near|visiting|out of|moving to|denver|boulder|springs|aurora|"
                       r"lakewood|fort collins)\W{1,2}|,\s?)CO\b(?!\W+(?:on|is|says|reading|level|alarm|detector))|"
                       r"\bCO\s?\d{5}\b", re.I)
_UNWELL_CUE = re.compile(_CO_SYMPTOM.pattern + r"|out of it|faint\w*|passed out|confus\w*|sick\b(?! of)|"
                         r"not (?:feeling|acting) (?:right|well|herself|himself)|can'?t wake", re.I)


def _abbrev_co(text: str) -> bool:
    if not _CO_UPPER.search(text) or _COLORADO.search(text):
        return False
    return bool(_UNWELL_CUE.search(_SYMPTOM_ELSEWHERE.sub(" ", text)))


_PRESENT_PERSON = re.compile(_PRESENT_PERSON_RE, re.I)
_CO_POISONING = re.compile(r"\b(?:carbon mon\w*|co|mon[oó]xido(?: de carbono)?)\s+poison\w*|"
                           r"intoxicaci[oó]n por mon[oó]xido", re.I)
_INGESTED = re.compile(r"\b(?:drank|ate|swallow\w*|took|pills?|bleach|chemical\w*|clean\w*)\b", re.I)


def _kind_of(text: str) -> str | None:
    """Layer-1 + concept match on prepared text (no framing)."""
    if _abbrev_co(text):
        return "co"
    if re.search(r"(smoke|co|fire) (alarm|detector)", text, re.I) and re.search(
            r"dizz|headache|nause|head hurts|sick", _SYMPTOM_ELSEWHERE.sub(" ", text), re.I):
        return "co"  # alarm + symptoms = treat as carbon monoxide
    text = _clean(text)
    if _POLICY_OR_FIGURATIVE.search(text):
        text = _POLICY_OR_FIGURATIVE.sub(" ", text)
    if _PAST_PROPERTY_CRIME.search(text) and not _PRESENT_PERSON.search(text):
        text = _PAST_PROPERTY_CRIME.sub(" ", text)
    if _cold_exposure(text):
        return "medical"  # fix round: extreme cold + a vulnerable person with a sign of harm (911, stay with them)
    # "Is the parking lot well lit? I don't feel safe walking" asks about lighting; it is not a threat in progress.
    threat = re.search(r"following|stranger|\bex\b|someone|scared|threat|gun|knife|hit|hurt|kill|break", text, re.I)
    if not threat and "?" in text and re.search(r"feel safe (walking|at night|in the parking)", text, re.I):
        text = re.sub(r"feel safe", " ", text, flags=re.I)
    if _BENIGN_CHIRP.search(text) and not re.search(r"smoke (is|coming)|fire|flame|head|dizz|nause", text, re.I):
        return None
    if _BENIGN_CHIRP.search(text) and not _CHIRP_BUT_DANGER.search(text):
        return None
    if _indirect_co(text):
        return "co"
    for kind, pat in KINDS:
        if pat.search(text):
            if kind == "poison" and _CO_POISONING.search(text) and not _INGESTED.search(text):
                return "co"  # "carbon monoxide poisoning" is CO (fresh air first), not an ingestion
            return kind
    for kind, pat in CONCEPTS:
        if pat.search(text):
            return kind
    return None


_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")
# Fix round (P0): clause boundaries used to find what the message says OUTSIDE its question / past-event part.
_CLAUSE = re.compile(r"[.!?;,:\n]+|\s+(?=(?:we|i|there|it|they|he|she)\s+(?:had|was|were|used to|did|got|once)\b)|"
                     r"\s+[-\u2013\u2014]+\s+|\b(?:but|because|cause|cuz|since|although|though|so|"
                     r"y|pero|porque)\b|\band\b(?=\s+(?:now|right now|then|the|he|she|they|it|it'?s|there|someone|"
                     r"somebody|that|this)\b)", re.I)
_IF_CLAUSE = re.compile(r"^\s*(?:and\s+)?(?:what if|if|in case|si|en caso)\b", re.I)
_PAST_CLAUSE = re.compile(_PAST.pattern + r"|\b(?:last (?:night|week|weekend)|yesterday|the other (?:day|night)|"
                          r"over the weekend|earlier (?:this|today)|(?:years?|months?|weeks?|days?) ago|anoche|ayer)\b"
                          r"", re.I)


def _present_now(text: str) -> bool:
    """Fix round (P0): does the message ALSO describe a current situation (a person or the speaker with a symptom
    now, a hazard sign perceived now, a person / intruder present now) outside its question or past-event clauses?
    If so, the "asking about signs" and "past event" framings never apply: a question plus a live report is a
    report ("what are the signs of a stroke, my dad can't lift his arm")."""
    rest = [c for c in _CLAUSE.split(text) if c and c.strip() and not _HYPO.search(c) and not _IF_CLAUSE.search(c)
            and not _PAST_CLAUSE.search(c) and not re.search(r"\?\s*$", c)]
    residual = " , ".join(rest)
    if not residual.strip():
        return False
    clean = _clean(residual)
    # Fix round: the hazard named in a clause that is not a question / "if" / past clause is a current report on its
    # own ("the outlet is sparking, we had a leak last year"); no subject word is needed.
    return _present_signs(clean) or bool(_kind_of(residual)) or bool(_kind_of(residual) and re.search(
        r"\b(?:i|we|my|our|his|her|he|she|they|it|it'?s|there'?s|everyone|everybody|someone|somebody|the (?:guy|man|"
        r"baby|kids?))\b", clean, re.I))


def describes_current_situation(message: str) -> bool:
    """Sprint 7 (for app/risk/frame.py): the message also describes something happening now, outside its question or
    past-event clauses ("how do I recognise a gas leak, it smells like sulfur in here")."""
    return _present_now(_prepare(message))


def scan(message: str) -> tuple[str | None, str]:
    """(hazard kind, framing). framing: report | hypothetical | past | joking | none.

    Only "report" is an emergency. Self-harm and personal-safety mentions are never downgraded by framing, except
    that a laughing marker turns a self-harm alert into the 988 care line (still shown, never silent)."""
    text = _prepare(message)
    kind = _kind_of(text)
    if not kind:
        return None, "none"
    if kind == "self_harm" and _LAUGH.search(text):
        return kind, "joking"
    if kind in _NEVER_DOWNGRADE:
        return kind, "report"
    sentences = [s for s in _SENTENCE.split(text) if s and s.strip()]
    hits = [(s, _kind_of(s)) for s in sentences]
    hazard = [(s, k) for s, k in hits if k] or [(text, kind)]
    now_any = bool(_NOW.search(text))
    if (_HYPO.search(text) or _PAST.search(text)) and _present_now(text):
        return kind, "report"  # a question / past event PLUS a current situation in the same message
    framings: list[tuple[str, str]] = []
    for s, k in hazard:
        if k in _NEVER_DOWNGRADE:
            return k, "report"
        if _HYPO.search(s) and not _NOW.search(s):
            framings.append(("hypothetical", k))
        elif _PAST.search(s) and not now_any:
            framings.append(("past", k))
        else:
            return k, "report"
    if len(hazard) == 1 and hazard[0][0] is text and not (_HYPO.search(text) or _PAST.search(text)):
        return kind, "report"
    return framings[0][1], framings[0][0]


def emergency_kind(message: str) -> str | None:
    """Hazard kind for an acute emergency being reported now, or None.

    Sprint 7: the same single-message decision as the safety layer (phrase rules + the compositional frame in
    app.risk.detect), so the decision gate and the planner never disagree with it: a look-alike the frame reads as a
    drill / policy question / past event is not re-raised here, and a frame alert (a symptom-only or Spanish
    subjectless report) is an emergency here too."""
    from app.risk.detect import detect  # late import: app.risk.detect imports this module

    det = detect(message)
    return det.kind if det.framing == "report" else None


def intent_to_self_harm(message: str) -> bool:
    """A poisoning/overdose alert where the person may have done it on purpose: add the 988 line too."""
    text = _prepare(message)
    return bool(_SELF_HARM_HINT.search(text) or _DISTRESS.search(text) or re.search(
        r"on purpose|intentional\w*|so i (?:could|would|wouldn'?t)|wanted to (?:sleep|not|stop|end)|\bi (?:took|"
        r"swallowed|downed|popped)\b|a prop[oó]sito|me tom[eé]", text, re.I))


# Fix round (P1), NEEDS McKINLEY REVIEW: asked for the emergency number during an incident. The prototype has no
# community emergency line, so say so plainly; the closing 911 sentence is the approved emergency_follow wording.
NO_LINE = {
    "en": "I don't have your community's emergency maintenance number in this prototype, and I can't call or connect "
          "you from here. Your urgent note {ref} is saved, but nobody is notified automatically. If anyone feels "
          "unwell or is in danger, call 911.",
    "es": "En este prototipo no tengo el número de emergencias de mantenimiento de su comunidad, y desde aquí no puedo "
          "llamar ni comunicarle. Su nota urgente {ref} está guardada, pero no se avisa a nadie automáticamente. Si "
          "alguien se siente mal o corre peligro, llame al 911.",
}
_ASKS_LINE = re.compile(
    r"\b(?:don'?t|do not|dont|didn'?t|never got|can'?t find|cant find|lost) (?:have |know |get )?(?:the|an?|your|that|"
    r"any|their) (?:\w+ )?(?:emergency |maintenance |after[- ]?hours |on[- ]?call )?(?:number|line|phone(?: number)?|"
    r"contact)\b|\bwhat(?:'?s| is) (?:the|that|your|their) (?:\w+ )?(?:emergency|maintenance|after[- ]?hours|on["
    r"- ]?call)"
    r" (?:number|line|phone)\b|\b(?:where|how) (?:do|can|would) (?:i|we) (?:find|get|call) (?:the|that|your) "
    r"(?:\w+ )?(?:emergency|maintenance) (?:number|line)\b|\b(?:which|what) (?:number|line) (?:do|should) (?:i|we) "
    r"call\b|\bno tengo (?:el|ese) (?:n[uú]mero|tel[eé]fono)\b|\bcu[aá]l es el (?:n[uú]mero|tel[eé]fono)\b", re.I)


def asks_emergency_line(message: str) -> bool:
    """'I don't have the emergency number' / 'what's the maintenance line?' (fix round P1)."""
    return bool(_ASKS_LINE.search(_prepare(message)))


# Sprint 8, NEEDS McKINLEY REVIEW: labels of the explicit contact links the website shows under a safety alert or a
# concern line (ChatResponse.safety_contacts, chosen in app/risk/ui_state.py). A link is only ever a labelled tel:/sms:
# link the person taps themselves; nothing is dialled, sent or notified. The prototype has no community emergency
# maintenance number, so that entry is plain information with no link.
CONTACT_LABEL: dict[str, dict[str, str]] = {
    "call_911": {"en": "Call 911", "es": "Llamar al 911"},
    "call_911_gas": {"en": "Call 911 once you're outside", "es": "Llamar al 911 cuando esté afuera"},
    "gas_company": {"en": "Or call your gas company's emergency line (it's on your gas bill)",
                    "es": "O llame a la línea de emergencias de su compañía de gas (está en su factura)"},
    "call_911_poison": {"en": "Call 911 if they're hard to wake or not breathing",
                        "es": "Llamar al 911 si no despierta bien o no respira"},
    "poison_help": {"en": "Call Poison Help 1-800-222-1222",
                    "es": "Llamar a Poison Help 1-800-222-1222 (hay ayuda en español)"},
    "call_988": {"en": "Call 988", "es": "Llamar al 988"},
    "text_988": {"en": "Text 988", "es": "Enviar un mensaje al 988"},
    "call_911_self": {"en": "Call 911 if you're in immediate danger", "es": "Llamar al 911 si está en peligro ahora"},
    "call_911_if_danger": {"en": "Call 911 if anyone is in danger", "es": "Llamar al 911 si alguien corre peligro"},
    "call_911_if_worse": {"en": "Call 911 if anyone feels very unwell or it gets worse",
                          "es": "Llamar al 911 si alguien se siente muy mal o empeora"},
    "maintenance_line": {"en": "Your community's emergency maintenance line (this prototype doesn't have the number)",
                         "es": "La línea de emergencias de mantenimiento de su comunidad (este prototipo no tiene el "
                               "número)"},
}


QUEUE_NOTE = {
    "en": " An urgent note is saved in the staff queue, but this prototype can't page or call anyone, so please "
          "make that call yourself.",
    "es": " Dejé una nota urgente para el personal, pero este prototipo no puede avisar ni llamar a nadie, así que "
          "por favor haga usted esa llamada.",
}

HEADING = {
    "self_harm": {"en": "You can call or text 988 now", "es": "Puede llamar o enviar un mensaje al 988 ahora"},
    "gas": {"en": "Leave now, then call 911 from outside", "es": "Salga ahora y llame al 911 desde afuera"},
    "co": {"en": "Get everyone outside, then call 911", "es": "Salgan todos y llame al 911"},
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



def notice(kind: str, lang: str = "en") -> str:
    return NOTICE[kind].get(lang) or NOTICE[kind]["en"]


def heading(kind: str | None, lang: str = "en") -> str:
    h = HEADING[kind if kind in ("self_harm", "gas", "co") else "default"]
    return h.get(lang) or h["en"]
