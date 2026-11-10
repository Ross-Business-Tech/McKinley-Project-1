"""Contact details typed into an open tour draft never overwrite the community/city (simulator finding D-7)."""

import pytest

from app.intake import bare_area_answer, extract_area_correction


@pytest.mark.parametrize("msg", [
    "Alex Rivera, alex.rivera@example.com",
    "Alex Rivera, [email]",
    "My name is Jordan Lee",
    "Sam Park, (734) 555-0142",
    "Sam Park, 734-555-0142",
])
def test_contact_details_are_not_a_place(msg):
    assert extract_area_correction(msg) is None
    assert bare_area_answer(msg) is None


@pytest.mark.parametrize("msg,place", [
    ("Orlando, FL", "Orlando"),
    ("actually Ann Arbor not Ypsilanti", "Ann Arbor"),
    ("in Lansing", "Lansing"),
])
def test_real_place_answers_still_work(msg, place):
    assert extract_area_correction(msg) == place
