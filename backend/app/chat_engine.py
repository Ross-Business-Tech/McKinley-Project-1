"""Orchestrates one chat turn: context -> policy gates -> Claude -> output checks -> handoff merge."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import Settings
from app.context import Workbook
from app.db import Store
from app.llm import LLMError, LLMGateway, LLMResult, Target
from app.models import ChatResponse, Mode, OutputCheck, PolicySignal, SafeContext, Usage
from app.personas import build_context
from app.prompts import PromptBundle, aware_user_turn, baseline_prompt, load_aware_prompt
from app.safety import output_checks, pre_model_gates, redact

_TAG = re.compile(r"</?\s*(safe_context|customer_message|system)\s*>", re.IGNORECASE)

# Categories where the backend always recommends a human, regardless of model output (aware mode).
ALWAYS_ESCALATE = {
    "safety_emergency", "human_requested", "fair_housing_or_legal", "financial_or_lease",
    "sensitive_data_request", "policy_or_eligibility",
}
CATEGORY_PRIORITY = [
    "safety_emergency", "sensitive_data_request", "fair_housing_or_legal", "repeat_issue",
    "unresolved_commitment", "financial_or_lease", "human_requested", "policy_or_eligibility",
    "leasing_follow_up", "other",
]


@dataclass
class EngineDeps:
    settings: Settings
    llm: LLMGateway
    store: Store | None
    workbook: Workbook | None


def clean_message(message: str) -> str:
    return redact(_TAG.sub("", message)).strip()


def prompt_for(mode: Mode, settings: Settings) -> PromptBundle:
    return load_aware_prompt(settings.prompt_path) if mode == "aware" else baseline_prompt()


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


def merge_handoff(
    mode: Mode, model_handoff: bool, model_category: str, model_reason: str, signals: list[PolicySignal],
    ctx: SafeContext,
) -> tuple[bool, str, str | None]:
    """Aware mode: model recommendation OR deterministic escalation. Baseline: model only (generic)."""
    if mode == "baseline":
        if not model_handoff:
            return False, "none", None
        return True, model_category if model_category != "none" else "other", (model_reason or None)

    has_history = any(f.name == "repeat_issue_flag" for f in ctx.fields)
    escalating = [
        s for s in signals
        if s.category in ALWAYS_ESCALATE
        or s.code in {"context_repeat_issue", "context_open_commitment"}
        or (s.code == "repeat_language" and has_history)
    ]
    handoff = model_handoff or bool(escalating)
    if not handoff:
        return False, "none", None
    cats = [s.category for s in escalating] + ([model_category] if model_handoff else [])
    category = next((c for c in CATEGORY_PRIORITY if c in cats), model_category or "other")
    reasons = [s.detail for s in escalating]
    if model_handoff and model_reason:
        reasons.insert(0, f"Model: {model_reason}")
    return True, category, " | ".join(dict.fromkeys(reasons)) or None


def resolve_target(deps: EngineDeps, target_key: str | None) -> Target:
    """Only targets configured on the server may be used (prevents arbitrary model/key use from the browser)."""
    if not target_key:
        return deps.llm.default_target
    allowed = {t.key: t for t in deps.llm.eval_targets()}
    if target_key not in allowed:
        raise LLMError("UNKNOWN_TARGET", f"Target '{target_key}' is not configured in EVAL_TARGETS.",
                       http_status=400)
    return allowed[target_key]


def run_turn(
    deps: EngineDeps, message: str, mode: Mode, persona_id: str | None, session_id: str | None,
    use_history: bool = True, target: Target | None = None,
) -> ChatResponse:
    settings = deps.settings
    target = target or deps.llm.default_target
    session_id = session_id or uuid.uuid4().hex
    msg = clean_message(message)
    ctx = build_context(persona_id, msg, deps.workbook)
    bundle = prompt_for(mode, settings)

    history = []
    hist_key = persona_id or "none"
    if use_history and deps.store:
        history = deps.store.history(session_id, f"{mode}|{target.key}", hist_key)
    user_turn = aware_user_turn(msg, ctx) if mode == "aware" else msg
    messages = [*history, {"role": "user", "content": user_turn}]

    result: LLMResult = deps.llm.complete(bundle.system, messages, target)  # raises LLMError
    out = result.output
    raw_reply = out.reply.strip()
    allowed_text = " ".join(f.value for f in ctx.fields) if mode == "aware" else ""
    checks: list[OutputCheck] = output_checks(raw_reply, allowed_text)
    checks.append(OutputCheck(
        code="structured_output",
        passed=result.parse_mode != "text_fallback",
        detail={"json": "Valid JSON contract", "json_extracted": "JSON extracted from surrounding text",
                "text_fallback": "Model ignored JSON contract; raw text used, no model handoff signal"}
        [result.parse_mode],
    ))
    reply = redact(raw_reply)  # model output is untrusted; never display PII patterns

    signals = pre_model_gates(msg) + (context_signals(ctx) if mode == "aware" else [])
    handoff, category, reason = merge_handoff(
        mode, out.recommended_handoff, out.handoff_category, out.handoff_reason, signals, ctx
    )

    if deps.store and use_history:
        deps.store.append_turns(session_id, f"{mode}|{target.key}", hist_key, msg, reply)

    audience = out.audience if out.audience in ("prospect", "resident", "unknown") else "unknown"
    return ChatResponse(
        reply=reply,
        mode=mode,
        audience=audience,  # type: ignore[arg-type]
        recommended_handoff=handoff,
        handoff_reason=reason,
        handoff_category=category,  # type: ignore[arg-type]
        model_handoff=out.recommended_handoff,
        policy_signals=signals,
        output_checks=checks,
        source_context_fields=[f"{f.name} ← {f.source}" for f in ctx.fields] if mode == "aware" else [],
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
    )
