"""Run the persona usability suite and write structured records + a report.

  uv run python -m app.usability.run --base-url http://127.0.0.1:8000      # real HTTP endpoints (default)
  uv run python -m app.usability.run --in-process                          # FastAPI TestClient, temp DB, mock

Outputs (evals/usability/): results.json (one structured record per scenario incl. the full conversation),
report.md (summary tables). The model used is whatever the backend is configured with; each record says
whether it was mock or live. Mock results measure the product pipeline, NOT language-model quality.
"""

import argparse
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import REPO_DIR
from app.usability.evaluator import evaluate
from app.usability.personas import PERSONAS
from app.usability.scenarios import SCENARIOS
from app.usability.simulator import HttpTransport, Transport, run_scenario

OUT = REPO_DIR / "evals" / "usability"
OUTCOMES = ("success", "simulated_success", "blocked", "partial", "failure")


class InProcessTransport:
    def __init__(self, client):
        self.c = client

    def post(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        r = self.c.post(path, json=body)
        return r.status_code, r.json()


def run_all(transport: Transport, only: list[str] | None = None) -> list[dict[str, Any]]:
    tag = datetime.now(UTC).strftime("%H%M%S") + str(time.time_ns())[-4:]
    rows = []
    for sc in SCENARIOS:
        if only and sc.id not in only:
            continue
        convo = run_scenario(transport, sc, tag)
        rows.append({**evaluate(sc, convo), "conversation": convo["turns"]})
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(PERSONAS[r["persona"]].group, []).append(r)

    def agg(rs: list[dict[str, Any]]) -> dict[str, Any]:
        lat = [x for r in rs for x in r["latency_ms"] if x is not None]
        return {
            "scenarios": len(rs), "outcomes": {o: sum(r["outcome"] == o for r in rs) for o in OUTCOMES},
            "avg_user_turns": round(statistics.mean(r["user_turns"] for r in rs), 2) if rs else 0,
            "questions_asked": sum(r["questions_asked"] for r in rs),
            "unnecessary_questions": sum(len(r["unnecessary_questions"]) for r in rs),
            "repeated_questions": sum(len(r["repeated_questions"]) for r in rs),
            "repeated_replies": sum(len(r["repeated_replies"]) for r in rs),
            "unwanted_records": sum(len(r["unwanted_records"]) for r in rs),
            "routing_ok": sum(r["routing_ok"] for r in rs), "handoff_ok": sum(r["handoff_ok"] for r in rs),
            "context_checked": sum(r["context_ok"] is not None for r in rs),
            "context_ok": sum(bool(r["context_ok"]) for r in rs),
            "false_claims": sum(len(r["false_claims"]) for r in rs),
            "safety_violations": sum(len(r["safety_violations"]) for r in rs),
            "avg_friction": round(statistics.mean(r["friction"] for r in rs), 2) if rs else 0,
            "latency_ms_p50": int(statistics.median(lat)) if lat else None,
            "latency_ms_max": max(lat) if lat else None,
        }

    return {"all": agg(rows), **{g: agg(rs) for g, rs in sorted(groups.items())},
            "execution": dict(Counter(r["execution"] for r in rows)),
            "models": sorted({m for r in rows for m in r["models"]})}


def write(rows: list[dict[str, Any]], meta: dict[str, Any], label: str = "") -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    doc = {"meta": meta, "summary": summary, "results": rows}
    sfx = f"-{label}" if label else ""
    (OUT / f"results{sfx}.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")
    (OUT / f"report{sfx}.md").write_text(render_md(doc))
    return doc


def render_md(doc: dict[str, Any]) -> str:
    s, meta = doc["summary"], doc["meta"]
    lines = [
        "# Persona usability suite: results", "",
        f"Run {meta['run_at']} against `{meta['target']}`. Execution: {s['execution']}. Models: {s['models']}.", "",
        "**PROVISIONAL, automated.** " + (
            "Every turn used the deterministic MOCK model, so this measures the product pipeline (routing, "
            "questions, actions, safety rules, honesty), not language-model quality."
            if s["execution"].get("mock") == len(doc["results"]) else
            "Includes live-model turns; live results are small-sample."),
        "Simulated success = a record was written to the PROTOTYPE store (not Yardi, nobody notified). "
        "Blocked = the best answer needs a missing integration or McKinley approval and the product said so.", "",
        "| Group | Scenarios | Success | Simulated | Blocked | Partial | Failure | Avg turns | Unneeded Qs | "
        "Repeated Qs | Repeated replies | Unwanted records | Routing ok | Handoff ok | Context ok | False claims | "
        "Safety violations | Friction |",
        "| --- |" + " ---: |" * 17,
    ]
    for g in ("resident", "prospect", "adversarial", "all"):
        a = s.get(g)
        if not a:
            continue
        o = a["outcomes"]
        lines.append(f"| {g} | {a['scenarios']} | {o['success']} | {o['simulated_success']} | {o['blocked']} | "
                     f"{o['partial']} | {o['failure']} | {a['avg_user_turns']} | {a['unnecessary_questions']} | "
                     f"{a['repeated_questions']} | {a['repeated_replies']} | {a['unwanted_records']} | "
                     f"{a['routing_ok']}/{a['scenarios']} |"
                     f" {a['handoff_ok']}/{a['scenarios']}"
                     f" | {a['context_ok']}/{a['context_checked']} | {a['false_claims']} | {a['safety_violations']} | "
                     f"{a['avg_friction']} |")
    lines += ["", f"Latency p50 {s['all']['latency_ms_p50']} ms, max {s['all']['latency_ms_max']} ms.", "",
              "## Per scenario", "",
              "| Scenario | Persona | Risk | Outcome | Turns | Qs | Unneeded | Notes / violations |",
              "| --- | --- | --- | --- | ---: | ---: | ---: | --- |"]
    for r in doc["results"]:
        extra = "; ".join(r["safety_violations"] + r["unnecessary_questions"] + r["notes"]
                          + ([f"blocked by: {r['blocked_by']}"] if r["blocked_by"] else []))
        lines.append(f"| {r['scenario']} | {r['persona']} | {r['risk']} | **{r['outcome']}** | {r['user_turns']} | "
                     f"{r['questions_asked']} | {len(r['unnecessary_questions'])} | {extra.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--label", default="", help="suffix for the output files, e.g. baseline")
    ap.add_argument("--note", default="", help="free text recorded in meta (e.g. which commit the server runs)")
    a = ap.parse_args()
    if a.in_process:
        import tempfile

        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app

        tmp = tempfile.mkdtemp()
        app = create_app(Settings(llm_provider="mock", llm_model="mock-deterministic-v1",
                                  db_path=Path(tmp) / "ux.sqlite3", _env_file=None))  # type: ignore[call-arg]
        transport: Transport = InProcessTransport(TestClient(app))
        target = "in-process TestClient (mock)"
    else:
        transport, target = HttpTransport(a.base_url), a.base_url
    rows = run_all(transport, a.only)
    meta = {"run_at": datetime.now(UTC).isoformat(timespec="seconds"), "target": target,
            "scenarios": len(rows), "personas": len({r["persona"] for r in rows})}
    if a.no_write:
        print(json.dumps(summarize(rows), indent=2))
        return
    meta["note"] = a.note
    doc = write(rows, meta, a.label)
    print(json.dumps(doc["summary"]["all"], indent=2))
    for r in rows:
        if r["outcome"] in ("failure", "partial"):
            print(f"{r['outcome']:8} {r['scenario']}: {'; '.join(r['safety_violations'] + r['notes'])[:220]}")


if __name__ == "__main__":
    main()
