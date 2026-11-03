"""Provider registry and gateway. Add a provider by implementing `LLMProvider` and registering it here."""

from collections.abc import Callable

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
                              s.openrouter_app_title)


def _ollama(s: Settings) -> LLMProvider:
    from app.llm.ollama import OllamaProvider
    return OllamaProvider(s.base_url_for("ollama") or "http://localhost:11434")


def _mock(s: Settings) -> LLMProvider:
    from app.llm.mock import MockProvider
    return MockProvider()


def _anthropic(s: Settings) -> LLMProvider:
    from app.llm.anthropic_provider import AnthropicProvider
    return AnthropicProvider(s.api_key_for("anthropic"), s.anthropic_effort)


# Gemini, Groq, etc. can be added here (Groq and many others are OpenAI-compatible like OpenRouter).
FACTORIES: dict[str, Callable[[Settings], LLMProvider]] = {
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
        if provider in ("openrouter", "anthropic"):
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
            temperature=None if target.provider == "anthropic" else s.llm_temperature,
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

    def complete(self, system: str, messages: list[dict[str, str]], target: Target | None = None,
                 strict_model: bool = True) -> LLMResult:
        target = target or self.default_target
        result = self._provider(target.provider).complete(
            system, messages, target, self.generation_config(target)
        )
        if strict_model and not same_model(result.model, target.model):
            raise LLMError(
                "MODEL_SWITCHED",
                f"Provider served '{result.model}' instead of requested '{target.model}'. Result discarded to "
                "keep the evaluation controlled.",
            )
        return result
