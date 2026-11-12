"""Sprint 6: paraphrase families for the structured understanding layer (RULES path, offline) and API replays.

Each behaviour has >= 8 varied phrasings and >= 4 near-miss negatives, written from the behaviour's description
(not from one reported sentence), so a fix that only matches the reported wording fails here.
Fixture residents (tests/conftest.py): R001 (AC history I002/I003 closed, I008 "AC rattling" open), R003 (none).
"""

import pytest

from app.state import get_state
from app.understanding import (
    DialogueAct,
    asks_history,
    budget,
    cancels,
    checks_status,
    dates,
    frustration,
    issue_rewrite,
    requests_human,
    resumes,
    understand_rules,
)


def chat(client, msg, session, persona="R003"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


def press_send(client, session, kind, persona="R003"):
    return client.post("/api/actions/confirm", json={"session_id": session, "persona_id": persona,
                                                     "kind": kind}).json()


def fields(r):
    return {f["key"]: f["value"] for f in (r.get("action") or {}).get("fields", [])}


def records(session):
    return get_state().store.records(session_id=session, limit=50)


REPAIR = {"kind": "maintenance_request",
          "fields": {"issue": {"value": "The kitchen sink is leaking", "source": "you_said"},
                     "location": {"value": "Kitchen", "source": "you_said"}}}
TOUR = {"kind": "tour_request", "fields": {"area": {"value": "Heron Lake Apartments", "source": "you_said"},
                                           "days": {"value": "Saturday", "source": "you_said"},
                                           "time": {"value": "Morning", "source": "you_said"}}}

# ---- 1. asking for a person --------------------------------------------------------------------------------

HUMAN_YES = ["I want a manager.", "can I please get hold of a real human",
             "is there someone in charge I can talk to?", "put me through to your supervisor",
             "I'd like to speak with a person please", "connect me with the office",
             "let me talk to someone from the office", "I need a human, not a bot", "get me your boss",
             "transfer me to a representative", "I'd rather deal with a human", "escalate this please"]
HUMAN_NO = ["my manager at work is annoying", "my phone is broken", "I need someone to fix the sink",
            "I don't want to talk to anyone, just fix it", "the manager said parking is free",
            "can a person come in while I'm out?", "my boss wants me in early tomorrow",
            "is the office open on saturday?"]


@pytest.mark.parametrize("msg", HUMAN_YES)
def test_handoff_request_paraphrases(msg):
    u = understand_rules(msg, REPAIR, "entry")
    assert requests_human(msg) and u.requests_human and u.has(DialogueAct.REQUEST_HUMAN)


@pytest.mark.parametrize("msg", HUMAN_NO)
def test_handoff_near_misses(msg):
    assert not requests_human(msg) and not understand_rules(msg, REPAIR, "entry").requests_human


@pytest.mark.parametrize("msg", ["put me through to your supervisor", "is there someone in charge I can talk to?",
                                 "can I please get hold of a real human"])
def test_handoff_paraphrase_mid_repair_keeps_the_repair(client, msg):
    s = f"h-{abs(hash(msg))}"
    chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert r["action"]["kind"] == "staff_handoff" and "nothing is lost" in r["reply"]
    assert "fan" in fields(r)["earlier"].lower() and records(s) == []


@pytest.mark.parametrize("msg", ["my manager at work is annoying", "my phone is broken"])
def test_handoff_near_miss_makes_no_note(client, msg):
    r = chat(client, msg, f"hn-{abs(hash(msg))}")
    assert not r["action"] or r["action"]["kind"] != "staff_handoff"


# ---- 2. corrections ------------------------------------------------------------------------------------------

CORR_YES = [("actually it's the bathroom", "location", "Bathroom"),
            ("sorry, I meant the bedroom", "location", "Bedroom"),
            ("my bad, bedroom", "location", "Bedroom"), ("correction: the bathroom", "location", "Bathroom"),
            ("wait, it's the living room", "location", "Living room"),
            ("the description should be: the faucet drips constantly", "issue", "The faucet drips constantly"),
            ("change the text to say the sink is clogged", "issue", "The sink is clogged"),
            ("please update it to say the disposal is jammed", "issue", "The disposal is jammed"),
            ("it's not the sink, it's the dishwasher", "issue", "Dishwasher"),
            ("rewrite the problem as water under the sink", "issue", "Water under the sink")]
CORR_NO = ["the kitchen light is also flickering", "yes you can come in", "is the bathroom included too?", "thanks",
           "it started last night"]


@pytest.mark.parametrize("msg,fld,value", CORR_YES)
def test_correction_paraphrases(msg, fld, value):
    u = understand_rules(msg, REPAIR, "entry")
    got = {c.field: c.value for c in u.corrections}
    assert u.has(DialogueAct.CORRECT_INFORMATION) and fld in got and value.lower() in got[fld].lower(), got


@pytest.mark.parametrize("msg", CORR_NO)
def test_correction_near_misses(msg):
    assert not understand_rules(msg, REPAIR, "entry").corrections


@pytest.mark.parametrize("msg,expect", [("the description should be: fan makes a loud rattling noise",
                                         "Fan makes a loud rattling noise"),
                                        ("change the text to say the fan rattles", "The fan rattles"),
                                        ("rewrite the issue as fan is rattling", "Fan is rattling")])
def test_rewritten_description_replaces_without_the_prefix(client, msg, expect):
    s = f"rw-{abs(hash(msg))}"
    chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert fields(r)["issue"] == expect and "should" not in fields(r)["issue"].lower()
    assert issue_rewrite(msg) == expect


# ---- 3. side questions while a card is open --------------------------------------------------------------------

SIDE_Q = ["who sees this?", "what does Send do?", "will it cost me anything?", "has anyone fixed this before?",
          "is this marked urgent?", "do you need my name?", "what's the gate code?", "did this happen before?",
          "is there a record of this?"]
SIDE_NO = ["the bathroom", "yes you can come in", "it's also leaking under the sink", "thanks"]


@pytest.mark.parametrize("msg", SIDE_Q)
def test_side_question_paraphrases(msg):
    u = understand_rules(msg, REPAIR, "entry")
    assert u.has(DialogueAct.ASK_QUESTION) and not u.has(DialogueAct.CANCEL) and not u.corrections


@pytest.mark.parametrize("msg", SIDE_NO)
def test_side_question_near_misses(msg):
    assert not understand_rules(msg, REPAIR, "entry").has(DialogueAct.ASK_QUESTION)


@pytest.mark.parametrize("msg", ["who sees this?", "will it cost me anything?", "has anyone fixed this before?",
                                 "is this marked urgent?"])
def test_side_question_keeps_the_card_unchanged(client, msg):
    s = f"q-{abs(hash(msg))}"
    first = chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert r["action"]["kind"] == "maintenance_request" and fields(r) == fields(first) and records(s) == []
    assert "Got it" not in r["reply"]


HISTORY_YES = ["Has anyone fixed this before?", "did this happen before?", "is there a record of this?",
               "have I reported this before", "was it repaired before", "how many times has this broken",
               "has maintenance ever looked at the AC before", "any history on this?"]
HISTORY_NO = ["it worked before", "I fixed it before by resetting", "before you send it, add the dog",
              "has anyone seen my package?", "did someone fix it yet?"]


@pytest.mark.parametrize("msg", HISTORY_YES)
def test_history_question_paraphrases(msg):
    assert asks_history(msg) and understand_rules(msg, REPAIR, "entry").question_topic == "history"


@pytest.mark.parametrize("msg", HISTORY_NO)
def test_history_question_near_misses(msg):
    assert not asks_history(msg)


def test_history_answer_uses_only_the_residents_own_record(client):
    chat(client, "My AC is broken.", "hist1", persona="R001")
    r = chat(client, "Has anyone fixed this before?", "hist1", persona="R001")
    assert "I002" in r["reply"] and "I008" in r["reply"] and "I007" not in r["reply"]  # dog-park gate: not the AC
    assert "SECRET-TRANSCRIPT" not in r["reply"] and "555-0199" not in r["reply"]
    assert r["action"]["kind"] == "maintenance_request"
    none = chat(client, "My AC is broken.", "hist2", persona="R003")
    assert none["action"]["kind"] == "maintenance_request"
    r2 = chat(client, "Has anyone fixed this before?", "hist2", persona="R003")
    assert "don't see an earlier repair" in r2["reply"]
    g = chat(client, "has this happened before?", "hist3", persona="")
    assert "I002" not in g["reply"] and "I008" not in g["reply"]


# ---- 4. cancel / switch topic ---------------------------------------------------------------------------------

CANCEL_YES = ["scrap that, I dont need it anymore", "forget it", "never mind, don't send it", "cancel the request",
              "I don't need the repair anymore", "drop it", "don't bother, it's fixed now", "nah leave it",
              "call it off", "let's not", "hold off on that", "the fan started working again"]
CANCEL_NO = ["don't cancel it", "never mind the location, it's the kitchen", "don't forget the dog is inside",
             "can I cancel my lease?", "no need to call first, you can enter", "it's not urgent",
             "just leave it by the door"]


@pytest.mark.parametrize("msg", CANCEL_YES)
def test_cancel_paraphrases(msg):
    assert cancels(msg) and understand_rules(msg, REPAIR, "entry").has(DialogueAct.CANCEL)


@pytest.mark.parametrize("msg", CANCEL_NO)
def test_cancel_near_misses(msg):
    assert not understand_rules(msg, REPAIR, "entry").has(DialogueAct.CANCEL)


@pytest.mark.parametrize("msg", ["scrap that, I dont need it anymore", "call it off", "drop it"])
def test_cancel_paraphrase_declines_without_saving(client, msg):
    s = f"c-{abs(hash(msg))}"
    chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert r["action"] is None and "haven't sent" in r["reply"] and records(s) == []
    back = chat(client, "undo", s)
    assert back["action"]["kind"] == "maintenance_request" and "fan" in fields(back)["issue"].lower()


@pytest.mark.parametrize("msg", ["forget it, what are the pool hours?", "never mind. who sees these requests?",
                                 "nvm, do you have a gym?"])
def test_cancel_word_then_new_question_keeps_the_card(client, msg):
    s = f"sw-{abs(hash(msg))}"
    first = chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert r["action"]["kind"] == "maintenance_request" and fields(r) == fields(first)
    assert "hasn't been sent" in r["reply"] and records(s) == []


def test_cancel_request_question_is_still_a_cancel(client):
    chat(client, "the bathroom fan is buzzing", "cq")
    r = chat(client, "Can you cancel that request?", "cq")
    assert r["action"] is None and "haven't sent" in r["reply"]


# ---- 5. resume a declined card ----------------------------------------------------------------------------------

RESUME_YES = ["oops I hit dont send by accident, I want it back", "undo", "I didn't mean to cancel that",
              "that was a mistake, I still want it", "bring my request back", "I pressed the wrong button",
              "restore it please", "changed my mind, send it after all", "I tapped cancel by mistake"]
RESUME_NO = ["don't bring it back", "my AC is back to blowing warm air", "I'll be back later", "the leak came back",
             "go back to sleep", "I didn't mean the kitchen, I meant the bathroom"]
DECLINED = {**REPAIR, "declined": True}


@pytest.mark.parametrize("msg", RESUME_YES)
def test_resume_paraphrases(msg):
    assert resumes(msg) and understand_rules(msg, DECLINED, None).has(DialogueAct.RESUME_TASK)


@pytest.mark.parametrize("msg", RESUME_NO)
def test_resume_near_misses(msg):
    assert not understand_rules(msg, DECLINED, None).has(DialogueAct.RESUME_TASK)


@pytest.mark.parametrize("msg", ["oops I hit dont send by accident, I want it back", "that was a mistake, I still want "
                                 "it", "I tapped cancel by mistake"])
def test_resume_brings_back_the_same_card_once(client, msg):
    s = f"r-{abs(hash(msg))}"
    first = chat(client, "the bathroom fan is buzzing", s)
    chat(client, "don't send it", s)
    r = chat(client, msg, s)
    assert r["action"]["kind"] == "maintenance_request" and fields(r) == fields(first) and records(s) == []


# ---- 6. status checks ----------------------------------------------------------------------------------------

STATUS_YES = ["any update on my request?", "what's happening with my repair?", "has anyone looked at my ticket yet",
              "where are we on the dishwasher request", "check on my work order please", "is anyone working on it?",
              "did my request go through", "is my repair scheduled yet", "have you heard back", "status of my request"]
STATUS_NO = ["the status light on my router is blinking", "update: the leak is worse now",
             "I want to update my phone number", "has anyone fixed this before?",
             "my dishwasher is making a grinding noise"]


@pytest.mark.parametrize("msg", STATUS_YES)
def test_status_paraphrases(msg):
    assert checks_status(msg) and understand_rules(msg, None, None).has(DialogueAct.CHECK_STATUS)


@pytest.mark.parametrize("msg", STATUS_NO)
def test_status_near_misses(msg):
    assert not understand_rules(msg, None, None).has(DialogueAct.CHECK_STATUS)


@pytest.mark.parametrize("msg", ["has anyone looked at my ticket yet", "where are we on my repair",
                                 "check on my work order please"])
def test_status_paraphrase_lists_open_items(client, msg):
    r = chat(client, msg, f"st-{abs(hash(msg))}", persona="R001")
    assert any(i["reference"] == "I008" for i in r["status_items"]) and r["records_created"] == []


# ---- 7. frustration with the chat ------------------------------------------------------------------------------

FRUST_YES = ["this is going nowhere", "you're not listening", "this is ridiculous", "what a waste of time",
             "we're going in circles", "I'm sick of this", "I've had enough", "why is this so hard",
             "do you even understand me"]
FRUST_NO = ["my manager at work is annoying", "I'm not upset, just asking", "the dog next door barks a lot",
            "this is not urgent", "is it hard to set up autopay?", "the leak is happening for the third time"]


@pytest.mark.parametrize("msg", FRUST_YES)
def test_frustration_paraphrases(msg):
    assert frustration(msg) == "assistant"
    assert understand_rules(msg, REPAIR, "entry").frustration_target == "assistant"


@pytest.mark.parametrize("msg", FRUST_NO)
def test_frustration_near_misses(msg):
    assert frustration(msg) != "assistant"


@pytest.mark.parametrize("msg", ["this is going nowhere", "what a waste of time", "do you even understand me"])
def test_frustration_gets_one_apology_and_the_card_stays(client, msg):
    s = f"f-{abs(hash(msg))}"
    first = chat(client, "the bathroom fan is buzzing", s)
    r = chat(client, msg, s)
    assert "sorry" in r["reply"].lower() and r["action"]["kind"] == "maintenance_request"
    assert fields(r) == fields(first) and records(s) == []


# ---- 8. two issues in one message ------------------------------------------------------------------------------

TWO_YES = ["the kitchen faucet is leaking and the bathroom light keeps flickering",
           "my toilet keeps running, plus the oven won't heat up",
           "the dishwasher won't drain and also the bedroom window lock is broken",
           "two things: the fridge is warm and the bathroom fan is loud",
           "the garbage disposal is jammed; the hallway light is out",
           "my AC is broken, oh and the dryer won't start",
           "the oven won't turn on. Also the bathroom door is stuck",
           "the shower is dripping as well as the kitchen sink is clogged"]
TWO_NO = ["the kitchen faucet is leaking and dripping everywhere", "my AC is broken, the one in the bedroom",
          "the bathroom fan is loud and it rattles", "water is leaking from the ceiling and dripping onto the floor",
          "the sink is clogged and it smells"]


@pytest.mark.parametrize("msg", TWO_YES)
def test_two_issue_paraphrases(msg):
    assert len(understand_rules(msg, None, None).entities.issues) == 2


@pytest.mark.parametrize("msg", TWO_NO)
def test_two_issue_near_misses(msg):
    assert len(understand_rules(msg, None, None).entities.issues) < 2


def test_two_issues_become_two_named_requests_never_merged(client):
    s = "two1"
    r = chat(client, "the kitchen faucet is leaking and the bathroom light keeps flickering", s)
    assert fields(r)["issue"] == "The kitchen faucet is leaking" and "light" not in fields(r)["issue"]
    assert "bathroom light keeps flickering" in r["action"]["note"]  # the second one is visible and named
    chat(client, "yes you can come in", s)
    sent1 = press_send(client, s, "maintenance_request")
    assert sent1["ok"] and "bathroom light" in sent1["message"]
    nxt = chat(client, "yes", s)
    assert fields(nxt)["issue"] == "The bathroom light keeps flickering" and fields(nxt)["location"] == "Bathroom"
    assert "faucet" not in fields(nxt)["issue"]
    sent2 = press_send(client, s, "maintenance_request")
    assert sent2["ok"] and sent2["record"]["id"] != sent1["record"]["id"]
    again = press_send(client, s, "maintenance_request")  # a repeated Send: nothing more is written
    assert not again["ok"]
    chat(client, "send it", s)
    assert sorted(r_["title"] for r_ in records(s)) == ["The bathroom light keeps flickering",
                                                        "The kitchen faucet is leaking"]


def test_the_same_request_is_never_saved_twice(client):
    s = "dup1"
    for _ in range(2):
        chat(client, "the bathroom fan is buzzing", s)
        chat(client, "yes you can come in", s)
        res = press_send(client, s, "maintenance_request")
    assert res["ok"] and res["error_code"] == "ALREADY_SAVED" and len(records(s)) == 1


# ---- 9. tour date vs move-in -----------------------------------------------------------------------------------

TOUR_DATE = [("Could we do December 14th instead?", TOUR), ("how about Dec 6?", TOUR),
             ("can the tour be on Nov 20?", TOUR), ("I'd like to visit on January 3", None),
             ("let's do Dec 10 for the visit", None), ("can I come see it on dec 2", None),
             ("we're moving Dec 1 but want to tour on Nov 20", None), ("make it December 9 instead", TOUR),
             ("actually December 12 works better", TOUR)]
MOVE_DATE = [("we're moving January 15", TOUR), ("move-in would be Feb 1", TOUR), ("I need a place by March 1", TOUR),
             ("lease start March 3", None), ("we plan to move in on Dec 1", None), ("moving dec 20", TOUR),
             ("I'm moving on April 2, any day works for the tour", TOUR), ("we need to move by May 5", None)]


@pytest.mark.parametrize("msg,card", TOUR_DATE)
def test_a_tour_date_is_never_the_move_in(msg, card):
    tour, move = dates(msg, card is not None, None, card)
    assert tour and (move is None or move.lower() != tour.lower()), (tour, move)


@pytest.mark.parametrize("msg,card", MOVE_DATE)
def test_a_move_in_date_is_never_the_tour(msg, card):
    tour, move = dates(msg, card is not None, None, card)
    assert move and tour is None, (tour, move)


@pytest.mark.parametrize("msg", ["the tour is fine", "not dec 1", "any day works", "weekends are best"])
def test_dates_near_misses(msg):
    assert dates(msg, True, None, TOUR)[1] is None


def test_tour_date_change_on_a_ready_card_leaves_move_in_alone(client):
    s = "td1"
    for m in ("I would like a tour of Heron Lake", "saturday", "morning"):
        r = chat(client, m, s, persona="P-RELOCATE-AA")
    before = fields(r)["move_in"]
    r = chat(client, "Could we do December 14th instead?", s, persona="P-RELOCATE-AA")
    assert fields(r)["days"] == "December 14th" and fields(r)["move_in"] == before


# ---- 10. budget ------------------------------------------------------------------------------------------------

BUDGET_YES = [("I can spend about 1500 a month", "Around 1,500 a month"), ("1.6k max", "Up to 1,600"),
              ("keep it under 1400", "Up to 1,400"), ("my budget is 1,800", "Up to 1,800"),
              ("no more than $1500/mo", "Up to $1,500 a month"), ("looking to pay around 1300", "Around 1,300"),
              ("up to 2000 a month", "Up to 2,000 a month"), ("I can afford 1450", "Up to 1,450")]
BUDGET_NO = ["is it $1,600?", "my unit number is 1204", "I make $3,000 a month", "the special is $500 off",
             "how much is the 2 bed", "the deposit is 1500?"]


@pytest.mark.parametrize("msg,value", BUDGET_YES)
def test_budget_paraphrases(msg, value):
    assert budget(msg) == value


@pytest.mark.parametrize("msg", BUDGET_NO)
def test_budget_near_misses(msg):
    assert budget(msg) is None


def test_paraphrased_budget_lands_on_the_tour_card(client):
    chat(client, "I want to tour Heron Lake Apartments", "b1", persona="P-BROWSE-FL")
    r = chat(client, "1.6k max", "b1", persona="P-BROWSE-FL")
    assert fields(r)["budget"] == "Up to 1,600" and r["action"]["kind"] == "tour_request"


# ---- the worked example (brief), end to end through the API -----------------------------------------------------


@pytest.mark.parametrize("persona", ["R001", "R003"])
def test_worked_example_ac_bedroom_history_manager(client, persona):
    s = f"we-{persona}"
    r1 = chat(client, "My AC is broken.", s, persona)
    assert r1["action"]["kind"] == "maintenance_request" and "AC" in fields(r1)["issue"]
    r2 = chat(client, "Actually, it is the bedroom AC.", s, persona)
    assert fields(r2)["location"] == "Bedroom" and fields(r2)["issue"] == fields(r1)["issue"]  # updated, not restarted
    assert "updated the room to Bedroom" in r2["reply"] and "I'd be glad" not in r2["reply"]
    r3 = chat(client, "Has anyone fixed this before?", s, persona)
    assert fields(r3) == fields(r2)  # draft intact
    assert ("I002" in r3["reply"]) if persona == "R001" else ("don't see an earlier repair" in r3["reply"])
    r4 = chat(client, "I want a manager.", s, persona)
    assert r4["action"]["kind"] == "staff_handoff" and "Bedroom" in fields(r4)["earlier"]
    assert "AC" in fields(r4)["earlier"] and "management" in fields(r4)["topic"]
    assert records(s) == []  # nothing saved yet
    r5 = chat(client, "yes", s, persona)
    assert r5["records_created"] == [] and records(s) == []  # a bare yes never saves
    r6 = chat(client, "send it", s, persona)  # explicit confirmation
    assert len(r6["records_created"]) == 1 and len(records(s)) == 1
    chat(client, "send it", s, persona)
    assert len([x for x in records(s) if x["kind"] == "staff_handoff"]) == 1  # exactly one record
    back = get_state().store.get_draft(s, persona)
    assert back and back["kind"] == "maintenance_request" and back["fields"]["location"]["value"] == "Bedroom"
