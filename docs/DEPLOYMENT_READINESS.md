# Deployment readiness: Render website + Render backend + Supabase + OpenRouter

**Status 2026-11-11: a public demo is deployed and its customer journeys were tested on the real URLs.** It is a
**prototype on synthetic data, NOT production ready** (blockers below).

| | Address | Render service |
| --- | --- | --- |
| Website (static site, free) | https://mckinley-frontend.onrender.com | `mckinley-frontend` `srv-dbqbpgrm8hqs73acc0f0` |
| Backend (web service, free) | https://mckinley-backend.onrender.com | `mckinley-backend` `srv-dbpr730ae00c73cdsl80` |
| Database | the team's **development** Supabase project (synthetic data, RLS on all 13 tables) | — |
| Replies | OpenRouter `nvidia/nemotron-3.5-super-vl:free` (live, not mock) | — |

Both services deploy the `development` branch automatically. Guides: [Render backend](deployment/render.md) ·
[Render website](deployment/render-frontend.md) · [Supabase + migrations](deployment/supabase.md) ·
[Vercel website](deployment/vercel.md) · [Gemini](deployment/gemini.md).

## Two ways to host the website (one backend either way)
| | Option A: Vercel + Render | Option B: Render + Render (**live**) |
| --- | --- | --- |
| Website | Vercel, Root Directory `frontend`, `frontend/vercel.json` | Render static site, `render.yaml` `mckinley-frontend` |
| Build | `NEXT_STATIC_EXPORT=1 npm run build` → `out/` | `npm ci && NEXT_STATIC_EXPORT=1 npm run build` → `out/` |
| Website variable | `NEXT_PUBLIC_API_BASE_URL` = Render backend address (public) | same |
| Backend `CORS_ORIGINS` | the exact `https://….vercel.app` address | `https://mckinley-frontend.onrender.com` |
| Headers | `vercel.json` | `render.yaml` `headers` (not yet on the live site, see the website guide) |

## Verified on the deployed URLs (2026-11-11)
| Check | Result |
| --- | --- |
| Health | `app_env: hosted`, `provider: openrouter`, `provider_ready: true`, `is_mock: false`, demo personas off |
| Real AI replies | `reply_source: model`, provider `openrouter`, model `nvidia/nemotron-3.5-super-vl:free`; 10–55 s per reply |
| Context across turns | "What day did I say I wanted?" → "You said Sunday afternoon." (after a correction from Saturday) |
| Tour request | ask → read-back card → correction (Saturday → Sunday) → Send → `DEMO-TOUR-1043`, row in Supabase, bound to the session |
| Duplicates | a second Send on the same conversation saves nothing (`NO_PENDING_ACTION`); the card's Send button disappears |
| Restart | after a redeploy the same conversation continues and remembers the community and day; a new conversation sees nothing |
| Supabase | migrations at `0004 (head)`; 20 synthetic residents loaded from the database; chat turns and records written; client connection uses TLS |
| Authorization | staff records 403 without / with a wrong token; persona chat 403; `/api/personas` empty; CORS only for the website origin |
| Secrets | none in the website's HTML/JS; customer errors no longer show provider text |
| Browser (live) | phone 390×844 Chromium journey 17/17 (tour, correction, Send, no duplicate, refresh, offline + retry, staff page shows no data, axe 0 violations) |

**Not verified on the deployment:** resident repair requests, repeat-issue history and resident status lists. They
need a signed-in resident, and the hosted backend correctly refuses demo personas (there is no sign-in). They pass in
the local Postgres test runs only. Real phones and screen readers were not tested.

## Configuration
Backend variables and secrets: [Render guide](deployment/render.md) and `backend/.env.example`. Website: only
`NEXT_PUBLIC_API_BASE_URL` (public by design). Never put a key, database URL or Supabase service-role key in the
website, the repository, a pull request or a chat.

## Blockers before any real resident uses it (unchanged by this work)
- **Missed emergencies:** Sprint 6 independent holdout 76% full alert / 85% any guidance; 16 of 109
  immediate-danger messages got nothing ([SAFETY_STATE_AND_EVALUATION.md §7](safety/SAFETY_STATE_AND_EVALUATION.md);
  earlier holdouts: [safety evaluation](safety/safety-evaluation.md)). Gemini may run as the semantic safety
  classifier; it never removes a rules alert or care line (Sprint 7), and it has not been evaluated.
- **No authentication:** the demo sign-in (`persona_id`) is chosen by the browser; staff tools are protected only by a
  loopback/token boundary. Real resident and staff sign-in, enforced on the backend, is required. Since Sprint 6,
  `APP_ENV=hosted` turns demo personas off (`DEMO_PERSONAS_ENABLED`), so a hosted backend serves **public
  information only** and never reads resident records ([security/AUTHORIZATION_BOUNDARIES.md](security/AUTHORIZATION_BOUNDARIES.md)).
  Do not add a bypass; keep real resident data disconnected until real sign-in exists.
- **Unapproved scripts:** emergency and escalation wording (I-17/I-18) are team drafts; McKinley must approve them.
- **No live-model evaluation:** the deployed demo replies through a free OpenRouter model (checked by hand on a few
  journeys, not evaluated); Gemini has never been called; reply quality and the semantic safety classifier on a live
  model are unevaluated. Free models may log prompts: synthetic data only.
- **No integrations:** no Yardi, work orders, CRM, paging or messaging. Nobody is notified.
- **No real-device testing:** the phone checks ran in Playwright Chromium/WebKit (locally and, on 2026-11-11, against
  the public Render URLs); no real iPhone/Android and no real screen reader yet
  ([INTERACTIVE_DEMO_READINESS.md](INTERACTIVE_DEMO_READINESS.md)).
- **here.now preview is not interactive:** it replays recorded conversations; the Render demo above is the live one.
- **Public demo is guest-only:** visitors can ask questions, request tours and leave notes; resident features need a
  sign-in that does not exist. Saved requests reach nobody (no integrations).
- **Data:** synthetic only. No real McKinley data may be loaded without approval.
