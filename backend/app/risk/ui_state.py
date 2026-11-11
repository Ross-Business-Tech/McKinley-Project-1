"""Sprint 8: the UI safety state and its category-specific contacts (the contract the website consumes).

Computed in chat_engine step 8 from what is actually SHOWN this turn (after the incident state machine and the
planner), so the state can never disagree with the safety text on screen:

  active   a full alert (safety_notice) is shown: a policy alert R1 / R2 / R9e, an incident follow-up R10, or an
           emergency decided by the gate (generic steps).
  concern  a calm line or safety info is shown: distress / unwell / danger care lines, R5 safety info (a hypothetical,
           educational or past mention), R5c (a serious conditional about a specific person), R9 remembered lines,
           R10q quiet turns of an active incident.
  normal   nothing is shown (benign messages, look-alikes, resolved incidents).

Contacts (labels in app/emergency.CONTACT_LABEL, NEEDS McKINLEY REVIEW; links are only ever tapped by the person):

  | category                                         | contacts                                                   |
  | medical, fire_smoke, co, personal_safety, trapped,| Call 911                                                   |
  |   extreme_temp, unknown / gate emergency           |                                                            |
  | structural                                       | Call 911; maintenance line (info)                          |
  | gas                                              | Call 911 once outside; gas company line (info)             |
  | poison                                           | Poison Help 1-800-222-1222; Call 911 if hard to wake...    |
  | self_harm                                        | Call 988; Text 988; Call 911 if in immediate danger        |
  | flood, electrical                                | maintenance line (info); Call 911 if anyone is in danger   |
  | also_988 on any alert                            | + Call 988; Text 988                                       |

  concern (fix round: never empty; the contacts match the line shown):
    distress line            -> 988 call + text
    R10q quiet incident turn -> the incident's category contacts
    safety info (R5 / R5c)   -> the category's contacts; fire / electrical / flood / structural information gets
                                "911 if anyone is in danger" + the maintenance line (info)
    R9, or a person sign     -> Call 911
    unwell line              -> "Call 911 if anyone feels very unwell or it gets worse"
    broad danger line        -> "Call 911 if anyone is in danger" + the maintenance line (info)
  Pending conditional (app/risk/incident.py): after R5 / R5c, a "yes" or a description of the sign in the next
  PENDING_TURNS turns becomes the full alert (rule R5f).
"""

from typing import Any

from app.emergency import CONTACT_LABEL
from app.risk.models import RiskDecision

_HREF = {"call_911": "tel:911", "call_911_gas": "tel:911", "call_911_poison": "tel:911", "call_911_self": "tel:911",
         "call_911_if_danger": "tel:911", "call_911_if_worse": "tel:911", "call_988": "tel:988", "text_988": "sms:988",
         "poison_help": "tel:18002221222", "gas_company": None, "maintenance_line": None}
_KIND = {"text_988": "text", "gas_company": "info", "maintenance_line": "info"}
_BY_CATEGORY: dict[str, list[str]] = {
    "gas": ["call_911_gas", "gas_company"],
    "poison": ["poison_help", "call_911_poison"],
    "self_harm": ["call_988", "text_988", "call_911_self"],
    "flood": ["maintenance_line", "call_911_if_danger"],
    "electrical": ["maintenance_line", "call_911_if_danger"],
    "structural": ["call_911", "maintenance_line"],
}
_988 = ["call_988", "text_988"]
# safety information (a question, a past or controlled event): the same help, worded "if"
_INFO: dict[str, list[str]] = {
    "fire_smoke": ["call_911_if_danger", "maintenance_line"], "electrical": ["maintenance_line", "call_911_if_danger"],
    "flood": ["maintenance_line", "call_911_if_danger"], "structural": ["call_911_if_danger", "maintenance_line"],
}


def _contact(key: str, lang: str) -> dict[str, Any]:
    label = CONTACT_LABEL[key].get(lang) or CONTACT_LABEL[key]["en"]
    return {"label": label, "href": _HREF[key], "kind": _KIND.get(key, "call")}


def contact_keys(category: str | None, also_988: bool = False) -> list[str]:
    keys = list(_BY_CATEGORY.get(category or "", ["call_911"]))
    if also_988 and category != "self_harm":
        keys += _988
    return keys


def safety_ui(decision: RiskDecision, *, alert_shown: bool, care_kind: str | None,
              lang: str = "en") -> tuple[str, list[dict[str, Any]]]:
    """(safety_state, safety_contacts) for what this turn shows (see the module docstring)."""
    lang = lang if lang in ("en", "es") else "en"
    d = decision
    if alert_shown:
        kind = d.kind if d.response == "full_alert" else None
        keys = contact_keys(kind if kind != "other" else None, d.also_988)
    elif care_kind:
        # fix round: a concern turn is never empty: its contacts always match the line it shows
        if care_kind == "distress":
            keys = _988
        elif d.rule == "R10q" and d.incident:
            keys = contact_keys(d.incident)
        elif care_kind == "info":
            keys = _INFO.get(d.kind or "", contact_keys(d.kind)) if d.kind else ["call_911_if_danger"]
        elif d.rule == "R9" or d.person_danger:
            keys = ["call_911"]
        elif care_kind == "unwell":
            keys = ["call_911_if_worse"]
        else:  # the broad 911 + maintenance line, no person named
            keys = ["call_911_if_danger", "maintenance_line"]
        return "concern", [_contact(k, lang) for k in keys]
    else:
        return "normal", []
    return "active", [_contact(k, lang) for k in keys]
