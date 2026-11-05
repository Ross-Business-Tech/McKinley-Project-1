"""Selects the configured gate (DECISION_GATE_PROVIDER), applies the safety floor and falls back to rules."""

import time

from app.config import Settings
from app.gates.base import GateContext, GateProvider, GateUnavailable
from app.gates.jev_gate import JevGate
from app.gates.llm_gate import LLMGate
from app.gates.policy import apply_safety_floor
from app.gates.rules import classify_rules
from app.llm import LLMGateway, Target
from app.models import GateDecision

GATE_PROVIDERS = ["rules", "llm", "jev"]


class DecisionGateService:
    def __init__(self, settings: Settings, gateway: LLMGateway):
        self.settings = settings
        self.gateway = gateway

    @property
    def configured(self) -> str:
        return self.settings.decision_gate_provider

    def gate_target(self) -> Target:
        raw = self.settings.decision_gate_llm_target
        return Target.parse(raw) if raw else self.gateway.default_target

    def provider(self, name: str) -> GateProvider | None:
        s = self.settings
        if name == "llm":
            return LLMGate(self.gateway, self.gate_target(), s.decision_gate_timeout_seconds)
        if name == "jev":
            key = s.typesafe_api_key.get_secret_value().strip() if s.typesafe_api_key else None
            return JevGate(key or None, s.typesafe_base_url, s.jev_model, s.decision_gate_timeout_seconds)
        return None

    def availability(self) -> dict[str, str]:
        s = self.settings
        out = {"rules": "ready (deterministic, always on as safety floor)"}
        target = self.gate_target()
        ready, status = self.gateway.provider_ready(target.provider)
        out["llm"] = f"{'ready' if ready else 'unavailable'}: {target.key} ({status})"
        out["jev"] = ("configured (EXPERIMENTAL, response schema undocumented)" if s.typesafe_api_key
                      else "unavailable: TYPESAFE_API_KEY not set")
        return out

    def classify(self, message: str, ctx: GateContext, provider: str | None = None) -> GateDecision:
        """Never raises: external failures fall back to the rules decision and are recorded."""
        name = provider or self.configured
        start = time.perf_counter()
        rules = classify_rules(message, ctx)
        rules = rules.model_copy(update={
            "latency_ms": int((time.perf_counter() - start) * 1000), "requested_provider": name,
        })
        gate = self.provider(name)
        if gate is None:
            return rules
        try:
            external = gate.classify(message, ctx, rules)
        except GateUnavailable as e:
            return rules.model_copy(update={"fallback_used": True, "fallback_reason": f"{e.code}: {e.message}"})
        return apply_safety_floor(external.model_copy(update={"requested_provider": name}), rules, ctx)
