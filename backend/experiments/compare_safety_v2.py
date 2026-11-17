"""Offline comparison of the safety experiment against production on labelled message sets (no model calls).

    cd backend && uv run python -m experiments.compare_safety_v2 ../evals/final/holdout/safety.json \
        ../evals/acceptance/investigation/proposed_regression_set.json

Each message is decided under stub classifier answers. A stub "none" on a genuine emergency is the classifier being
WRONG: the "lost guidance" column is the worst case, not a prediction.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from app.risk.detect import detect
from experiments.safety_v2 import decide
from tests.test_experiment_safety_v2 import SCENARIOS


def load(path: str) -> list[tuple[str, str, str]]:
    data = json.load(open(path))
    rows = data["single"] if isinstance(data, dict) else data
    out = []
    for r in rows:
        exp = r["expected"]
        benign = exp in ("no_alarm", "none")
        out.append((r["id"], r["text"], "benign" if benign else "genuine"))
    return out


def main(paths: list[str]) -> None:
    rows = [x for p in paths for x in load(p)]
    print(f"{len(rows)} messages ({Counter(r[2] for r in rows)})")
    for name, s in SCENARIOS.items():
        fixed, lost, changes = 0, [], Counter()
        for cid, text, label in rows:
            d = decide(detect(text, []), s, text)
            if d.changed_by:
                changes[d.changed_by] += 1
                if label == "benign":
                    fixed += 1
                else:
                    lost.append(cid)
        print(f"  {name:<17} changed={sum(changes.values()):>3} {dict(changes)}  benign quieted={fixed:>2}  "
              f"genuine lost={len(lost)} {lost}")


if __name__ == "__main__":
    main(sys.argv[1:])
