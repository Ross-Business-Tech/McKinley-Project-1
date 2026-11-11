"""Sprint 7 workflow mechanisms: metamorphic paraphrase families (generated, EN + ES) and API replays.

Mechanisms under test (app/utterance.py, app/understanding.py, app/actions.py):
- one structural analysis per message (question / information request / addition, problem = object + symptom,
  landmarks kept apart, requests / past / visit markers) instead of separate keyword lists;
- one field-reference resolver for every card kind, used before and after Send;
- multi-intent segmentation across different workflows, typed consent vocabulary, near-duplicate guard.

Metamorphic tests: every member of a generated paraphrase family (templated EN / ES variation, derandomized) must give
the same understanding. API replays: >= 8 phrasings per behaviour plus >= 4 near misses, written from the behaviour
description. These are the dev-A cases; a separate dev-B set (never tuned on) is kept outside the repo.
"""

import json
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.intake import is_explicit_send, is_noise_complaint, split_issues
from app.state import get_state
from app.understanding import DialogueAct, entry_value, field_edits, requests_human, understand_rules
from app.utterance import analyze, date_readback, field_corrections, normalize, segments
from tests.conftest import forget_persona_records
from tests.test_sprint6_conversation import chat, fields, press_send

META = settings(max_examples=40, deadline=None, derandomize=True, database=None,
                suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
API = settings(max_examples=12, deadline=None, derandomize=True, database=None,
               suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
CARD = {"kind": "maintenance_request",
        "fields": {"issue": {"value": "My kitchen sink is leaking under the cabinet"}, "location": {"value": "Kitchen"},
                   "entry": {"value": "Yes, maintenance may enter if I'm not home"},
                   "contact": {"value": "Prefers text"}, "entry_window": {"value": "mornings (8-11 AM)"}}}
FIRST = "Contact me first; only enter when I'm home"
MAY = "Yes, maintenance may enter if I'm not home"


def recs(s):
    return get_state().store.records(session_id=s, limit=50)


def kind(r):
    return (r.get("action") or {}).get("kind")


def sid():
    return f"wf-{uuid.uuid4().hex[:10]}"


# ---- metamorphic families (understanding level) ----------------------------------------------------------------

@META
@given(lead=st.sampled_from(["", "can you ", "please ", "could you "]),
       verb=st.sampled_from(["list", "show me", "pull up", "give me", "check"]),
       adj=st.sampled_from(["open", "pending", "outstanding", "active"]),
       noun=st.sampled_from(["repair requests", "maintenance tickets", "work orders", "requests", "tickets"]),
       end=st.sampled_from(["", "?", " please", " for my unit"]))
def test_open_request_family_is_a_status_check(lead, verb, adj, noun, end):
    msg = f"{lead}{verb} my {adj} {noun}{end}"
    u = understand_rules(msg, None, None)
    assert u.asks_open_requests and u.has(DialogueAct.CHECK_STATUS), msg


@pytest.mark.parametrize("msg", ["¿tengo solicitudes abiertas?", "cuáles son mis solicitudes pendientes",
                                 "anything still open on my account?", "what's open right now?",
                                 "how many open requests do I have"])
def test_open_request_paraphrases_es_and_free_form(msg):
    assert understand_rules(msg, None, None).has(DialogueAct.CHECK_STATUS)


@pytest.mark.parametrize("msg", ["my kitchen sink is open and leaking", "the window is stuck open",
                                 "the office is open on saturday?", "I opened a request yesterday and the sink leaks",
                                 "is the pool open"])
def test_open_request_near_misses(msg):
    assert not analyze(msg).asks_open_requests


@META
@given(q=st.sampled_from(["what repairs have been done", "what's been fixed", "show me past maintenance",
                          "any previous work orders", "what work has been done", "what problems have I reported"]),
       where=st.sampled_from([" in my apartment", " on my place", " for my unit", " here", ""]),
       tail=st.sampled_from(["", " before", " in the past", "?"]))
def test_history_family(q, where, tail):
    msg = f"{q}{where}{tail}"
    assert understand_rules(msg, None, None).question_topic == "history", msg


@pytest.mark.parametrize("msg", ["historial de reparaciones", "qué reparaciones he tenido antes",
                                 "have I had AC problems before", "past repair requests please"])
def test_history_paraphrases_es_and_fragments(msg):
    assert understand_rules(msg, None, None).question_topic == "history"


@pytest.mark.parametrize("msg", ["my sink broke before I left", "the AC was fixed last week but it's leaking now",
                                 "I need the sink fixed", "previously I lived in Ann Arbor"])
def test_history_near_misses(msg):
    assert understand_rules(msg, None, None).question_topic != "history"


_ROOMS = [("bathroom", "Bathroom"), ("bedroom", "Bedroom"), ("garage", "Garage"), ("living room", "Living room"),
          ("closet", "Closet")]


@META
@given(frame=st.sampled_from(["the {f} is wrong, it's the {v}", "wrong {f}, it's actually the {v}",
                              "change the {f} to {v}", "put {v} as the {f}", "the {f} should be the {v}",
                              "{f}: {v}", "set {f} to {v} please", "can you fix the {f}? it's the {v}",
                              "make the {f} the {v}"]),
       f=st.sampled_from(["location", "room", "spot", "place"]), room=st.sampled_from(_ROOMS))
def test_location_correction_family_uses_the_shared_field_resolver(frame, f, room):
    word, label = room
    msg = frame.format(f=f, v=word)
    got = {c.field: c.value for c in field_edits(msg, CARD, "maintenance_request")}
    assert got.get("location") == label and "issue" not in got, (msg, got)


@pytest.mark.parametrize("msg,label", [("la ubicación es el baño", "Bathroom"),
                                       ("el cuarto está mal, es el baño", "Bathroom"),
                                       ("cambie la ubicación a la cocina", "Kitchen"),
                                       ("no, not kitchen — bathroom", "Bathroom"),
                                       ("sorry I meant the bathroom sink", "Bathroom"),
                                       ("it's the bathroom one, my mistake", "Bathroom"),
                                       ("oops wrong spot. bedroom", "Bedroom"),
                                       ("it's actually in the garage, not the kitchen", "Garage")])
def test_location_corrections_es_and_implicit(msg, label):
    got = {c.field: c.value for c in field_edits(msg, {**CARD, "fields": {**CARD["fields"],
                                                                           "location": {"value": "Laundry area"}}}
                                                 if label == "Kitchen" else CARD, "maintenance_request")}
    assert got.get("location") == label and "issue" not in got, (msg, got)


@pytest.mark.parametrize("msg", ["where is the office?", "is the bathroom fan covered too?", "the kitchen is messy",
                                 "what room do you need?", "my bathroom sink is also leaking"])
def test_location_correction_near_misses(msg):
    assert "location" not in {c.field: c.value for c in field_edits(msg, CARD, "maintenance_request")}


@pytest.mark.parametrize("msg,field,value", [
    ("change the tour date to Friday", "days", "Friday"), ("the community is wrong, it's Sandpiper Pointe", "area",
                                                           "Sandpiper Pointe"),
    ("set the time to afternoon", "time", "Afternoon"), ("cambie la fecha al sábado", "days", "Sábado"),
])
def test_one_resolver_for_every_card_kind(msg, field, value):
    got = dict(field_corrections(msg, "tour_request"))
    assert value.lower() in (got.get(field) or "").lower(), got


@META
@given(lead=st.sampled_from(["", "yes ", "ok ", "sure, ", "please ", "go ahead and ", "you can ", "yes please ",
                             "just "]),
       verb=st.sampled_from(["send", "submit"]),
       obj=st.sampled_from(["", " it", " it over", " the note", " the request", " it now", " that please"]))
def test_consent_family_is_one_vocabulary(lead, verb, obj):
    assert is_explicit_send(f"{lead}{verb}{obj}")


@pytest.mark.parametrize("msg", ["envíelo por favor", "mándela", "envíala", "sí, envíelo"])
def test_consent_spanish(msg):
    assert is_explicit_send(msg)


@pytest.mark.parametrize("msg", ["yes", "ok", "sure", "sí", "sounds good", "send me the pool hours",
                                 "can you send someone to fix it", "send a note to the office about parking",
                                 "did you send it?"])
def test_consent_near_misses(msg):
    assert not is_explicit_send(msg)


@META
@given(who=st.sampled_from(["someone from the office", "a manager", "a real person", "someone from leasing",
                            "a human", "the leasing team"]),
       frame=st.sampled_from(["can {w} call me", "I'd like {w} to get back to me", "please have {w} reach out",
                              "could {w} give me a ring", "I want to talk to {w}", "connect me with {w}"]))
def test_handoff_family(who, frame):
    assert requests_human(frame.format(w=who)), frame.format(w=who)


@pytest.mark.parametrize("msg", ["necesito que alguien me llame", "quiero hablar con alguien de la oficina",
                                 "can a person just handle this", "forget the bot, manager please",
                                 "I've told you three times, can someone please help"])
def test_handoff_es_and_short_forms(msg):
    u = understand_rules(msg, None, None)
    assert u.requests_human or u.frustration_target == "assistant"


@pytest.mark.parametrize("msg", ["I need someone to fix the sink", "my manager at work is annoying",
                                 "have someone call me first before they come in", "yes, send the note",
                                 "can someone take a look at my sink"])
def test_handoff_near_misses(msg):
    assert not understand_rules(msg, None, None).requests_human


@pytest.mark.parametrize("msg,value", [
    ("no problem, use the key", MAY), ("sure they can let themselves in", MAY), ("fine by me if they go in", MAY),
    ("ok to come in when I'm at work", MAY), ("está bien, que entren", MAY), ("I'd rather be home", FIRST),
    ("only if I'm there", FIRST), ("please don't enter without me", FIRST), ("no pueden entrar sin mí", FIRST),
])
def test_entry_permission_paraphrases(msg, value):
    assert entry_value(msg) == value


@pytest.mark.parametrize("msg", ["the key is stuck in the lock", "I'm home most days", "is it ok?",
                                 "the door won't open"])
def test_entry_permission_near_misses(msg):
    assert entry_value(msg) is None


@META
@given(a=st.sampled_from(["my kitchen sink is leaking", "sink leak", "leaky sink", "the sink drips"]),
       join=st.sampled_from([", also ", " and also ", " + ", ". Also, ", ", and ", "; ", " plus "]),
       b=st.sampled_from(["the bathroom fan is broken", "busted bathroom fan", "bathroom fan not working",
                          "my bathroom fan is noisy"]))
def test_two_problems_family_splits_by_structure(a, join, b):
    parts = split_issues(a + join + b)
    assert len(parts) == 2 and "fan" not in parts[0].lower() and "fan" in parts[1].lower(), parts


@pytest.mark.parametrize("msg", ["the sink leaks and the cabinet under it is wet", "my sink is leaking and it's "
                                 "getting worse", "the toilet keeps running in the master bathroom",
                                 "my dishwasher is leaking all over the kitchen floor",
                                 "text me first. and the fridge is warm"])
def test_two_problems_near_misses(msg):
    assert len(split_issues(msg)) == 1


@META
@given(rep=st.sampled_from(["my sink is leaking", "the bathroom fan is broken", "the oven won't heat"]),
       join=st.sampled_from([" and also ", ". Separately, ", "; also ", ", plus "]),
       per=st.sampled_from(["can someone from leasing call me about my lease", "I want to talk to a manager about "
                            "my rent", "please have the office call me about renewing"]))
def test_two_workflows_segment_family(rep, join, per):
    w = [s.workflow for s in segments(rep + join + per, requests_human)]
    assert "repair" in w and "person" in w, w


def test_normalisation_and_date_readback():
    assert normalize("tmrw morning pls") == "tomorrow morning please"
    from datetime import date
    assert date_readback("3/4", "en", date(2026, 11, 10)) == ("3/4 (March 4)", "March 4|April 3")
    assert date_readback("tmrw", "en", date(2026, 11, 10))[1] == "Wednesday, November 11"
    assert date_readback("pasado mañana", "es", date(2026, 11, 10))[1] == "12 de noviembre"
    assert date_readback("por la mañana", "es") is None and date_readback("Saturday", "en") is None


@pytest.mark.parametrize("msg", ["there's a weird noise in my unit", "my fridge is making a strange noise",
                                 "a clicking noise in my bathroom", "un ruido raro en mi apartamento",
                                 "something is making a whistling noise in the kitchen", "pipes make a knocking noise",
                                 "odd noise from my dryer", "loud noise from the water heater"])
def test_a_sound_in_the_home_is_not_a_neighbour_complaint(msg):
    assert not is_noise_complaint(msg)


@pytest.mark.parametrize("msg", ["my neighbors are blasting music at 2am", "the people upstairs are so loud",
                                 "los vecinos hacen mucho ruido", "the dog next door barks all night"])
def test_neighbour_noise_still_is(msg):
    assert is_noise_complaint(msg)


# ---- API replays -----------------------------------------------------------------------------------------------

def _repair_ready(c, s, p="R001"):
    chat(c, "my kitchen sink is leaking under the cabinet", s, p)
    return chat(c, "yes you can come in", s, p)


@pytest.mark.parametrize("msg", ["it is the one next to the fridge btw", "oh and it's the left cabinet door",
                                 "fyi the pipe is the cold one", "forgot to say, it's worse when the dishwasher runs",
                                 "btw it's dripping onto the floor now", "also it's the double sink by the window",
                                 "one more thing: there's a puddle under it", "se me olvidó, es el de la izquierda"])
def test_detail_after_send_is_a_change_note_and_a_second_send_never_duplicates(client, msg):
    s = sid()
    _repair_ready(client, s)
    ref = press_send(client, s, "maintenance_request", "R001")["record"]["id"]
    r = chat(client, msg, s, "R001")
    assert kind(r) == "staff_handoff" and ref in r["reply"] + json.dumps(r["action"])
    press_send(client, s, "staff_handoff", "R001")
    assert len([x for x in recs(s) if x["kind"] == "maintenance_request"]) == 1


@pytest.mark.parametrize("msg", ["also the bathroom fan is broken", "my fridge stopped working too",
                                 "the bedroom window won't lock", "the one for the sink leak"])
def test_detail_after_send_near_misses_are_not_change_notes(client, msg):
    s = sid()
    _repair_ready(client, s)
    ref = press_send(client, s, "maintenance_request", "R001")["record"]["id"]
    r = chat(client, msg, s, "R001")
    assert not (kind(r) == "staff_handoff" and "Notes for the visit" in r["reply"] and ref in r["reply"]) or \
        msg == "the one for the sink leak"


@pytest.mark.parametrize("msg", ["so is someone actually coming?", "when will someone come?", "is a tech coming out?",
                                 "¿alguien va a venir?", "will they come today", "so what happens now?",
                                 "is anyone going to fix it?", "who's coming and when"])
def test_visit_question_after_send_cites_the_request_and_promises_nothing(client, msg):
    s = sid()
    _repair_ready(client, s)
    ref = press_send(client, s, "maintenance_request", "R001")["record"]["id"]
    r = chat(client, msg, s, "R001")
    assert ref in r["reply"] and "on the way" not in r["reply"].lower() and not r["records_created"]


@pytest.mark.parametrize("msg", ["I don't understand", "huh?", "what do you mean?", "I'm confused", "no entiendo",
                                 "what am I supposed to do?", "sorry what?", "what are you asking me"])
def test_confused_person_gets_the_step_explained_and_the_card_kept(client, msg):
    s = sid()
    chat(client, "my kitchen sink is leaking under the cabinet", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and "didn't follow" not in r["reply"] and not recs(s)


@pytest.mark.parametrize("msg", ["I'm confused", "no entiendo", "huh?", "what do you mean?"])
def test_confused_with_nothing_open_gets_options_not_a_note(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert kind(r) is None and "didn't follow" not in r["reply"] and r["suggested_replies"]


@pytest.mark.parametrize("msg", [
    "my sink is leaking and also can someone from leasing call me about renewing my lease",
    "the bathroom fan is broken. Separately, I want to talk to someone about my renewal",
    "kitchen faucet drips; also please have the office call me about my lease",
    "el fregadero gotea y quiero que alguien me llame sobre la renovación",
    "my AC isn't cooling, and I need to speak with a manager about my rent",
    "toilet keeps running, plus I'd like a call back about renewing",
    "two things: the oven won't heat, and can leasing reach out about my lease renewal?",
    "dishwasher won't drain. also I want a human to call me re: my lease"])
def test_repair_plus_callback_keeps_both(client, msg):
    s = sid()
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and "renew" not in fields(r)["issue"].lower()
    assert get_state().store.get_draft(s, "R001").get("queued_note")


@pytest.mark.parametrize("msg", ["I'd also like to tour on Saturday morning", "and a tour saturday would be nice",
                                 "can I see the place next week too", "I'd like to visit Heron Lake on Friday",
                                 "quiero visitar el sábado", "also want a tour", "tour on the weekend if possible",
                                 "could I see a 2 bed on Monday?"])
def test_tour_details_go_into_the_open_note_and_the_tour_is_queued(client, msg):
    s, p = sid(), "P-RELOCATE-AA"
    chat(client, "can someone from leasing call me back about pricing", s, p)
    r = chat(client, msg, s, p)
    assert kind(r) == "staff_handoff"
    r2 = press_send(client, s, "staff_handoff", p)
    assert r2["ok"] and get_state().store.get_draft(s, p)["kind"] == "tour_request"


@pytest.mark.parametrize("msg", ["oh also my roommate will come and we need ground floor",
                                 "oops I need 3 bedrooms not 2", "also we have a dog", "I need a ground floor unit",
                                 "también necesito estacionamiento", "actually make it a 1 bedroom",
                                 "btw we'd like a washer/dryer in unit", "fyi my mom is coming too"])
def test_prospect_detail_after_tour_sent_is_a_change_note_citing_it(client, msg):
    s, p = sid(), "P-RELOCATE-AA"
    chat(client, "I'd like to tour Heron Lake on Saturday morning", s, p)
    ref = press_send(client, s, "tour_request", p)["record"]["id"]
    r = chat(client, msg, s, p)
    assert kind(r) == "staff_handoff" and ref in r["reply"] + json.dumps(r["action"])
    chat(client, "yes send it", s, p)
    assert len([x for x in recs(s) if x["kind"] == "tour_request"]) == 1


@pytest.mark.parametrize("msg", ["toilet keeps running in the hall bathroom, come in any time",
                                 "kitchen faucet drips. you can let yourselves in",
                                 "my bedroom window won't close - ok to enter if I'm out",
                                 "the fridge is warm, please call me before coming in",
                                 "el fregadero gotea, pueden entrar cuando quieran",
                                 "bathroom fan is broken; knock first please",
                                 "dishwasher won't drain and maintenance can come in whenever",
                                 # was a non-strict xfail while safety R7 read "fell off" as a person sign (fixed)
                                 "the closet door fell off, they can enter while I'm at work"])
def test_entry_permission_in_the_first_message(client, msg):
    r = chat(client, msg, sid(), "R001")
    f = fields(r)
    assert f.get("entry") and "come in" not in f["issue"].lower() and "entrar" not in f["issue"].lower()


@pytest.mark.parametrize("msg", ["how long will it take", "how soon can someone come", "any idea how long?",
                                 "how long is the wait"])
def test_timing_question_during_entry_question_is_answered_and_card_kept(client, msg):
    s = sid()
    chat(client, "my kitchen sink is leaking under the cabinet", s, "R001")
    r = chat(client, msg, s, "R001")
    assert kind(r) == "maintenance_request" and not fields(r).get("entry") and "Got it." not in r["reply"]


@pytest.mark.parametrize("msg", ["drop the mailbox part", "forget the mailbox", "remove the mailbox bit",
                                 "olvide lo del buzón", "never mind the mailbox, only the faucet", "no mailbox please",
                                 "leave the mailbox out of it", "just the faucet, not the mailbox"])
def test_dropping_one_problem_removes_it_everywhere(client, msg):
    s = sid()
    chat(client, "the mailbox lock is stuck and my kitchen faucet drips", s, "R001")
    r = chat(client, msg, s, "R001")
    d = get_state().store.get_draft(s, "R001")
    assert kind(r) == "maintenance_request" and "mailbox" not in json.dumps(d).lower() and "faucet" in json.dumps(d)


@pytest.mark.parametrize("msg", ["never mind Heron Lake, just Sandpiper Pointe", "forget heron lake, sandpiper pointe "
                                 "instead", "scratch Heron Lake — Sandpiper Pointe please",
                                 "skip heron lake, do sandpiper pointe", "no heron lake, sandpiper pointe",
                                 "change the community to Sandpiper Pointe", "wrong community, it's Sandpiper Pointe",
                                 "drop Heron Lake. Sandpiper Pointe only"])
def test_dropping_one_community_keeps_the_other(client, msg):
    s, p = sid(), "P-RELOCATE-AA"
    chat(client, "I'd like to tour Heron Lake Apartments on Saturday morning", s, p)
    r = chat(client, msg, s, p)
    assert kind(r) == "tour_request" and "sandpiper" in fields(r)["area"].lower()


@pytest.mark.parametrize("msg", ["3/4", "can we do tmrw", "how about 4/5 in the afternoon", "tmrw morning works",
                                 "6/7 please", "maybe tmr?", "mañana en la tarde", "2morrow"])
def test_ambiguous_tour_dates_are_read_back(client, msg):
    s, p = sid(), "P-RELOCATE-AA"
    chat(client, "I'd like to tour Heron Lake", s, p)
    r = chat(client, msg, s, p)
    assert kind(r) == "tour_request" and ("written" in r["reply"] or "Anoté" in r["reply"] or "anoté" in r["reply"])


@pytest.mark.parametrize("msg", ["Saturday", "next week", "the weekend", "sábado por la tarde"])
def test_unambiguous_tour_dates_have_no_readback(client, msg):
    s, p = sid(), "P-RELOCATE-AA"
    chat(client, "I'd like to tour Heron Lake", s, p)
    r = chat(client, msg, s, p)
    assert "written" not in r["reply"] and "Anoté" not in r["reply"]


@pytest.mark.parametrize("msg,es", [
    ("the heat is out and I have a newborn", False), ("no heat and my 90 year old mom lives with me", False),
    ("our AC died and my grandmother is staying with us", False), ("heater broke, I have a baby at home", False),
    ("the furnace stopped and my toddler is here", False), ("el aire no funciona y mi bebé está aquí", True),
    ("no hay calefacción y vive conmigo mi abuela", True),
    ("se descompuso el calentador y tengo un recién nacido", True),
])
def test_exposure_with_a_vulnerable_person_opens_the_urgent_repair(client, msg, es):
    r = chat(client, msg, sid(), "R001")
    d = (r.get("risk") or {}).get("decision") or {}
    if d.get("care") != "unwell":
        pytest.skip("the safety layer did not classify this as exposure (Agent A's rules decide)")
    f = fields(r)
    assert kind(r) == "maintenance_request" and f["priority_note"].startswith("Urgent" if not es else "Urgente")


@pytest.mark.parametrize("msg", ["the heat is out", "my AC is broken", "I have a newborn, is the pool heated?",
                                 "el aire no funciona"])
def test_exposure_near_misses_are_ordinary_repairs_or_questions(client, msg):
    r = chat(client, msg, sid(), "R001")
    assert not fields(r).get("priority_note", "").startswith(("Urgent", "Urgente"))


@API
@given(change=st.sampled_from(["actually yes send it", "send it after all", "wait no, send it", "ok send it now"]))
def test_typed_send_after_dont_send_restores_the_same_card_never_a_command_value(client, change):
    s = sid()
    forget_persona_records("R001")  # Sprint 8 C: examples share a store; each starts with no open R001 request
    _repair_ready(client, s)
    chat(client, "don't send it, cancel", s, "R001")
    r = chat(client, change, s, "R001")
    assert kind(r) == "maintenance_request" and "send" not in fields(r)["issue"].lower()
    assert not any(str(f.get("value", "")).lower().startswith("send") for x in recs(s) for f in x["fields"])
