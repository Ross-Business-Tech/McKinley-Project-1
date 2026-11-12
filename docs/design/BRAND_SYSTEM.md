# McKinley brand system (customer chat and staff console)

One small system shared by `/` (customer chat) and `/staff/` (staff and demo console). Tokens live in
`frontend/src/app/globals.css` (`--color-mk-*`); components use only those tokens. Mobile UX evidence:
[MOBILE_UX_AUDIT.md](MOBILE_UX_AUDIT.md). How the design skills were used: [TASTE_SKILL_REVIEW.md](TASTE_SKILL_REVIEW.md).

## Where the colours come from
Checked on 2026-11-10 against McKinley's own site, mckinley.com. The values come from its stylesheet
(`styles.*.css`) and its app icon:

| McKinley value | Where mckinley.com uses it | Our use |
| --- | --- | --- |
| `#4e6f92` blue | `bg-style-blue`, `font-color-blue`, button hover; app icon `#4f7094` | **brand**: header band, primary buttons, avatar, selected tab |
| `#4681c7` link blue | links in page copy | **not used for text**: 4.0:1 on white, below AA. Links use `#3f5b79` (7.0:1) |
| `#a3b49d` sage | deal badges | not used (2.2:1 with white text; no role without a decorative use) |
| `#5c6369` grey | subtitles, body copy | **muted text** |
| `#ef6c49` orange | form errors | not used: our errors and emergencies keep the tested red / amber pair |
| Barlow (BarlowLight on site) | the whole site | **headings, wordmark, buttons** (500–700, loaded with `next/font`) |

The real McKinley logo (`/imgs/mcklogo.png`, white on blue) is **not** copied into this public repository. The header
shows a Barlow wordmark until McKinley supplies its logo files and approves their use.

## Tokens

| Token | Value | Role | Contrast (WCAG 2.2) |
| --- | --- | --- | --- |
| `mk-brand` | `#4e6f92` | band, primary button, avatar | white text 5.23:1 (AA); 4.84:1 vs paper (non-text) |
| `mk-brand-hover` | `#3f5b79` | hover/pressed; brand-coloured text and links | white 7.04:1; on white 7.04:1; on paper 6.51:1 |
| `mk-brand-strong` | `#2b4660` | staff band; small brand text on tints | white 9.78:1 |
| `mk-brand-soft` | `#e8eef4` | your messages, selected rows, hover | ink 13.24:1; muted 5.22:1 |
| `mk-ink` | `#1c2530` | body text | 14.31:1 paper, 15.48:1 white |
| `mk-muted` | `#5c6369` | secondary text (McKinley's grey) | 5.64:1 paper, 6.10:1 white |
| `mk-paper` / `mk-surface` | `#f5f6f8` / `#ffffff` | page / cards | — |
| `mk-line` / `mk-line-strong` | `#dde3ea` / `#7a8796` | dividers / input borders | line-strong 3.66:1 white, 3.39:1 paper (non-text ≥ 3:1) |
| `mk-focus` | `#1f3a56` | 3px focus ring, 2px offset | 10.8:1 on paper; **white** ring on the blue bands (5.23:1 / 9.78:1) |
| `mk-done` / `-soft` | `#2d6a44` / `#e7f2ea` | saved / submitted records (check icon) | 5.62:1 on tint, 6.45:1 on white |
| `mk-sent` / `-soft` | `#2b4660` / `#eaf0f6` | calm care notes (information) | 8.52:1 |
| `mk-attention` / `-soft` | `#7a4206` / `#fff3e0` | "a person should help" (clock icon) | 7.34:1 |
| `mk-danger` / `-soft` | `#a3241c` / `#fdeceb` | emergencies only (warning icon, call buttons) | 6.5:1 on tint, 7.4:1 under white |
| `mk-draft` / `-soft` | `#5c6369` / `#eef1f4` | drafts, not sent, not available | 5.38:1 |

Ratios were computed with the WCAG relative-luminance formula; the accessibility reviewer re-measured the rendered
colours ([MOBILE_UX_AUDIT.md](MOBILE_UX_AUDIT.md), Agent E).

**Status is never colour alone.** Each status pill has an icon and words:
- **Emergency:** red with a warning triangle.
- **A person should help:** amber with a clock.
- **Check, then send:** blue with a clipboard.
- **Saved:** green with a check.
- **Draft:** grey with a pencil.
- **Not sent:** grey with a ban sign.
- **Not available:** grey with a lock.

Green appears **only after the backend actually saved something**. Brand blue never means "done".

## Typography
- **Barlow 500/600/700** for the wordmark, headings, card titles, tab labels and primary buttons: McKinley's voice.
- **Atkinson Hyperlegible Next** for everything people read: messages, fields and help text. It was chosen earlier for
  low-vision legibility (clear 1/l/I and 0/O) and is kept.
- Body text is 16px with a line height of about 1.6. Secondary text is 14px. Nothing is under 12px except the staff
  table meta. Inputs are 16px, so iOS never zooms.

## Components
- **Header band** (customer): McKinley blue, wordmark plus "Resident and leasing help". It is static on phones
  (scrolls away) and sticky from 640px wide. The staff band is deep blue `#2b4660` with a white **Staff** tag, so
  the two pages cannot be confused.
- **Demo row:** one 56px row containing the "Demo sign-in" select (always visible, so testers can switch personas)
  and an **About this demo** toggle (`aria-expanded`). The toggle reveals what the demo is, where replies come
  from (fixed rules or an AI model) and the staff link. Escape closes it and returns focus.
- **Messages:**
  - The assistant speaks plainly, with a blue "M" avatar and its name, shown once per run of messages.
  - Your messages are blue-soft bubbles, right-aligned, with a 16px radius and a 6px tail corner.
  - A failed message gets a dashed amber outline and "Not sent".
- **Start options:** a white list of up to 5 rows, each 48px with a blue chevron, max 448px wide.
- **Suggestion chips:** white with a blue outline, 44px tall. On short screens they become one scrolling row.
- **Composer:**
  - Pinned to the bottom at every height.
  - A 48px input and a 48px send button. Send is blue when there is text and grey with an outline when empty, so
    the two states never look alike.
  - Under it: **Talk to a person** (always) and **Start over** (once you have talked).
  - Then one line: "Prototype with made-up data. In an emergency, call 911." (Sprint 8: plain muted text, **not** a
    link; tap-to-call links appear only inside a contextual emergency alert). That line is hidden
    visually on screens under 480px tall but stays available to screen readers.
- **Action card:**
  - A white card with a 12px radius: Barlow title, status pill, field list with sources.
  - The buttons are **Send** (48px, blue) and **Don't send** (outline).
  - After a save it gets a green border, a green "Saved in demo" pill, a one-line summary of the details and, on the
    demo line, the reference number (Sprint 9).
  - A progress hint ("Tour request. Still needed: community or city") uses a static checklist icon, not a spinner.
- **Emergency block:** unchanged on purpose. It has a 2px red border, a role=alert heading and a 48px red
  **Call 911 / 988** button. It is never restyled to match the brand.
- **Staff status:** a labelled grid (Replies, Database, Residents from, Environment) instead of one running line.
- **Staff tabs:** one row, scrolling sideways on phones with the next tab peeking in. The selected tab has a 3px blue bar.

## Accessibility decisions
- Focus is always visible: a 3px ring, white on the bands. The sticky composer pads scrolling by its own height,
  so focused controls are never hidden behind it (2.4.11).
- Touch targets are at least 44px, with 8px gaps between separate controls in the composer. The one exception is
  the inline 911 link in running text (2.5.8 exempts it).
- Live region: one polite announcement per reply. Emergencies use role=alert once. Restored messages are never
  re-announced.
- Visible labels: "Demo sign-in" is a real `<label>`. The note "changing this starts a new conversation" is the
  select's description, and switching asks for confirmation once you have talked.
- Reduced motion turns off every transition. The only animation is the typing dots.
- Language: each message carries `lang` (EN/ES), and the Spanish UI strings are a **draft** translation.

## Not done / open
- The real McKinley logo, approved brand guidelines and photography were not supplied. The colours are taken from
  the public site, not from a brand book.
- The Spanish strings need review by a fluent McKinley staff member.
- No dark theme.
