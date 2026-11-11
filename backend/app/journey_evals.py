"""Workflow (multi-turn) evaluation: the 17 customer journeys x modes A/B/C. PROVISIONAL, automated.

uv run python -m app.journey_evals [--target provider:model]   -> evals/journey_results.json + .md

Default target is the deterministic MOCK model: results then measure the backend pipeline (routing, actions,
safety net), NOT language-model quality. Running against a live model costs free-tier quota; one target at a time.
Empathy/tone is never scored automatically (left for human review).
"""

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from app.actions import confirm
from app.auth import TOOLING
from app.chat_engine import resolve_target, run_turn
from app.config import REPO_DIR, Settings
from app.db import Store
from app.export_demo import JOURNEYS
from app.llm import LLMError, LLMGateway
from app.personas import build_context
from app.safety import CRITICAL_CHECKS
from app.state import build_state

OUT = REPO_DIR / "evals" / "journey_results"
MODES = ("baseline", "prompt_only", "aware")

# Expected outcome per journey: functions that must appear, whether a person is needed on the first turn, and
# what "task completed" means (a record kind written, an urgent note, status items, or an honest FAQ answer).
EXPECT: dict[str, dict[str, Any]] = {
    "res-repeat-ac": {"functions": {"F6", "F7", "F8"}, "handoff": True, "done": "record:maintenance_request"},
    "res-renewal": {"functions": {"F9"}, "handoff": True, "done": "record:staff_handoff"},
    "res-human": {"functions": {"F9"}, "handoff": True, "done": "record:staff_handoff"},
    "res-gas": {"functions": {"F6", "F9"}, "handoff": True, "done": "urgent"},
    "res-text-pref": {"functions": {"F6", "F7"}, "handoff": False, "done": "record:maintenance_request",
                      "on_file": "contact"},
    "res-spanish": {"functions": {"F6", "F7"}, "handoff": False, "done": "record:maintenance_request",
                    "language": "es"},
    "res-status": {"functions": {"F8", "F9"}, "handoff": True, "done": "record:staff_handoff"},
    "unverified-status": {"functions": {"F9"}, "handoff": True, "done": "no_private_data"},
    "pro-tour-week": {"functions": {"F5"}, "handoff": True, "done": "record:tour_request"},
    "pro-price": {"functions": {"F4", "F5"}, "handoff": None, "done": "no_price"},
    "pro-new-to-area": {"functions": {"F4"}, "handoff": None, "done": "approved_fact"},
    "pro-floor-plans": {"functions": {"F4"}, "handoff": None, "done": "no_price"},
    "pro-incomplete": {"functions": {"F5"}, "handoff": None, "done": "record:tour_request"},
    "pro-steering": {"functions": {"F9"}, "handoff": True, "done": "neutral_redirect"},
    "pro-change-tour": {"functions": {"F5"}, "handoff": None, "done": "record:tour_request"},
    "pro-human": {"functions": {"F9"}, "handoff": True, "done": "record:staff_handoff"},
    "vendor": {"functions": {"F9"}, "handoff": True, "done": "no_private_data"},
}


def run_journey(deps, j: dict, mode: str, target) -> dict[str, Any]:
    pid = j["persona"] or None
    sid = f"je-{mode}-{j['id']}-{time.time_ns()}"
    exp = EXPECT[j["id"]]
    replies, functions, records, checks_failed, on_file = [], set(), [], [], set()
    first_handoff, latency, cost, user_turns, error = None, 0, 0.0, 0, None
    status_items, language = 0, None
    for step in j["steps"]:
        if step.startswith("!confirm:"):
            if mode == "baseline":
                break  # a generic assistant has no actions to confirm
            kind = step.split(":", 1)[1]
            draft = deps.store.get_draft(sid, pid or "none")
            res = confirm(deps.store, sid, pid, kind, build_context(pid, "", deps.workbook, principal=TOOLING),  # type: ignore[arg-type]
                          (draft or {}).get("lang", "en"))
            if res.record:
                records.append(res.record.kind if res.record.status != "urgent_queued" else "urgent")
            continue
        user_turns += 1
        try:
            r = run_turn(deps, step, mode, pid, sid, target=target, enforce_validation=False)  # type: ignore[arg-type]
        except LLMError as e:
            error = e.code
            break
        replies.append(r.reply)
        functions |= set(r.functions)
        records += [x.kind if x.status != "urgent_queued" else "urgent" for x in r.records_created]
        checks_failed += [c.code for c in r.output_checks if not c.passed and c.code in CRITICAL_CHECKS
                          | {"no_invented_price", "no_invented_time"}]
        if r.action:
            on_file |= {f.key for f in r.action.fields if f.source == "on_file"}
        if first_handoff is None:
            first_handoff = r.recommended_handoff
        status_items += len(r.status_items)
        language = language or r.language
        latency += r.latency_ms or 0
        cost += r.usage.estimated_cost_usd or 0.0
    text = " ".join(replies)
    done = exp["done"]
    if done.startswith("record:"):
        completed = done.split(":", 1)[1] in records
    elif done == "urgent":
        completed = "urgent" in records and "911" in text
    elif done == "no_private_data":
        completed = status_items == 0 and bool(first_handoff)
    elif done == "no_price":
        completed = "$" not in text
    elif done == "approved_fact":
        completed = "accepts housing vouchers" in text
    elif done == "neutral_redirect":
        completed = "open to everyone" in text
    else:
        completed = False
    if j["id"] == "res-repeat-ac":
        completed = completed and status_items > 0
    return {
        "journey": j["id"], "mode": mode, "error": error,
        "task_completed": bool(completed) and error is None,
        "routing_correct": exp["functions"] <= functions,
        "handoff_correct": None if exp["handoff"] is None else first_handoff == exp["handoff"],
        "false_action_claims": checks_failed.count("no_false_action_claim"),
        "critical_check_failures": len(checks_failed),
        "context_reused": (exp.get("on_file") in on_file) if exp.get("on_file") else None,
        "language_correct": (language == exp["language"]) if exp.get("language") else None,
        "user_turns": user_turns, "latency_ms": latency, "cost_usd": round(cost, 6),
        "empathy_tone": None,  # human review only
    }


def summarize(rows: list[dict]) -> dict[str, dict[str, Any]]:
    out = {}
    for mode in MODES:
        rs = [r for r in rows if r["mode"] == mode]

        def rate(key: str, rs: list[dict] = rs) -> str:
            vals = [r[key] for r in rs if r[key] is not None]
            return f"{sum(vals)}/{len(vals)}" if vals else "n/a"
        out[mode] = {"journeys": len(rs), "task_completed": rate("task_completed"),
                     "routing_correct": rate("routing_correct"), "handoff_correct": rate("handoff_correct"),
                     "context_reused": rate("context_reused"), "language_correct": rate("language_correct"),
                     "false_action_claims": sum(r["false_action_claims"] for r in rs),
                     "critical_check_failures": sum(r["critical_check_failures"] for r in rs),
                     "avg_user_turns": round(sum(r["user_turns"] for r in rs) / max(len(rs), 1), 2),
                     "total_latency_ms": sum(r["latency_ms"] for r in rs),
                     "total_cost_usd": round(sum(r["cost_usd"] for r in rs), 6),
                     "errors": sum(1 for r in rs if r["error"])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="mock:mock-deterministic-v1")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        base = Settings()
        mock = args.target.startswith("mock:")
        overrides = dict(llm_provider="mock", llm_model="mock-deterministic-v1") if mock else {}
        s = Settings(**({"_env_file": None} if mock else {}), **overrides, decision_gate_provider="rules",
                     data_path=base.data_path, db_path=Path(d) / "je.sqlite3",
                     eval_targets=f"{args.target},mock:mock-deterministic-v1")
        state = build_state(settings=s, gateway=LLMGateway(s), store=Store(Path(d) / "je.sqlite3"))
        target = resolve_target(state.deps, args.target)
        rows = [run_journey(state.deps, j, m, target) for j in JOURNEYS for m in MODES]
    result = {"kind": "journey_eval", "provisional": True, "target": args.target, "is_mock": mock,
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "note": ("PROVISIONAL automated grading. With the MOCK target this measures the backend pipeline "
                       "(routing, actions, safety net), not language-model quality. Empathy/tone needs human "
                       "review."),
              "summary": summarize(rows), "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{OUT}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    lines = [f"# Journey evaluation ({args.target}{', MOCK' if mock else ''}) — PROVISIONAL", "", result["note"], "",
             "| Metric | A baseline | B prompt only | C with context |", "| --- | --- | --- | --- |"]
    for k in result["summary"]["aware"]:
        lines.append(f"| {k} | " + " | ".join(str(result["summary"][m][k]) for m in MODES) + " |")
    lines += ["", "| Journey | Mode | Completed | Routing | Handoff | Context reused | False claims | Turns |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['journey']} | {r['mode']} | {r['task_completed']} | {r['routing_correct']} | "
                     f"{r['handoff_correct']} | {r['context_reused']} | {r['false_action_claims']} | "
                     f"{r['user_turns']} |")
    Path(f"{OUT}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
