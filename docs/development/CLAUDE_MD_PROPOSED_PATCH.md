# Proposed addition to the root `CLAUDE.md` (for Ross IT; NOT applied)

The root `CLAUDE.md` and `.claude/` are maintained by Ross IT and were not modified. This is a suggested, additive
section for the maintainers to review. It keeps every existing instruction (sign-in, the publish loop, branch and
PR rules, protected paths, data and privacy) and only points Claude Code at the project's own guidance.

Rationale: today a new session reads the root file (here.now workflow only) and, inside `backend/` or `frontend/`,
the engineering rules. Nothing at the root tells it the project is safety-sensitive, not production ready, or where
the current state is recorded.

```diff
@@ end of CLAUDE.md @@
+
+## This project (McKinley AI prototype)
+
+Before coding, read `README.md`, `docs/PROJECT_HANDOFF.md` and `docs/development/CLAUDE_PROJECT_GUIDE.md`.
+The app is a **synthetic-data prototype, not production ready** (see `docs/safety/safety-evaluation.md`); never
+describe it otherwise.
+
+- Backend: Python with `uv` in `backend/`; frontend: Next.js in `frontend/`. Run both test suites before committing.
+- Planned hosting (not yet live; Ross IT approved): Render (website and backend), Supabase (database and sign-in); see
+  `docs/DEPLOYMENT_READINESS.md`. Keep `npm run publish:preview` as the preview path until Ross IT approves the switch.
+- Safety changes (`backend/app/risk/`, `backend/app/emergency.py`, safety wording) need tests and an independent
+  review; never let a model write safety text or claim anyone was notified.
+- Model keys live only in `backend/.env`; mock or template output is never reported as live-model evidence.
+- Update the docs your change makes untrue (README status, traceability, safety and evaluation pages).
```

If accepted, nothing else needs to change: the linked documents already exist on this branch.
