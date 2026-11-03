"""Ollama provider for locally hosted models (http://localhost:11434 by default). No API key."""

from typing import Any

import httpx

from app.llm.base import OUTPUT_SCHEMA, GenerationConfig, LLMError, LLMResult, Target, parse_output
from app.llm.http import post_json


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = client

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig) -> LLMResult:
        options: dict[str, Any] = {"num_predict": cfg.max_tokens}
        if cfg.temperature is not None:
            options["temperature"] = cfg.temperature
        payload = {
            "model": target.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "format": OUTPUT_SCHEMA,  # Ollama structured outputs
            "options": options,
        }
        try:
            data, latency_ms = post_json(self.name, f"{self._base_url}/api/chat", payload, {},
                                         cfg.timeout_seconds, cfg.max_retries, self._client)
        except LLMError as e:
            if e.code == "MODEL_NOT_FOUND":
                e.message = f"Ollama model '{target.model}' is not pulled. Run: ollama pull {target.model}"
            elif e.code == "MODEL_CONNECTION_ERROR":
                e.message = f"Ollama is not reachable at {self._base_url}. Start it with: ollama serve"
            raise
        if data.get("error"):
            raise LLMError("MODEL_API_ERROR", f"ollama error: {str(data['error'])[:200]}")
        content = (data.get("message") or {}).get("content") or ""
        if data.get("done_reason") == "length":
            raise LLMError("MODEL_TRUNCATED", "Model output hit the token limit before completing.")
        output, mode = parse_output(content)
        return LLMResult(
            output=output,
            provider=self.name,
            requested_model=target.model,
            model=data.get("model") or target.model,
            stop_reason=data.get("done_reason"),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            latency_ms=latency_ms,
            parse_mode=mode,
            estimated_cost_usd=0.0,
        )
