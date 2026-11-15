# Demo video: workflow walkthrough

Finished files are in [`output/`](output/):

| File | What it is |
| --- | --- |
| `mckinley-demo-full.mp4` | About 2 min 5 s, 1920×1080, narrated, captions burned in, starts with the cover |
| `mckinley-demo-full.srt` | The same captions as a separate file (YouTube, Canvas, video editors) |
| `cover.png` | The cover on its own (1920×1080), for a thumbnail or a slide |

The video follows the required structure, with a label for each part in the corner:
1. Who it's for and what it replaces
2. The input
3. The output and what it means
4. The human check
5. One limitation

Rules followed: sample data only (a made-up resident, "Marisol", with fictional details). The recording shows only
the app page: no browser tabs, bookmarks or notifications are captured.

## How it is made

A browser types into the real app and clicks through it, and a free voice model that runs on this machine (Kokoro)
reads the narration. The captions come from the same text, so they always match the voice.

The deployed site could not be reached from the cloud session, so the video records the same final code running
locally: the website plus the backend, with sample residents and the backend's built-in reply rules (no AI key).
The screens are the same as the deployed site; the assistant's exact wording can differ from the live AI.

## Changing the words or the clicks

Edit [`script.json`](script.json):

- `say`: what the narrator says. It is also the caption. Write `AI`, not `A.I.` (the dots make the voice pause).
- `caption` (optional): when the caption should be written differently from how it is spoken.
- `do`: what happens on screen during that line: `type` (text typed into the message box), `press` (a key, e.g.
  `Enter`), `click`, `hover`, `select` (a demo sign-in such as `R001`), `scroll`, `wait` (seconds), `goto` (a page,
  e.g. `/staff/`).
- `chapter`: the label shown in the corner during a scene. `cover`: the title card's words.
- `speed`: 1.0 is the voice's normal pace; the video uses 1.1.

## Rebuilding (about 5 minutes)

```bash
cd backend
PYTHONPATH=. uv run python ../demo-video/sample_workbook.py /tmp/mk/sample.xlsx
export DB_PATH=/tmp/mk/demo.sqlite3 DATA_PATH=/tmp/mk/sample.xlsx LLM_PROVIDER=mock LLM_MODEL=mock-deterministic-v1 RESIDENT_DATA_SOURCE=database CORS_ORIGINS=http://127.0.0.1:4173
uv run alembic upgrade head && uv run python -m app.seed_synthetic
uv run uvicorn app.main:app --port 8000 &
cd ../frontend && NEXT_STATIC_EXPORT=1 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npx next build
python3 -m http.server 4173 --bind 127.0.0.1 --directory out &
cd .. && SITE=http://127.0.0.1:4173 bash demo-video/make-video.sh
```

Delete `/tmp/mk/demo.sqlite3` and repeat the seed step before each take, so the reference number starts at
DEMO-WO-1001. Without `SITE`, the script records the static here.now preview instead.

Files: `voice.py` (narration), `record.cjs` (browser, cover, chapter labels), `assemble.py` (picture, voice and
captions), `make-video.sh` (runs them), `sample_workbook.py` (made-up residents).
