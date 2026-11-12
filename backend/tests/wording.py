"""Sprint 9: the honesty facts a customer reply must still state, independent of the exact (warmer, shorter) wording.

Before Sprint 9 every reply carried the sentence "nobody is notified automatically". The demo limit is now said once
per step ("hasn't been sent to the leasing team", "this demo doesn't send requests to McKinley staff"); these helpers
pin the fact, not the sentence."""
import re

_NOT_SENT = re.compile(r"hasn't been sent|wasn't sent|isn't sent|not sent to|doesn't send|won't notify|"
                       r"nobody is notified|no one is notified|no se envi[oó]|no avisa|no se avisa", re.I)


def says_not_sent(text: str) -> bool:
    """The reply says plainly that nothing reached McKinley staff."""
    return bool(_NOT_SENT.search(text or ""))
