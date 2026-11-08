"""Layer 1: deterministic risk detection (wraps app.emergency) on the message and the recent conversation."""

import re

from app.emergency import intent_to_self_harm, possible_risk, scan
from app.risk.models import DeterministicRisk

WINDOW_TURNS = 3  # earlier user messages combined with this one
# "It's happening now" after a hypothetical/past mention turns that mention into a report.
_HAPPENING_NOW = re.compile(r"\b(?:it'?s|it is|this is|that'?s) (?:happening|going on) (?:now|right now)\b|"
                            r"\b(?:yes|yeah|yep)\W+(?:\w+\W+){0,2}(?:right )?now\b|\bhappening now\b|"
                            r"est[aá] pasando (?:ahora)?|s[ií],? ahora", re.I)


def detect(message: str, recent: list[str] | None = None) -> DeterministicRisk:
    """`recent` = earlier user messages in this conversation (oldest first, current message excluded)."""
    kind, framing = scan(message)
    out = DeterministicRisk(care=possible_risk(message))  # type: ignore[arg-type]
    if kind and framing == "report":
        out.kind, out.framing = kind, "report"
    elif kind:
        out.mentioned_kind, out.framing = kind, framing  # type: ignore[assignment]
    prev = [m for m in (recent or []) if m][-WINDOW_TURNS:]
    if not out.kind and prev:
        # Danger that only becomes clear across turns ("the kid got under the sink" ... "now he's throwing up").
        before, _ = scan(" . ".join(prev))
        joined_kind, joined_framing = scan(" . ".join([*prev, message]))
        if joined_kind and joined_framing == "report" and joined_kind != before:
            out.kind, out.framing, out.via_window = joined_kind, "report", True
    if not out.kind and prev and _HAPPENING_NOW.search(message):
        for m in reversed(prev):
            k, _f = scan(m)
            if k:
                out.kind, out.framing, out.via_window = k, "report", True
                break
    if out.kind == "poison" and (intent_to_self_harm(message) or any(intent_to_self_harm(m) for m in prev)):
        out.self_harm_intent = True
    return out
