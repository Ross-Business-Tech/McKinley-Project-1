# Design skills: what was actually used (Sprint 4)

This file says plainly which design skills were available and what each one changed. Skills were installed at
the user level only (`~/.claude/plugins`, `~/.claude/skills`); the protected `.claude/` folder in this repo was not touched.

| Skill | Available? | How it was used |
| --- | --- | --- |
| **Taste Skill** `design-taste-frontend` 2.5.1 (leonxlnx/taste-skill) | Yes. The user installed it with `/plugin install taste-skill@taste-skill` | Read SKILL.md, `system.md` and `cards.md`. See below |
| **oil-ui** | Yes (user skill) | Followed its main sequence: product facts, then baseline screenshots, one recommended direction, the representative screen first, real-screenshot review, then independent reviewers (visual and UX walkthrough) |
| **frontend-design** (Anthropic plugin) | Yes | Two-pass plan (tokens → review against the brief → build), the "generic AI design" checklist and its writing rules |
| **ui-ux-pro-max** | **Not installed** | Not used. I did not install unrequested third-party code; the official WCAG 2.2 guidance was used directly |
| **web-accessibility** | **Not installed** | Not used as a skill. Accessibility came from WCAG 2.2 AA and an independent reviewer (Agent E, axe-core plus manual checks) |

## Taste Skill: what applied and what didn't
Version 2.5.1 has **no "App Screen / Dashboard" workflow**. Its process (dealt heroes, one section per screen,
photographs, scroll moments, the finish gate) is for marketing and company websites. Its only app guidance says to
show the product's real UI, never a generic dashboard. Running its layout dealer or finish gate on a chat screen
would have pushed the product toward a landing page, which the brief rules out. So:

**Applied (its `system.md` rules):**
- **A 90–95% neutral interface with one accent from the client.** McKinley blue is used only for the band, primary
  buttons, the avatar, the selected tab and links. Status colours stay separate.
- **Text people read at 16px or more, at 7:1 or better in ink.** Muted text is used only for meta. Ink is 14.3:1
  and muted is 5.6:1.
- **One system:** one button pair (blue filled and outline), one card style (12px radius, one hairline, one soft
  shadow), one link look.
- **Sentence case everywhere, no tracked capitals.** Labels are 13–14px at medium weight.
- **44px targets with 8px gaps.** Focus rings show at once and are never hidden under the sticky composer.
- **Motion answers people, it is not decoration:** button hover and press states only. No scroll reveals, no
  entrance animation in a working tool, and reduced motion is respected.
- **Never:** violet, invented reviews or figures, or a drawn copy of the real logo. The wordmark is set in Barlow;
  the real logo waits for McKinley's files.
- **Its copy checker** (`scripts/copy-lint.mjs`) ran on the customer interface wording: **0 FAIL, 0 WARN**, mean
  sentence 7.9 words. The built HTML itself holds only 8 words, because the chat renders in the browser, so the
  wording was linted from `customer.ts`.

**Not applied (marketing-only):** dealt heroes, palettes and fonts (the client's real colours and font were used
instead), one section per screen, photographs, moments, CSS grounds, the finish gate (`gate.mjs`) and
`consistency.mjs` section checks.

## frontend-design: decisions it shaped
- **Plan first, then a generic-design check.** The first idea was "replace green with blue". Reviewing it against
  the brief showed that colour wasn't the main problem. Layout was: the demo picker filled the top of the phone,
  the composer vanished when the keyboard opened, and the bottom had three rows. So layout was redesigned before
  any colour changed.
- **Avoided its listed AI tells:**
  - no cream and terracotta;
  - no all-caps eyebrows;
  - no "A · B · C" meta strings in the customer view (the staff status became a labelled grid);
  - no → arrows in button labels;
  - no identical-card kit (the start options are one list, not a grid of cards).
- **Words:** buttons name the action ("Send repair request", "Talk to a person", "Start over"), errors say what
  happened and what to do, and an action keeps the same name through the flow. The pressed "Send repair request"
  is echoed as the user's own turn.
- **Two families, clearly different:** Barlow (McKinley's voice) and Atkinson Hyperlegible (reading).

## oil-ui: decisions it shaped
- **One recommended direction, not a gallery.** The direction is "a McKinley front desk in a phone": brand band,
  a quiet paper background, the conversation as the hero, and the composer as the one main action.
- **Real-screen review before calling it done.** Every round was judged from Playwright screenshots at 320–1440
  and in landscape, never from code. The independent judge (Agent C) scored the baseline at 4/10 visual and 3/10
  usability, and round 2 at 6.5/10 and 6/10, with new issues (C-R1…C-R7). Those were fixed in round 3.
- **A separate UX walkthrough of the main paths,** by Agent D (simulator, 9 scenarios), with the reviewer working
  only from the running page.
- **Visual quality and task success judged separately.** That is why the conversation-logic findings are kept as
  their own open list ([MOBILE_UX_AUDIT.md](MOBILE_UX_AUDIT.md)) instead of being hidden by a nicer screen.

## Review findings that changed the design
- **Judge C, baseline:**
  - the keyboard bug (P0);
  - the oversized demo header;
  - Send looked the same whether ready or empty;
  - the dashed "spinner" progress chip;
  - the three rows of staff tabs.
- **Judge C, round 2:**
  - the see-through composer;
  - the cramped composer at 320 while typing;
  - 911 hidden on short screens;
  - "I'm an AI" shown while the mock was answering.
- **Mobile B:**
  - long replies scrolled past their start;
  - the first screen auto-scrolled;
  - no `visualViewport` handling;
  - safe-area insets had no effect.
- **Accessibility E:**
  - focus lost after Start over;
  - outcomes of Send not announced;
  - the demo row outside any landmark;
  - the staff select overflowing at 320.
- **Simulator D:**
  - contact details overwrote the tour area (backend P0);
  - confusing after-send suggestions;
  - the confirmation running into the previous bubble.

Judge disagreements and how they were settled:
- **Link colour:** the judge asked for McKinley's link blue `#4681c7`. It measures 4.0:1 on white, below AA, so
  links use `#3f5b79` (7.0:1). The judge agreed in round 2.
- **Mock wording:** the judge asked to remove all mock or AI wording from the customer view. The project rules
  require a visible demo indicator, so "Prototype with made-up data" stays visible and the reply-source sentence
  moved into "About this demo". The judge accepted this as reasonable.
- **Header height:** the judge wanted at most 64px. The result is 105px (band plus demo row), because testers need
  the persona picker. This is kept as PARTIAL.
