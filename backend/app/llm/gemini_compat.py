"""Gemini through an OpenAI-compatible gateway (e.g. the U-M GPT Toolkit), selected when GEMINI_BASE_URL is set.

Same request/response handling as the OpenRouter provider (chat completions + strict JSON schema), but reported as
provider "gemini" so targets stay `gemini:<model>`. Exactly one model per call; retries use the same model.
"""

from typing import Any

import httpx

from app.llm.base import GenerationConfig, LLMError, LLMResult, Target
from app.llm.openrouter import OpenRouterProvider


class GeminiCompatProvider(OpenRouterProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, base_url: str, app_title: str, client: httpx.Client | None = None,
                 thinking_level: str | None = None):
        # OpenRouter's `reasoning` object is not part of the OpenAI API; the thinking level is recorded only.
        super().__init__(api_key, base_url, app_title, client=client, reasoning_effort=None)
        self._thinking_level = thinking_level

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        if not self._api_key:
            raise LLMError("NEEDS_API_KEY", "GEMINI_API_KEY is not configured on the backend (GEMINI_BASE_URL is "
                           "set). Add it to backend/.env or set LLM_PROVIDER=mock.", http_status=503)
        try:
            result = super().complete(system, messages, target, cfg, schema, schema_name)
        except LLMError as e:
            e.message = e.message.replace("openrouter", "gemini gateway")
            e.args = (e.message,)
            raise
        result.extra["thinking_level"] = self._thinking_level or "model default"
        result.extra.pop("reasoning", None)
        return result
