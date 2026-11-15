# Interactive demo readiness: "a link anyone can open on their phone and ask a question"

**Short answer (2026-11-10): NOT yet satisfied.** No public URL exists that an outside phone can open and hold a
real conversation with. The redesigned chat **does** work interactively on phones. That was proven against a locally
running backend with the deterministic mock responder. The repo script (`frontend/e2e/mobile-acceptance.mjs`)
fills the box, sends, gets multi-turn replies and refreshes, in Chromium and WebKit at 7 sizes. Reviewers separately
checked key-by-key typing, cards with Send, Talk to a person and error retry at several sizes. The public step is blocked: the backend and database are not deployed,
and there is no Gemini key ([DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md)).

## Three levels, kept separate

| Level | What it means | Status | Evidence |
| --- | --- | --- | --- |
| 1. Interactive frontend, **mock** replies | Type and send on a phone-sized browser; the local FastAPI backend answers with fixed rules (labelled "fixed rules, not an AI model") | **VERIFIED (local, MOCK ONLY)** | [design/MOBILE_UX_AUDIT.md](design/MOBILE_UX_AUDIT.md): 14/14 engine×size runs pass; resident/prospect simulations (Agent D) |
| 2. Live **Gemini** conversation | The same, with Gemini writing replies | **BLOCKED**: no `GEMINI_API_KEY`; never called | [deployment/gemini.md](deployment/gemini.md) |
| 3. **Public** end-to-end | An outside phone opens a public Vercel URL → Render backend → Gemini → Supabase | **BLOCKED**: nothing deployed; no accounts or credentials | [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md) |

The **here.now preview link** is a static showcase. It replays conversations recorded from the prototype, with
typing turned off, and says so on screen. It is kept as the fallback and is **not** evidence for level 1, 2 or 3.

## What the website does in each situation (no silent substitution)
- **Built with no backend address** (here.now): recorded replay with a "Preview link" notice. Typing is off.
- **Built with a backend address, backend reachable:** a live chat. If that backend runs the mock, the
  "About this demo" panel says replies come from fixed rules. With Gemini it says an AI model writes them and fixed
  safety rules check them.
- **Built with a backend address, backend unreachable:** "The live assistant can't be reached right now…", plus Try
  again and the recorded replay. It is never presented as the live assistant.
- **Backend reachable but Gemini fails** (no key, rate limit, timeout): the backend answers with its approved
  templates or a clear error. It **never** switches to the mock silently.
- **Render free plan waking up:** after 4 seconds the site says "Waking the assistant up. This can take up to a
  minute the first time." Requests wait up to 90 seconds.
- No key, database URL or service-role key is ever in the website. The only browser setting is
  `NEXT_PUBLIC_API_BASE_URL`, which is public by design.

## How to run the interactive phone test yourself (local, mock)
```bash
# backend (mock responder, throwaway database)
cd backend && LLM_PROVIDER=mock LLM_MODEL=mock-deterministic-v1 DB_PATH=/tmp/mk-demo.sqlite3 \
  CORS_ORIGINS=http://127.0.0.1:3000 uv run uvicorn app.main:app --port 8000
# website pointed at it
cd frontend && NEXT_STATIC_EXPORT=1 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npx next build
# phone-size acceptance run (Chromium + WebKit, 7 sizes): see frontend/e2e/README.md
node frontend/e2e/mobile-acceptance.mjs frontend/out /tmp/mk-shots
```

## What must happen before the requirement is met
1. Deploy the backend on Render with Supabase and Gemini (checklist in [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md)).
2. Deploy the website on Vercel with `NEXT_PUBLIC_API_BASE_URL` set to the Render address. Add the Vercel address to
   `CORS_ORIGINS`.
3. Run `frontend/e2e/mobile-acceptance.mjs` against the **public** URL (it accepts a URL), and on at least one real
   iPhone (Safari) and one real Android phone (Chrome): open the link, type a question, get a reply, send a second
   message, report a repair through to Send, use Talk to a person, and refresh.
4. Only then mark level 3 VERIFIED here, with the date, the URL and the device list.

Known limits even then: emergency detection misses some immediate dangers, there is no real sign-in (the demo
picker chooses the identity), and the scripts are not approved by McKinley. It stays a prototype on made-up data.
