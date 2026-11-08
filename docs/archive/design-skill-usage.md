# Design skill usage (sprint 2)

## Sprint 3

| Skill | Installed? | Used this sprint |
| --- | --- | --- |
| `oil-ui` | Yes (v0.32.0; 0.33.1 available, not applied) | Not re-invoked. The sprint-3 UI changes were small, local fixes driven by reviewer findings (chips after Send, a "Talk to a person" button, a neutral safety-info note, wording on the gas button, wrapping). For that scope oil-ui's own guidance is a self-check plus an independent reviewer, which is what was done (UI reviewer before, regression verifier after, neither read the code). |
| `frontend-design` | Plugin present (other project) | Its copy rule ("errors and actions say what happens and what to do") informed "Get outside, then call 911" and the honest "I haven't saved it" reply to typed phone numbers. Not invoked. |
| `ui-ux-pro-max` | No | Sprint-2 notes reused (`focus-not-obscured`, `chip-collection-reflow`); nothing new read. |
| `web-accessibility` | No | Not used; WCAG 2.2 checks done by the reviewers directly. |

No design change was made to raise a subjective score; each traces to a reviewer finding in
`docs/evaluation/accessibility-review.md` or `docs/evaluation/ux-review.md`.

---

This records which design skills were available, what each one actually told us to do, what we changed
because of it, and how it was checked. Where a skill could not be used, that is said plainly.

## 1. Availability

| Skill | Installed for this project? | How it was used | Source / version |
| --- | --- | --- | --- |
| `oil-ui` | Yes (user-level skill) | **Invoked** with the Skill tool; its review protocol was used to brief reviewers | `~/.claude/skills/oil-ui`, v0.32.0 (an update to 0.33.1 is available; not applied) |
| `frontend-design` (`anthropics/frontend-design`) | Installed as a plugin, but for a different project | Its `SKILL.md` was **read** and applied by the main agent and given to the UI reviewer. Not invoked as a skill in this project | `claude-plugins-official/frontend-design` 1.1.1 |
| `ui-ux-pro-max` | **No** | Upstream repo cloned into the session scratchpad and its guidance files **read** (SKILL.md, `references/quick-reference.md`, `references/pro-rules.md`, `data/ux-guidelines.csv`). Its `search.py` tool was **not run**: the permission system blocked executing downloaded code, so no design-system search output was used | github.com/nextlevelbuilder/ui-ux-pro-max-skill @ 0da327f |
| `web-accessibility` | **No** | Upstream `SKILL.md` **read** and given to the accessibility reviewer; the reviewer noted where it is out of date | github.com/hoodini/ai-agents-skills @ a52f5f4 (`skills/web-accessibility`) |

Nothing was installed into `~/.claude` or the repository's `.claude/`. Ross IT-managed configuration was not
touched.

## 2. Guidance that changed the implementation

### oil-ui
- **"For an existing product, polish from the source: reuse tokens and shared components, keep brand assets,
  don't redesign for its own sake."** Status colours were consolidated into one shared component
  (`frontend/src/components/customer/StatusPill.tsx`) used by chat cards, the status list and the staff queue,
  instead of per-screen colours.
- **"One hero and one primary action per screen; merge or demote competing ones."** Collecting-stage cards were
  replaced by a one-line progress note; only the read-back card carries the Send button.
- **Independent review protocol** (`references/visual-review.md`, `references/ux-review.md`): reviewers received
  screenshots, the task and constraints, but no source code, no implementer justification and no earlier
  scores. The UX walkthrough reviewer was given no expected paths, only the live page. Fixes were implemented
  by a separate agent, then re-reviewed (round 2) and verified by an agent that implemented nothing (Agent H).
- **"Good-looking and task-completing are accepted separately."** Separate scores are kept for visual design,
  usability, accessibility, conversation quality and safety (see `docs/archive/sprint2/sprint2-review-report.md`).

### frontend-design
- **Avoid the "SaaS card kit" tells**: identical cards with the same stripe/shadow, a tracked all-caps label on
  everything. The 6px coloured left stripe on every card was removed; status lives in one pill; all-caps
  status labels in the staff tabs (`NEEDS_API_KEY`, `MOCK`) became plain words ("Needs API key", "Mock").
- **Copy rules**: name things by what users understand; one action keeps its name through the flow; errors say
  what happened and what to do. Examples: "Send it after all" restores a declined card; "Ask the office" chips
  on unanswered policy questions; the after-send answer says plainly that nobody is notified in this
  prototype.
- **Empty screen is an invitation to act**: the first screen now shows an assistant marker and the main tasks
  as tappable rows under the greeting.

### ui-ux-pro-max (read-only)
- `focus-not-obscured` (WCAG 2.2): page `scroll-padding-bottom` now follows the measured composer height; the
  composer stops being sticky on short screens.
- `compact-label-overflow` / `chip-collection-reflow`: status pills wrap instead of `whitespace-nowrap`; the
  chip row has an edge fade so it reads as scrollable.
- `color-not-only` and `state-clarity`: every status keeps icon + text + colour; urgent is red with a warning
  icon everywhere (it was green in the status list).
- `loading-buttons`, `error-feedback`, `error-recovery`: kept (reviewers asked to keep the existing replying
  line and "Send again").
- `redundant-entry` (WCAG 2.2 3.3.7): office notes created from a button now carry the person's own recent
  messages instead of asking again or saving the button text.
- Pre-delivery checklist items used for verification: 375 px width, reduced motion, 44 px touch targets,
  scroll content not hidden behind fixed bars, focus order.

### web-accessibility (read-only)
- Used: contrast formula, form-error pattern, screen-reader-only text, testing with axe.
- Not followed, with reason (from Agent F): it targets WCAG 2.1 and omits 2.2 criteria (2.4.11, 2.5.8,
  3.3.7/3.3.8); its navigation example uses `role="menubar"`, which the ARIA Authoring Practices advise against
  for site navigation; its modal example hand-rolls a focus trap where native `<dialog>`/`inert` is preferred;
  it relies on jest-axe alone, while axe reported 0 violations here although 8 real issues existed.

## 3. Verification

- Visual: Agent A re-scored real screenshots at 375/390/768/1440 (round 2; see the sprint report).
- Accessibility: Agent F manual WCAG 2.2 AA audit plus axe in 27 (round 1) and 44 (frontend fork) states.
- UX: Agent B walkthrough of live journeys; persona suite metrics (`evals/usability/`).
- What was not verified: real screen readers, real phones and on-screen keyboards, dark mode, forced colours.
