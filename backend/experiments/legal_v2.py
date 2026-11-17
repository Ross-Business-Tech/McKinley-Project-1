"""EXPERIMENT (offline only; app/ never imports it): a structured sensitive-topic boundary for fair-housing / legal
questions, as a possible long-term replacement for the growing reply-pattern list in app/guardrails.py (PR #20).
Production enforcement is not changed.

    structured topic (model) ─┐
                              ├─ either says sensitive ─> backend referral policy: the approved / provisional
    message topic gate  ──────┘                           knowledge-base referral is shown and the note is routed;
                                                          the model's own prose on these topics is never shown
    neither says sensitive ──> the model's reply, checked by a SMALL backstop (named law / "legal(ly)" /
                               "illegal" / "entitled" forms, EN + ES); a hit is replaced by the referral

The model only RECOGNISES the topic (an enum it would return next to its reply; simulated here). It never gets
authority: on a sensitive topic its wording is dropped whatever it says. Two independent recognisers (model label and
the existing message gate) cover each other's misses, and the backstop covers a reply on a topic both missed.
Provider failures: no model text exists (the production fallback sentence is shown); routing then uses the message
gate alone. A missing or invalid topic label counts as "not recognised", never as "not sensitive" proof.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.guardrails import _RESIDENT_PROFILE, _RESIDENT_PROFILE_ES, legal_referral, legal_sensitive

TOPICS = {"none", "pet_policy", "amenities", "pricing", "maintenance", "accommodation", "assistance_animal",
          "disability_access", "fair_housing", "resident_demographics", "legal_action"}
SENSITIVE = {"accommodation", "assistance_animal", "disability_access", "fair_housing", "resident_demographics",
             "legal_action"}

# The small backstop: a reply that names the law, says something is (il)legal, or grants a right. Deliberately NOT the
# obligation / permission paraphrase list: those topics are recognised from the question instead.
_BACKSTOP = re.compile(
    r"\b(?:fair housing|the|federal|state)? ?(?:law|laws|act|fha|ada|hud)\b[^.?!]{0,40}?\b(?:prohibits?|requires?|"
    r"allows?|permits?|forbids?|protects?|says)\b|\b(?:by|under) (?:the )?(?:law|fair housing(?: act)?|fha|ada)\b|"
    r"\blegally\b|\billegal\b|\blegal right\b|\bunlawful\b|"
    r"\bdiscriminat\w*|\bentitled\b|\byou (?:qualify|are eligible|'re eligible)\b|"
    r"\b(?:la|las) ley(?:es)?\b[^.?!]{0,40}?\b(?:proh[ií]be|exige|requiere|permite|obliga|protege)\w*|"
    r"\b(?:por|seg[uú]n la|bajo la) (?:ley|normativa)\b|\blegalmente\b|\bes (?:il)?legal\b|\bdiscrimina\w*|"
    r"\btiene(?:s)? (?:el )?derecho\b", re.I)
_QUOTED = re.compile(r"\"[^\"]{1,300}\"|“[^”]{1,300}”|«[^»]{1,300}»")
_NOT_A_CLAIM = re.compile(r"\b(?:what|whether|if|si|qu[eé]|lo que)\s+(?:\S+\s+)?$", re.I)


@dataclass(frozen=True)
class Signal:
    """The model's structured topic label. `topic=None`: missing, invalid or the call failed."""
    topic: str | None

    @classmethod
    def parse(cls, raw: object) -> Signal:
        return cls(raw if isinstance(raw, str) and raw in TOPICS else None)


@dataclass(frozen=True)
class LegalDecision:
    shown: str | None  # None = production's own fallback sentence (no model text this turn)
    source: str  # "model" | "referral"
    reason: str  # "ordinary" | "topic_model" | "topic_message" | "topic_both" | "backstop" | "no_model_text"
    route_team: str | None  # "leasing" / "management" for a sensitive topic, else None
    wording: str | None = None  # "provisional" / "approved" when the referral is shown


def backstop(reply: str) -> bool:
    """A named-law / legality / right claim, or a description of who lives somewhere (production's existing
    resident-profile patterns, reused: demographics are often missed by the topic recognisers)."""
    text = _QUOTED.sub(" ", reply or "")
    if _RESIDENT_PROFILE.search(text) or _RESIDENT_PROFILE_ES.search(text):
        return True
    return any(not _NOT_A_CLAIM.search(text[max(0, m.start() - 20):m.start()]) for m in _BACKSTOP.finditer(text))


def decide(message: str, reply: str | None, signal: Signal, lang: str, prospect: bool) -> LegalDecision:
    by_model = signal.topic in SENSITIVE
    by_message = legal_sensitive(message)
    team = "leasing" if prospect else "management"
    if by_model or by_message:
        text, wording = legal_referral(lang, prospect)
        why = "topic_both" if by_model and by_message else "topic_model" if by_model else "topic_message"
        return LegalDecision(text if reply is not None else None, "referral" if reply is not None else "model",
                             why if reply is not None else "no_model_text", team, wording)
    if reply is None:
        return LegalDecision(None, "model", "no_model_text", None)
    if backstop(reply):
        text, wording = legal_referral(lang, prospect)
        return LegalDecision(text, "referral", "backstop", None, wording)
    return LegalDecision(reply, "model", "ordinary", None)
