"""Optional Anthropic Claude provider. Install with `uv sync --extra anthropic`; not required to run the app.

Current Claude models reject temperature, so `effort` is the sampling control and temperature is recorded as None.
"""

import time
from typing import Any

from app.llm.base import OUTPUT_SCHEMA, GenerationConfig, LLMError, LLMResult, Target, parse_output

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {  # published list prices cached 2026-10; estimates only
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None, effort: str):
        self._api_key = api_key
        self._effort = effort
        self._client: Any = None

    def _get_client(self, cfg: GenerationConfig) -> Any:
        if not self._api_key:
            raise LLMError("NEEDS_API_KEY", "ANTHROPIC_API_KEY is not configured on the backend.", http_status=503)
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("PROVIDER_NOT_INSTALLED",
                           "Anthropic SDK not installed. Run: uv sync --extra anthropic", http_status=503) from e
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key, timeout=cfg.timeout_seconds,
                                               max_retries=cfg.max_retries)
        return self._client

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig) -> LLMResult:
        client = self._get_client(cfg)
        import anthropic

        start = time.perf_counter()
        try:
            resp = client.messages.create(
                model=target.model,
                max_tokens=max(cfg.max_tokens, 2000),  # leave room for adaptive thinking
                system=system,
                messages=messages,
                output_config={"effort": self._effort,
                               "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("MODEL_AUTH_ERROR", "Anthropic rejected the API key (401).") from e
        except anthropic.NotFoundError as e:
            raise LLMError("MODEL_NOT_FOUND", f"Anthropic model '{target.model}' not found (404).") from e
        except anthropic.RateLimitError as e:
            raise LLMError("MODEL_RATE_LIMITED", "Anthropic rate limit (429).", retryable=True,
                           http_status=503) from e
        except anthropic.APITimeoutError as e:
            raise LLMError("MODEL_TIMEOUT", "Anthropic request timed out.", retryable=True, http_status=504) from e
        except anthropic.APIConnectionError as e:
            raise LLMError("MODEL_CONNECTION_ERROR", "Could not reach the Anthropic API.", retryable=True) from e
        except anthropic.APIStatusError as e:
            raise LLMError("MODEL_API_ERROR", f"Anthropic API error ({e.status_code}).",
                           retryable=e.status_code >= 500) from e
        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.stop_reason == "refusal":
            raise LLMError("MODEL_REFUSAL", "The model declined this request.")
        if resp.stop_reason == "max_tokens":
            raise LLMError("MODEL_TRUNCATED", "Model output hit max_tokens before completing.")
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        output, mode = parse_output(text)
        price = PRICES_PER_MTOK.get(resp.model)
        cost = (round((resp.usage.input_tokens * price[0] + resp.usage.output_tokens * price[1]) / 1e6, 6)
                if price else None)
        return LLMResult(
            output=output, provider=self.name, requested_model=target.model, model=resp.model,
            stop_reason=resp.stop_reason, input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens, latency_ms=latency_ms, parse_mode=mode,
            estimated_cost_usd=cost, extra={"effort": self._effort},
        )
