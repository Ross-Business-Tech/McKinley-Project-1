"""Run the persona usability suite (48 scenarios) or the customer-journey suite (35 journeys).

  uv run python -m app.usability.run --base-url http://127.0.0.1:8000      # persona suite, real HTTP endpoints
  uv run python -m app.usability.run --in-process                          # persona suite, TestClient, mock

  uv run python -m app.usability.run --suite journeys                      # journeys, in-process MOCK (default)
  uv run python -m app.usability.run --suite journeys --live --base-url http://127.0.0.1:8001 --max-calls 40
                                                                           # journeys over HTTP, stops at N model
                                                                           # replies (reply_source == "model")
Journey outputs: evals/usability/journeys-<label>.json and .md (label defaults to "mock" / "live").

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
            "Every reply came from the deterministic MOCK model or fixed backend templates (no live model), so "
            "this measures the product pipeline (routing, questions, actions, safety rules, honesty), not "
            "language-model quality."
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


def export_summary(labels: list[str]) -> Path:
    """Compact summary of several runs (no transcripts) for the staff console's Usability tab."""
    runs = []
    for label in labels:
        doc = json.loads((OUT / f"results-{label}.json").read_text())
        runs.append({
            "label": label, "meta": doc["meta"], "summary": doc["summary"],
            "rows": [{k: r[k] for k in ("scenario", "persona", "goal", "risk", "outcome", "blocked_by", "user_turns",
                                        "questions_asked", "routing_ok", "handoff_ok", "context_ok", "friction",
                                        "execution")}
                     | {"group": PERSONAS[r["persona"]].group, "unnecessary": len(r["unnecessary_questions"]),
                        "repeated_replies": len(r.get("repeated_replies", [])),
                        "unwanted_records": len(r.get("unwanted_records", [])),
                        "false_claims": len(r["false_claims"]), "safety_violations": len(r["safety_violations"]),
                        "notes": "; ".join(r["safety_violations"] + r["notes"])[:220]}
                     for r in doc["results"]],
        })
    out = REPO_DIR / "frontend" / "src" / "lib" / "usability.json"
    out.write_text(json.dumps({"runs": runs}, indent=1, default=str) + "\n")
    return out


def _mock_state(workbook=None):  # noqa: ANN001, ANN202 - small helper shared by the suites and tests
    import tempfile

    from app.config import Settings
    from app.db import Store
    from app.llm import LLMGateway
    from app.state import build_state, set_state

    settings = Settings(llm_provider="mock", llm_model="mock-deterministic-v1",  # type: ignore[call-arg]
                        db_path=Path(tempfile.mkdtemp()) / "ux.sqlite3", _env_file=None)
    state = build_state(settings=settings, gateway=LLMGateway(settings), store=Store(settings.db_path),
                        workbook=workbook)
    set_state(state)
    return state


def run_journeys(transport: Transport, only: list[str] | None = None, *, store=None,  # noqa: ANN001
                 workbook=None) -> list[dict[str, Any]]:
    """Simulate each journey, then grade it with the separate evaluator. ``store`` (mock runs) lets the evaluator
    see the records the database really holds for the session; live runs grade what the responses showed."""
    from app.usability.journey_evaluator import PrivacyLexicon, evaluate_journey
    from app.usability.journey_simulator import BudgetTransport, run_journey
    from app.usability.journeys import JOURNEYS

    tag = datetime.now(UTC).strftime("%H%M%S") + str(time.time_ns())[-4:]
    lex = PrivacyLexicon.from_workbook(workbook) if workbook else None
    rows = []
    for j in JOURNEYS:
        if only and j.id not in only:
            continue
        if isinstance(transport, BudgetTransport) and transport.calls >= transport.max_calls:
            rows.append({"journey": j.id, "category": j.category, "persona": j.persona.id, "goal": j.goal,
                         "verdict": "NOT_RUN", "reasons": ["model-call budget reached before this journey"],
                         "execution": "NONE"})
            continue
        convo = run_journey(transport, j, tag)
        db = allowed = None
        if store is not None:
            db = store.records(session_id=convo["session_id"], limit=50)
            allowed = {r["id"] for r in store.records(persona_id=j.persona.identity, limit=200)} \
                if j.persona.identity else set()
        rows.append(evaluate_journey(j, convo, db_records=db, privacy=lex, allowed_refs=allowed))
    return rows


def summarize_journeys(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from app.usability.journeys import CATEGORIES

    def agg(rs: list[dict[str, Any]]) -> dict[str, Any]:
        ran = [r for r in rs if r["verdict"] != "NOT_RUN"]
        f = [r["friction"] for r in ran]
        return {
            "journeys": len(rs), "ran": len(ran),
            "verdicts": {v: sum(r["verdict"] == v for r in rs) for v in ("PASS", "WARN", "FAIL", "INCOMPLETE",
                                                                         "NOT_RUN")},
            "completed": sum(r["completed"] for r in ran),
            "avg_turns": round(statistics.mean(x["user_turns"] for x in f), 2) if f else 0,
            "questions": sum(x["questions"] for x in f),
            "repeated_questions": sum(len(x["repeated_questions"]) for x in f),
            "unnecessary_questions": sum(len(x["unnecessary_questions"]) for x in f),
            "repeated_replies": sum(len(x["repeated_replies"]) for x in f),
            "duplicate_records": sum(len(r["side_effects"]["duplicates"]) for r in ran),
            "honesty_safety_flags": sum(not c["ok"] for r in ran for c in r["safety_checks"]),
            "model_calls": sum(x["model_calls"] for x in f),
        }

    by = {c: agg([r for r in rows if r["category"] == c]) for c in CATEGORIES}
    return {"all": agg(rows), **by, "execution": dict(Counter(r["execution"] for r in rows))}


def write_journeys(rows: list[dict[str, Any]], meta: dict[str, Any], label: str) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {"meta": meta, "summary": summarize_journeys(rows), "results": rows}
    (OUT / f"journeys-{label}.json").write_text(json.dumps(doc, indent=2, default=str) + "\n")
    (OUT / f"journeys-{label}.md").write_text(render_journeys_md(doc))
    return doc


def render_journeys_md(doc: dict[str, Any]) -> str:
    s, meta = doc["summary"], doc["meta"]
    mode = meta["mode"]
    lines = [f"# Customer-journey suite: {mode} results", "",
             f"Run {meta['run_at']} against `{meta['target']}`. Execution per journey: {s['execution']}. "
             f"{meta.get('note') or ''}", "",
             ("**MOCK.** Replies came from the deterministic mock model or fixed backend templates: this measures the "
              "product pipeline (routing, cards, records, safety rules, honesty), not language-model quality."
              if mode == "MOCK" else
              f"**LIVE** (small sample; model-call budget {meta.get('max_calls')}, used {s['all']['model_calls']})."),
             "Records are written to the PROTOTYPE store only (not Yardi; nobody is notified).", "",
             "| Category | Journeys | PASS | WARN | FAIL | Incomplete | Completed | Avg turns | Repeated Qs | "
             "Unneeded Qs | Repeated replies | Duplicates | Honesty/safety flags |", "| --- |" + " ---: |" * 12]
    from app.usability.journeys import CATEGORIES
    for c in (*CATEGORIES, "all"):
        a = s[c]
        v = a["verdicts"]
        lines.append(f"| {c} | {a['journeys']} | {v['PASS']} | {v['WARN']} | {v['FAIL']} | "
                     f"{v['INCOMPLETE'] + v['NOT_RUN']} | {a['completed']}/{a['ran']} | {a['avg_turns']} | "
                     f"{a['repeated_questions']} | {a['unnecessary_questions']} | {a['repeated_replies']} | "
                     f"{a['duplicate_records']} | "
                     f"{a['honesty_safety_flags']} |")
    lines += ["", "## Per journey", "", "| Journey | Category | Verdict | Turns | Records | Reasons |",
              "| --- | --- | --- | ---: | --- | --- |"]
    for r in doc["results"]:
        recs = ", ".join(f"{k}x{n}" for k, n in (r.get("side_effects") or {}).get("by_kind", {}).items()) or "-"
        turns = (r.get("friction") or {}).get("user_turns", 0)
        why = "; ".join(r["reasons"])[:300].replace("|", "/")
        lines.append(f"| {r['journey']} | {r['category']} | **{r['verdict']}** | {turns} | {recs} | {why} |")
    return "\n".join(lines) + "\n"


def main_journeys(a: argparse.Namespace) -> None:
    from app.usability.journey_simulator import BudgetTransport

    store = workbook = None
    if a.live:
        if not a.max_calls or a.max_calls < 1:
            raise SystemExit("--live needs --max-calls N (the model-call budget)")
        transport: Transport = BudgetTransport(HttpTransport(a.base_url), a.max_calls)
        target, mode = a.base_url, "LIVE"
        try:  # the same synthetic workbook, locally, for the other-resident privacy check (never sent anywhere)
            from app.config import BACKEND_DIR
            from app.context import load_workbook
            workbook = load_workbook(BACKEND_DIR / "data" / "um_ai_sprint_sample_residents.xlsx")
        except Exception:  # noqa: BLE001 - privacy lexicon is optional; record-id checks still run
            workbook = None
    else:
        from fastapi.testclient import TestClient

        from app.main import app
        state = _mock_state()
        store, workbook = state.store, state.deps.workbook
        transport, target, mode = InProcessTransport(TestClient(app)), "in-process TestClient (mock)", "MOCK"
    rows = run_journeys(transport, a.only, store=store, workbook=workbook)
    execs = {r["execution"] for r in rows} - {"NONE"}
    if mode == "LIVE" and execs <= {"MOCK"}:
        mode = "MOCK"  # a backend running the mock over HTTP is still a mock run
    label = a.label or mode.lower()
    meta = {"run_at": datetime.now(UTC).isoformat(timespec="seconds"), "target": target, "mode": mode,
            "suite": "journeys", "journeys": len(rows), "max_calls": a.max_calls if a.live else None,
            "privacy_lexicon": workbook is not None, "note": a.note}
    if a.no_write:
        print(json.dumps(summarize_journeys(rows), indent=2))
        return
    doc = write_journeys(rows, meta, label)
    print(json.dumps({k: v for k, v in doc["summary"].items() if k != "all"} | {"all": doc["summary"]["all"]},
                     indent=1))
    for r in rows:
        if r["verdict"] in ("FAIL", "INCOMPLETE"):
            print(f"{r['verdict']:10} {r['journey']}: {'; '.join(r['reasons'])[:240]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=("persona", "journeys"), default="persona",
                    help="persona = the 48 persona scenarios; journeys = the 35 adaptive customer journeys")
    ap.add_argument("--live", action="store_true", help="journeys: send to --base-url over HTTP (needs --max-calls)")
    ap.add_argument("--max-calls", type=int, default=0, help="journeys --live: stop after N model-written replies")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--label", default="", help="suffix for the output files, e.g. baseline")
    ap.add_argument("--note", default="", help="free text recorded in meta (e.g. which commit the server runs)")
    ap.add_argument("--export-summary", default="", help="comma-separated labels -> frontend/src/lib/usability.json")
    a = ap.parse_args()
    if a.suite == "journeys":
        main_journeys(a)
        return
    if a.export_summary:
        print(export_summary([x for x in a.export_summary.split(",") if x]))
        return
    if a.in_process:
        import tempfile

        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.db import Store
        from app.llm import LLMGateway
        from app.main import app
        from app.state import build_state, set_state

        settings = Settings(llm_provider="mock", llm_model="mock-deterministic-v1",  # type: ignore[call-arg]
                            db_path=Path(tempfile.mkdtemp()) / "ux.sqlite3", _env_file=None)
        set_state(build_state(settings=settings, gateway=LLMGateway(settings), store=Store(settings.db_path)))
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
