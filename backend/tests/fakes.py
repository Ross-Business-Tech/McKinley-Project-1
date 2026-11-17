"""One scripted stand-in for a model provider, shared by the test modules (it replaces five near-identical copies).

    ScriptedProvider(content)                          the same answer for every call (classifier tests)
    ScriptedProvider(error=LLMError(...))              every call fails
    ScriptedProvider(chat=..., risk=...)               separate answers for the conversation and the safety
                                                       classifier; each is a string, a list (answered in order,
                                                       then `chat_default` / `risk_default`) or an LLMError to raise
"""

from __future__ import annotations

from typing import Any

from app.llm.base import LLMResult, ModelOutput

RISK_SCHEMA = "mckinley_risk"


class ScriptedProvider:
    name = "openrouter"

    def __init__(self, content: Any = None, *, error: Exception | None = None, chat: Any = None, risk: Any = None,
                 chat_default: str | None = None, risk_default: str | None = None, model: str | None = None):
        self.content, self.error, self.chat, self.risk = content, error, chat, risk
        self.chat_default, self.risk_default, self.model = chat_default, risk_default, model
        self.calls: list[str] = []  # schema names, in call order
        self.cfgs: list[Any] = []
        self.chat_calls = 0

    def _answer(self, schema_name: str) -> Any:
        if self.error is not None:
            return self.error
        if self.chat is None and self.risk is None:
            return self.content
        is_risk = schema_name == RISK_SCHEMA
        what = self.risk if is_risk else self.chat
        if isinstance(what, list):
            what = what.pop(0) if what else None
        if what is None:
            what = self.risk_default if is_risk else self.chat_default
        return what

    def complete(self, system, messages, target, cfg, schema=None, schema_name="mckinley_reply"):  # noqa: ANN001
        self.calls.append(schema_name)
        self.cfgs.append(cfg)
        if schema_name != RISK_SCHEMA:
            self.chat_calls += 1
        answer = self._answer(schema_name)
        if isinstance(answer, Exception):
            raise answer
        return LLMResult(output=ModelOutput(reply=""), provider=self.name, requested_model=target.model,
                         model=self.model or target.model, stop_reason="stop", input_tokens=5, output_tokens=5,
                         latency_ms=3, parse_mode="json", extra={"content": answer})
