# CodeGraph evaluation (developer tool)

**Tool:** [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph), a local SQLite knowledge graph of symbols and call edges, exposed as an MCP tool (`codegraph_explore`) and a CLI (`codegraph explore "<query>"`). It is **not** part of the product and nothing at runtime depends on it.

## Setup status in this repo

CodeGraph was already installed and indexed on this machine when the sprint started (an untracked `.codegraph/` directory). This sprint added `.codegraph/` to `.gitignore` so the index is never committed.

The current Claude Code hook (`codegraph prompt-hook`) and permission are **local, uncommitted edits** to `.claude/settings.json`, along with untracked `.claude/CLAUDE.md`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`, `.codex/`, `.cursor/` and `.gemini/`. `.claude/` is maintained by Ross IT, so these were **left uncommitted**. To use CodeGraph on another clone:

1. Install it by following the README at https://github.com/colbymchenry/codegraph.
2. From the repo root, build the index (`codegraph init` / `codegraph index` per the README). This creates `.codegraph/`, which is git-ignored.
3. Register the MCP server in your *user-level* Claude Code config, not in the repo's `.claude/`, unless Ross IT agrees to add it.

## Trace: one conversation, end to end

Query: `chat run_turn DecisionGateService.classify apply_safety_floor select_workflow build_handoff`

CodeGraph returned in one call:
- the path `api/chat.py:chat → chat_engine.run_turn → workflows.select_workflow`;
- the verbatim source of each symbol;
- a blast-radius summary: `run_turn` has several callers (API, demo export, tests), and `apply_safety_floor` by `service.py`.

What it missed:
- The hop `run_turn → DecisionGateService.classify`. This is called as `deps.gates.classify(...)` through a dataclass attribute, so CodeGraph listed `classify` as a related symbol but not on the path.
- The browser → backend link. `frontend/src/lib/api.ts` calls `fetch(`${API_BASE}/api/chat`)`, and CodeGraph does not connect that to the FastAPI route `@router.post("/chat")` across the HTTP boundary. The frontend half came back as a separate, related cluster (`ChatWorkbench.send`).

## Compared with standard exploration

| | CodeGraph | grep + reading files |
|---|---|---|
| Finding a symbol and its callers before editing | Fast: one call with source and blast radius | Several greps, and dynamic calls are easy to miss |
| Impact of changing a shared function (`run_turn`, `output_checks`) | Good: lists callers and tests | Manual |
| Attribute or DI calls (`deps.gates.classify`) | Partial | grep finds the text but not the type |
| Cross-language HTTP flow (TS fetch → Python route) | Not linked | grep on the `/api/...` path string works well |
| Config, docs and Mermaid | Not indexed | Needed |

## Verdict

CodeGraph is useful but not essential for a codebase this size (about 3.5k lines of Python and 1.5k of TSX). It saves the most time on "what breaks if I change X" questions before editing the shared pipeline. For frontend ↔ backend contract questions, grep on the endpoint path is still the better tool. Keep it as an optional personal tool. Do not make it a requirement for students.
