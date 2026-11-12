"""OpenRouter provider (OpenAI-compatible chat completions). Default target uses a free model."""

from typing import Any

import httpx

from app.llm.base import OUTPUT_SCHEMA, GenerationConfig, LLMError, LLMResult, Target, parse_output
from app.llm.http import map_status, post_json


class OpenRouterProvider:
    name = "openrouter"
    token_param = "max_tokens"  # newer OpenAI models (U-M Toolkit) need "max_completion_tokens"
    missing_key = ("OPENROUTER_API_KEY is not configured on the backend. Add it to backend/.env (free key at "
                   "openrouter.ai) or set LLM_PROVIDER=mock.")

    def __init__(self, api_key: str | None, base_url: str, app_title: str, client: httpx.Client | None = None,
                 reasoning_effort: str | None = None):
        self._reasoning = reasoning_effort  # None = model default (parameter not sent)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._app_title = app_title
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "X-Title": self._app_title}

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        schema = schema or OUTPUT_SCHEMA
        if not self._api_key:
            raise LLMError("NEEDS_API_KEY", self.missing_key, http_status=503)
        payload: dict[str, Any] = {
            "model": target.model,
            "messages": [{"role": "system", "content": system}, *messages],
            self.token_param: cfg.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            # Exactly one model: no `models` fallback list and no auto-router, so evaluations never switch models.
        }
        if cfg.temperature is not None:
            payload["temperature"] = cfg.temperature
        if self._reasoning:
            payload["reasoning"] = {"enabled": False} if self._reasoning == "none" else {"effort": self._reasoning}
        headers = self._headers()
        data, latency_ms = post_json(self.name, f"{self._base_url}/chat/completions", payload, headers,
                                     cfg.timeout_seconds, cfg.max_retries, self._client)
        if "error" in data:
            # OpenRouter can report an upstream failure inside a 200 body; a numeric code maps exactly like the
            # HTTP status would (so a 429 here is MODEL_RATE_LIMITED, not a generic API error).
            err = data["error"]
            msg = err.get("message", "unknown error") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            if isinstance(code, int) and 400 <= code < 600:
                raise map_status(self.name, code, str(msg)[:200])
            raise LLMError("MODEL_API_ERROR", f"{self.name} error: {str(msg)[:200]}")
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("MODEL_EMPTY_RESPONSE", f"{self.name} returned no choices.")
        choice = choices[0]
        finish = choice.get("finish_reason")
        if finish == "length":
            raise LLMError("MODEL_TRUNCATED", "Model output hit max_tokens before completing.")
        message = choice.get("message") or {}
        if finish == "content_filter" or message.get("refusal"):
            raise LLMError("MODEL_REFUSAL", f"{self.name}: the model or provider declined the request ({finish}).")
        content = message.get("content") or ""
        output, mode = parse_output(content)
        usage = data.get("usage") or {}
        # completion_tokens already includes reasoning tokens (OpenAI convention); split them out like Gemini does.
        details = usage.get("completion_tokens_details") or {}
        thinking = details.get("reasoning_tokens") if isinstance(details, dict) else None
        completion = usage.get("completion_tokens")
        answer = completion - thinking if isinstance(completion, int) and isinstance(thinking, int) else completion
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
            extra={"content": content, "thinking_tokens": thinking, "answer_tokens": answer,
                   "schema_name": schema_name, "reasoning": self._reasoning or "model default"},
        )
