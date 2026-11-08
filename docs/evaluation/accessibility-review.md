# Accessibility review (WCAG 2.2 AA)

## Sprint 3

Reviewed in a real browser twice by independent agents that did not read the code: a UI + accessibility reviewer on
the baseline build and a regression verifier on the sprint-3 build (frozen `bf6575b`), at 375×812, 390×844,
768×1024, 1440×900 and 375×420 (keyboard-proxy height). The `web-accessibility` skill is still not installed.

| Finding (baseline reviewer) | WCAG | Sprint 3 change | Regression verifier |
| --- | --- | --- | --- |
| Corrections applied silently; identical sentence announced twice | 4.1.3 | Backend says what changed ("Updated: the location is now Hall bathroom") | Fixed |
| Hidden live-region paragraph stays in the page, so browsing reads each reply twice | 4.1.3 (best practice) | Live-region text clears 6 s after it is announced | Fixed (one polite region, each reply announced once) |
| Composer off-screen when focused on short screens | 2.4.11 | Composer scrolls into view on focus below 480 px height | Fixed at 375×420 |
| Chip row scrolls sideways, last chip clipped | 1.4.10 (reflow, practical) | Chips wrap; "Talk to a person" no longer duplicated as a chip | Fixed after the verifier's run (`f31ce6c`); re-check pending |
| No permanent way to reach a person | 3.2.6 (consistent help, AA in 2.2) | Always-visible "Talk to a person" button under the composer | Fixed |
| Staff tab bar clipped at 390 px | 1.4.10 | Tabs wrap on phones | Fixed |
| Gas alert button "Call 911" contradicts "don't use phones inside" | – (content) | "Get outside, then call 911"; gas/CO headings say to leave first | Fixed |
| Safety info for a hypothetical question | – | Neutral note, no call buttons, no `role=alert` | Verified |

axe-core 4.14 on the sprint-3 build: 0 violations on the customer page and the staff console (Next.js dev overlay
excluded). Automated checks are not sufficient; the manual keyboard pass (visible 3 px focus, chips and Send
reachable, focus returns to the composer) passed. Not verified: real screen readers (VoiceOver/NVDA), real phones
with on-screen keyboards, forced colours, dark mode.

Scores from the independent reviewers (0–10): customer accessibility 7.5 (baseline) → 8 (sprint 3); staff
accessibility 7.5 → 8.

---

## Sprint 2

The **web-accessibility skill is not installed**. Its upstream instructions (hoodini/ai-agents-skills) were read and
given to Agent F, who found them out of date: WCAG 2.1 only, a `menubar` navigation example the ARIA Authoring
Practices advise against, a hand-rolled focus trap, and reliance on axe alone (see `docs/archive/design-skill-usage.md`).
Agent F audited manually in Chromium via Playwright (keyboard-only journeys, live-region recorder, accessibility
tree, computed styles, zoom / text-spacing / 200% text emulation); axe-core ran in 27 states (round 1) and 35
states (round 2): **0 violations both times**. Every finding below was manual.

| Score | Round 1 (`d3d64d6`) | Round 2 (`a9154ac`) |
| --- | --- | --- |
| Customer | 7/10 | 8/10 |
| Staff | 6/10 | 6.5/10 |

| ID | SC | Round-1 finding | Status after round 2 (Agent F) | Then (main agent, `8fdf0d3`, not yet re-audited) |
| --- | --- | --- | --- | --- |
| F1 | 2.4.11, 1.4.10 | Sticky composer hid focused buttons at 400% zoom | Fixed | |
| F2 | 1.4.12, 1.4.4 | Pills clipped with text spacing / 200% text | Partial: progress line overflowed at 200% | Progress line wraps |
| F3 | 3.1.2 | Spanish label/button in `lang=en`, English status text in `lang=es` | Partial: status titles still English | |
| F4 | 3.1.2 | Cancel-failure error English only | Fixed | |
| F5 | 1.4.11 | Staff tab focus ~1.5:1 | Fixed (3px solid) | |
| F6 | 2.4.7 | Tab panel focus invisible | Not fixed | `outline-hidden focus-visible:outline-solid` |
| F7 | 3.2.2 risk | Sign-in change silently reset | Fixed (visible hint + confirm) | |
| F8 | — | Composer didn't grow | Fixed | |
| F9 | 4.1.2 | `aria-label` on plain divs | Fixed | |
| F10 | 1.3.1 | Card title h2 at same level as Conversation | Fixed (h3) | |
| F11 | — | Stale "Not sent" bubble after retry | Fixed | |
| F12 | 4.1.3 | Focus to plain div after confirm/cancel | Fixed (`role=article`) | |
| F13 | 1.4.1 | Urgent items green | Fixed (red + icon) | |
| F14 | 2.5.8 | Evaluation checkboxes 16 px | Not fixed (P3; passes via label) | |
| N1 | 1.4.4 | Progress line off-screen at 200% text | New in round 2 | Fixed |
| N2 | 4.1.3 | Reload re-announced an old emergency alert | New | Restored messages render without `role=alert` |
| N3 | 2.4.3 | Phone: transcript opens 1,800 px below, focus stays on list | New | Focus moves to the transcript heading below 768 px |
| N4 | 4.1.3 | Transcript pane `aria-live` read everything twice | New | One short status: "Conversation loaded, N messages" |
| N5 | 3.1.2 | Spanish staff transcript turns tagged `en` | New | Per-turn `lang` (simple heuristic) |
| N6 | 2.4.11 | "Show fewer" pushed behind the composer at 1440 | New (P3) | Not fixed |
| N7 | — | Every urgent item pinned (21) | New (P3) | Capped at 3 |
| N8 | 1.3.1 | Staff queue cards have no headings | New (P3) | Not fixed |

Not tested: real screen readers (NVDA, JAWS, VoiceOver, TalkBack), real phones and on-screen keyboards, Windows
select/confirm behaviour, forced colours, dark mode, preview (replay) mode in depth.

---

## Sprint 1 (kept for comparison)


The **web-accessibility skill was not installed**, so Agent E (an independent accessibility subagent) reviewed directly against WCAG 2.2 AA. It used Playwright (Chromium), axe-core 4.x (tags wcag2a/aa, wcag21a/aa, wcag22aa, best-practice), the accessibility tree, computed styles and screenshots. The main agent also ran axe in 10 journey states after every rebuild (`scratchpad/smoke/drive.cjs`).

## 1. Automated results

| Round | Customer view (all states) | Staff console |
| --- | --- | --- |
| Self-check before review | heading-order ×8, landmark-unique ×5 (duplicate IDs on cards) → fixed before the reviewers saw it | 0 |
| Round 1 (Agent E) | 0 violations in 12 live + 3 preview states | color-contrast (Model comparison 2, Evaluation 3); scrollable-region-focusable at 320px |
| Round 2 (Agent E) | **0** in every state, including the new "Not sent" card, the Call 911 alert, the Spanish emergency, and the error with a failed message | **0** on all 5 tabs at 1280 and 320px |
| After round-2 fixes (main agent) | 0 in 8 journey states (phone + desktop) | 0 |

axe catching nothing is not a pass on its own. The manual findings below are what mattered.

## 2. Manual findings and status

| # | Sev | WCAG SC | Finding | Fix | Status (verified by) |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 (language access) | 3.1.2 / app safety rule | "Huelo a gas" missed | Spanish first-person forms in the emergency classifier | Fixed (E, round 2) |
| 2 | P1 | 2.4.3, 2.1.1 | Focus fell to `<body>` after "Don't send" | Focus moves to the new message | Fixed (E) |
| 3 | P1 | 1.4.10, 1.3.2 | Staff tabs overlapped the heading below 768px | Single scrolling tab row | Fixed (E) |
| 4 | P2 | 3.1.2 | Spanish user text and chips tagged English; English chrome inside Spanish | EN/ES UI strings; `lang` on every message, chips, textarea and footer; live region and hidden heading tagged | Mostly fixed (E). The live region `lang` was added after round 2. Workbook values such as "Afternoons (1-5 PM)" stay English |
| 5 | P2 | 4.1.3, 2.4.3 | Whole cards re-read by the live log; focus moved after every send | The transcript is no longer live; one short polite announcement per reply; focus stays in the composer after sending | Fixed (E) |
| 6 | P2 | 1.4.11, 2.4.7 | Staff tab focus ring ~1.6:1; selected tab ~1.09:1 | 3px #1D4F91 ring; 2px green underline + bold | Fixed (E); the ring clipped by the scroll row (N4) was padded after round 2 |
| 7 | P2 | 1.4.3 | Staff small text 4.0–4.3:1 | Darker `--muted-foreground` / `--destructive` | Fixed (E: axe 0) |
| 8 | P2 | 2.1.1 | Records table not keyboard-scrollable | `tabIndex=0` region with a label | Fixed (E) |
| 9 | P3 | 1.3.1 | Card `dt` contained label + source | Grid layout, `dt` = label only | Fixed (E). Round 2 A found the tablet/desktop column order broken; fixed and checked by screenshot |
| 10 | P3 | 1.3.1, 2.4.6 | Heading outline skipped levels | Hidden h2 "Conversation"; staff h3/h4 | Fixed (E) |
| 11 | P3 | 3.3.2 | Preview: why typing is off was not announced | Textarea described by the preview banner | Fixed (E) |
| 12 | P3 | 3.2.2 (advisory) | Sign-in change silently resets | Select described "Changing this starts a new conversation" | Fixed (E) |
| 13 | P3 | 2.5.8 (passes) | Staff controls 16–36px | Not changed: they pass 24×24, and it's the older staff tooling | Documented |
| 14 | P3 | — | 13-digit non-card number redacted | Luhn check | Fixed (E) |
| N1 | P2 | 2.4.7 | Chip focus ring clipped in the scrolling row on phones | Vertical padding on the scroll row | Fixed after round 2 (needs re-verification on a real phone) |
| N2 | P3 | 4.1.3 | Confirm/cancel/error could be announced twice | No live text when focus moves to the new message; `role=status` removed from the error box | Fixed after round 2 |
| N5 | P3 | — | Error messages always English | Spanish error strings | Fixed after round 2 |

## 3. What passes (verified by Agent E)

- Names and labels: sign-in select, textarea, icon-only send button.
- Each message is prefixed for screen-reader users ("You said:", "Assistant said:", and the Spanish equivalents).
- Cards are named groups; the status list is a named list; the emergency uses `role=alert` and is announced once.
- Keyboard: logical tab order; Enter sends, Shift+Enter adds a newline, IME composition is respected; standard tab pattern in the staff console.
- 3px focus ring at 7.6:1 on every customer control; nothing hidden under the sticky composer (2.4.11).
- Reflow at 320px with no horizontal scroll; text-spacing override; landscape works.
- Reduced motion respected; no autoplay motion.
- Customer tap targets are 44px or larger. The Call 911 button is 48px tall (`tel:911`), white on #A3241C.

## 4. Not tested

Real screen readers (VoiceOver, NVDA, JAWS, TalkBack), real phones and on-screen keyboards, forced colours / high contrast, dark mode, speech input and switch access, Firefox and Safari, native select behaviour per OS, Spanish translation quality, AAA criteria, and the staff "Compare" and "Run evaluations" actions beyond page load.
