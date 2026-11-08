# evals/live: controlled live A/B/C evaluation

**Status: BLOCKED** until `OPENROUTER_API_KEY` is set in `backend/.env` (see `status.json`). Full description,
comparability rules and budget flags: [`docs/evaluation/live-llm.md`](../../docs/evaluation/live-llm.md).

| File | What it is |
| --- | --- |
| `status.json` | live run status (`blocked`, why, key presence as booleans) |
| `preflight.json` | public OpenRouter model list check (no key needed) |
| `results-mock-dryrun.json`, `report-mock-dryrun.md`, `status-mock-dryrun.json` | MOCK dry run: proves recording only, every record `comparable: false` |

```bash
cd backend
uv run python -m app.live_eval.preflight          # exit code 3 = blocked
uv run python -m app.live_eval.abc --target recommended --label live-v1
```
