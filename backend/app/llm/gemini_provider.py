"""Google Gemini provider through the official `google-genai` SDK (Gemini Developer API, key from AI Studio).

Same contract as every provider: it receives only the system prompt and chat messages (never workbook rows) and
returns an `LLMResult`. Structured output uses `response_mime_type="application/json"` + `response_json_schema`.
Retries (429 / 5xx) are done by the SDK on the SAME model; the served `model_version` is returned so the gateway's
strict check can raise MODEL_SWITCHED. No prices are hard-coded: cost is left unknown (None) rather than guessed.
"""

import time
from typing import Any

from app.llm.base import OUTPUT_SCHEMA, GenerationConfig, LLMError, LLMResult, Target, parse_output

_REFUSAL_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}
_RETRY_STATUS = [429, 500, 502, 503, 504]


def _to_contents(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Chat history in Gemini's shape: roles 'user' / 'model'. Any system text is passed separately."""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        out.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": m.get("content", "")}]})
    return out


def _enum_name(v: Any) -> str | None:
    if v is None:
        return None
    return getattr(v, "name", None) or str(v).split(".")[-1]


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None, client: Any = None):
        self._api_key = api_key
        self._client = client  # injected in tests; real client created lazily

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMError("NEEDS_API_KEY", "GEMINI_API_KEY is not configured on the backend. Add it to backend/.env "
                           "(key from aistudio.google.com) or set LLM_PROVIDER=mock.", http_status=503)
        from google import genai

        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        schema = schema or OUTPUT_SCHEMA
        client = self._get_client()
        import httpx
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=cfg.max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
            http_options=types.HttpOptions(
                timeout=int(cfg.timeout_seconds * 1000),  # milliseconds
                retry_options=types.HttpRetryOptions(attempts=cfg.max_retries + 1, http_status_codes=_RETRY_STATUS),
            ),
            **({"temperature": cfg.temperature} if cfg.temperature is not None else {}),
        )
        start = time.perf_counter()
        try:
            resp = client.models.generate_content(model=target.model, contents=_to_contents(messages), config=config)
        except errors.ClientError as e:
            code = getattr(e, "code", None)
            if code in (401, 403):
                raise LLMError("MODEL_AUTH_ERROR", f"Gemini rejected the API key or access ({code}).") from e
            if code == 404:
                raise LLMError("MODEL_NOT_FOUND", f"Gemini model '{target.model}' not found (404).") from e
            if code == 429:
                raise LLMError("MODEL_RATE_LIMITED", "Gemini rate limit or quota reached (429).", retryable=True,
                               http_status=503) from e
            raise LLMError("MODEL_BAD_REQUEST", f"Gemini rejected the request ({code}).") from e
        except errors.ServerError as e:
            raise LLMError("MODEL_API_ERROR", f"Gemini server error ({getattr(e, 'code', '5xx')}).",
                           retryable=True) from e
        except errors.APIError as e:
            raise LLMError("MODEL_API_ERROR", f"Gemini API error ({getattr(e, 'code', '?')}).") from e
        except httpx.TimeoutException as e:
            raise LLMError("MODEL_TIMEOUT", "Gemini request timed out.", retryable=True, http_status=504) from e
        except httpx.TransportError as e:
            raise LLMError("MODEL_CONNECTION_ERROR", "Could not reach the Gemini API.", retryable=True) from e
        latency_ms = int((time.perf_counter() - start) * 1000)

        feedback = getattr(resp, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise LLMError("MODEL_REFUSAL", f"Gemini blocked the prompt ({_enum_name(feedback.block_reason)}).")
        candidates = getattr(resp, "candidates", None) or []
        finish = _enum_name(getattr(candidates[0], "finish_reason", None)) if candidates else None
        if finish == "MAX_TOKENS":
            raise LLMError("MODEL_TRUNCATED", "Model output hit max_output_tokens before completing.")
        if finish in _REFUSAL_REASONS:
            raise LLMError("MODEL_REFUSAL", f"Gemini stopped the response ({finish}).")
        try:
            text = resp.text or ""
        except (ValueError, AttributeError):
            text = ""
        if not text.strip():
            raise LLMError("MODEL_EMPTY_RESPONSE", "Gemini returned no text.")
        output, mode = parse_output(text)
        usage = getattr(resp, "usage_metadata", None)
        thoughts = getattr(usage, "thoughts_token_count", None) if usage else None
        return LLMResult(
            output=output, provider=self.name, requested_model=target.model,
            model=getattr(resp, "model_version", None) or target.model,
            stop_reason=finish, input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
            output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
            latency_ms=latency_ms, parse_mode=mode, estimated_cost_usd=None,
            extra={"content": text, "thinking_tokens": thoughts, "schema_name": schema_name},
        )
