"""Orchestrates one chat turn as a deterministic pipeline with at most one response-generation LLM call.

  1 receive -> 2 identity -> 3 privacy -> 4 retrieve authorized context -> 5 decision gate -> 6 workflow + action
  plan (app/actions.py) -> 7 generate (LLM, skipped for fully deterministic replies) -> 8 validate (critical
  failures are replaced by the backend template) -> 9 handoff recommendation -> 10 persist safe metadata

Modes: baseline (generic prompt; steps 4-6 and 9 skipped), prompt_only (McKinley prompt + gate/workflow, no
resident context), aware (everything). See docs/diagrams/sequence.md.
"""

import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.actions import TurnPlan, identity_note, plan_turn, resident_for
from app.config import Settings
from app.context import Workbook
from app.db import Store
from app.gates import DecisionGateService, GateContext
from app.handoff import build_handoff
from app.intake import detect_language
from app.llm import LLMError, LLMGateway, LLMResult, Target
from app.models import (
    Channel,
    ChatResponse,
    GateDecision,
    HandoffCategory,
    Mode,
    OutputCheck,
    PipelineStep,
    PolicySignal,
    SafeContext,
    Usage,
)
from app.personas import build_context
from app.prompts import PromptBundle, aware_user_turn, baseline_prompt, load_aware_prompt
from app.safety import (
    CRITICAL_CHECKS,
    contains_pii,
    normalize_for_matching,
    output_checks,
    pre_model_gates,
    redact,
)
from app.workflows import (
    EMERGENCY_NOTICE,
    WORKFLOW_VERSION,
    lead_profile,
    maintenance_triage,
    renewal_assessment,
    select_workflow,
    workflow_prompt_section,
)

_TAG = re.compile(r"</?\s*(safe_context|customer_message|system|facts)\s*>", re.IGNORECASE)


@dataclass
class EngineDeps:
    settings: Settings
    llm: LLMGateway
    store: Store | None
    workbook: Workbook | None
    gates: DecisionGateService | None = None

    def __post_init__(self) -> None:
        if self.gates is None:
            self.gates = DecisionGateService(self.settings, self.llm)


def clean_message(message: str) -> str:
    return redact(_TAG.sub("", normalize_for_matching(message))).strip()


def prompt_for(mode: Mode, settings: Settings) -> PromptBundle:
    if mode == "baseline":
        return baseline_prompt()
    bundle = load_aware_prompt(settings.prompt_path)
    suffix = "+ctx" if mode == "aware" else "+noctx"
    return PromptBundle(system=bundle.system, version=f"{bundle.version}+{WORKFLOW_VERSION}{suffix}")


def context_signals(ctx: SafeContext) -> list[PolicySignal]:
    names = {f.name for f in ctx.fields}
    out = []
    if "repeat_issue_flag" in names:
        out.append(PolicySignal(code="context_repeat_issue", category="repeat_issue",
                                detail="Context shows repeated related maintenance contacts."))
    if "open_commitment_flag" in names:
        out.append(PolicySignal(code="context_open_commitment", category="unresolved_commitment",
                                detail="Context shows an open related item where follow-up is owed."))
    if ctx.persona_kind == "unmatched_resident":
        out.append(PolicySignal(code="no_matched_record", category="other",
                                detail="No verified resident record; do not assume history (informational)."))
    return out


def identity_only(ctx: SafeContext) -> SafeContext:
    """prompt_only mode: keep the app-established audience, drop every resident field."""
    return ctx.model_copy(update={
        "fields": [], "dropped_items": [],
        "notes": ["Mode B (McKinley prompt only): no resident context is provided in this mode."],
    })


def resolve_target(deps: EngineDeps, target_key: str | None) -> Target:
    """Only targets configured on the server may be used (prevents arbitrary model/key use from the browser)."""
    if not target_key:
        return deps.llm.default_target
    allowed = {t.key: t for t in deps.llm.eval_targets()}
    if target_key not in allowed:
        raise LLMError("UNKNOWN_TARGET", f"Target '{target_key}' is not configured in EVAL_TARGETS.",
                       http_status=400)
    return allowed[target_key]


# Runtime model failures where the customer gets the backend template instead of an error. Configuration
# errors (missing key, unknown target, auth) still surface as errors so staff notice them.
FALLBACK_CODES = {"MODEL_API_ERROR", "MODEL_CONNECTION_ERROR", "MODEL_TIMEOUT", "MODEL_RATE_LIMITED",
                  "MODEL_EMPTY_RESPONSE", "MODEL_BAD_RESPONSE", "MODEL_TRUNCATED", "MODEL_REFUSAL"}
# Failed checks that make a model reply unsafe to show (fabrication, false completion, leakage, unsafe advice).
REPLACE_ON_FAIL = CRITICAL_CHECKS | {"no_invented_price", "no_invented_time", "terminology"}

CHANNEL_RULES = {
    "web_chat": "Channel: web chat. 2-4 short sentences.",
    "sms": "Channel: SMS (I-07 team draft). At most 2 short sentences, under 320 characters, no lists.",
    "email": "Channel: email (I-07 team draft). Complete sentences; end with the line "
             "'McKinley resident services assistant (AI)'.",
}


def plan_prompt_section(plan: TurnPlan, channel: Channel, lang: str) -> str:
    """Trusted backend facts for the response model: the next step, and a draft reply it must stay faithful to."""
    lines = [
        "## Backend next step (authoritative)",
        CHANNEL_RULES[channel],
        f"Reply language: {'Spanish' if lang == 'es' else 'English'}.",
        "Rewrite the backend draft reply below in your own warm, plain words. Keep every fact and every "
        "limitation it states. Do not add facts, times, prices, names of staff or promises. Do not say anything was "
        "sent, submitted, created or scheduled unless the draft says so. The interface shows any form or "
        "confirmation button separately, so do not repeat field lists.",
    ]
    if plan.action:
        lines.append(f"Action card shown to the person: {plan.action.title} (stage={plan.action.stage}).")
    lines.append(f"<backend_draft_reply>{plan.template}</backend_draft_reply>")
    return "\n".join(lines)


def _template_result(target: Target, reason: str) -> LLMResult:
    from app.llm.base import ModelOutput

    return LLMResult(output=ModelOutput(reply=""), provider="backend", requested_model=target.model,
                     model="deterministic-template", stop_reason=reason, input_tokens=0, output_tokens=0,
                     latency_ms=0, parse_mode="json", is_mock=False, estimated_cost_usd=0.0)


class _Trace:
    def __init__(self) -> None:
        self.steps: list[PipelineStep] = []
        self._t = time.perf_counter()

    def add(self, step: str, status: str, detail: str) -> None:
        now = time.perf_counter()
        self.steps.append(PipelineStep(step=step, status=status, detail=detail,  # type: ignore[arg-type]
                                       ms=int((now - self._t) * 1000)))
        self._t = now


def run_turn(
    deps: EngineDeps, message: str, mode: Mode, persona_id: str | None, session_id: str | None,
    use_history: bool = True, target: Target | None = None, gate_provider: str | None = None,
    channel: Channel = "web_chat", enforce_validation: bool = True, fallback_on_model_error: bool = False,
) -> ChatResponse:
    """`enforce_validation=False` keeps the raw model reply (evals measure the model, not the safety net)."""
    settings = deps.settings
    target = target or deps.llm.default_target
    session_id = session_id or uuid.uuid4().hex
    hist_key = persona_id or "none"
    mode_key = f"{mode}|{target.key}"
    trace = _Trace()

    # 1. receive: strip delimiter tags, redact PII patterns before anything else sees the text
    msg = clean_message(message)
    pii_found = contains_pii(_TAG.sub("", normalize_for_matching(message)))
    trace.add("1_receive", "ok", f"{len(msg)} chars after cleaning")

    # 2. identity: audience comes ONLY from the trusted app context (demo persona), never from the message/model
    full_ctx = build_context(persona_id, msg, deps.workbook)
    verified = full_ctx.persona_kind == "resident" and full_ctx.record_found
    trace.add("2_identity", "ok" if full_ctx.audience != "unknown" else "warn",
              f"audience={full_ctx.audience}, identity_verified={verified} (demo persona = trusted app context)")

    # 3. privacy
    trace.add("3_privacy", "warn" if pii_found else "ok",
              f"redacted from message: {pii_found}" if pii_found else "no PII patterns in message")

    # 4. retrieve authorized context (allowlisted, topic-gated, injection-screened)
    if mode == "aware":
        ctx = full_ctx
        trace.add("4_context", "warn" if ctx.dropped_items else "ok",
                  f"{len(ctx.fields)} fields; {len(ctx.dropped_items)} item(s) dropped by injection screen")
    else:
        ctx = identity_only(full_ctx)
        trace.add("4_context", "skipped", f"mode={mode}: no resident context sent to the model")

    # 5. decision gate
    gate: GateDecision | None = None
    if mode != "baseline":
        prior = deps.store.last_gate(session_id, mode_key, hist_key) if (deps.store and use_history) else None
        if deps.store and use_history and deps.store.get_draft(session_id, hist_key):
            prior = None  # short answers to the assistant's own questions are not "unsure"
        gctx = GateContext(
            audience=full_ctx.audience, identity_verified=verified, record_found=full_ctx.record_found,
            topics=full_ctx.topics,
            context_flags=frozenset(f.name for f in ctx.fields if f.name.endswith("_flag")),
            prior_low_confidence=bool(prior and "low_confidence" in prior.get("risk_flags", [])),
        )
        assert deps.gates is not None
        override = gate_provider if settings.gate_override_enabled else None
        gate = deps.gates.classify(msg, gctx, override)
        trace.add("5_gate", "fallback" if gate.fallback_used else "ok",
                  f"{gate.decision_source}: intent={gate.intent}, urgency={gate.urgency}, "
                  f"human={gate.requires_human}" + (f" (fallback: {gate.fallback_reason})" if gate.fallback_used
                                                    else ""))
    else:
        trace.add("5_gate", "skipped", "baseline mode: generic assistant, no McKinley routing")

    # 6. workflow selection + deterministic workflow analysis + customer action plan
    workflow = routed = triage = lead = renewal = None
    plan: TurnPlan | None = None
    preferred = next((f.value for f in ctx.fields if f.name == "preferred_language"), None)
    lang = detect_language(msg, preferred)
    bundle = prompt_for(mode, settings)
    system = bundle.system
    if gate:
        workflow = routed = select_workflow(gate)
        if workflow.id == "maintenance" or gate.intent == "maintenance":
            triage = maintenance_triage(msg, ctx, gate)
        if workflow.id == "leasing":
            lead = lead_profile(msg, ctx)
        if workflow.id == "renewal":
            renewal = renewal_assessment(msg, ctx)
        plan = plan_turn(msg=msg, gate=gate, workflow=workflow, ctx=ctx, triage=triage,
                         store=deps.store if use_history else None, session_id=session_id, persona_id=persona_id,
                         resident=resident_for(persona_id, deps.workbook) if verified else None,
                         channel=channel, lang=lang)  # type: ignore[arg-type]
        if plan.consumed_by_draft and "low_confidence" in gate.risk_flags:
            gate = gate.model_copy(update={
                "risk_flags": [f for f in gate.risk_flags if f not in ("low_confidence", "repeated_low_confidence")],
                "overrides": [*gate.overrides, "low_confidence cleared: message answered the assistant's question"],
            })
        workflow = plan.workflow if plan.workflow.id != workflow.id else workflow
        system = (f"{system}\n\n{workflow_prompt_section(workflow, gate, triage, lead, renewal)}\n\n"
                  f"{plan_prompt_section(plan, channel, lang)}")
        trace.add("6_workflow", "ok", f"{workflow.id}: {workflow.reason} | functions={plan.functions}"
                  + (f" | action={plan.action.kind}:{plan.action.stage}" if plan.action else ""))
    else:
        trace.add("6_workflow", "skipped", "baseline mode")

    # 7. generate (the only response-generation LLM call)
    history = deps.store.history(session_id, mode_key, hist_key) if (use_history and deps.store) else []
    user_turn = msg if mode == "baseline" else aware_user_turn(msg, ctx)
    reply_source = "model"
    if plan and plan.skip_model:
        result = _template_result(target, "deterministic")
        reply_source = "template"
        trace.add("7_generate", "skipped", "fully deterministic reply (no model call, no cost)")
    else:
        try:
            result = deps.llm.complete(system, [*history, {"role": "user", "content": user_turn}], target)
            trace.add("7_generate", "ok" if result.parse_mode != "text_fallback" else "warn",
                      f"{result.provider}:{result.model} parse={result.parse_mode}"
                      f"{' (MOCK)' if result.is_mock else ''}")
        except LLMError as e:
            if not (fallback_on_model_error and plan and e.code in FALLBACK_CODES):
                raise
            result = _template_result(target, f"model_error:{e.code}")
            reply_source = "template_after_model_error"
            trace.add("7_generate", "fallback", f"{target.key} failed ({e.code}); backend template used")
    out = result.output
    if reply_source != "model" and plan:
        out = out.model_copy(update={"reply": plan.template, "audience": gate.audience if gate else "unknown",
                                     "recommended_handoff": plan.force_handoff})

    # 8. validate (model output is untrusted)
    raw_reply = out.reply.strip()
    allowed_text = " ".join(f.value for f in ctx.fields)
    checks: list[OutputCheck] = output_checks(raw_reply, allowed_text, gate.urgency if gate else None)
    checks.append(OutputCheck(
        code="structured_output",
        passed=result.parse_mode != "text_fallback",
        detail={"json": "Valid JSON contract", "json_extracted": "JSON extracted from surrounding text",
                "text_fallback": "Model ignored JSON contract; raw text used, no model handoff signal"}
        [result.parse_mode],
    ))
    if plan and plan.records:  # a completion claim is true when this turn actually wrote a prototype record
        ids = ", ".join(r.id for r in plan.records)
        checks = [c.model_copy(update={"passed": True, "detail": f"Completion backed by prototype record {ids}"})
                  if c.code == "no_false_action_claim" and not c.passed else c for c in checks]
    reply = redact(raw_reply)
    safety_notice = EMERGENCY_NOTICE if gate and gate.urgency == "emergency" else None
    failed = [c.code for c in checks if not c.passed]
    unsafe = [c for c in failed if c in REPLACE_ON_FAIL]
    if enforce_validation and plan and unsafe and reply_source == "model":
        reply = redact(plan.template)
        reply_source = "template_after_validation"
        trace.add("8_validate", "warn", f"failed checks {failed}: model reply replaced by backend template")
    else:
        trace.add("8_validate", "warn" if failed else "ok",
                  f"failed checks: {failed}" if failed else "all checks passed")

    # 9. handoff recommendation (recommendation only; nothing is sent)
    signals = pre_model_gates(msg) + (context_signals(ctx) if mode == "aware" else [])
    handoff = None
    if gate and workflow:
        handoff = build_handoff(gate, workflow, ctx, out.recommended_handoff, out.handoff_reason, triage, lead)
        if handoff is None and plan and plan.handoff:
            handoff = plan.handoff
        staff_recs = [r for r in (plan.records if plan else []) if r.kind == "staff_handoff"]
        if handoff and staff_recs:
            handoff = handoff.model_copy(update={"delivery_note": (
                f"Saved to the PROTOTYPE staff queue as {staff_recs[0].id}. No one is paged, called or notified.")})
        recommended = handoff is not None
        category: HandoffCategory = handoff.category if handoff else "none"
        reason = " | ".join(handoff.reasons) if handoff else None
        trace.add("9_handoff", "ok", f"recommended to {handoff.team} ({handoff.priority}); NOT sent" if handoff
                  else "no handoff needed")
    else:  # baseline: report only the model's own (generic, unlayered) recommendation
        recommended = out.recommended_handoff
        category = (out.handoff_category if out.handoff_category != "none" else "other") if recommended else "none"
        reason = (out.handoff_reason or None) if recommended else None
        trace.add("9_handoff", "skipped", "baseline: model's own recommendation only")

    # 10. persist safe metadata (turn text for session memory; gate log has no message text)
    if deps.store and use_history:
        deps.store.append_turns(session_id, mode_key, hist_key, msg, reply)
        if gate:
            deps.store.log_gate(session_id, mode_key, hist_key, {
                "intent": gate.intent, "urgency": gate.urgency, "requires_human": gate.requires_human,
                "confidence": gate.confidence, "risk_flags": gate.risk_flags, "source": gate.decision_source,
                "requested_provider": gate.requested_provider, "fallback_used": gate.fallback_used,
                "workflow": workflow.id if workflow else None, "latency_ms": gate.latency_ms,
                "functions": plan.functions if plan else [], "channel": channel,
                "action": f"{plan.action.kind}:{plan.action.stage}" if plan and plan.action else None,
                "records": [r.id for r in plan.records] if plan else [], "reply_source": reply_source,
            })
    trace.add("10_persist", "ok" if (deps.store and use_history) else "skipped",
              "gate metadata logged (no message text)" if (deps.store and use_history and gate) else
              "session turns stored" if (deps.store and use_history) else "eval run: not stored as session")

    audience = out.audience if out.audience in ("prospect", "resident", "unknown") else "unknown"
    if gate:
        audience = gate.audience  # trusted audience wins over the model's guess
    return ChatResponse(
        reply=reply,
        safety_notice=safety_notice,
        mode=mode,
        audience=audience,  # type: ignore[arg-type]
        recommended_handoff=recommended,
        handoff_reason=reason,
        handoff_category=category,
        model_handoff=out.recommended_handoff,
        policy_signals=signals,
        output_checks=checks,
        source_context_fields=[f"{f.name} ← {f.source}" for f in ctx.fields],
        provider=result.provider,
        requested_model=result.requested_model,
        model=result.model,
        is_mock=result.is_mock,
        parse_mode=result.parse_mode,
        temperature=deps.llm.generation_config(target).temperature,
        prompt_version=bundle.version,
        usage=Usage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=result.estimated_cost_usd,
        ),
        latency_ms=result.latency_ms,
        stop_reason=result.stop_reason,
        session_id=session_id,
        created_at=datetime.now(UTC),
        gate=gate,
        workflow=workflow,
        routed_workflow=routed,
        maintenance=triage,
        lead=lead,
        renewal=renewal,
        handoff=handoff,
        pipeline=trace.steps,
        channel=channel,
        language=lang,  # type: ignore[arg-type]
        functions=plan.functions if plan else [],
        reply_source=reply_source,  # type: ignore[arg-type]
        action=plan.action if plan else None,
        records_created=plan.records if plan else [],
        status_items=plan.status_items if plan else [],
        suggested_replies=plan.chips if plan else [],
        identity_note=identity_note(full_ctx),
    )
