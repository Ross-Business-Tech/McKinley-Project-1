# Emergency UX review (Sprint 8)

This review covers removing the persistent tap-to-call 911 control and adding contextual safety states. The
independent UI / accessibility judge (Agent G) reviewed it in two rounds, in real Chromium and WebKit, with axe-core
and keyboard and screen-reader checks. Screenshots are in [../screenshots/sprint8/](../screenshots/sprint8/); the full
sprint report is [../evaluation/SPRINT8_EMERGENCY_UX_MAINTENANCE.md](../evaluation/SPRINT8_EMERGENCY_UX_MAINTENANCE.md).

## What changed for the resident

| Before | After |
| --- | --- |
| A red "911" tap-to-call link on every screen, in every state ([before](../screenshots/sprint8/before-normal-390.png)) | **Normal:** nothing safety-related; only a muted, non-tappable footer line, "In an emergency, call 911" ([faucet repair](../screenshots/sprint8/after-N4-faucet-390.png)) |
| A worried or "what if" question got either nothing or a red alert | **Concern:** a calm blue note with the matching contact, for example "Call 911" for a CO question or "Call 988 / Text 988" for distress ([CO question](../screenshots/sprint8/after-C4-co-question-390.png)) |
| A poisoned child got only "Call 911" | **Active:** a clear alert first in the turn, with the contact links straight under the heading: Poison Help first for poisoning, 988 for self-harm, and "Call 911 once you're outside" for gas ([gas](../screenshots/sprint8/after-A1-gas-390.png), [poison](../screenshots/sprint8/after-A4-poison-child-390.png), [self-harm at 320 px](../screenshots/sprint8/after-A3-selfharm-320.png)) |
| The 911 link stayed after a false alarm | **Recovery:** the next ordinary turn is calm ([recovery](../screenshots/sprint8/after-R1-recovery-390.png)) |

## Checklist (judge, round 2 on `423f00a`; the UI is unchanged since then)

| Criterion | Result |
| --- | --- |
| No persistent 911 control in normal chat (greeting, composer, footer, chips, cards, status list) | PASS at all 6 sizes |
| No accidental activation (chips, Send, Talk to a person, Start over) | PASS |
| Correct contextual state (normal / concern / active) and clearly labelled links | PASS; nothing dials on render or on open |
| First contact link visible above the composer when the alert arrives | PASS in 48 checks (4 alert types × 6 sizes × 2 engines) |
| Mobile layout, landscape, safe areas, composer never hidden | PASS |
| Keyboard (tab order, 3 px focus ring) and screen reader (one `role="alert"`, polite note once) | PASS. Focus deliberately stays in the message box, so a stray Enter on a focused call link can never dial |
| No flashing or animation | PASS |
| Calm, McKinley blue; red only for active | PASS |
| axe (WCAG 2.2 AA plus best practice) | 0 violations in every state, size and engine |

## Fixed between the judge's rounds
- The first call link was hidden under the composer at 320×568 and 844×390. The links now sit directly under the
  alert heading.
- The Poison Help number wrapped mid-number. Numbers are now unbreakable.
- The "What was sent" disclosure was under 24 px in WebKit. It is now 44 px.
- "Is carbon monoxide dangerous?" showed a red alert. It now gets a calm note with Call 911.

## Open (product decisions, not defects)
- **The footer 911 line** is kept as a backstop because some emergencies still get no automatic guidance (see the
  sprint report). The product owner may remove it.
- **"Call 911 once you're outside"** is directive for a "what if" gas question. The judge suggests plain "Call 911"
  in the concern state. NEEDS McKINLEY REVIEW.
- **"What if my kid swallowed a cleaning product?"** is now **active** (past-tense "swallowed" about a specific
  child is treated as possibly real); a clearly hypothetical form gets a concern. This is intentional, and errs on
  the safe side.
- **Not tested:** real devices and real screen readers. All checks above used Playwright engines.
