"""CLI: run the five-case eval and write evals/actual_results.json.

    uv run python -m app.run_evals                       # default target (LLM_PROVIDER / LLM_MODEL)
    uv run python -m app.run_evals --targets mock:mock-deterministic-v1 openrouter:google/gemma-4-31b-it:free
"""

import argparse
import json

from app.chat_engine import resolve_target
from app.evals import export_results, regrade_run, run_evals, summarize
from app.llm import LLMError
from app.state import build_state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--targets", nargs="*", help="provider:model keys (must be in EVAL_TARGETS or the default)")
    ap.add_argument("--cases", nargs="*", help="case ids (default: all five)")
    ap.add_argument("--regrade", type=int, metavar="RUN_ID",
                    help="re-run automated grading on stored replies of RUN_ID (no model calls) and re-export")
    args = ap.parse_args()

    state = build_state()
    if args.regrade:
        n = regrade_run(state.deps, state.store, args.regrade)
        export_results(state.store, args.regrade, state.deps.settings.eval_results_path)
        print(f"Regraded {n} stored results of run {args.regrade}; exported {state.deps.settings.eval_results_path}")
        return 0
    if state.data_error:
        print(f"WARNING: {state.data_error}")
    try:
        targets = [resolve_target(state.deps, t) for t in (args.targets or [None])]
    except LLMError as e:
        print(f"ERROR {e.code}: {e.message}")
        return 2
    run_id = run_evals(state.deps, state.store, args.cases, None, targets)
    payload = export_results(state.store, run_id, state.deps.settings.eval_results_path)
    for r in payload["results"]:
        status = r.get("provisional_verdict") or f"ERROR {r.get('error_code')}"
        mock = " [MOCK]" if r.get("is_mock") else ""
        print(f"{r['target']:<50} {r['case_id']:<30} {r['mode']:<8} {status}{mock}")
        if r.get("error_message"):
            print(f"    {r['error_message']}")
    print(json.dumps(summarize(payload["results"]), indent=2))
    print(f"Wrote {state.deps.settings.eval_results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
