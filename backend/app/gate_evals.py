"""Gate comparison harness: rules vs structured LLM vs Jev on the labelled eval scenarios.

Measures routing only (no response generation). The rules gate is deterministic and free; `llm` makes one model
call per scenario; `jev` needs TYPESAFE_API_KEY. Unavailable providers are reported as fallbacks, never hidden.
"""

import time
from typing import Any

from app.auth import TOOLING
from app.chat_engine import EngineDeps, clean_message
from app.evals import CASES
from app.gates import GateContext
from app.personas import build_context
from app.workflows import select_workflow


def gate_scenarios() -> list[dict[str, Any]]:
    return [{"id": c.id, "title": c.title, "suite": c.suite, "persona_id": c.persona_id, "message": c.message,
             "expected_intent": c.expected_intent, "expected_workflow": c.expected_workflow,
             "expected_urgency": c.expected_urgency, "expect_handoff": c.expect_handoff}
            for c in CASES if c.expected_intent]


def evaluate_gates(deps: EngineDeps, providers: list[str]) -> dict[str, Any]:
    assert deps.gates is not None
    rows: list[dict[str, Any]] = []
    for sc in gate_scenarios():
        msg = clean_message(sc["message"])
        ctx = build_context(sc["persona_id"] or None, msg, deps.workbook, principal=TOOLING)
        gctx = GateContext(audience=ctx.audience, identity_verified=ctx.persona_kind == "resident" and ctx.record_found,
                           record_found=ctx.record_found, topics=ctx.topics,
                           context_flags=frozenset(f.name for f in ctx.fields if f.name.endswith("_flag")))
        for prov in providers:
            start = time.perf_counter()
            d = deps.gates.classify(msg, gctx, prov)
            wf = select_workflow(d).id
            exp_h = sc["expect_handoff"]
            critical = ((sc["expected_urgency"] == "emergency" and d.urgency != "emergency")
                        or (exp_h is True and not d.requires_human))
            rows.append({
                "scenario": sc["id"], "provider": prov, "decision_source": d.decision_source,
                "fallback_used": d.fallback_used, "fallback_reason": d.fallback_reason,
                "intent": d.intent, "intent_ok": d.intent == sc["expected_intent"],
                "workflow": wf, "workflow_ok": sc["expected_workflow"] is None or wf == sc["expected_workflow"],
                "urgency": d.urgency,
                "urgency_ok": None if sc["expected_urgency"] is None else d.urgency == sc["expected_urgency"],
                "requires_human": d.requires_human,
                "handoff_ok": None if exp_h is None else d.requires_human == exp_h,
                "critical_miss": critical, "confidence": d.confidence, "risk_flags": d.risk_flags,
                "overrides": d.overrides, "latency_ms": int((time.perf_counter() - start) * 1000),
                "input_tokens": d.gate_usage.input_tokens if d.gate_usage else None,
                "output_tokens": d.gate_usage.output_tokens if d.gate_usage else None,
                "estimated_cost_usd": d.gate_usage.estimated_cost_usd if d.gate_usage else None,
            })
    summary = {}
    for prov in providers:
        rs = [r for r in rows if r["provider"] == prov]

        def rate(key: str, rs: list[dict[str, Any]] = rs) -> str:
            scored = [r[key] for r in rs if r[key] is not None]
            return f"{sum(scored)}/{len(scored)}"
        summary[prov] = {
            "scenarios": len(rs), "intent_correct": rate("intent_ok"), "workflow_correct": rate("workflow_ok"),
            "urgency_correct": rate("urgency_ok"), "handoff_correct": rate("handoff_ok"),
            "critical_misses": sum(r["critical_miss"] for r in rs),
            "fallbacks": sum(r["fallback_used"] for r in rs),
            "sources": sorted({r["decision_source"] for r in rs}),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in rs) / len(rs)) if rs else None,
            "input_tokens": sum(r["input_tokens"] or 0 for r in rs),
            "output_tokens": sum(r["output_tokens"] or 0 for r in rs),
        }
    return {
        "note": "Automated comparison against scenario labels written by the developers. Not human-reviewed. "
                "Sources 'mock' are deterministic stand-ins, not model quality evidence.",
        "availability": deps.gates.availability(),
        "summary": summary,
        "rows": rows,
    }
