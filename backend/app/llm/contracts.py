"""The three structured model uses the application makes, named in one place.

Every model call in the app goes through `LLMGateway.complete` with one of three JSON schemas:

- generate_response: `app.chat_engine.run_turn` (customer reply), `mckinley_reply`, `app.llm.base.OUTPUT_SCHEMA`
- converse: `app.assistant.ask` (the one conversational call), `mckinley_assistant`, `app.assistant.SCHEMA`
- classify_risk: `app.risk.classifier.SemanticRiskClassifier`, `mckinley_risk`, `app.risk.classifier.SCHEMA`

This module is a thin, documented facade: it holds NO business logic (prompts, parsing, validation and policy stay
with the callers above) and the existing callers do not use it. It exists so provider contract tests, the live
smoke script and docs can refer to "the gate schema" without copying it, and so a drift between the facade and the
real callers is caught by tests (tests/test_llm_providers.py).
"""

from dataclasses import dataclass
from typing import Any

from app.llm import GenerationConfig, LLMGateway, LLMResult, Target
from app.llm.base import OUTPUT_SCHEMA
from app.risk.classifier import SCHEMA as RISK_SCHEMA
from app.risk.classifier import SCHEMA_NAME as RISK_SCHEMA_NAME


@dataclass(frozen=True)
class ModelUse:
    name: str
    schema_name: str
    schema: dict[str, Any]
    caller: str


GENERATE_RESPONSE = ModelUse("generate_response", "mckinley_reply", OUTPUT_SCHEMA, "app.chat_engine.run_turn")
CONVERSE = ModelUse("converse", "mckinley_assistant", {}, "app.assistant.ask")  # schema filled below
CLASSIFY_RISK = ModelUse("classify_risk", RISK_SCHEMA_NAME, RISK_SCHEMA,
                         "app.risk.classifier.SemanticRiskClassifier.classify")
MODEL_USES: dict[str, ModelUse] = {u.name: u for u in (GENERATE_RESPONSE, CONVERSE, CLASSIFY_RISK)}


def complete_for(use: ModelUse, gateway: LLMGateway, system: str, messages: list[dict[str, str]],
                 target: Target | None = None, cfg: GenerationConfig | None = None,
                 strict_model: bool = True) -> LLMResult:
    """One gateway call with the schema of `use`. The raw model text is in `result.extra["content"]`."""
    return gateway.complete(system, messages, target, strict_model=strict_model, schema=use.schema,
                            schema_name=use.schema_name, cfg=cfg)


def generate_response(gateway: LLMGateway, system: str, messages: list[dict[str, str]],
                      target: Target | None = None, cfg: GenerationConfig | None = None) -> LLMResult:
    """Customer reply: `result.output` is the parsed `ModelOutput`."""
    return complete_for(GENERATE_RESPONSE, gateway, system, messages, target, cfg)


def converse(gateway: LLMGateway, system: str, messages: list[dict[str, str]],
             target: Target | None = None, cfg: GenerationConfig | None = None) -> LLMResult:
    """The conversational turn: parse `result.extra["content"]` like `app.assistant.ask` does."""
    return complete_for(CONVERSE, gateway, system, messages, target, cfg)


def classify_risk(gateway: LLMGateway, system: str, messages: list[dict[str, str]],
                  target: Target | None = None, cfg: GenerationConfig | None = None) -> LLMResult:
    """Semantic risk: parse `result.extra["content"]` with `app.risk.classifier.parse`."""
    return complete_for(CLASSIFY_RISK, gateway, system, messages, target, cfg)


def _fill() -> None:  # late import: app.assistant imports app.llm
    from app.assistant import SCHEMA, SCHEMA_NAME
    CONVERSE.schema.update(SCHEMA)
    assert CONVERSE.schema_name == SCHEMA_NAME


_fill()
