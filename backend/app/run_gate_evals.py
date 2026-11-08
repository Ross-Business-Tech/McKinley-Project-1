"""CLI: uv run python -m app.run_gate_evals --providers rules,llm,jev [--out ../evals/gate_results.json]

`llm` uses DECISION_GATE_LLM_TARGET (or the default chat target) and makes one call per scenario.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.gate_evals import evaluate_gates
from app.state import build_state


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="rules")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    state = build_state()
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    result = evaluate_gates(state.deps, providers)
    result["generated_at"] = datetime.now(UTC).isoformat()
    print(json.dumps(result["summary"], indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
