"""Resident history selection (app/context.related_interactions): maintenance items are matched by the physical thing
the message names (shared object lexicon), not only by topic bucket; the acceptance T1a/T1b defect was a ceiling leak
matched to kitchen-sink history because both say "leak". New wording and locations throughout; the person's own
records only."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.context import Interaction, Resident, build_resident_context, related_interactions


def item(iid, when, subject, status="closed", category="maintenance", follow=False):
    return Interaction(interaction_id=iid, resident_id="R900", timestamp=datetime(*when), channel="portal",
                       category=category, subject=subject, full_text="(not used)", status=status,
                       resolved_date=None if status == "open" else date(*when[:3]), follow_up_needed=follow)


HISTORY = [
    item("I901", (2025, 12, 1), "Kitchen faucet leaking at the base"),
    item("I902", (2026, 2, 3), "Water stain on hallway ceiling"),
    item("I903", (2026, 3, 9), "Kitchen faucet dripping again"),
    item("I904", (2026, 5, 2), "Hallway ceiling patched and painted"),
    item("I905", (2026, 7, 1), "Bedroom window won't latch"),
    item("I906", (2026, 9, 14), "Heater makes a clicking noise"),
    item("I907", (2026, 10, 2), "Hallway ceiling drip is back", status="open", follow=True),
    item("I908", (2026, 10, 9), "Renewal question about the 15-month term", category="renewal"),
]
RES = Resident("R900", {"resident_id": "R900", "first_name": "Ana", "community": "Test Commons",
                        "preferred_contact": "email", "preferred_language": "English"}, HISTORY)


def related(msg, history=HISTORY):
    from app.context import detect_topics
    topics = set(detect_topics(msg)) - {"contact_preference"}
    from app.context import MAINTENANCE_TOPICS
    is_maint = bool(topics & (MAINTENANCE_TOPICS | {"maintenance_general"}))
    items, _ = related_interactions(history, msg, topics, is_maint)
    return [i.interaction_id for i in items]


@pytest.mark.parametrize("msg", ["Water is leaking from the hallway ceiling again",
                                 "there's a drip coming through the ceiling by the front door",
                                 "otra vez hay una gotera en el techo del pasillo"])
def test_a_ceiling_leak_gets_the_ceiling_history_not_the_faucet_history(msg):
    assert related(msg) == ["I902", "I904", "I907"]


@pytest.mark.parametrize("msg", ["the kitchen faucet is leaking again", "my faucet keeps dripping"])
def test_a_faucet_leak_gets_the_faucet_history(msg):
    assert related(msg) == ["I901", "I903"]


def test_other_categories_still_match_by_topic():
    assert related("I have a question about renewing my lease") == ["I908"]
    assert related("the heater is clicking loudly") == ["I906"]


def test_generic_wording_without_a_named_thing_keeps_the_topic_rule():
    # unchanged fallback: no named thing -> the topic buckets decide (general-maintenance items here)
    from app.context import interaction_topics
    want = [i.interaction_id for i in HISTORY if interaction_topics(i) & {"maintenance_general"}]
    assert related("something is broken, can someone come fix it?") == want == ["I904", "I905"]
    assert related("hello there") == []


def test_open_items_are_always_kept_and_the_list_is_capped():
    many = [item(f"I8{k:02d}", (2026, 1, k + 1), f"Ceiling stain number {k}") for k in range(10)]
    old_open = item("I799", (2025, 1, 1), "Ceiling sagging near the vent", status="open", follow=True)
    got = related("the ceiling has a new stain", [old_open, *many])
    assert len(got) == 6 and got[0] == "I799"  # oldest open item kept, then the most recent five
    assert got[1:] == [f"I8{k:02d}" for k in range(5, 10)]


def test_the_context_flags_follow_the_matched_items_and_stay_minimal():
    ctx = build_resident_context(RES, "The hallway ceiling is leaking again", "R900")
    fields = {f.name: f.value for f in ctx.fields}
    lines = [f.value for f in ctx.fields if f.name == "related_history"]
    assert len(lines) == 3 and all("ceiling" in x.lower() for x in lines)
    assert fields["repeat_issue_flag"].startswith("3 related")
    assert fields["open_commitment_flag"].startswith("1 related")
    assert not any("faucet" in x.lower() for x in lines)
    assert "(not used)" not in str(ctx.fields)  # full_text never reaches the context


def test_only_the_residents_own_records_are_ever_considered():
    other = [item("I999", (2026, 10, 1), "Hallway ceiling leaking badly")]
    other = [Interaction(**{**i.__dict__, "resident_id": "R901"}) for i in other]
    ctx = build_resident_context(Resident("R900", RES.row, []), "the hallway ceiling is leaking", "R900")
    assert not [f for f in ctx.fields if f.name == "related_history"]  # no history of their own: nothing
    assert "I999" not in str(ctx.fields) and other  # another resident's items are never passed in or shown
