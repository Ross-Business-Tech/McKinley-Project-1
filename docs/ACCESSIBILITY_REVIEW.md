# Accessibility review (WCAG 2.2 AA)

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
