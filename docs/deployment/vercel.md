# Vercel (website)

**Status: config ready (`frontend/vercel.json`); never deployed.** The here.now preview workflow
(`npm run publish:preview`) is unchanged and remains the team's default until Vercel is validated.

- Project **Root Directory: `frontend`**. `vercel.json` builds the static export (`NEXT_STATIC_EXPORT=1 next build`
  → `out/`), enables `trailingSlash` (so `/staff` → `/staff/`, refresh works) and adds basic security headers.
- One environment variable: `NEXT_PUBLIC_API_BASE_URL` = the Render address (no trailing slash). It is public by
  design and baked in at build time — **redeploy after changing it**. Never put a key in any `NEXT_PUBLIC_*` value.
- Add the Vercel address to Render's `CORS_ORIGINS`. Preview deployments get different addresses: typing works on
  them only if their address is added too.
- What people see: the customer chat says whether replies come from fixed rules or an AI model; if the backend is
  asleep or down the message is kept and "Send again" appears. The staff console's live tabs need staff access
  (not available from the browser on a hosted backend) and fall back to the recorded demo where possible.
