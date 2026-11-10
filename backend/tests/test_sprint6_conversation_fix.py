"""Sprint 6 fix round: mechanisms for the failures independent simulators found on unseen wording.

Each family has >= 8 phrasings and >= 4 near misses written from the behaviour (not from the reported sentence), plus
API replays. Offline (mock provider). Fixture residents (tests/conftest.py): R001 (AC history), R003 (none).
"""

import pytest

from app.intake import is_explicit_send, is_noise_complaint, split_issues, states_repeat
from app.understanding import (
    accepts_offer,
    asks_history,
    asks_saved,
    asks_split,
    budget_range,
    checks_status,
    complains_about_staff,
    date_target,
    field_edits,
    frustration,
    holds,
    partial_cancel,
    requests_human,
    understand_rules,
)
from tests.test_sprint6_conversation import chat, fields, press_send, records

CARD = {"kind": "maintenance_request",
        "fields": {"issue": {"value": "My dishwasher is leaking all over the kitchen floor"},
                   "location": {"value": "Kitchen"},
                   "entry": {"value": "Yes, maintenance may enter if I'm not home"},
                   "contact": {"value": "Prefers text"}, "entry_window": {"value": "mornings (8-11 AM)"}}}
FIRST = "Contact me first; only enter when I'm home"
MAY = "Yes, maintenance may enter if I'm not home"


def edits(msg, card=CARD, kind="maintenance_request"):
    return {c.field: c.value for c in field_edits(msg, card, kind)}


# ---- 1. field-targeted corrections: the named (or implied) field, the NEW value ("X not Y" takes X) -------------

EDIT_YES = [
    ("actually a phone call is better than email", "contact", "call"),
    ("email is better than a text", "contact", "email"),
    ("contact preference: email", "contact", "email"),
    ("and actually call me instead of texting", "contact", "call"),
    ("ring me, not the portal", "contact", "call"),
    ("i'd prefer email for this one", "contact", "email"),
    ("rather they knock first, i work from home", "entry", FIRST),
    ("wait no, they should call me first, i have a dog", "entry", FIRST),
    ("no. they can NOT just come in", "entry", FIRST),
    ("perdón, mejor que me llamen antes de entrar", "entry", FIRST),
    ("can they come after 6pm not 5", "entry_window", "After 6pm"),
    ("oh visits better after 6pm not 5", "entry_window", "After 6pm"),
    ("also evenings dont work anymore, mornings only", "entry_window", "Mornings only"),
    ("change best time for visits to evenings after 6", "entry_window", "Evenings after 6"),
    ("its the hallway inside my apt not common area", "location", "Hallway"),
    ("where: bedroom", "location", "Bedroom"),
    ("let me rephrase: the pipe under the kitchen sink is dripping", "issue",
     "The pipe under the kitchen sink is dripping"),
    ("correction: it drips mostly at night", "issue", "It drips mostly at night"),
    ("update the problem to say: slow drip under the sink", "issue", "Slow drip under the sink"),
    ("no the what's wrong part is wrong. change it to: kitchen sink leaking under the cabinet", "issue",
     "Kitchen sink leaking under the cabinet"),
    ("wait actually its under the sink not the dishwasher itself", "issue",
     "Leaking under the sink, not the dishwasher itself"),
]
EDIT_NO = ["is it ok if they text me?", "when will they call me?", "the leak is getting worse",
           "what time do they usually come?", "thanks", "my phone is broken", "how do i call the office?",
           "can you call it a night", "nobody answered my 2 emails", "the kitchen light is also out",
           "they can come in", "will someone call me?"]


@pytest.mark.parametrize("msg,field,value", EDIT_YES)
def test_field_edit_paraphrases(msg, field, value):
    got = edits(msg)
    assert got.get(field) == value, got


def test_field_edit_keeps_two_fields_in_one_message():
    assert edits("contact me first. and CALL me, dont email, i never check email") == {"entry": FIRST,
                                                                                       "contact": "call"}


@pytest.mark.parametrize("msg", EDIT_NO)
def test_field_edit_near_misses(msg):
    assert edits(msg) == {}


@pytest.mark.parametrize("msg,key,value", [
    ("actually a phone call is better than email", "contact", "Prefers call"),
    ("rather they knock first, i work from home", "entry", FIRST),
    ("let me rephrase: the pipe under the sink is dripping", "issue", "The pipe under the sink is dripping"),
    ("can they come after 6pm not 5", "entry_window", "After 6pm"),
    ("correction: it drips mostly at night", "issue", "It drips mostly at night"),
])
def test_correction_replaces_the_field_and_says_so(client, msg, key, value):
    s = f"fe-{abs(hash(msg))}"
    chat(client, "my kitchen sink is leaking", s, "R001")
    chat(client, "yes you can come in", s, "R001")
    r = chat(client, msg, s, "R001")
    f = fields(r)
    assert f[key] == value and "Also:" not in f["issue"] and "Updated:" in r["reply"]
    assert not records(s)


def test_correction_keeps_a_visit_note_said_with_it(client):
    s = "fe-dog"
    chat(client, "my kitchen sink is leaking", s, "R001")
    chat(client, "yes you can come in", s, "R001")
    r = chat(client, "wait no, they should call me first, i have a dog", s, "R001")
    assert fields(r)["entry"] == FIRST and "dog" in fields(r)["notes"].lower()


@pytest.mark.parametrize("msg,lang", [("actually call me before entering, not just come in", "en"),
                                      ("perdón, mejor que me llamen antes de entrar", "es")])
def test_correction_after_send_is_a_change_note_citing_the_reference(client, msg, lang):
    s = f"fe-sent-{lang}"
    chat(client, "my kitchen sink is leaking" if lang == "en" else "el fregadero de la cocina gotea", s, "R001")
    chat(client, "yes you can come in" if lang == "en" else "sí, pueden entrar", s, "R001")
    ref = press_send(client, s, "maintenance_request", "R001")["record"]["id"]
    r = chat(client, msg, s, "R001")
    assert r["action"]["kind"] == "staff_handoff" and ref in r["reply"]
    assert ("Entry permission" if lang == "en" else "Permiso de entrada") in r["reply"]
    assert len(records(s)) == 1  # nothing new saved until the note is sent


# ---- 2. two issues, any coordination; an explicit later split ---------------------------------------------------

SPLIT_YES = ["kitchen faucet drips constantly; also the smoke detector in the hallway keeps chirping",
             "my bedroom window wont lock and separately the dryer takes 3 cycles to dry anything",
             "two things: 1) shower drain is slow 2) the oven light is out",
             "el inodoro no deja de correr, y aparte la puerta del balcón no cierra bien",
             "my oven light is out. Separately, the garbage disposal is jammed",
             "the bathroom fan is loud; plus the closet door is off its track",
             "no hot water for 3 days and my front door deadbolt is jammed",
             "the bedroom window wont lock and also the hallway smoke detector keeps chirping"]
SPLIT_NO = ["the sink is leaking and it is getting worse", "my fan is loud and it rattles",
            "the kitchen faucet drips and the kitchen floor is wet", "the dishwasher won't drain; it smells too"]


@pytest.mark.parametrize("msg", SPLIT_YES)
def test_two_issue_coordinations_split(msg):
    assert len(split_issues(msg)) == 2


@pytest.mark.parametrize("msg", SPLIT_NO)
def test_one_issue_is_not_split(msg):
    assert split_issues(msg) == [msg]


ASK_SPLIT_YES = ["those are 2 different things btw", "can you split those into two requests?",
                 "make the oven light its own request", "the smoke detector is a separate thing, can that be its own "
                 "request", "son dos cosas distintas", "they're two separate issues", "file repair requests for both",
                 "please separate them"]
ASK_SPLIT_NO = ["the oven light is out", "it's the same problem as before", "separate the trash please",
                "two weeks now"]


@pytest.mark.parametrize("msg", ASK_SPLIT_YES)
def test_split_request_paraphrases(msg):
    assert asks_split(msg)[0]


@pytest.mark.parametrize("msg", ASK_SPLIT_NO)
def test_split_request_near_misses(msg):
    assert not asks_split(msg)[0]


def test_split_request_splits_a_merged_card(client):
    s = "sp-merged"
    chat(client, "the bathroom fan is buzzing", s, "R003")
    chat(client, "bathroom", s, "R003")
    chat(client, "also the oven light is out", s, "R003")  # appended as more detail
    r = chat(client, "make the oven light its own request", s, "R003")
    f = fields(r)
    assert "oven" not in f["issue"].lower() and "fan" in f["issue"].lower() and "oven light" in r["reply"].lower()


def test_split_request_on_an_already_split_card_changes_nothing(client):
    s = "sp-already"
    r = chat(client, "kitchen faucet drips constantly; also the smoke detector keeps chirping", s, "R003")
    before = fields(r)
    r = chat(client, "those are 2 different things", s, "R003")
    assert fields(r) == before and "smoke detector" in r["reply"].lower()


# ---- 3. partial cancel, a cancel word inside a correction, hold -------------------------------------------------

DROP_YES = [("never mind the smoke detector, only the faucet", "smoke detector"),
            ("forget about the oven light, i fixed it", "oven light"), ("drop the dryer part", "dryer"),
            ("nvm the fan, just the toilet", "fan"), ("skip the window one", "window"),
            ("cancel the smoke detector part", "smoke detector"), ("leave out the dishwasher", "dishwasher"),
            ("don't need the fridge one anymore", "fridge")]
DROP_NO = ["never mind", "forget it", "cancel the request", "never mind the location, it's the kitchen"]


@pytest.mark.parametrize("msg,thing", DROP_YES)
def test_partial_cancel_names_one_problem(msg, thing):
    assert partial_cancel(msg)[0] == thing


@pytest.mark.parametrize("msg", DROP_NO)
def test_whole_card_cancel_names_no_problem(msg):
    assert partial_cancel(msg)[0] is None


def test_partial_cancel_drops_only_that_problem(client):
    s = "pc-1"
    chat(client, "the bathroom faucet drips; also the smoke detector chirps", s, "R003")
    r = chat(client, "never mind the smoke detector, only the faucet", s, "R003")
    assert r["action"]["kind"] == "maintenance_request" and "faucet" in fields(r)["issue"].lower()
    assert "smoke" not in r["reply"].split(". This")[-1].lower() or "taken" in r["reply"]
    r = press_send(client, s, "maintenance_request", "R003") if not r["action"]["missing"] else r
    assert all("smoke" not in str(x).lower() for x in records(s))


HOLD_YES = ["dont send yet", "don't send it yet", "not yet", "hold on", "wait a sec", "don't submit it just yet",
            "i'll send it later", "todavía no"]
HOLD_NO = ["don't send it", "cancel it", "never mind", "send it"]


@pytest.mark.parametrize("msg", HOLD_YES)
def test_hold_paraphrases(msg):
    assert holds(msg)


@pytest.mark.parametrize("msg", HOLD_NO)
def test_hold_near_misses(msg):
    assert not holds(msg)


def test_hold_keeps_the_card_unsent(client):
    s = "hold-1"
    chat(client, "my kitchen sink is leaking", s, "R003")
    chat(client, "yes you can come in", s, "R003")
    r = chat(client, "dont send yet", s, "R003")
    assert r["action"]["kind"] == "maintenance_request" and not records(s) and "won't send" in r["reply"]


def test_cancel_word_inside_a_correction_is_a_correction(client):
    s = "nvm-switch"
    chat(client, "i'd like to tour sandpiper pointe next week, mornings", s, None)
    r = chat(client, "nvm switch it to heron lake. actually no, fernhill", s, None)
    assert r["action"]["kind"] == "tour_request" and fields(r)["area"].startswith("Fernhill")


def test_never_mind_that_for_a_sec_answers_and_keeps_the_card(client):
    s = "nvm-sec"
    chat(client, "my kitchen sink is leaking", s, "R003")
    r = chat(client, "never mind that for a sec, what are the pool hours?", s, "R003")
    assert r["action"] and r["action"]["kind"] == "maintenance_request" and not records(s)


# ---- 4. accepting the assistant's own offer ---------------------------------------------------------------------

OFFER_YES = ["ok sure", "yeah send them my questions", "ok yes send them that", "yes please", "sure, go ahead",
             "yeah do that", "sounds good", "yes please do that", "sí, por favor"]
OFFER_NO = ["no thanks", "ok but what about parking?", "maybe later", "how much is it?"]


@pytest.mark.parametrize("msg", OFFER_YES)
def test_offer_acceptance_paraphrases(msg):
    assert accepts_offer(msg)


@pytest.mark.parametrize("msg", OFFER_NO)
def test_offer_acceptance_near_misses(msg):
    assert not accepts_offer(msg)


def test_ok_sure_after_a_tour_offer_opens_the_tour_card(client):
    s = "offer-tour"
    r = chat(client, "do your apartments come with parking?", s, None)
    assert "Would you like to request a tour?" in r["reply"]
    r = chat(client, "ok sure", s, None)
    assert r["action"] and r["action"]["kind"] == "tour_request" and not records(s)


def test_yes_send_them_my_questions_opens_the_leasing_note(client):
    s = "offer-note"
    chat(client, "how much is a 2 bedroom at sandpiper pointe?", s, None)
    r = chat(client, "is there an application fee? and do you allow cats", s, None)
    assert "send them your question" in r["reply"]
    r = chat(client, "yeah send them my questions", s, None)
    assert r["action"] and r["action"]["kind"] == "staff_handoff" and not records(s)  # Send still needed


# ---- 5. dates and budgets ---------------------------------------------------------------------------------------

BOTH = {"fields": {"days": {"value": "Thursday"}, "move_in": {"value": "next month"}}}
DATE_CASES = [("push it to the 20th", BOTH, "ask"), ("change it to the 18th", BOTH, "ask"),
              ("can we do the 20th instead", BOTH, "ask"), ("move the tour to the 20th not thursday", BOTH, "days"),
              ("push my move in date to the 20th", BOTH, "move_in"),
              ("move in is dec 15 btw. and can we do the 20th instead", BOTH, "days"),
              ("push it to the 20th", {"fields": {"days": {"value": "Thursday"}}}, "days"),
              ("push it to the 20th", {"fields": {"move_in": {"value": "Dec 1"}}}, "move_in")]


@pytest.mark.parametrize("msg,card,field", DATE_CASES)
def test_month_less_date_goes_to_one_field_or_asks(msg, card, field):
    assert date_target(msg, card)[1] == field


@pytest.mark.parametrize("msg", ["this is the 3rd time", "i live on the 2nd floor", "my unit is 4th from the left",
                                 "thanks"])
def test_month_less_date_near_misses(msg):
    assert date_target(msg, BOTH) == (None, None)


RANGES = [("1200 to 1400", "$1,200 to $1,400"), ("somewhere in the 1.2-1.4k range", "$1,200 to $1,400"),
          ("between $1,200 and $1,500", "$1,200 to $1,500"), ("1300-1600 a month", "$1,300 to $1,600"),
          ("$1,100 - $1,350", "$1,100 to $1,350"), ("1.5k to 1.8k", "$1,500 to $1,800"),
          ("900 to 1100 is my range", "$900 to $1,100"), ("2000-2400", "$2,000 to $2,400")]


@pytest.mark.parametrize("msg,value", RANGES)
def test_budget_ranges_keep_the_range(msg, value):
    assert budget_range(msg) == value


@pytest.mark.parametrize("msg", ["I make 3000 to 4000 a month", "units 1200 to 1400 sq ft", "1400", "move in 12/20"])
def test_budget_range_near_misses(msg):
    assert budget_range(msg) is None


def test_ambiguous_date_asks_then_applies(client):
    s = "date-ask"
    chat(client, "book me a tour at fernhill apartments for tuesday at 3pm, moving in next month", s, None)
    r = chat(client, "can we push it to the 20th?", s, None)
    assert "tour or for the move-in" in r["reply"]
    r = chat(client, "the tour", s, None)
    assert fields(r)["days"] == "The 20th" and fields(r)["move_in"] != "The 20th"


def test_tour_there_uses_the_community_just_mentioned(client):
    s = "there"
    chat(client, "your website said rent at heron lake 2br is $1350, right?", s, "P-RELOCATE-AA")
    r = chat(client, "ok then set up a tour there for sunday around noon", s, "P-RELOCATE-AA")
    assert fields(r)["area"].startswith("Heron Lake")


# ---- 6. handoff by frame ----------------------------------------------------------------------------------------

HANDOFF_YES = ["I want to speak to whoever runs this place", "can a human take over", "your team needs to call me",
               "i want a callback from the leasing office", "can someone from the office reach out to me",
               "i want an explanation from a manager", "this bot isnt helping, connect me with someone",
               "connect me w someone in the leasing office", "I do want someone from leasing to reach out",
               "i want a leasing rep to get in touch", "can a leasing manager just call me instead",
               "speak to whoever handles leases", "is anyone from your team available to talk?",
               "could a real human ring me about my lease renewal", "have someone from the office call me",
               "quiero hablar con una persona", "i asked for a HUMAN", "send the leasing team a note"]
HANDOFF_NO = ["my manager at work is annoying", "can you call it a night", "I need someone to fix the sink",
              "can a person come in while I'm out?", "someone left trash in the hallway",
              "have someone call me first before they come in", "the office is closed today",
              "can someone fix the dishwasher", "I talked to someone yesterday about the leak",
              "I don't want to talk to anyone, just fix it"]


@pytest.mark.parametrize("msg", HANDOFF_YES)
def test_handoff_frame_paraphrases(msg):
    assert requests_human(msg)


@pytest.mark.parametrize("msg", HANDOFF_NO)
def test_handoff_frame_near_misses(msg):
    assert not requests_human(msg)


def test_prospect_asking_for_a_call_gets_a_note_not_a_contact_preference(client):
    s = "ho-prospect"
    chat(client, "i'd like to tour sandpiper pointe next week", s, None)
    r = chat(client, "can a leasing manager just call me instead", s, None)
    assert r["action"]["kind"] == "staff_handoff"


# ---- 7/8. what have you saved / history -------------------------------------------------------------------------

SAVED_YES = ["what have you saved so far?", "what have u saved for me", "what's saved now?",
             "did my note actually get saved?", "will anyone contact me about the note?", "did that actually save",
             "can you confirm you have it", "was my complaint saved or not", "are both of those actually saved?",
             "show me what you saved", "recap what you've got on file for me?"]
SAVED_NO = ["save me a spot", "I saved the receipt", "what's the pet policy?", "the toilet keeps running"]


@pytest.mark.parametrize("msg", SAVED_YES)
def test_saved_status_paraphrases(msg):
    assert asks_saved(msg)


@pytest.mark.parametrize("msg", SAVED_NO)
def test_saved_status_near_misses(msg):
    assert not asks_saved(msg)


def test_saved_question_with_a_draft_open_is_honest(client):
    s = "saved-1"
    chat(client, "my kitchen sink is leaking", s, "R003")
    r = chat(client, "what have you saved so far?", s, "R003")
    assert "nothing has been sent" in r["reply"] and r["action"]["kind"] == "maintenance_request"


HIST_YES = ["did someone already look at this before?", "did someone already look at it?",
            "has anyone ever fixed the AC?", "did maintenance already check this?", "has a tech looked at this before",
            "did they fix it last time?", "alguien ya revisó esto?", "have you guys already worked on my fridge?"]
HIST_NO = ["did someone fix it yet?", "has anyone seen my package?", "any update on my request?", "it worked before"]


@pytest.mark.parametrize("msg", HIST_YES)
def test_history_paraphrases(msg):
    assert asks_history(msg)


@pytest.mark.parametrize("msg", HIST_NO)
def test_history_near_misses(msg):
    assert not asks_history(msg)


def test_history_question_keeps_the_card_and_uses_only_own_record(client):
    s = "hist-1"
    chat(client, "the AC in the bedroom is not cooling", s, "R001")
    r = chat(client, "did someone already look at this before?", s, "R001")
    assert r["action"]["kind"] == "maintenance_request" and "I00" in r["reply"]


@pytest.mark.parametrize("msg", ["hay novedades de lo del aire?", "do i even have a heater request open",
                                 "cómo va lo de mi refrigerador?", "any news on the dishwasher thing?"])
def test_status_paraphrases_incl_spanish(msg):
    assert checks_status(msg)


# ---- 9. Spanish -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("msg", ["el aire acondicionado no enfría y hace mucho ruido", "la nevera hace mucho ruido",
                                 "la secadora hace un ruido fuerte", "el ventilador del baño hace ruido"])
def test_spanish_appliance_noise_is_a_repair(msg):
    assert not is_noise_complaint(msg)


@pytest.mark.parametrize("msg", ["los vecinos hacen mucho ruido", "música alta del vecino toda la noche"])
def test_spanish_neighbour_noise_is_still_noise(msg):
    assert is_noise_complaint(msg)


def test_spanish_ac_repair_card(client):
    r = chat(client, "hola, el aire acondicionado no enfría y hace mucho ruido", "es-ac", "R001")
    assert r["action"]["kind"] == "maintenance_request"


@pytest.mark.parametrize("msg", ["envíala", "ok, envíalo", "mándala", "envíelo por favor"])
def test_spanish_explicit_send(msg):
    assert is_explicit_send(msg)


# ---- 10. the note keeps the repair details; no "with the details" claim when there are none ---------------------

def test_note_keeps_repair_details_across_repeated_paraphrases(client):
    s = "note-keep"
    chat(client, "the dishwasher is leaking water onto the kitchen floor", s, "R003")
    for m in ["honestly can i just talk to an actual person about this",
              "is there someone in the office who could take over",
              "i'd rather not deal with a bot, put me through to staff pls"]:
        r = chat(client, m, s, "R003")
    assert "dishwasher" in fields(r).get("earlier", "").lower()


def test_note_confirmation_never_claims_details_it_does_not_have(client):
    s = "note-plain"
    chat(client, "Talk to a person", s, "R003")
    r = press_send(client, s, "staff_handoff", "R003")
    assert r["ok"] and "with the details" not in r["message"]


def test_note_confirmation_with_details_says_so(client):
    s = "note-details"
    chat(client, "my bathroom fan is buzzing", s, "R003")
    chat(client, "I want to talk to a manager", s, "R003")
    r = press_send(client, s, "staff_handoff", "R003")
    assert r["ok"] and "with the details" in r["message"]


# ---- coordinator additions: frustrated repair reports, staff complaints, repeats --------------------------------

@pytest.mark.parametrize("msg", ["this is the FOURTH time my kitchen sink is leaking under the cabinet. i'm so done",
                                 "no hot water for 3 days and my door is jammed. how many times do i have to report",
                                 "this is ridiculous, my toilet is clogged again",
                                 "i've had enough, the heater is broken again"])
def test_frustrated_repair_report_is_about_the_situation(msg):
    assert frustration(msg) != "assistant"


@pytest.mark.parametrize("msg", ["you're not listening", "this bot is useless", "this chat is going nowhere",
                                 "we're going in circles"])
def test_frustration_with_the_chat_stays_assistant(msg):
    assert frustration(msg) == "assistant"


def test_frustrated_first_message_starts_the_repair(client):
    r = chat(client, "this is the FOURTH time my kitchen sink is leaking under the cabinet. i'm so done with this",
             "fr-1", "R001")
    assert r["action"]["kind"] == "maintenance_request"


COMPLAINT_YES = ["the tech was rude to me", "i want to file a formal complaint", "the maintenance guy left a mess",
                 "they missed my Tuesday visit and nobody called", "nobody showed up for the appointment",
                 "i want an explanation from someone", "complaint about your staff",
                 "the worker was unprofessional and yelling"]
COMPLAINT_NO = ["the faucet is rude-ly loud lol", "my dishwasher is broken", "the tech fixed it, thanks",
                "can a tech come tuesday?"]


@pytest.mark.parametrize("msg", COMPLAINT_YES)
def test_staff_complaint_paraphrases(msg):
    assert complains_about_staff(msg)


@pytest.mark.parametrize("msg", COMPLAINT_NO)
def test_staff_complaint_near_misses(msg):
    assert not complains_about_staff(msg)


def test_staff_complaint_is_a_note_not_a_repair(client):
    r = chat(client, "i want to file a formal complaint. the maintenance guy left a mess and was rude to me",
             "cmp-1", "R003")
    assert r["action"]["kind"] == "staff_handoff" and "Which room" not in r["reply"]


REPEAT_YES = ["the toilet keeps running, been reported twice already", "the AC has been broken for 2 weeks",
              "es la tercera vez que se descompone", "you marked my fridge request as done but it is NOT fixed",
              "they closed it without fixing", "this is the 4th time", "it broke again", "same problem again"]
REPEAT_NO = ["i'm not answering that again", "can you say that again?", "the sink is leaking",
             "i'm not repeating myself again"]


@pytest.mark.parametrize("msg", REPEAT_YES)
def test_stated_repeat_paraphrases(msg):
    assert states_repeat(msg)


@pytest.mark.parametrize("msg", REPEAT_NO)
def test_stated_repeat_near_misses(msg):
    assert not states_repeat(msg)


def test_understanding_reports_the_new_fields():
    u = understand_rules("never mind the smoke detector, only the faucet",
                         {"kind": "maintenance_request", "fields": {"issue": {"value": "faucet drips; smoke detector "
                                                                                       "chirps"}}}, "entry")
    assert u.drop_issue == "smoke detector" and u.keep_issue == "faucet" and "cancel" not in [a.value for a in u.acts]
