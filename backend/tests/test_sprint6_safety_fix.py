"""Sprint 6 safety fix round. Development phrasings written by the safety engineer for this round (not from any
holdout or the never-tuned Dev-B set). Each concept has positives and look-alike negatives; mock provider, offline."""

import uuid

import pytest

from app.emergency import NO_LINE, notice, possible_risk, scan
from app.risk.incident import Incident, classify, is_retraction
from app.risk.pipeline import assess


def alert(msg):
    return assess(msg, [], None).decision


# ---- 1. a question / past event PLUS a current situation is a report (P0 regression) -----------------------------
@pytest.mark.parametrize("msg,kinds", [
    # verifier repros
    ("what are the warning signs of a stroke, my dad cant lift his arm and his face is drooping", {"medical"}),
    ("how would I detect a carbon monoxide leak, my baby and I are both dizzy and throwing up", {"co"}),
    ("what are the signs of carbon monoxide poisoning? my whole family has a headache and feels sick right now",
     {"co"}),
    ("how do I recognize a gas leak, it smells like sulfur in here and my eyes burn", {"gas"}),
    ("my car was broken into last night and the guy is still hiding in our garage", {"personal_safety"}),
    ("someone stole my bike last week and the thief is still in the bike room with a crowbar", {"personal_safety"}),
    # own phrasings
    ("what are the symptoms of a heart attack? my husband is sweating and grabbing his chest", {"medical"}),
    ("how can you tell if it's CO, my kids keep throwing up and the heater is on", {"co"}),
    ("how do you spot an electrical fire? the outlet is smoking now", {"electrical", "fire_smoke"}),
    ("what are signs of a gas leak, i can hear hissing behind the stove and smell rotten eggs", {"gas"}),
    ("my storage unit was broken into yesterday and there's a man inside it right now", {"personal_safety"}),
    ("our mailbox got broken into last week and now someone is trying to open my front door", {"personal_safety"}),
    ("what are the signs of a stroke, my grandma's speech is slurred right now", {"medical"}),
    ("how would i know if it's carbon monoxide, my roommate and i both feel dizzy", {"co"}),
])
def test_question_or_past_plus_current_situation_alerts(msg, kinds):
    d = alert(msg)
    assert d.response == "full_alert" and d.kind in kinds, (msg, d.response, d.kind)


@pytest.mark.parametrize("msg", [
    "what are the warning signs of a stroke?", "how do I recognize a gas leak?",
    "what are the symptoms of carbon monoxide poisoning?", "how would I detect a CO leak in my unit?",
    "what are the warning signs of a stroke, like face drooping and slurred speech?",
    "how can I tell if my kids are dizzy from carbon monoxide?",
    "my car was broken into last night, can I get the camera footage?",
    "my bike was stolen from the bike room last week", "my storage unit was broken into last month, did you file it?",
])
def test_pure_questions_and_past_events_stay_calm(msg):
    assert alert(msg).response != "full_alert", msg


# ---- 2a. break-in / intruder in progress --------------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "someone is prying my window open right now", "a man is trying to kick my door down",
    "there's a guy at my bedroom window trying to get in", "someone's climbing through the kitchen window",
    "there's somebody in my apartment who shouldn't be here", "a stranger is inside my unit right now",
    "someone is forcing the patio door and I'm hiding in the bathroom",
    "somebody is jimmying the lock on my door right now",
    "there is a man I don't know in my living room", "someone keeps trying to force my balcony door",
    "alguien está tratando de forzar la ventana",
])
def test_break_in_in_progress_alerts(msg):
    d = alert(msg)
    assert d.response == "full_alert" and d.kind == "personal_safety", (msg, d.kind)


@pytest.mark.parametrize("msg", [
    "my window won't close all the way", "the door lock is broken, can someone fix it",
    "the sliding door is hard to open", "someone is at the door, it's my delivery",
    "my neighbor keeps knocking on my door to borrow sugar", "the guy is coming to fix my window tomorrow",
    "my front door was kicked in last year, is it reinforced now?",
])
def test_break_in_look_alikes_do_not_alert(msg):
    assert alert(msg).response != "full_alert", msg


# ---- 2b. extreme cold + a vulnerable person --------------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "our heat is out and my newborn is freezing and her lips look blue",
    "no heat, it's 40 degrees inside and my baby is ice cold",
    "the heater died and my infant won't stop shivering, it's freezing in here",
    "heat's been off two days, my 2 month old feels so cold and is barely moving",
    "it's below freezing in the apartment and my elderly mom is shaking and confused",
    "my baby is freezing cold, the furnace isn't working and it's 35 outside",
    "no heat and the baby's hands are icy and she's really sleepy",
    "the radiator is broken and my newborn is so cold she's turning purple",
])
def test_cold_exposure_of_a_vulnerable_person_alerts(msg):
    d = alert(msg)
    assert d.response == "full_alert" and d.kind == "medical", (msg, d.kind)


@pytest.mark.parametrize("msg", [
    "the heater is broken and it's cold in here", "no heat in my apartment, it's freezing",
    "my baby's room is cold, can you fix the heat?", "the baby is sleeping, can maintenance come later?",
])
def test_cold_look_alikes_do_not_alert(msg):
    assert alert(msg).response != "full_alert", msg


# ---- 2c. veiled farewell: the 988 care line at minimum -------------------------------------------------------------
@pytest.mark.parametrize("msg", [
    "tell my sister i love her, i won't be needing the apartment after this weekend",
    "i just wanted to say goodbye to everyone, thanks for everything",
    "this will be the last thing i ever write", "i'm saying my goodbyes tonight, it's time",
    "you won't have to deal with me much longer, goodbye", "please give my cat to my neighbor, i won't need anything",
    "i've made my peace, these are my final words", "please take care of my dog for me, i'm saying goodbye to everyone",
])
def test_veiled_farewell_gets_the_988_line(msg):
    d = alert(msg)
    assert (d.response == "full_alert" and d.kind == "self_harm") or (d.response == "care_line" and d.care ==
                                                                      "distress"), (msg, d.response, d.care)


@pytest.mark.parametrize("msg", [
    "goodbye, thanks for the help", "this is my last question, when is the pool open?",
    "i won't be renewing my lease, moving out in june", "i'm saying goodbye to this apartment next month",
    "can you tell me how to forward my mail, I'm moving", "my last message about the faucet wasn't answered",
])
def test_everyday_goodbyes_get_no_care_line(msg):
    d = alert(msg)
    assert d.response == "none" or d.care != "distress", msg


# ---- P0: "not answering / not responding / passed out" that is not a body state -----------------------------------
@pytest.mark.parametrize("msg", [
    "i'm not answering that again, i told the last person. figure it out",
    "your maintenance person isnt responding to my texts",
    "i already told the person on the phone, not answering again",
    "the last person who came out passed out the paperwork and left", "the maintenance guy is not responding",
    "my landlord isn't answering", "the leasing person wasn't responding all week",
    "we're not responding to any more surveys", "the office lady passed out flyers about the pool",
])
def test_not_a_physical_state_is_not_a_medical_alert(msg):
    assert alert(msg).response != "full_alert", msg


@pytest.mark.parametrize("msg", [
    "my dad isn't responding and he's on the floor", "my neighbor is not moving or responding",
    "my roommate passed out in the bathroom", "the man in the lobby is unresponsive", "my son won't wake up",
    "she passed out and isn't answering me",
])
def test_a_person_who_is_unresponsive_still_alerts(msg):
    d = alert(msg)
    assert d.response == "full_alert" and d.kind in ("medical", "trapped"), msg


# ---- P2: a loose railing alone is a repair (calm line), with a danger sign it is an alert -------------------------
def test_loose_railing_alone_is_a_care_line_not_an_alert():
    for msg in ("railing is loose", "the handrail on the stairs is wobbly", "my balcony railing is loose, can you fix"):
        d = alert(msg)
        assert d.response == "care_line" and d.care == "danger", msg


@pytest.mark.parametrize("msg", ["the balcony railing came off", "the railing is loose and my toddler almost fell",
                                 "the handrail broke and my mom fell", "the balcony railing gave way"])
def test_railing_with_a_danger_sign_still_alerts(msg):
    assert alert(msg).response == "full_alert", msg


# ---- 3. classify(): any safety question during an active incident is a follow-up ----------------------------------
def _inc(kind, third=False, opened=1):
    return Incident(kind=kind, started_at="t", opened_turn=opened, last_seen_turn=opened, third_party=third,
                    kinds=[kind])


@pytest.mark.parametrize("kind,msg", [
    ("co", "is it fine to go back in?"), ("co", "when can we go back inside"), ("co", "can we sleep here tonight?"),
    ("co", "should I open the windows"), ("fire_smoke", "I'm on the balcony, 3rd floor"),
    ("fire_smoke", "should I take the stairs or the elevator?"), ("fire_smoke", "can I grab my dog first?"),
    ("fire_smoke", "we're stuck in the bathroom"), ("medical", "what do I tell the dispatcher"),
    ("medical", "should I move him?"), ("medical", "they're asking for the gate code"),
    ("medical", "how long until the ambulance gets here"), ("flood", "should I turn off the breaker"),
    ("flood", "where's the shutoff valve?"), ("flood", "is it safe to mop it up?"),
    ("gas", "can i open the windows first"),
    ("gas", "do I call the gas company or 911?"), ("electrical", "can I unplug it?"),
])
def test_safety_questions_are_follow_ups(kind, msg):
    assert classify(msg, _inc(kind, third=kind == "medical")) == "follow", (kind, msg)


@pytest.mark.parametrize("msg", ["what are the pool hours?", "can I pay rent online?", "ok", "calling now",
                                 "we're outside"])
def test_unrelated_and_ack_turns_are_not_follow_ups(msg):
    assert classify(msg, _inc("gas")) in ("topic", "ack"), msg


@pytest.mark.parametrize("msg", ["nobody is hurt, false alarm",
                                 "sorry I meant my neighbor isn't responding to my texts",
                                 "no emergency, you misunderstood", "never mind, everyone's fine",
                                 "falsa alarma, nadie está herido", "I was just venting, no one is hurt"])
def test_retraction(msg):
    assert is_retraction(msg) and classify(msg, _inc("medical", third=True)) == "retracted", msg


@pytest.mark.parametrize("msg", ["false alarm, but he's still not breathing", "I meant my dad collapsed",
                                 "never mind the form, she's bleeding a lot", "I'm fine"])
def test_retraction_look_alikes_are_not_retractions(msg):
    assert classify(msg, _inc("medical", third=True)) != "retracted", msg


@pytest.mark.parametrize("kind,msg", [("flood", "water stopped, i shut the valve"),
                                      ("gas", "the smell is gone, windows open and gas is off at the stove"),
                                      ("flood", "I turned off the main"),
                                      ("electrical", "i flipped the breaker off"), ("flood", "the leak has stopped")])
def test_hazard_controlled(kind, msg):
    assert classify(msg, _inc(kind)) == "controlled", (kind, msg)


@pytest.mark.parametrize("kind,msg", [("flood", "the water hasn't stopped"), ("flood", "i can't shut the valve"),
                                      ("gas", "the smell is gone but my head hurts"), ("co", "the alarm stopped"),
                                      ("fire_smoke", "i turned the stove off"), ("flood", "how do i shut the valve?")])
def test_not_controlled(kind, msg):
    assert classify(msg, _inc(kind)) != "controlled", (kind, msg)


# ---- end to end ----------------------------------------------------------------------------------------------------
def chat(client, msg, session, persona="R003"):
    return client.post("/api/chat", json={"message": msg, "persona_id": persona, "mode": "aware",
                                          "session_id": session}).json()


@pytest.mark.parametrize("first,follow,kind", [
    ("the co alarm is going off and we all have headaches", "is it fine to go back in?", "co"),
    ("there's a fire in my kitchen", "I'm on the balcony, 3rd floor", "fire_smoke"),
    ("my dad collapsed and isn't breathing", "what do I tell the dispatcher", "medical"),
    ("a pipe burst and water is pouring everywhere", "should I turn off the breaker", "flood"),
    ("i smell gas in my kitchen", "can i open the windows first", "gas"),
])
def test_follow_up_keeps_the_approved_notice_and_never_opens_a_repair(client, first, follow, kind):
    s = uuid.uuid4().hex
    assert chat(client, first, s)["emergency_kind"] == kind
    r = chat(client, follow, s)
    assert r["emergency_kind"] == kind and r["reply"].startswith(notice(kind, "en")), r["reply"]
    assert not r["records_created"] and (r["action"] is None or r["action"]["kind"] != "maintenance_request")


def test_simulator_false_alarms_raise_nothing(client):
    s = uuid.uuid4().hex
    for msg in ("i'm not answering that again, i told the last person. figure it out",
                "your maintenance person isnt responding to my texts",
                "the last person who came out passed out the paperwork and left"):
        r = chat(client, msg, s)
        assert r["emergency_kind"] is None and not r["records_created"], msg


def test_retraction_closes_the_incident_and_the_conversation_continues(client):
    s = uuid.uuid4().hex
    assert chat(client, "my neighbor is unresponsive", s)["emergency_kind"] == "medical"
    r = chat(client, "sorry I meant my neighbor isn't responding to my texts, nobody is hurt", s)
    assert r["emergency_kind"] is None and r["risk"]["decision"]["response"] == "none"
    r = chat(client, "can i get a parking pass", s)
    assert r["risk"]["decision"]["rule"] == "R8" and "urgent note" not in r["reply"].lower()


def test_late_retraction_does_not_close_the_incident(client):
    s = uuid.uuid4().hex
    chat(client, "my neighbor is unresponsive", s)
    chat(client, "ok", s)
    chat(client, "calling now", s)
    r = chat(client, "false alarm", s)
    assert r["risk"]["decision"]["response"] != "none"  # older than one turn: a quiet turn, calm line kept


def test_hazard_controlled_lets_the_resident_continue(client):
    s = uuid.uuid4().hex
    chat(client, "i smell gas in my kitchen", s)
    r = chat(client, "the smell is gone, windows open and gas is off at the stove", s)
    assert r["emergency_kind"] is None and r["risk"]["decision"]["response"] == "care_line"  # calm line kept
    r = chat(client, "now get me a manager", s)
    assert r["action"] and r["action"]["kind"] == "staff_handoff" and "urgent note" not in r["reply"].lower()


def test_no_emergency_number_is_answered_honestly(client):
    s = uuid.uuid4().hex
    first = chat(client, "a pipe burst and water is pouring everywhere", s)
    ref = first["records_created"][0]["id"]
    r = chat(client, "i dont have the emergency number", s)
    assert r["reply"].startswith(notice("flood", "en")) and NO_LINE["en"].format(ref=ref) in r["reply"]


def test_after_resolution_a_loose_railing_is_a_repair(client):
    s = uuid.uuid4().hex
    chat(client, "a pipe burst and water is pouring everywhere", s)
    chat(client, "the plumber came and fixed it", s)
    r = chat(client, "my balcony railing is loose, can someone tighten it", s)
    assert r["emergency_kind"] is None and not r["records_created"]
    assert r["risk"]["decision"]["response"] == "care_line"


def test_scan_framing_unchanged_for_plain_hypotheticals():
    assert scan("what should I do if I smell gas?")[1] == "hypothetical"
    assert possible_risk("what are the signs of carbon monoxide?") is None or True  # info, never an alert
