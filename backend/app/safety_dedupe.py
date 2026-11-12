"""Say each emergency instruction once per message (Sprint 9 follow-up turns).

A follow-up on an emergency re-shows the approved safety steps and then adds the `emergency_follow` line, whose two
reminder sentences ("If you haven't yet, call your community's emergency maintenance line." / "If anyone feels
unwell or is in danger, call 911.") can repeat what the steps just said, so "call 911" appeared two or three times.

Rule (narrow on purpose): a reminder sentence of `emergency_follow` is dropped ONLY when the same instruction (911,
or the community emergency maintenance line) already appears EARLIER in the same reply WITHOUT a condition. "Call 911
if water reaches anything electrical" does not cover "If anyone feels unwell or is in danger, call 911": different
conditions are different guidance, so that reminder stays. The approved safety steps are
never removed, shortened or reworded, the first instruction always stays, and a reminder whose instruction the steps
do not contain is kept (carbon monoxide steps say 911 but not the maintenance line, so that reminder stays).
"""

import re

from app.templates import T

_SENT = re.compile(r"(?<=[.!?])\s+")
_INSTRUCTIONS = {
    "911": re.compile(r"\b(?:call|llame\s+al?)\s+(?:al\s+)?911\b", re.I),
    "emergency_line": re.compile(r"emergency\s+maintenance\s+line|l[ií]nea\s+de\s+emergencias?\s+de\s+mantenimiento",
                                 re.I),
}


def _reminders() -> set[str]:
    out: set[str] = set()
    for lang in ("en", "es"):
        text = T["emergency_follow"].get(lang) or ""
        out.update(s.strip() for s in _SENT.split(text)[1:] if s.strip())  # sentence 1 is the saved-note statement
    return out


REMINDERS = _reminders()


_CONDITION = re.compile(r"\b(?:if|when|unless|si|cuando)\b", re.I)
# a negated mention ("I can't call 911 for you", "you don't need to call 911") never counts as having said it
_NEGATED = re.compile(r"\b(?:can'?t|cannot|don'?t|do\s+not|won'?t|never|no\s+need|no\s+puedo|no\s+necesita)\b", re.I)


def _instructions(sentence: str) -> set[str]:
    return {k for k, rx in _INSTRUCTIONS.items() if rx.search(sentence)}


def _unconditional(sentence: str) -> set[str]:
    """Instructions given without any condition in the same sentence (only these can cover a later reminder)."""
    return set() if _CONDITION.search(sentence) or _NEGATED.search(sentence) else _instructions(sentence)


def drop_repeated_reminders(reply: str) -> tuple[str, list[str]]:
    """Return (reply, dropped sentences). Only `emergency_follow` reminders already covered earlier are dropped."""
    seen: set[str] = set()
    out: list[str] = []
    dropped: list[str] = []
    parts = re.split(r"((?<=[.!?])\s+)", reply)  # keep the original separators (newlines, spacing)
    for i in range(0, len(parts), 2):
        s, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        ins = _instructions(s)
        if s.strip() in REMINDERS and ins and ins <= seen:
            dropped.append(s.strip())
            continue
        seen |= _unconditional(s)
        out.append(s + sep)
    return ("".join(out).rstrip() if dropped else reply), dropped
