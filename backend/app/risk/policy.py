"""Layer 3: explicit, conservative combination of the deterministic and semantic results.

Rules are applied in order; the first that fires decides. Each has an id recorded on the decision.
  R1 deterministic emergency (message or conversation window)  -> full alert. The semantic layer cannot remove it;
     a disagreement is recorded. If the semantic layer also sees self-harm, the 988 line is added.
  R2 semantic emergency, or urgent + immediate danger           -> full alert (semantic may ADD an alert).
  R3 deterministic "joking" self-harm                           -> 988 care line (never silent).
  R4 semantic urgent / uncertain with a category                -> category care line; staff check for self-harm.
  R5 deterministic hypothetical / past hazard                   -> calm safety info (same approved steps, no alarm).
  R6 deterministic care tier: distress / unwell                 -> that care line (semantic cannot remove it).
  R4u semantic "uncertain" with no category                     -> 911 care line (possible danger is never silence).
  R7 deterministic "danger" vocabulary line                     -> 911 care line. Sprint 7: ALWAYS shown. The semantic
     layer can no longer remove it (the old R7-suppressed exception, semantic none at confidence >= 0.8, is gone): a
     model can only ADD guidance, never remove deterministic guidance. A semantic "none" is recorded as a conflict.
  R9e after a person-danger alert, new danger words             -> full alert again (same kind)
  R9 earlier in this conversation: a person-danger alert       -> keep a calm line (988 for self-harm, else 911)
     on every later turn, even if the person says "I'm fine, stop" (applies wherever R7/R8 would show nothing).
  R8 nothing                                                    -> no safety text.
A failed / unavailable semantic layer never makes the result less cautious than the deterministic layer alone, and
is recorded as `degraded` so staff can see it.
"""

from app.risk.models import DeterministicRisk, RiskDecision, SemanticResult

_PEOPLE = {"self_harm", "medical", "personal_safety", "poison", "trapped"}


def _care_for(category: str) -> str:
    return {"self_harm": "distress", "medical": "unwell", "poison": "danger"}.get(category, "danger")


def decide(det: DeterministicRisk, sem: SemanticResult, prior_hazards: list[str] | None = None) -> RiskDecision:
    ok = sem.status == "ok" and sem.risk is not None
    s = sem.risk if ok else None
    degraded = not ok and sem.status not in ("disabled",)
    sem_self_harm = bool(s and "self_harm" in s.risk_categories and s.risk_level in ("urgent", "emergency"))

    if det.kind:  # R1
        conflict = None
        if s and s.risk_level in ("none", "uncertain"):
            conflict = f"semantic said {s.risk_level}; deterministic alert kept (never suppressed)"
        also = det.self_harm_intent or (sem_self_harm and det.kind != "self_harm")
        return RiskDecision(response="full_alert", kind=det.kind, also_988=also, needs_human=True,
                            escalation_priority="urgent", rule="R1",
                            sources=["window" if det.via_window else "deterministic"] + (["semantic"] if s else []),
                            conflict=conflict, degraded=degraded)
    if s and (s.risk_level == "emergency" or (s.risk_level == "urgent" and s.immediate_danger)):  # R2
        cats = list(s.risk_categories)
        kind = "self_harm" if "self_harm" in cats else (cats[0] if cats else "other")
        conflict = "semantic raised an alert the rules missed" if not det.mentioned_kind else (
            f"rules saw a {det.framing} mention; semantic says active danger, alert shown")
        return RiskDecision(response="full_alert", kind=kind, also_988=sem_self_harm and kind != "self_harm",
                            needs_human=True, escalation_priority="urgent", rule="R2", sources=["semantic"],
                            conflict=conflict)
    if det.framing == "joking" and det.mentioned_kind == "self_harm":  # R3
        return RiskDecision(response="care_line", care="distress", needs_human=sem_self_harm,
                            escalation_priority="high" if sem_self_harm else None, rule="R3",
                            sources=["deterministic"] + (["semantic"] if s else []), degraded=degraded)
    if s and s.risk_level == "uncertain" and not s.risk_categories and not det.care and not det.mentioned_kind \
            and not prior_hazards:  # R4u
        return RiskDecision(response="care_line", care="danger", needs_human=s.needs_human,
                            escalation_priority="high" if s.needs_human else None, rule="R4u", sources=["semantic"],
                            conflict="semantic uncertain, no category: calm 911 line rather than silence")
    if s and s.risk_level in ("urgent", "uncertain") and s.risk_categories:  # R4
        cat = "self_harm" if "self_harm" in s.risk_categories else s.risk_categories[0]
        care = _care_for(cat)
        if det.care == "distress":
            care = "distress"
        human = s.needs_human or cat == "self_harm" or s.risk_level == "urgent"
        return RiskDecision(response="care_line", care=care, needs_human=human,  # type: ignore[arg-type]
                            escalation_priority="high" if human else None, rule="R4",
                            sources=["semantic"] + (["deterministic"] if det.care else []))
    if det.mentioned_kind and det.framing in ("hypothetical", "past"):  # R5
        return RiskDecision(response="safety_info", kind=det.mentioned_kind, care="info", rule="R5",
                            sources=["deterministic"], degraded=degraded,
                            conflict="semantic agreed no active danger" if s else None)
    if det.care in ("distress", "unwell"):  # R6
        human = det.care == "distress"
        return RiskDecision(response="care_line", care=det.care, needs_human=human,
                            escalation_priority="high" if human else None, rule="R6",
                            sources=["deterministic"] + (["semantic"] if s else []), degraded=degraded,
                            conflict=(f"semantic said none; {det.care} line kept" if s and s.risk_level == "none"
                                      else None))
    prior = [h for h in (prior_hazards or []) if is_people_hazard(h)]
    if prior and det.care == "danger" and prior[-1] != "self_harm":  # R9e: "he's outside my door right now"
        return RiskDecision(response="full_alert", kind=prior[-1], needs_human=True, escalation_priority="urgent",
                            rule="R9e", sources=["session", "deterministic"], degraded=degraded,
                            conflict=f"danger words after an earlier {prior[-1]} alert: alert shown again")
    if det.care == "danger":  # R7: never removed by the semantic layer (sprint 7)
        return RiskDecision(response="care_line", care="distress" if "self_harm" in prior else "danger",
                            rule="R7", sources=["deterministic"] + (["semantic"] if s else []), degraded=degraded,
                            conflict=(f"semantic said none ({s.confidence or 0:.2f}); deterministic 911 line kept"
                                      if s and s.risk_level == "none" else None))
    if prior:  # R9
        care = "distress" if "self_harm" in prior else "danger"
        return RiskDecision(response="care_line", care=care, rule="R9",  # type: ignore[arg-type]
                            sources=["session"], degraded=degraded,
                            conflict=f"earlier {prior[-1]} alert in this conversation; calm line kept")
    return RiskDecision(response="none", rule="R8", sources=["semantic"] if s else [], degraded=degraded)


def is_people_hazard(kind: str | None) -> bool:
    return kind in _PEOPLE
