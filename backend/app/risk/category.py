"""Layer 4a (sprint 6): incident-specific notice selection.

The detectors name a hazard KIND; the approved notice for that kind must also fit the incident. Earlier sprints sent
every "trapped" alert to the elevator text, sparks to the fire text and some generator CO to the medical text. This
step picks the EXISTING approved notice whose steps are right for the message. No new safety wording is written here.

  trapped, no elevator/lift named               -> medical   (911 now, stay with the person: child or pet in a hot
                                                               car, a child shut in a room, a person pinned)
  personal_safety, a fall / injury, no attacker  -> medical   ("tripped and is screaming her leg hurts")
  fire_smoke from a device, no flames named      -> electrical (don't touch; smoke/sparks/heat -> leave, 911)
  medical with a fuel-burning source + symptoms  -> co        (fresh air first, then 911)

Sprint 7:
  poison with no ingestion / substance / overdose word -> medical (blue lips alone are a medical sign)
  medical where a person is doing it TO someone        -> personal_safety ("my partner is choking me")
  fire_smoke from an appliance flame colour + symptoms  -> co ("the water heater flame is yellow, we all have
                                                           headaches")

Everything else keeps its detected kind. The original kind is kept on the decision (`detected_kind`).
"""

import re

from app.risk.concepts import HARM, MECHANISM, PERSON

_ELEVATOR = re.compile(r"\b(?:elevator|elevators|lift|lifts|ascensor|elevador)\b", re.I)
_ATTACK = re.compile(
    r"\b(?:hit(?:ting)?|hits|beat\w*|attack\w*|punch\w*|slap\w*|chok\w*|strangl\w*|threat\w*|gun|knife|weapon|"
    r"stab\w*|shoot\w*|intruder|break(?:ing)? in|broke in|broken into|breaking into|stalk\w*|follow\w* me|kick\w* "
    r"(?:in )?(?:the|my) door|abus\w*|pushed me|shoved|grabbed|golpe\w*|peg\w*|amenaz\w*|arma|cuchillo|pistola)\b",
    re.I)
_FALL = re.compile(rf"(?:{PERSON})\W+(?:\w+\W+){{0,3}}(?:{MECHANISM})\W+(?:\w+\W+){{0,10}}(?:{HARM})", re.I)
_DEVICE = re.compile(r"\b(?:outlet|socket|plug|switch|breaker|panel|fuse ?box|wire|wires|wiring|cord|extension cord|"
                     r"charger|power strip|enchufe|tomacorriente|cable|cables)\b", re.I)
_OPEN_FIRE = re.compile(r"\bflames?\b|\bon fire\b|\bfire\b|\bablaze\b|\bburning down\b|\bllamas?\b|\bfuego\b|"
                        r"\bincendio\b|spreading", re.I)
_FUEL_SOURCE = re.compile(r"\bgenerator\b|engine (?:running|on)|car (?:running|on) in (?:the )?garage|charcoal|"
                          r"grill (?:inside|indoors|in the)|(?:space )?heater|furnace|boiler|water heater|generador|"
                          r"calentador|caldera", re.I)
_CO_SYMPTOMS = re.compile(r"headache|head (?:hurts|is pounding)|dizz\w*|nause\w*|faint\w*|sleepy|drows\w*|groggy|"
                          r"confus\w*|throwing up|vomit\w*|mare\w*|dolor de cabeza", re.I)
_TRAUMA = re.compile(r"chest pain|heart attack|bleed\w*|fell|fallen|broken|seizure|stroke|not breathing|choking",
                     re.I)


_INGESTION = re.compile(r"\b(?:swallow\w*|ate|eaten|drank|drunk|took|taken|popped|ingest\w*|overdos\w*|od'?d|pills?|"
                        r"meds|medic\w*|tablets?|bleach|cleaner|chemical\w*|poison\w*|pods?|batter\w*|narcan|"
                        r"naloxone|fentanyl|opioid\w*|heroin|drugs?|alcohol|se (?:trag|tom|comi|bebi)\w*|pastillas|"
                        r"cloro|veneno|sobredosis|fumes|bug spray|pesticide)\b", re.I)
_ASSAULT = re.compile(r"\b(?:he|she|they|my (?:ex|partner|husband|wife|boyfriend|girlfriend|roommate|dad|mom|son|"
                      r"brother)|someone|somebody|a (?:man|guy|stranger)|the (?:man|guy))\s+(?:is |are |keeps |was |"
                      r"started |just |'s |'re )?(?:chok|strangl|hit|beat|punch|kick|stab|shoot|smother)\w*\s+(?:me|us"
                      r")\b|"
                      r"\bme est[aá] (?:ahorcando|asfixiando|golpeando)\b", re.I)
_FLAME_COLOUR = re.compile(r"\bflames? (?:is |are |looks? )?(?:yellow|orange|lazy|floppy)\b|\b(?:yellow|orange|lazy) "
                           r"flames?\b", re.I)
_LIVE_FIRE = re.compile(r"\bon fire\b|\bspread\w*|\bsmoke\b|\bburning\b|\bcaught\b|\bflames? (?:coming|shooting|"
                        r"everywhere|growing)", re.I)


# Sprint 7: a heater that is OFF plus a cold body ("the heater died, dad is shivering and confused") is cold exposure
# (medical), not carbon monoxide.
_COLD_BODY = re.compile(r"\bshiver\w*|cold to the touch|ice[- ]cold|\b(?:is|feels?) (?:so |very |really )?cold\b|"
                        r"temblando de fr[ií]o|helad[oa]|\b(?:heat|heater|furnace|calefacci[oó]n)\W+(?:\w+\W+){0,3}"
                        r"(?:died|out|off|broke|stopped|not working|no funciona)", re.I)


def refine(kind: str | None, text: str) -> tuple[str | None, str | None]:
    """(notice kind, reason) for a detected kind in the context of the message text."""
    if not kind or kind == "other":
        return kind, None
    if kind == "poison" and not _INGESTION.search(text):
        return "medical", "a body sign with no ingestion named (medical notice)"
    if kind == "medical" and _ASSAULT.search(text):
        return "personal_safety", "a person is hurting someone (personal safety notice)"
    if (kind == "fire_smoke" and _FLAME_COLOUR.search(text) and _CO_SYMPTOMS.search(text)
            and not _LIVE_FIRE.search(text)):
        return "co", "an appliance flame colour with symptoms (carbon monoxide notice)"
    if kind == "trapped" and not _ELEVATOR.search(text):
        return "medical", "trapped outside an elevator: 911 + stay with the person (medical notice)"
    if kind == "personal_safety" and _FALL.search(text) and not _ATTACK.search(text):
        return "medical", "a fall or injury with no attacker named (medical notice)"
    if kind == "fire_smoke" and _DEVICE.search(text) and not _OPEN_FIRE.search(text):
        return "electrical", "smoke/heat from an electrical device, no flames (electrical notice)"
    if (kind == "medical" and _FUEL_SOURCE.search(text) and _CO_SYMPTOMS.search(text)
            and not _TRAUMA.search(text) and not _COLD_BODY.search(text)):
        return "co", "symptoms next to a fuel-burning source (carbon monoxide notice: fresh air first)"
    return kind, None
