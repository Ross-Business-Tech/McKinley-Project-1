"""One chat turn. Five owners, called in this order:

  A identity      server-side principal and a store scoped to (this session, this principal)     app/auth, app/db
  B safety        rules -> optional semantic classifier -> policy, on EVERY message; an emergency  app/risk
                  gets fixed approved instructions and pauses any open task (no model call)
  C conversation  ONE language-model call: a natural reply + at most one proposed task operation  app/assistant
                  (privacy refusals and explicit sends are decided before it, deterministically)  app/guardrails
  D tasks         validates and applies the proposal: start/continue/switch/suspend/resume/cancel  app/tasks
                  (complete = save, only via Send or an explicit typed send)
  E tools         authorized resident context, own history, approved property facts, prototype    app/personas,
                  records                                                                         app/tasks

Nothing in a turn reaches McKinley staff or any real system: saved items are prototype records.
"""

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from app import assistant, guardrails, tasks
from app.auth import Principal, derive_principal, session_bound_to
from app.config import Settings
from app.context import Workbook
from app.db import ScopedStore, Store
from app.emergency import (
    FOLLOW_UP,
    NO_LINE,
    PEOPLE_FOLLOW_UP,
    QUEUE_NOTE,
    REFUSE_LEAD,
    REFUSING_TO_LEAVE,
    asks_emergency_line,
)
from app.emergency import heading as emergency_heading
from app.emergency import notice as emergency_notice
from app.llm import LLMError, LLMGateway, LLMResult, Target
from app.models import (
    Channel,
    ChatResponse,
    HandoffRecommendation,
    Mode,
    OutputCheck,
    PipelineStep,
    PrototypeRecord,
    SafeContext,
    StatusItem,
    Usage,
)
from app.personas import apply_account_holder_rule, build_context, holder_disclaimed
from app.risk import escalation as risk_escalation
from app.risk import responses as risk_responses
from app.risk.classifier import SemanticRiskClassifier
from app.risk.incident import active as incident_active
from app.risk.incident import prior_hazards as incident_prior_hazards
from app.risk.incident import step as incident_step
from app.risk.models import SemanticResult
from app.risk.pipeline import assess
from app.risk.pipeline import diagnostics as risk_diagnostics
from app.risk.policy import decide as risk_decide
from app.risk.policy import is_people_hazard
from app.risk.ui_state import safety_ui
from app.safety import CRITICAL_CHECKS, normalize_for_matching, output_checks, redact

log = logging.getLogger("mckinley")
PROMPT_VERSION = "mvp-" + hashlib.sha256(assistant.RULES.encode()).hexdigest()[:8]
# Any tag-like markup is removed from user text, so it can never imitate a backend delimiter.
_TAG = re.compile(r"</?\s*[A-Za-z_][\w:-]*(?:\s[^<>]*)?/?\s*>")
_WS_RUN = re.compile(r"\s{2,}")
_LINE_BREAKS = str.maketrans({"\r": "\n", "\u2028": "\n", "\u2029": "\n", "\x0b": "\n", "\x0c": "\n", "\x85": "\n"})


@dataclass(frozen=True)
class PromptBundle:
    system: str
    version: str


@dataclass
class EngineDeps:
    settings: Settings
    llm: LLMGateway
    store: Store | None
    workbook: Workbook | None
    risk: SemanticRiskClassifier | None = None

    def __post_init__(self) -> None:
        if self.risk is None:
            self.risk = SemanticRiskClassifier(self.settings, self.llm)


def clean_message(message: str) -> str:
    """Tags removed, PII patterns redacted, whitespace runs collapsed (before anything else sees the text)."""
    text = redact(_TAG.sub("", normalize_for_matching(message)))
    return _WS_RUN.sub(lambda m: "\n" if "\n" in m.group(0) else " ", text.translate(_LINE_BREAKS)).strip()


def prompt_for(mode: Mode, settings: Settings) -> PromptBundle:  # noqa: ARG001 - one prompt in every mode now
    return PromptBundle(system=assistant.RULES, version=PROMPT_VERSION)


def resolve_target(deps: EngineDeps, target_key: str | None) -> Target:
    """Only targets configured on the server may be used (prevents arbitrary model/key use from the browser)."""
    if not target_key:
        return deps.llm.default_target
    allowed = {t.key: t for t in deps.llm.eval_targets()}
    if target_key not in allowed:
        raise LLMError("UNKNOWN_TARGET", f"Target '{target_key}' is not configured in EVAL_TARGETS.",
                       http_status=400)
    return allowed[target_key]


def identity_note(ctx: SafeContext, verified: bool) -> str:
    name = next((f.value for f in ctx.fields if f.name == "first_name"), None)
    if verified:
        return f"Signed in as {name} (demo account)" if name else "Signed in (demo account)"
    return {"unmatched_resident": "Not matched to a resident account",
            "prospect": "Browsing as a prospective resident (demo profile)"}.get(ctx.persona_kind or "",
                                                                                  "Not signed in")


class _Trace:
    def __init__(self) -> None:
        self.steps: list[PipelineStep] = []
        self._t = time.perf_counter()

    def add(self, step: str, status: str, detail: str) -> None:
        now = time.perf_counter()
        self.steps.append(PipelineStep(step=step, status=status, detail=detail,  # type: ignore[arg-type]
                                       ms=int((now - self._t) * 1000)))
        self._t = now


def _no_model(target: Target, reason: str) -> LLMResult:
    from app.llm.base import ModelOutput
    return LLMResult(output=ModelOutput(reply="", audience="unknown"), provider="backend", requested_model=target.model,
                     model="deterministic-template", stop_reason=None, input_tokens=None, output_tokens=None,
                     latency_ms=0, parse_mode="json", extra={"reason": reason})


# Runtime model failures get a fixed message; configuration errors (missing key, unknown target, auth) surface as
# errors so staff notice them.
FALLBACK_CODES = {"MODEL_API_ERROR", "MODEL_CONNECTION_ERROR", "MODEL_TIMEOUT", "MODEL_RATE_LIMITED",
                  "MODEL_EMPTY_RESPONSE", "MODEL_BAD_RESPONSE", "MODEL_TRUNCATED", "MODEL_REFUSAL",
                  "MODEL_CONTENT_FILTERED", "LLM_BUDGET_EXHAUSTED", "BAD_OUTPUT"}
# Remediation P0: when the turn already shows approved safety text (an alert, a care line, an active incident) and the
# conversation model fails for ANY reason, the safety text stays and this fixed line replaces the model's reply; the
# turn is never turned into an error. No new capability is claimed. Wording NEEDS McKINLEY REVIEW.
SAFETY_FALLBACK = ("I can't answer the rest of that right now. The safety information above is there for you any time.",
                   "No puedo responder el resto en este momento. La información de seguridad de arriba está disponible "
                   "en todo momento.")
FALLBACK_REPLY = ("Sorry, I couldn't work that out just now. Could you say it another way?",
                  "Perdón, no pude procesarlo ahora. ¿Puede decirlo de otra forma?")
KEPT = (" Your {what} is still here, unchanged.", " Su {what} sigue aquí, sin cambios.")
BACK = ("Thanks for the update. Your {what} from before is back, not sent yet.",
        "Gracias por avisar. Su {what} de antes volvió, sin enviar.")
TOUR_NEXT = ("Your tour request is waiting as the next card, after this one. Nothing has been sent.",
             "Su solicitud de visita espera como la siguiente tarjeta, después de esta. No se envió nada.")
NOT_YET = ("I can't send your {what} yet, so nothing was saved. Still needed: {miss}.",
           "Todavía no puedo enviar su {what}, así que no se guardó nada. Falta: {miss}.")


@dataclass
class _Turn:
    """Everything one chat turn knows, filled in step by step by run_turn (the steps run in this order:
    identity/context -> safety -> emergency | backend-only reply | model turn -> validation -> persistence)."""

    msg: str
    session_id: str
    mode_key: str
    principal: Principal
    persona_id: str | None
    key: str
    store: ScopedStore | None
    ctx: SafeContext
    verified: bool
    name: str | None
    said_ever: list[str]
    legal: bool
    trace: _Trace
    # safety
    history: list[dict[str, str]] = field(default_factory=list)
    prior: list[str] = field(default_factory=list)
    risk: Any = None
    rd: Any = None
    st: Any = None
    safety_notice: str | None = None
    hazard: str | None = None
    inc: Any = None
    # tasks and reply
    lang: str = "en"
    active: dict[str, Any] | None = None
    waiting: list[dict[str, Any]] = field(default_factory=list)
    before: tuple[str, str] = ("", "")
    kind_before: str | None = None
    shown: Any = None
    records: list[PrototypeRecord] = field(default_factory=list)
    status_items: list[StatusItem] = field(default_factory=list)
    queued_tour: bool = False
    result: Any = None
    reply: str = ""
    reply_source: str = "template"
    handoff_team: str | None = None
    handoff_reason: str = ""
    op_done: str = "none"
    # validation
    checks: list[OutputCheck] = field(default_factory=list)
    model_text: bool = False
    reasons: list[str] = field(default_factory=list)


def run_turn(
    deps: EngineDeps, message: str, mode: Mode, persona_id: str | None, session_id: str | None,
    use_history: bool = True, target: Target | None = None, gate_provider: str | None = None,  # noqa: ARG001
    channel: Channel = "web_chat", enforce_validation: bool = True, fallback_on_model_error: bool = True,
    principal: Principal | None = None, local_request: bool = True,  # noqa: ARG001
) -> ChatResponse:
    target = target or deps.llm.default_target
    t = _prepare(deps, message, persona_id, session_id, use_history, target, principal)  # A. identity + context
    _assess_safety(deps, t)  # B. safety on every message, before anything else
    _start_reply(t, target)
    if t.safety_notice:
        _emergency_turn(t)  # an emergency interrupts everything
    elif not _backend_reply(t):  # privacy refusal, "a separate request", explicit typed send
        _model_turn(deps, t, target, local_request, fallback_on_model_error)  # C. the one model call
    _validate(deps, t, enforce_validation)  # model text is untrusted
    _persist(t)  # D. task state, the turn and its diagnostics
    return _response(deps, t, mode, channel, target)


def _prepare(deps: EngineDeps, message: str, persona_id: str | None, session_id: str | None, use_history: bool,
             target: Target, principal: Principal | None) -> _Turn:
    """A. Identity is derived server-side only (message text and the model never change it), then the minimized
    context for that principal."""
    settings = deps.settings
    session_id = session_id or uuid.uuid4().hex
    trace = _Trace()
    msg = clean_message(message)
    legal = guardrails.legal_sensitive(msg)  # accommodation / fair housing / legal topic (routing only)
    if principal is None:
        principal = derive_principal(settings, persona_id, session_id, deps.workbook, strict=False)
    principal = replace(principal, session_id=session_id)
    persona_id, key = principal.persona_id, principal.key
    store = deps.store if use_history else None
    if store is not None and not session_bound_to(store, principal):  # someone else's session id: start fresh
        session_id = uuid.uuid4().hex
        principal = replace(principal, session_id=session_id)
        session_bound_to(store, principal)
    if store is not None and not isinstance(store, ScopedStore):
        store = ScopedStore(store, session_id, key, principal_kind=principal.kind)  # type: ignore[arg-type]
    full_ctx = build_context(persona_id, msg, deps.workbook, principal=principal)
    said_ever = store.user_messages(session_id, key) if store else []
    record_ctx, ctx = full_ctx, apply_account_holder_rule(full_ctx, [*said_ever, msg])
    if holder_disclaimed(record_ctx, ctx) and isinstance(store, ScopedStore):
        store = store.without_account_access()  # "not the account holder": account records are dropped too
    verified = ctx.persona_kind == "resident" and ctx.record_found
    name = next((f.value for f in ctx.fields if f.name == "first_name"), None) if verified else None
    trace.add("A_identity", "ok", f"principal={principal.kind}; verified={verified} (demo sign-in, not real auth)")
    return _Turn(msg=msg, session_id=session_id, mode_key=f"aware|{target.key}", principal=principal,
                 persona_id=persona_id, key=key, store=store, ctx=ctx, verified=verified, name=name,
                 said_ever=said_ever, legal=legal, trace=trace)


def _assess_safety(deps: EngineDeps, t: _Turn) -> None:
    """B. Rules + classifier + policy (app.risk), then the incident state machine."""
    store, sid, key = t.store, t.session_id, t.key
    t.history = store.history(sid, t.mode_key, key) if store else []
    said_before = [m["content"] for m in t.history if m["role"] == "user"]
    prior = ([r.get("hazard") for r in store.records(session_id=sid, limit=50)
              if r.get("status") == "urgent_queued"] if store else [])
    if store:
        prior = incident_prior_hazards(store, sid, key, t.msg, len(t.said_ever) + 1, prior)
    t.prior = prior
    risk = assess(t.msg, said_before[-3:], deps.risk, prior)  # type: ignore[arg-type]
    t.risk = incident_step(store, sid, key, t.msg, risk, len(t.said_ever) + 1)
    t.rd = t.risk.decision
    t.trace.add("B_safety", "warn" if t.rd.response != "none" else "ok",
                f"{t.rd.rule}: {t.rd.response}; semantic={t.risk.semantic.status}")


def _start_reply(t: _Turn, target: Target) -> None:
    """Language, the task state as it was, and the approved safety text this turn will show."""
    store, sid, key = t.store, t.session_id, t.key
    t.lang = assistant.language(t.msg, _last_lang(store, sid, t.mode_key, key),
                                next((f.value for f in t.ctx.fields if f.name == "preferred_language"), None))
    t.active, t.waiting = tasks.load(store, sid, key)
    t.before, t.kind_before = (repr(t.active), repr(t.waiting)), (t.active or {}).get("kind")
    t.result = _no_model(target, "deterministic")
    t.st = risk_responses.select(t.rd, t.lang)
    t.safety_notice = t.st.safety_notice if t.rd.response == "full_alert" else None
    t.inc = incident_active(store, sid, key) if store else None
    t.hazard = t.rd.kind
    if not t.safety_notice and t.inc and REFUSING_TO_LEAVE.search(t.msg):
        # refusing to leave during an active incident is still an emergency turn: the approved steps again
        t.hazard = t.inc.kind
        t.safety_notice = emergency_notice(t.hazard, t.lang)


def _emergency_turn(t: _Turn) -> None:
    """Approved fixed text, one urgent prototype note, the open task waits unsent."""
    store, lang, hazard = t.store, t.lang, t.hazard
    team = "management" if is_people_hazard(hazard or "") else "emergency_maintenance"
    inc_now = incident_active(store, t.session_id, t.key) if store else None  # this turn's incident (just opened)
    rec, existed = tasks.save_urgent_note(store, t.session_id, t.persona_id, hazard or "other", t.msg, lang, team,
                                          incident=inc_now.started_at if inc_now else "")
    if rec and not existed:
        t.records = [rec]
    t.active, t.waiting = tasks.pause_for_emergency(t.active, t.waiting)
    lead = REFUSE_LEAD[lang] if existed and REFUSING_TO_LEAVE.search(t.msg) else ""
    follow = (QUEUE_NOTE[lang] if not existed else " " + NO_LINE[lang].format(ref=rec.id)
              if asks_emergency_line(t.msg) else
              (PEOPLE_FOLLOW_UP if team == "management" else FOLLOW_UP)[lang].format(ref=rec.id)) if rec else ""
    t.reply = lead + t.safety_notice + follow
    t.handoff_team, t.handoff_reason, t.op_done = team, f"Safety: {hazard}", "paused"


def _backend_reply(t: _Turn) -> bool:
    """Turns the backend answers without the model: a privacy refusal, consent to keep a possible duplicate as a
    separate request, and an explicit typed send (saved if the card is complete, otherwise what's missing).
    Returns False when the model should answer."""
    active, lang = t.active, t.lang
    if reason := guardrails.denied(t.msg, t.name, t.persona_id if t.verified else None):
        # privacy: refused before the model; the open card is untouched and nothing is listed
        last = next((h["content"] for h in reversed(t.history) if h.get("role") == "assistant"), "")
        t.reply = guardrails.refusal(reason, lang, t.name, last)
        if active:
            t.reply += tasks._l(KEPT, lang).format(what=tasks._l(tasks.WHAT[active["kind"]], lang))
        t.op_done = f"refused:{reason}"
    elif active and active.get("possible_duplicate") and guardrails.says_separate(t.msg):
        active["separate"], t.op_done = True, "separate"  # consent recorded; Send is still required
        t.reply = ("Okay, I'll keep it as a separate request. It isn't sent yet; press Send when it looks right."
                   if lang == "en" else "De acuerdo, la dejo como una solicitud aparte. Aún no se envía; pulse Enviar.")
    elif active and guardrails.explicit_send(t.msg) and not tasks.missing(active):
        res = tasks.confirm(t.store, t.session_id, t.persona_id, active["kind"], t.verified, lang)
        t.reply, t.shown = res.message, res.action
        t.records = [res.record] if res.record and res.ok else []
        t.active, t.waiting = tasks.load(t.store, t.session_id, t.key)
        t.before, t.op_done = (repr(t.active), repr(t.waiting)), "complete"
    elif active and guardrails.explicit_send(t.msg):
        # acceptance MN6: "send it" (the whole message) while the card on screen is incomplete. Answered here, not by
        # the model (it told the person to press a Send button that would also refuse): nothing saved; says what's left
        miss = ", ".join(tasks._l(tasks.LABEL[m], lang).lower() for m in tasks.missing(active))
        t.reply = tasks._l(NOT_YET, lang).format(what=tasks._l(tasks.WHAT[active["kind"]], lang), miss=miss)
        t.op_done = "send_refused:incomplete"
    else:
        return False
    return True


def _model_turn(deps: EngineDeps, t: _Turn, target: Target, local_request: bool,
                fallback_on_model_error: bool) -> None:
    """C. The one structured model call; its proposal goes through the task controller (the backend decides)."""
    store, lang = t.store, t.lang
    resumed = None
    if not t.active and (p := tasks.paused(t.waiting)) and t.rd.response != "full_alert" and not (
            store and incident_active(store, t.session_id, t.key)):
        t.active, t.waiting, _ = tasks.apply("resume", None, t.waiting, kind=p["kind"])  # safe again: it comes back
        resumed = tasks._l(BACK, lang).format(what=tasks._l(tasks.WHAT[t.active["kind"]], lang))
    own = tasks.my_requests(store, deps.workbook, t.persona_id, t.verified)
    system = assistant.system_prompt(t.ctx, t.verified, tasks.describe(t.active, t.waiting),
                                     guardrails.property_facts(_samples(deps.settings, local_request)), resumed,
                                     "\n".join(f"- {i.reference}: {i.title} ({i.status}, {i.opened})" for i in own))
    turn = assistant.ask(deps.llm, target, system, t.history, t.msg)
    if turn.result is not None:
        t.result = turn.result
    if turn.proposal is None:
        if turn.error == "MODEL_CONTENT_FILTERED" and t.rd.response == "none" and not t.safety_notice:
            # the CONVERSATION model's content filter refused the message (the classifier was off, unfiltered or
            # said none): treated exactly like a blocked classifier (policy R4b / R4n): a calm line when the rules
            # or the conversation show a sign of danger, otherwise the usual "say it another way" line (no warning)
            t.rd = risk_decide(t.risk.deterministic, SemanticResult(status="blocked", detail="conversation"), t.prior)
            t.risk = t.risk.model_copy(update={"decision": t.rd})
            t.st = risk_responses.select(t.rd, lang)
        safety_shown = t.rd.response != "none" or bool(t.safety_notice) or t.inc is not None
        t.reply = tasks._l(SAFETY_FALLBACK if safety_shown else FALLBACK_REPLY, lang)
        t.reply_source = "template_after_model_error"
        if turn.exc is not None and not safety_shown and (
                turn.error not in FALLBACK_CODES or not fallback_on_model_error):
            raise turn.exc  # an ordinary turn with no safety text: the API's usual error (never a 988 line)
    else:
        p = turn.proposal
        tours_before = _waiting_tours(t.waiting)
        t.active, t.waiting, t.op_done = _apply_proposal(p, t.active, t.waiting, t.ctx, t.verified, lang, t.msg)
        # a tour queued behind the card on screen is said in fixed words, so it is never invisible to the person
        t.queued_tour = bool(t.active) and t.active["kind"] != "tour_request" and _waiting_tours(
            t.waiting) > tours_before
        _add_history(p.include_history, t.active, t.waiting, deps.workbook, t.persona_id, t.verified)
        t.reply, t.reply_source = p.reply, "model"
        t.status_items = own if p.show_my_requests else []
        if p.team != "none" or (t.active and t.active["kind"] == "staff_handoff" and t.op_done == "started"):
            t.handoff_team = p.team if p.team != "none" else (t.active or {}).get("team", "management")
            t.handoff_reason = p.reason or "A team member should help"
        if t.legal and t.active and t.active["kind"] == "staff_handoff" and not t.active.get("guest_repair") and \
                t.active.get("priority") != "urgent":
            # acceptance MN9 (review: new AND already-open notes): an accommodation / fair-housing / legal note goes
            # to people who can answer it. Only the team changes; a visitor's repair note stays with maintenance
            t.active["team"] = t.handoff_team = "leasing" if t.ctx.audience == "prospect" else "management"
            t.handoff_reason = t.handoff_reason or "Accommodation, fair housing or legal question"
    t.trace.add("C_conversation", "ok" if t.reply_source == "model" else "warn",
                f"{t.result.provider}:{t.result.model} op={t.op_done}" + (" (MOCK)" if t.result.is_mock else ""))


def _validate(deps: EngineDeps, t: _Turn, enforce_validation: bool) -> None:
    """What will be shown is checked; model text that fails is replaced by the backend's own sentence. The legal
    boundary is mandatory (it does not depend on `enforce_validation`)."""
    store, ctx, lang = t.store, t.ctx, t.lang
    t.checks = output_checks(t.reply, " ".join(f.value for f in ctx.fields),
                             urgency="emergency" if t.safety_notice else None,
                             user_text=" ".join([*t.said_ever, t.msg]), nothing_sent=not t.records)
    session_saved = [r for r in (store.records(session_id=t.session_id, limit=20) if store else [])
                     if r.get("status") != "urgent_queued"]
    problems: list[str] = []
    legal_kind: str | None = None
    t.model_text = t.reply_source == "model"
    if t.model_text:
        own_items = tasks.my_requests(store, deps.workbook, t.persona_id, t.verified)
        history_text = " ".join([*(f.value for f in ctx.fields if f.name == "related_history"),
                                 *(f"{i.reference} {i.title}" for i in own_items)])
        problems = guardrails.unsupported_claims(
            t.reply, saved_refs={r.id for r in t.records} | {i.reference for i in own_items
                                                             if i.source == "prototype_store"},
            known_refs={i.reference for i in own_items} | set(
                re.findall(r"\b(?:DEMO-[A-Z]+-\d+|I\d{3})\b", history_text)),
            # what they said earlier in THIS chat is grounded too ("your faucet request from before")
            history_text=" ".join([history_text, *t.said_ever, t.msg]),
            own_name=t.name, saved_now=bool(t.records) or (t.active is None and bool(session_saved)))
        t.checks.append(OutputCheck(code="grounded_claims", passed=not problems,
                                    detail="; ".join(problems) or "no unsupported claims"))
        # acceptance MN9 (review): MANDATORY, whatever `enforce_validation` says: model text that states a legal
        # determination or describes a community by who lives there is never emitted; the referral replaces it
        if legal_kind := guardrails.legal_conclusion_kind(t.reply):
            referral, wording = guardrails.legal_referral(lang, prospect=ctx.audience == "prospect")
            t.checks.append(OutputCheck(code="no_legal_conclusion", passed=False,
                                        detail=f"{legal_kind}: replaced by the {wording} referral"))
            t.reply, t.reply_source = referral, "template_after_validation"
    t.reasons = guardrails.reason_codes(t.checks, problems, legal_kind) if t.model_text else []
    if t.reasons:
        log.info("model reply checks failed: %s", ", ".join(t.reasons))  # controlled codes only, never text
    if enforce_validation and t.reply_source == "model" and any(
            (c.code in CRITICAL_CHECKS or c.code == "grounded_claims") and not c.passed for c in t.checks):
        t.reply, t.reply_source = _plain_reply(t.active, lang, session_saved), "template_after_validation"
    if t.queued_tour:
        t.reply = f"{t.reply.rstrip()} {tasks._l(TOUR_NEXT, lang)}"
    t.reply = redact(t.reply)


def _persist(t: _Turn) -> None:
    """D. The task state (only if it changed), the turn and its decision log (codes only, never message text)."""
    store, active = t.store, t.active
    if store is not None and (repr(active), repr(t.waiting)) != t.before:
        tasks.save(store, t.session_id, t.key, active, t.waiting)
    care_kind = t.st.care_kind if not t.safety_notice else None
    safety_state, _ = safety_ui(t.rd, alert_shown=bool(t.safety_notice), care_kind=care_kind, lang=t.lang)
    if store is not None:
        try:
            store.append_turns(t.session_id, t.mode_key, t.key, t.msg, t.reply)
            store.log_gate(t.session_id, t.mode_key, t.key, {
                "op": t.op_done, "action": f"{active['kind']}:{'ready' if not tasks.missing(active) else 'collecting'}"
                if active else None, "records": [r.id for r in t.records], "reply_source": t.reply_source,
                "safety_rule": t.rd.rule, "safety_response": t.rd.response, "safety_semantic": t.risk.semantic.status,
                "requires_human": bool(t.handoff_team), "lang": t.lang,
                "workflow": "human_handoff" if t.handoff_team and not t.safety_notice else None,
                # acceptance 2026-11-17: why the safety layer decided what it did, and which reply checks failed
                # (codes only: never message text, prompts or resident data)
                "safety_trace": risk_diagnostics(t.risk, t.msg, safety_state),
                # (only for model-written text: backend templates are not validated output)
                "validator_failed": sorted({c.code for c in t.checks if not c.passed}) if t.model_text else [],
                "validator_reasons": t.reasons})
        except Exception as e:  # a failed save never replaces the reply, safety text included
            log.error("turn not persisted: %s", type(e).__name__)
    t.trace.add("D_tasks", "ok",
                f"{t.op_done}; active={active['kind'] if active else None}; waiting={len(t.waiting)}")


def _response(deps: EngineDeps, t: _Turn, mode: Mode, channel: Channel, target: Target) -> ChatResponse:
    ctx, rd, result, lang = t.ctx, t.rd, t.result, t.lang
    care_kind = t.st.care_kind if not t.safety_notice else None
    safety_state, safety_contacts = safety_ui(rd, alert_shown=bool(t.safety_notice), care_kind=care_kind, lang=lang)
    handoff = None
    if not t.handoff_team and rd.needs_human:  # e.g. a distress care line: a person should check in (not sent)
        handoff = risk_escalation.recommend(rd, sorted({f.name for f in ctx.fields}))
    if t.handoff_team:
        team = t.handoff_team if t.handoff_team in ("emergency_maintenance", "maintenance", "leasing", "accounting",
                                                    "management") else "management"
        handoff = HandoffRecommendation(
            team=team, priority="urgent" if t.safety_notice else "normal",  # type: ignore[arg-type]
            category="safety_emergency" if t.safety_notice else "human_requested", reasons=[t.handoff_reason],
            summary=f"{ctx.audience} · {team}", included_fields=sorted({f.name for f in ctx.fields}),
            contact_guidance=None, delivery_note="Not sent. This prototype has no staff notification integration.")
    return ChatResponse(
        reply=t.reply, safety_notice=t.safety_notice, emergency_kind=t.hazard if t.safety_notice else None,
        care_kind=care_kind, care_note=t.st.care_note if care_kind else None, risk=t.risk,  # type: ignore[arg-type]
        safety_heading=emergency_heading(t.hazard, lang) if t.safety_notice else None,
        safety_state=safety_state, safety_contacts=safety_contacts,  # type: ignore[arg-type]
        mode=mode, audience=ctx.audience, recommended_handoff=handoff is not None,  # type: ignore[arg-type]
        handoff_reason=t.handoff_reason or None, handoff_category=handoff.category if handoff else "none",
        model_handoff=False, policy_signals=[], output_checks=t.checks,
        source_context_fields=[f"{f.name} ← {f.source}" for f in ctx.fields], provider=result.provider,
        requested_model=result.requested_model, model=result.model, is_mock=result.is_mock,
        parse_mode=result.parse_mode, temperature=deps.llm.generation_config(target).temperature,
        prompt_version=PROMPT_VERSION, usage=Usage(input_tokens=result.input_tokens,
                                                   output_tokens=result.output_tokens,
                                                   estimated_cost_usd=result.estimated_cost_usd),
        latency_ms=result.latency_ms, stop_reason=result.stop_reason, session_id=t.session_id,
        created_at=datetime.now(UTC), handoff=handoff, pipeline=t.trace.steps, channel=channel,
        language=lang, reply_source=t.reply_source,  # type: ignore[arg-type]
        action=tasks.card(t.active, lang) if t.active else t.shown,
        records_created=t.records, status_items=t.status_items,
        identity_note=identity_note(ctx, t.verified),
        action_cleared=t.kind_before if t.op_done.startswith("cancel") else None,
    )


def _apply_proposal(p: assistant.Proposal, active, waiting, ctx: SafeContext, verified: bool, lang, msg: str):  # noqa: ANN001,ANN202
    """Policy on the model's proposal, then the controller. Guests and prospects never get a work order: a repair
    becomes a note for the office that needs community and unit."""
    op, kind = p.op, p.kind if p.kind in tasks.FIELDS else None
    values = dict(p.fields)
    new = None
    if op == "start" and kind:
        guest_repair = _guest_repair(kind, values, p.team, verified, ctx.audience)
        if guest_repair:
            kind = "staff_handoff"
            values.setdefault("message", values.get("issue") or msg)
        if kind == "staff_handoff":
            values.setdefault("message", msg)
            values.setdefault("topic", p.reason or ("Repair reported by a visitor" if guest_repair
                                                    else "Asked for a team member"))
        team = "maintenance" if guest_repair else (p.team if p.team != "none" else None)
        new = tasks.new_task(kind, lang, guest_repair=guest_repair, team=team, topic=values.get("topic"))
        if kind == "staff_handoff" and active is not None:  # the note carries what the person already told us
            earlier = "; ".join(v["value"] for k, v in active.get("fields", {}).items()
                                if k in ("issue", "location", "entry", "message") and v.get("value"))
            values.setdefault("earlier", earlier[:240])
        if kind == "maintenance_request" and (hist := _open_related(ctx, values.get("issue", msg))):
            new["fields"]["history"] = {"value": hist, "source": "on_file"}
    elif op == "update" and active is not None and active.get("guest_repair") and values.get("issue"):
        values.setdefault("message", values["issue"])
    active, waiting, done = tasks.apply(op if op in ("start", "update", "suspend", "resume", "cancel") else "none",
                                        active, waiting, kind=kind, values=values, new=new)
    for i, need in enumerate(p.other_needs):  # a second need in the same message waits; nothing is dropped
        need_kind = p.other_kinds[i] if i < len(p.other_kinds) else "staff_handoff"
        if need_kind == "maintenance_request" and verified and ctx.persona_kind == "resident":
            # remediation P2: a signed-in resident's second repair waits as its own repair card (never as a note);
            # a need that repeats the open card or a waiting repair is not added twice
            def norm(x: str) -> str:
                return " ".join(re.findall(r"\w+", x.casefold()))
            known = {norm(str((t.get("fields", {}).get("issue") or {}).get("value", "")))
                     for t in [*([active] if active else []), *waiting] if t.get("kind") == "maintenance_request"}
            if norm(need) in known:  # only the same repair again is skipped; when in doubt the card is kept
                continue
            repair = tasks.new_task("maintenance_request", lang)
            tasks.set_fields(repair, {"issue": need})
            waiting = [*waiting, repair]
            continue
        if need_kind == "tour_request":
            # acceptance MN6: a tour asked for alongside another need waits as a TOUR card (it used to become an "Also
            # asked about" note, which can never be sent as a tour). No fields are guessed from the text: the card asks.
            if any(t.get("kind") == "tour_request" and not t.get("declined") for t in [*([active] if active else []),
                                                                                     *waiting]):
                continue  # a tour card is already open or waiting
            waiting = [*waiting, tasks.new_task("tour_request", lang)]
            continue
        note = tasks.new_task("staff_handoff", lang, topic="Also asked about", team="leasing" if re.search(
            r"leas|renew|rent|contrat|renov", need, re.I) else "management")
        tasks.set_fields(note, {"topic": "Also asked about", "message": need})
        waiting = [*waiting, note]
    return active, waiting, done


def _waiting_tours(waiting: list) -> int:
    return sum(1 for t in waiting if t.get("kind") == "tour_request" and not t.get("declined"))


def _guest_repair(kind: str, values: dict[str, str], team: str, verified: bool, audience: str) -> bool:
    """A not-signed-in person's REPAIR becomes a note for the office that needs community and unit. Acceptance MN6: a
    note that merely names a community (a prospect's pricing, leasing or tour question) is not a repair, and a
    prospect is never asked for an apartment unit number."""
    if verified:
        return False
    if kind == "maintenance_request":
        return True
    return kind == "staff_handoff" and audience != "prospect" and (
        team in ("maintenance", "emergency_maintenance") or bool(values.get("issue")))


def _add_history(scope: str, active, waiting, wb, persona_id, verified: bool) -> None:  # noqa: ANN001
    """History on a note comes from the person's own record, never from model prose. A note made from a repair
    carries that repair's related history by default; 'related' / 'all' when the person asks for it."""
    if not active or active["kind"] != "staff_handoff" or not verified:
        return
    repair = next((t for t in [*waiting] if t["kind"] == "maintenance_request" and not t.get("declined")), None)
    about = " ".join(v.get("value", "") for k, v in (repair or active).get("fields", {}).items()
                     if k in ("issue", "message", "topic"))
    if scope == "all":
        text = tasks.history_text(tasks.history_lines(wb, persona_id, verified))
    elif scope == "related" or (repair is not None and "history" not in active["fields"]):
        text = tasks.history_text(tasks.history_lines(wb, persona_id, verified, about=about))
    else:
        return
    if text:
        active["fields"]["history"] = {"value": text, "source": "on_file"}


def _open_related(ctx: SafeContext, issue: str) -> str | None:
    """The resident's own open request about the SAME object, from their authorized context (repeat issues)."""
    from app.utterance import things
    objs = things(issue)
    open_items = [f.value for f in ctx.fields if f.name == "related_history" and " · maintenance · " in f.value
                  and " open" in f.value and objs & things(f.value)]
    return open_items[-1][:200] if open_items else None


def _plain_reply(active, lang: str, saved: list | None = None) -> str:  # noqa: ANN001
    """What is shown when a model reply can't be: the backend's own facts, nothing more."""
    if not active and saved:
        ref = saved[0]["id"]
        return (f"{ref} is saved in this demo only; nobody at McKinley has been notified." if lang == "en" else
                f"{ref} está guardada solo en esta demostración; no se avisó a nadie de McKinley.")
    if active:
        what = tasks._l(tasks.WHAT[active["kind"]], lang)  # type: ignore[arg-type]
        return (f"Your {what} is below; it isn't sent yet." if lang == "en" else
                f"Su {what} está abajo; aún no se ha enviado.")
    return tasks._l(FALLBACK_REPLY, lang)  # type: ignore[arg-type]


def _last_lang(store, session_id: str, mode_key: str, key: str) -> str | None:  # noqa: ANN001
    """The language of this conversation so far (kept on the previous turn's metadata row)."""
    return ((store.last_gate(session_id, mode_key, key) if store else None) or {}).get("lang")


def _samples(settings: Settings, local: bool) -> bool:
    return settings.knowledge_content_mode == "demo_samples" and settings.app_env != "hosted" and local
