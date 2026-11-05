"""Provider-agnostic LLM contract.

Providers receive only a system prompt and chat messages. They know nothing about residents, the
workbook or McKinley policy: that separation keeps synthetic data handling out of vendor adapters.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.models import HandoffCategory

HANDOFF_CATEGORIES: list[str] = list(HandoffCategory.__args__)  # type: ignore[attr-defined]

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "audience": {"type": "string", "enum": ["prospect", "resident", "unknown"]},
        "recommended_handoff": {"type": "boolean"},
        "handoff_category": {"type": "string", "enum": HANDOFF_CATEGORIES},
        "handoff_reason": {"type": "string"},
        "language": {"type": "string"},
    },
    "required": ["reply", "audience", "recommended_handoff", "handoff_category", "handoff_reason", "language"],
    "additionalProperties": False,
}

# How the structured output was obtained. "text_fallback" means the model ignored the JSON contract and the
# raw text was used as the reply with no model handoff signal; this is recorded and shown, never hidden.
ParseMode = Literal["json", "json_extracted", "text_fallback"]


class ModelOutput(BaseModel):
    reply: str
    audience: str = "unknown"
    recommended_handoff: bool = False
    handoff_category: HandoffCategory = "none"
    handoff_reason: str = ""
    language: str = "unknown"


@dataclass(frozen=True)
class Target:
    """A fixed provider + model pair. Evaluations run against exactly one Target per result."""

    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"

    @classmethod
    def parse(cls, s: str) -> "Target":
        provider, sep, model = s.strip().partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"Invalid target '{s}'; expected 'provider:model'")
        return cls(provider=provider.lower(), model=model)


@dataclass
class GenerationConfig:
    max_tokens: int
    temperature: float | None
    timeout_seconds: float
    max_retries: int


@dataclass
class LLMResult:
    output: ModelOutput
    provider: str
    requested_model: str
    model: str  # model actually reported by the provider
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    parse_mode: ParseMode
    is_mock: bool = False
    estimated_cost_usd: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, http_status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        """`schema` overrides OUTPUT_SCHEMA for auxiliary tasks (e.g. the decision gate). The raw model text is
        always returned in `LLMResult.extra["content"]` so callers with a custom schema can parse it themselves."""
        ...


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_output(text: str) -> tuple[ModelOutput, ParseMode]:
    """Parse the JSON contract leniently; many free/local models wrap JSON in prose or code fences."""
    raw = (text or "").strip()
    if not raw:
        raise LLMError("MODEL_EMPTY_RESPONSE", "The model returned an empty response.")
    for candidate, mode in ((_FENCE.sub("", raw), "json"), (None, "json_extracted")):
        if candidate is None:
            m = _JSON_OBJECT.search(raw)
            candidate = m.group(0) if m else ""
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and isinstance(data.get("reply"), str):
                if data.get("handoff_category") not in HANDOFF_CATEGORIES:
                    data["handoff_category"] = "other" if data.get("recommended_handoff") else "none"
                data["handoff_reason"] = str(data.get("handoff_reason") or "")
                return ModelOutput.model_validate(data), mode  # type: ignore[return-value]
        except (json.JSONDecodeError, ValidationError, TypeError):
            continue
    return ModelOutput(reply=raw), "text_fallback"
