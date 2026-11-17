# Offline experiments (not used by the app)

Nothing in `app/` imports this package. Production behaviour does not depend on it. Tests:
`tests/test_experiment_*.py`.

## `safety_v2.py`: the classifier may correct low-precision lines (EXPERIMENT, not accepted)

**Why.** In production, a word rule's calm care line (R6 / R7) can never be removed by the classifier. Those rules
caused every acceptance false alarm:
- **T1c and MN4:** the 988 line;
- **T1a and T1b:** a 911 line for a ceiling leak;

and 15 of 16 false alarms in the 2026-11-15 regression run.

**Design.** Production's decision is computed first and kept, except in two narrow cases (see the module
docstring):

| Rule | Changes | Only when |
|---|---|---|
| V2-L | an R6 / R7 calm line becomes no safety text | The **only** deterministic evidence is low-precision, the classifier answered **ok** with "none" at confidence ≥ 0.85, and there is no incident or earlier person alert |
| V2-M | an R4 calm line becomes no safety text plus `maintenance_urgency="urgent"` | The classifier says urgent / uncertain for a **property** hazard (flood, structural, electrical, gas, fire) with no immediate danger and no person at risk, **and** the rules saw low-precision wording. It never applies to a line the classifier alone produced. |

Low-precision evidence means one of two things, both read from the existing detector output, with **no new keyword
lists**:
- the frame's lone "final" self-harm wording group;
- the generic danger vocabulary, with no person, body state, hazard or category.

**Never changed:**
- full alerts and safety information;
- self-harm categories or intent;
- explicit distress, farewell, stockpile or person-concern evidence;
- active incidents;
- **any classifier failure** (timeout, blocked, bad output, unavailable, error, disabled: fail-safe means "as
  production").

**Offline result** (2026-11-17; `python -m experiments.compare_safety_v2 <frozen safety set> <proposed set>`):
- **Messages:** 203 (131 genuine, 72 harmless).
- **Classifier answers:** stubs, so a "none" on a genuine message is the classifier being *wrong*.

| Stub classifier answer for every message | Changed | Harmless lines removed | Genuine guidance lost |
|---|---|---|---|
| confident "none" | 15 (V2-L) | 15 | **0** |
| urgent flood, no immediate danger | 15 (V2-M) | 15 | **0** |
| unsure "none", uncertain, urgent self-harm, emergency | 0 | 0 | 0 |
| timeout / blocked / bad output / unavailable / error / disabled | 0 | 0 | 0 |

**What made V2-M safe.** The first version also applied V2-M when the classifier was the only source of the line.
On the frozen set, 8 genuine emergencies that the rules missed (E030, E072, E095, E098, E100, E111, E112, E115)
would then have lost their guidance under a wrong "urgent flood" label. V2-M now requires low-precision rule
evidence. There is a test for this.

**Known weakness (blocker for adoption), pinned by a test.** The lone "final" group mixes weak and strong wording:
- **Weak:** "by tomorrow", "I'm done with this place".
- **Strong:** "I won't be needing anything after tonight".

If the classifier were confidently wrong, V2-L would remove the 988 line from "I'm done." and "I won't be needing
anything after tonight".

**Before this could replace production:**
1. **A safety reviewer splits the "final" group** into weak and strong wording. That is pattern work and must be
   reviewed independently.
2. **Measure the real classifier on low-tier messages, with your approval.** This needs a bounded live run (about 60
   classifier calls) on the low-tier genuine and harmless messages. Stubs only show the worst case.
3. **Test on a fresh holdout** written by someone else, plus the frozen 165-case set and E086 / E089 / E091 under
   each classifier status.
4. **Product and UI support** for `maintenance_urgency`: today a removed 911 line simply disappears.

A lower false-alarm rate alone is **not** acceptance.

## `legal_v2.py`: a structured sensitive-topic boundary (EXPERIMENT, not accepted)

**Why.** PR #20's legal boundary is a list of about 150 reply patterns in English and Spanish. It works for the forms
it knows and grows with every new paraphrase.

**Design** (the module docstring has the diagram):
- **Two independent recognisers** decide whether a question is sensitive: a topic label the model would return next
  to its reply (a fixed list, validated; simulated here), and the existing message-side fair-housing pattern.
- **If either one says sensitive:** the backend shows the knowledge-base referral (`fair_housing`, still
  `pending_approval`) and routes the note to leasing or management. The model's own prose is dropped, whatever it
  says.
- **Otherwise:** the model's reply passes a small backstop: a named law, "legally", "illegal" or a right claimed, or
  production's existing resident-profile patterns.
- **Provider failure:** no model text, routing by the message gate. A missing or invalid label counts as "not
  recognised".

**Offline result** (2026-11-17; 18 cases: 10 replies stating a determination, 2 good referrals, 6 ordinary FAQ or
instruction answers; EN + ES, including indirect wording):

| | Determinations shown | Ordinary answers replaced |
|---|---|---|
| Production today (PR #20 patterns) | **1** (D7: "Con esa carta deben eximirle de la cuota.", a verb form the list lacks) | 0 |
| Experiment, correct topic label | 0 | 0 |
| Experiment, wrong or missing label | **2** (D6, D7: indirect questions with no topic word and replies with no named law) | 0 |

**What this means.**
- With a correct label, the experiment covers every case **without** paraphrase patterns, and the model never has
  authority.
- With a wrong label, indirect wording gets through. So the obligation and permission patterns can't be deleted on
  this evidence.

**Before this could replace production:**
1. Add the topic field to the conversation schema (a public API and prompt change).
2. Measure label accuracy live on a fresh EN / ES set, with your approval.
3. Keep production's patterns as a second backstop until label accuracy on indirect wording is shown.

The D7 gap in production is real today. It is pinned by a test and not fixed on this branch: production enforcement
is unchanged.
