"""Provider registry and gateway. Add a provider by implementing `LLMProvider` and registering it here."""

from collections.abc import Callable
from typing import Any

from app.config import Settings
from app.llm.base import (
    GenerationConfig,
    LLMError,
    LLMProvider,
    LLMResult,
    ModelOutput,
    Target,
    parse_output,
)

__all__ = [
    "GenerationConfig", "LLMError", "LLMGateway", "LLMProvider", "LLMResult", "ModelOutput", "Target",
    "parse_output", "SUPPORTED_PROVIDERS",
]


def _openrouter(s: Settings) -> LLMProvider:
    from app.llm.openrouter import OpenRouterProvider
    return OpenRouterProvider(s.api_key_for("openrouter"), s.base_url_for("openrouter") or "",
                              s.openrouter_app_title, reasoning_effort=s.openrouter_reasoning_effort or None)


def _ollama(s: Settings) -> LLMProvider:
    from app.llm.ollama import OllamaProvider
    return OllamaProvider(s.base_url_for("ollama") or "http://localhost:11434")


def _mock(s: Settings) -> LLMProvider:
    from app.llm.mock import MockProvider
    return MockProvider()


def _gemini(s: Settings) -> LLMProvider:
    base_url = s.base_url_for("gemini")
    if base_url:  # an OpenAI-compatible gateway in front of Gemini (GEMINI_BASE_URL / LLM_BASE_URL)
        from app.llm.gemini_compat import GeminiCompatProvider
        return GeminiCompatProvider(s.api_key_for("gemini"), base_url, s.openrouter_app_title,
                                    thinking_level=s.gemini_thinking_level or None)
    from app.llm.gemini_provider import GeminiProvider
    return GeminiProvider(s.api_key_for("gemini"), thinking_level=s.gemini_thinking_level or None)


def _anthropic(s: Settings) -> LLMProvider:
    from app.llm.anthropic_provider import AnthropicProvider
    return AnthropicProvider(s.api_key_for("anthropic"), s.anthropic_effort)


# Gemini, Groq, etc. can be added here (Groq and many others are OpenAI-compatible like OpenRouter).
FACTORIES: dict[str, Callable[[Settings], LLMProvider]] = {
    "gemini": _gemini,
    "openrouter": _openrouter,
    "ollama": _ollama,
    "mock": _mock,
    "anthropic": _anthropic,
}
SUPPORTED_PROVIDERS = list(FACTORIES)


def _normalize_model(m: str) -> str:
    m = m.strip().lower()
    for suffix in (":free", ":latest"):
        if m.endswith(suffix):
            m = m[: -len(suffix)]
    return m


def same_model(served: str, requested: str) -> bool:
    """True when the served ID is the requested model (allowing a dated snapshot suffix, e.g. '-20260901')."""
    s, r = _normalize_model(served), _normalize_model(requested)
    return s == r or (s.startswith(r + "-") and s[len(r) + 1:].replace("-", "").isdigit())


class LLMGateway:
    """Resolves a Target to its provider and enforces 'no silent model switching'."""

    def __init__(self, settings: Settings, providers: dict[str, LLMProvider] | None = None):
        self.settings = settings
        self._providers: dict[str, LLMProvider] = dict(providers or {})

    @property
    def default_target(self) -> Target:
        return Target(self.settings.llm_provider, self.settings.llm_model)

    def eval_targets(self) -> list[Target]:
        targets: list[Target] = []
        for raw in self.settings.eval_targets.split(","):
            if raw.strip():
                try:
                    t = Target.parse(raw)
                except ValueError:
                    continue
                if t.provider in FACTORIES and t not in targets:
                    targets.append(t)
        if self.default_target not in targets:
            targets.insert(0, self.default_target)
        return targets

    def provider_ready(self, provider: str) -> tuple[bool, str]:
        if provider in ("openrouter", "anthropic", "gemini"):
            ok = bool(self.settings.api_key_for(provider))
            return ok, "API key configured" if ok else "NEEDS_API_KEY"
        if provider == "ollama":
            return True, f"local server expected at {self.settings.base_url_for('ollama')}"
        if provider == "mock":
            return True, "deterministic mock (not a language model)"
        return False, "unsupported provider"

    def generation_config(self, target: Target) -> GenerationConfig:
        s = self.settings
        return GenerationConfig(
            max_tokens=s.llm_max_tokens,
            # Current Claude models reject temperature; Gemini 3.6 ignores it (Google: deprecated, future models 400).
            # None = not sent, and recorded as not set.
            temperature=None if target.provider in ("anthropic", "gemini") else s.llm_temperature,
            timeout_seconds=s.llm_timeout_seconds,
            max_retries=s.llm_max_retries,
        )

    def _provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            factory = FACTORIES.get(name)
            if not factory:
                raise LLMError("UNSUPPORTED_PROVIDER", f"Provider '{name}' is not supported.", http_status=400)
            self._providers[name] = factory(self.settings)
        return self._providers[name]

    # ---- central live-call budget and ledger (metadata only) ----
    def _calls_so_far(self) -> int:
        led = self.settings.llm_call_ledger
        if led:
            try:
                with open(led, encoding="utf-8") as f:
                    return sum(1 for line in f if line.strip())
            except FileNotFoundError:
                return 0
        return getattr(self, "_count", 0)

    def _check_budget(self) -> None:
        budget = self.settings.llm_call_budget
        if budget and self._calls_so_far() >= budget:
            raise LLMError("LLM_BUDGET_EXHAUSTED",
                           f"The live model-call budget ({budget}) is used up; no call was made.", http_status=503)

    def _record(self, target: Target, schema_name: str, result: LLMResult | None, error: str | None) -> None:
        import json
        import time

        self._count = getattr(self, "_count", 0) + 1
        led = self.settings.llm_call_ledger
        if not led:
            return
        extra = result.extra if result else {}
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "execution": "LIVE", "provider": target.provider,
               "requested_model": target.model, "served_model": result.model if result else None,
               "schema": schema_name, "latency_ms": result.latency_ms if result else None,
               "input_tokens": result.input_tokens if result else None,
               "output_tokens": result.output_tokens if result else None,
               "thinking_tokens": extra.get("thinking_tokens"), "reasoning": extra.get("reasoning"),
               "parse_mode": result.parse_mode if result else None, "error_code": error}
        with open(led, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def complete(self, system: str, messages: list[dict[str, str]], target: Target | None = None,
                 strict_model: bool = True, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply", cfg: GenerationConfig | None = None) -> LLMResult:
        target = target or self.default_target
        cfg = cfg or self.generation_config(target)
        provider = self._provider(target.provider)
        live = target.provider != "mock"
        if live:
            self._check_budget()
        try:
            if schema is None:
                result = provider.complete(system, messages, target, cfg)
            else:
                result = provider.complete(system, messages, target, cfg, schema=schema, schema_name=schema_name)
        except LLMError as e:
            if live and e.code not in ("NEEDS_API_KEY", "LLM_BUDGET_EXHAUSTED"):
                self._record(target, schema_name, None, e.code)
            raise
        if live:
            self._record(target, schema_name, result, None)
        if strict_model and not same_model(result.model, target.model):
            raise LLMError(
                "MODEL_SWITCHED",
                f"Provider served '{result.model}' instead of requested '{target.model}'. Result discarded to "
                "keep the evaluation controlled.",
            )
        return result
