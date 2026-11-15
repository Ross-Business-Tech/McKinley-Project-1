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
from dataclasses import dataclass, replace
from datetime import UTC, datetime

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
    SafeContext,
    Usage,
)
from app.personas import apply_account_holder_rule, build_context, holder_disclaimed
from app.risk import escalation as risk_escalation
from app.risk import responses as risk_responses
from app.risk.classifier import SemanticRiskClassifier
from app.risk.incident import active as incident_active
from app.risk.incident import prior_hazards as incident_prior_hazards
from app.risk.incident import step as incident_step
from app.risk.pipeline import assess
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
                  "LLM_BUDGET_EXHAUSTED", "BAD_OUTPUT"}
FALLBACK_REPLY = ("Sorry, I couldn't work that out just now. Could you say it another way?",
                  "Perdón, no pude procesarlo ahora. ¿Puede decirlo de otra forma?")
KEPT = (" Your {what} is still here, unchanged.", " Su {what} sigue aquí, sin cambios.")
BACK = ("Thanks for the update. Your {what} from before is back, not sent yet.",
        "Gracias por avisar. Su {what} de antes volvió, sin enviar.")


def run_turn(
    deps: EngineDeps, message: str, mode: Mode, persona_id: str | None, session_id: str | None,
    use_history: bool = True, target: Target | None = None, gate_provider: str | None = None,  # noqa: ARG001
    channel: Channel = "web_chat", enforce_validation: bool = True, fallback_on_model_error: bool = True,
    principal: Principal | None = None, local_request: bool = True,  # noqa: ARG001
) -> ChatResponse:
    settings = deps.settings
    target = target or deps.llm.default_target
    session_id = session_id or uuid.uuid4().hex
    mode_key = f"aware|{target.key}"
    trace = _Trace()
    msg = clean_message(message)

    # ---- A. identity: derived server-side only; message text and the model never change it --------------------
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

    # ---- B. safety on every message -------------------------------------------------------------------------
    history = store.history(session_id, mode_key, key) if store else []
    said_before = [m["content"] for m in history if m["role"] == "user"]
    prior = ([r.get("hazard") for r in store.records(session_id=session_id, limit=50)
              if r.get("status") == "urgent_queued"] if store else [])
    if store:
        prior = incident_prior_hazards(store, session_id, key, msg, len(said_ever) + 1, prior)
    risk = assess(msg, said_before[-3:], deps.risk, prior)  # type: ignore[arg-type]
    risk = incident_step(store, session_id, key, msg, risk, len(said_ever) + 1)
    rd = risk.decision
    trace.add("B_safety", "warn" if rd.response != "none" else "ok",
              f"{rd.rule}: {rd.response}; semantic={risk.semantic.status}")

    lang = assistant.language(msg, _last_lang(store, session_id, mode_key, key),
                              next((f.value for f in ctx.fields if f.name == "preferred_language"), None))
    active, waiting = tasks.load(store, session_id, key)
    before, kind_before, shown = (repr(active), repr(waiting)), (active or {}).get("kind"), None
    records, status_items = [], []
    result: LLMResult = _no_model(target, "deterministic")
    reply_source, handoff_team, handoff_reason, op_done = "template", None, "", "none"
    st = risk_responses.select(rd, lang)
    safety_notice = st.safety_notice if rd.response == "full_alert" else None
    inc = incident_active(store, session_id, key) if store else None
    hazard = rd.kind
    if not safety_notice and inc and REFUSING_TO_LEAVE.search(msg):
        # refusing to leave during an active incident is still an emergency turn: the approved steps again
        hazard = inc.kind
        safety_notice = emergency_notice(hazard, lang)

    if safety_notice:
        # an emergency interrupts everything: approved fixed text, one urgent prototype note, the task waits unsent
        team = "management" if is_people_hazard(hazard or "") else "emergency_maintenance"
        inc_now = incident_active(store, session_id, key) if store else None  # this turn's incident (just opened)
        rec, existed = tasks.save_urgent_note(store, session_id, persona_id, hazard or "other", msg, lang, team,
                                              incident=inc_now.started_at if inc_now else "")
        if rec and not existed:
            records = [rec]
        active, waiting = tasks.pause_for_emergency(active, waiting)
        lead = REFUSE_LEAD[lang] if existed and REFUSING_TO_LEAVE.search(msg) else ""
        follow = (QUEUE_NOTE[lang] if not existed else " " + NO_LINE[lang].format(ref=rec.id)
                  if asks_emergency_line(msg) else
                  (PEOPLE_FOLLOW_UP if team == "management" else FOLLOW_UP)[lang].format(ref=rec.id)) if rec else ""
        reply = lead + safety_notice + follow
        handoff_team, handoff_reason, op_done = team, f"Safety: {hazard}", "paused"
    elif reason := guardrails.denied(msg, name, persona_id if verified else None):
        # privacy: refused before the model; the open card is untouched and nothing is listed
        last = next((h["content"] for h in reversed(history) if h.get("role") == "assistant"), "")
        reply = guardrails.refusal(reason, lang, name, last)
        if active:
            reply += tasks._l(KEPT, lang).format(what=tasks._l(tasks.WHAT[active["kind"]], lang))
        op_done = f"refused:{reason}"
    elif active and active.get("possible_duplicate") and guardrails.says_separate(msg):
        active["separate"], op_done = True, "separate"  # consent recorded; Send is still required
        reply = ("Okay, I'll keep it as a separate request. It isn't sent yet; press Send when it looks right."
                 if lang == "en" else "De acuerdo, la dejo como una solicitud aparte. Aún no se envía; pulse Enviar.")
    elif active and guardrails.explicit_send(msg) and not tasks.missing(active):
        res = tasks.confirm(store, session_id, persona_id, active["kind"], verified, lang)
        reply, records, shown = res.message, [res.record] if res.record and res.ok else [], res.action
        active, waiting = tasks.load(store, session_id, key)
        before, op_done = (repr(active), repr(waiting)), "complete"
    else:
        resumed = None
        if not active and (p := tasks.paused(waiting)) and rd.response != "full_alert" and not (
                store and incident_active(store, session_id, key)):
            active, waiting, _ = tasks.apply("resume", None, waiting, kind=p["kind"])  # safe again: it comes back
            resumed = tasks._l(BACK, lang).format(what=tasks._l(tasks.WHAT[active["kind"]], lang))
        own = tasks.my_requests(store, deps.workbook, persona_id, verified)
        system = assistant.system_prompt(ctx, verified, tasks.describe(active, waiting),
                                         guardrails.property_facts(_samples(settings, local_request)), resumed,
                                         "\n".join(f"- {i.reference}: {i.title} ({i.status}, {i.opened})" for i in own))
        turn = assistant.ask(deps.llm, target, system, history, msg)
        if turn.result is not None:
            result = turn.result
        if turn.proposal is None:
            reply, reply_source = tasks._l(FALLBACK_REPLY, lang), "template_after_model_error"
            if turn.exc is not None and (turn.error not in FALLBACK_CODES or not fallback_on_model_error):
                raise turn.exc
        else:
            p = turn.proposal
            active, waiting, op_done = _apply_proposal(p, active, waiting, ctx, verified, lang, msg)
            _add_history(p.include_history, active, waiting, deps.workbook, persona_id, verified)
            reply, reply_source = p.reply, "model"
            status_items = own if p.show_my_requests else []
            if p.team != "none" or (active and active["kind"] == "staff_handoff" and op_done == "started"):
                handoff_team = p.team if p.team != "none" else (active or {}).get("team", "management")
                handoff_reason = p.reason or "A team member should help"
        trace.add("C_conversation", "ok" if reply_source == "model" else "warn",
                  f"{result.provider}:{result.model} op={op_done}" + (" (MOCK)" if result.is_mock else ""))

    # ---- validate what will be shown (model text is untrusted) --------------------------------------------------
    checks: list[OutputCheck] = output_checks(reply, " ".join(f.value for f in ctx.fields),
                                              urgency="emergency" if safety_notice else None,
                                              user_text=" ".join([*said_ever, msg]), nothing_sent=not records)
    session_saved = [r for r in (store.records(session_id=session_id, limit=20) if store else [])
                     if r.get("status") != "urgent_queued"]
    if reply_source == "model":
        own_items = tasks.my_requests(store, deps.workbook, persona_id, verified)
        history_text = " ".join([*(f.value for f in ctx.fields if f.name == "related_history"),
                                 *(f"{i.reference} {i.title}" for i in own_items)])
        problems = guardrails.unsupported_claims(
            reply, saved_refs={r.id for r in records} | {i.reference for i in own_items
                                                         if i.source == "prototype_store"},
            known_refs={i.reference for i in own_items} | set(
                re.findall(r"\b(?:DEMO-[A-Z]+-\d+|I\d{3})\b", history_text)),
            # what they said earlier in THIS chat is grounded too ("your faucet request from before")
            history_text=" ".join([history_text, *said_ever, msg]),
            own_name=name, saved_now=bool(records) or (active is None and bool(session_saved)))
        if problems:
            log.info("model reply replaced: %s", "; ".join(problems))  # reasons only, never the text
        checks.append(OutputCheck(code="grounded_claims", passed=not problems,
                                  detail="; ".join(problems) or "no unsupported claims"))
    if enforce_validation and reply_source == "model" and any(
            (c.code in CRITICAL_CHECKS or c.code == "grounded_claims") and not c.passed for c in checks):
        reply, reply_source = _plain_reply(active, lang, session_saved), "template_after_validation"
    reply = redact(reply)

    # ---- D. persist the task state (only if it changed) and the turn ------------------------------------------
    if store is not None and (repr(active), repr(waiting)) != before:
        tasks.save(store, session_id, key, active, waiting)
    care_kind = st.care_kind if not safety_notice else None
    safety_state, safety_contacts = safety_ui(rd, alert_shown=bool(safety_notice), care_kind=care_kind, lang=lang)
    if store is not None:
        try:
            store.append_turns(session_id, mode_key, key, msg, reply)
            store.log_gate(session_id, mode_key, key, {
                "op": op_done, "action": f"{active['kind']}:{'ready' if not tasks.missing(active) else 'collecting'}"
                if active else None, "records": [r.id for r in records], "reply_source": reply_source,
                "safety_rule": rd.rule, "safety_response": rd.response, "safety_semantic": risk.semantic.status,
                "requires_human": bool(handoff_team), "lang": lang,
                "workflow": "human_handoff" if handoff_team and not safety_notice else None})
        except Exception as e:  # a failed save never replaces the reply, safety text included
            log.error("turn not persisted: %s", type(e).__name__)
    trace.add("D_tasks", "ok", f"{op_done}; active={active['kind'] if active else None}; waiting={len(waiting)}")

    handoff = None
    if not handoff_team and rd.needs_human:  # e.g. a distress care line: a person should check in (not sent)
        handoff = risk_escalation.recommend(rd, sorted({f.name for f in ctx.fields}))
    if handoff_team:
        team = handoff_team if handoff_team in ("emergency_maintenance", "maintenance", "leasing", "accounting",
                                                "management") else "management"
        handoff = HandoffRecommendation(
            team=team, priority="urgent" if safety_notice else "normal",  # type: ignore[arg-type]
            category="safety_emergency" if safety_notice else "human_requested", reasons=[handoff_reason],
            summary=f"{ctx.audience} · {team}", included_fields=sorted({f.name for f in ctx.fields}),
            contact_guidance=None, delivery_note="Not sent. This prototype has no staff notification integration.")
    return ChatResponse(
        reply=reply, safety_notice=safety_notice, emergency_kind=hazard if safety_notice else None,
        care_kind=care_kind, care_note=st.care_note if care_kind else None, risk=risk,  # type: ignore[arg-type]
        safety_heading=emergency_heading(hazard, lang) if safety_notice else None,
        safety_state=safety_state, safety_contacts=safety_contacts,  # type: ignore[arg-type]
        mode=mode, audience=ctx.audience, recommended_handoff=handoff is not None,  # type: ignore[arg-type]
        handoff_reason=handoff_reason or None, handoff_category=handoff.category if handoff else "none",
        model_handoff=False, policy_signals=[], output_checks=checks,
        source_context_fields=[f"{f.name} ← {f.source}" for f in ctx.fields], provider=result.provider,
        requested_model=result.requested_model, model=result.model, is_mock=result.is_mock,
        parse_mode=result.parse_mode, temperature=deps.llm.generation_config(target).temperature,
        prompt_version=PROMPT_VERSION, usage=Usage(input_tokens=result.input_tokens,
                                                   output_tokens=result.output_tokens,
                                                   estimated_cost_usd=result.estimated_cost_usd),
        latency_ms=result.latency_ms, stop_reason=result.stop_reason, session_id=session_id,
        created_at=datetime.now(UTC), handoff=handoff, pipeline=trace.steps, channel=channel,
        language=lang, reply_source=reply_source,  # type: ignore[arg-type]
        action=tasks.card(active, lang) if active else shown,
        records_created=records, status_items=status_items,
        identity_note=identity_note(ctx, verified),
        action_cleared=kind_before if op_done.startswith("cancel") else None,
    )


def _apply_proposal(p: assistant.Proposal, active, waiting, ctx: SafeContext, verified: bool, lang, msg: str):  # noqa: ANN001,ANN202
    """Policy on the model's proposal, then the controller. Guests and prospects never get a work order: a repair
    becomes a note for the office that needs community and unit."""
    op, kind = p.op, p.kind if p.kind in tasks.FIELDS else None
    values = dict(p.fields)
    new = None
    if op == "start" and kind:
        guest_repair = not verified and (kind == "maintenance_request" or (
            kind == "staff_handoff" and bool(values.get("unit") or values.get("community"))))
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
    for need in p.other_needs:  # a second need in the same message waits as its own note; nothing is dropped
        note = tasks.new_task("staff_handoff", lang, topic="Also asked about", team="leasing" if re.search(
            r"leas|renew|rent|contrat|renov", need, re.I) else "management")
        tasks.set_fields(note, {"topic": "Also asked about", "message": need})
        waiting = [*waiting, note]
    return active, waiting, done


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
