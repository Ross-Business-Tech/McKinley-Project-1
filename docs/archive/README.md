# Archive: evidence kept in the tree

These files record what was true **at their date**; numbers and file names in them are not updated.

| Record | Why it is kept |
| --- | --- |
| [evaluation/five-case-live-run-2026-11-01.md](evaluation/five-case-live-run-2026-11-01.md) + [`.json`](evaluation/five-case-live-run-2026-11-01.json) | The only real-model comparison of the five reference cases (raw outputs + review) |
| [evaluation/sprint7-live-smoke-metadata.json](evaluation/sprint7-live-smoke-metadata.json) | Metadata (no message text) of the Sprint 7 live OpenRouter smoke run |

Everything else historical (sprint 1–9 reports, changelogs, the sprint-2 screenshots, design-skill notes, the v1
diagram, generated evaluation outputs under `evals/`) was removed in the repository simplification and stays in
Git history: `git show 59c155c:<path>`, for example `git show 59c155c:docs/evaluation/SPRINT7_GENERALIZATION.md`.
