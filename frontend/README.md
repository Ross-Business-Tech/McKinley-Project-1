# McKinley AI — frontend

Next.js App Router + TypeScript + Tailwind + shadcn/ui (base-nova). See the root `README.md` for full setup.

```bash
cp .env.example .env.local   # only NEXT_PUBLIC_API_BASE_URL; never put LLM keys here
npm install
npm run dev                  # http://localhost:3000 (backend must run on :8000)
npm run lint && npm run typecheck && npm test
```
