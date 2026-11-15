# Mobile acceptance test

`mobile-acceptance.mjs` checks the core requirement on real browser engines: open the chat, focus the box, type,
send, get a reply, send a second message, refresh. It runs in Chromium (Android-like, `isMobile` + touch) and WebKit
(Safari engine, touch) at 320x568, 375x667, 390x844, 430x932, 768x1024, 1440x900 and 844x390 (landscape).

Each run fails if:
- the page scrolls sideways;
- the message box is disabled, which means the site is the recorded replay and not live;
- the message box is off-screen when the page opens, or with the viewport cut to 55% height (a stand-in for the
  on-screen keyboard);
- the send button is under 44px;
- no reply arrives;
- the newest reply starts below the message box;
- a tap-to-call link (`tel:`/`sms:`) shows in a normal conversation (Sprint 8: the always-visible 911 link was removed);
- for each emergency message (medical, gas, poison, self-harm by default; override with
  `Q_EMERGENCY="kind=message|kind=message"`), each in a fresh conversation: no alert, no labelled contact link, the first
  link is not fully above the message box, a number breaks across lines, focus lands on a call link, or the message
  box is hidden.

It also lists small tap targets and console errors.

```bash
# 1. a backend (mock responder is fine) allowing the test origin
cd backend && LLM_PROVIDER=mock LLM_MODEL=mock-deterministic-v1 DB_PATH=/tmp/mk.sqlite3 \
  CORS_ORIGINS=http://127.0.0.1:3000 uv run uvicorn app.main:app --port 8000
# 2. the website built against it
cd frontend && NEXT_STATIC_EXPORT=1 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npx next build
# 3. the test (Playwright from npx; NODE_PATH must point at the node_modules that contains it)
node e2e/mobile-acceptance.mjs out /tmp/mk-shots            # or: an https:// URL of a deployed site
```

Screenshots and `results.json` go to the output folder. The test cannot open a real on-screen keyboard. Before
calling the public requirement met, also try a real iPhone (Safari) and Android phone (Chrome)
([docs/INTERACTIVE_DEMO_READINESS.md](../../docs/INTERACTIVE_DEMO_READINESS.md)).
