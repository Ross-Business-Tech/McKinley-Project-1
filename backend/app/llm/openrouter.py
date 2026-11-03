"""OpenRouter provider (OpenAI-compatible chat completions). Default target uses a free model."""

from typing import Any

import httpx

from app.llm.base import OUTPUT_SCHEMA, GenerationConfig, LLMError, LLMResult, Target, parse_output
from app.llm.http import post_json


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str | None, base_url: str, app_title: str, client: httpx.Client | None = None):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._app_title = app_title
        self._client = client

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig) -> LLMResult:
        if not self._api_key:
            raise LLMError("NEEDS_API_KEY", "OPENROUTER_API_KEY is not configured on the backend. Add it to "
                           "backend/.env (free key at openrouter.ai) or set LLM_PROVIDER=mock.", http_status=503)
        payload: dict[str, Any] = {
            "model": target.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": cfg.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "mckinley_reply", "strict": True, "schema": OUTPUT_SCHEMA},
            },
            # Exactly one model: no `models` fallback list and no auto-router, so evaluations never switch models.
        }
        if cfg.temperature is not None:
            payload["temperature"] = cfg.temperature
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Title": self._app_title,
        }
        data, latency_ms = post_json(self.name, f"{self._base_url}/chat/completions", payload, headers,
                                     cfg.timeout_seconds, cfg.max_retries, self._client)
        if "error" in data:
            err = data["error"]
            msg = err.get("message", "unknown error") if isinstance(err, dict) else str(err)
            raise LLMError("MODEL_API_ERROR", f"openrouter error: {str(msg)[:200]}")
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("MODEL_EMPTY_RESPONSE", "openrouter returned no choices.")
        choice = choices[0]
        finish = choice.get("finish_reason")
        if finish == "length":
            raise LLMError("MODEL_TRUNCATED", "Model output hit max_tokens before completing.")
        content = (choice.get("message") or {}).get("content") or ""
        output, mode = parse_output(content)
        usage = data.get("usage") or {}
        return LLMResult(
            output=output,
            provider=self.name,
            requested_model=target.model,
            model=data.get("model") or target.model,
            stop_reason=finish,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            parse_mode=mode,
            estimated_cost_usd=usage.get("cost") if isinstance(usage.get("cost"), (int, float)) else None,
        )
