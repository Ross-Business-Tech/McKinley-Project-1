"""Gateway wrapper used by the live A/B/C runner: records every model call, enforces a call budget and pacing, and
flags conditions that must stop the run. It keeps the gateway's no-silent-switch rule: the served model is checked
against the requested one and a mismatch raises MODEL_SWITCHED (after recording the served ID)."""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.llm import GenerationConfig, LLMError, LLMGateway, LLMProvider, LLMResult, Target
from app.llm import same_model as _same_model

# After bounded same-model retries these mean every further call would fail the same way: stop the run.
STOP_CODES = {"NEEDS_API_KEY", "MODEL_AUTH_ERROR", "MODEL_PAYMENT_REQUIRED", "MODEL_PERMISSION_DENIED",
              "MODEL_NOT_FOUND", "MODEL_CONNECTION_ERROR", "UNSUPPORTED_PROVIDER"}


class RunStopped(Exception):  # noqa: N818 - control flow, not an error condition
    """Raised before a model call once the run must stop (budget, persistent 429, fatal config error)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RecordingGateway(LLMGateway):
    def __init__(self, settings: Settings, providers: dict[str, LLMProvider] | None = None, *, max_calls: int = 60,
                 sleep_seconds: float = 3.0, max_rate_limit_errors: int = 1,
                 pricing: dict[str, tuple[float | None, float | None]] | None = None,
                 sleeper: Callable[[float], None] = time.sleep):
        super().__init__(settings, providers)
        self.max_calls = max_calls
        self.sleep_seconds = sleep_seconds
        self.max_rate_limit_errors = max_rate_limit_errors
        self.pricing = pricing or {}
        self.sleeper = sleeper
        self.calls: list[dict[str, Any]] = []
        self.rate_limit_errors = 0
        self.stop_code: str | None = None
        self.stop_message: str | None = None

    def _stop(self, code: str, message: str) -> None:
        if not self.stop_code:
            self.stop_code, self.stop_message = code, message

    def _cost(self, target: Target, result: LLMResult) -> tuple[float | None, str]:
        if result.is_mock:
            return 0.0, "mock"
        if result.estimated_cost_usd is not None:
            return result.estimated_cost_usd, "provider_reported"
        p_in, p_out = self.pricing.get(target.model, (None, None))
        if p_in is not None and p_out is not None and result.input_tokens is not None \
                and result.output_tokens is not None:
            return round(result.input_tokens * p_in + result.output_tokens * p_out, 8), "listing_price_x_tokens"
        return None, "unknown"

    def complete(self, system: str, messages: list[dict[str, str]], target: Target | None = None,
                 strict_model: bool = True, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply", cfg: GenerationConfig | None = None) -> LLMResult:
        target = target or self.default_target
        if self.stop_code:
            raise RunStopped(self.stop_code, self.stop_message or self.stop_code)
        if len(self.calls) >= self.max_calls:
            self._stop("BUDGET_EXHAUSTED", f"Call budget of {self.max_calls} model calls reached (--max-calls).")
            raise RunStopped(self.stop_code or "BUDGET_EXHAUSTED", self.stop_message or "")
        if self.calls and self.sleep_seconds > 0:
            self.sleeper(self.sleep_seconds)
        rec: dict[str, Any] = {"call_index": len(self.calls) + 1, "started_at": datetime.now(UTC).isoformat(),
                               "target": target.key, "provider": target.provider, "requested_model": target.model,
                               "schema_name": schema_name, "served_model": None}
        self.calls.append(rec)
        t0 = time.perf_counter()
        try:
            result = super().complete(system, messages, target, strict_model=False, schema=schema,
                                      schema_name=schema_name, cfg=cfg)
        except LLMError as e:
            rec.update(status="error", error_code=e.code, error_message=e.message[:300],
                       wall_ms=int((time.perf_counter() - t0) * 1000))
            if e.code == "MODEL_RATE_LIMITED":
                self.rate_limit_errors += 1
                if self.rate_limit_errors >= self.max_rate_limit_errors:
                    self._stop("RATE_LIMITED", "Provider kept returning 429 after the bounded same-model retries; "
                                               "stopped to respect the free-tier limit. Retry later or raise --sleep.")
            elif e.code in STOP_CODES:
                self._stop(e.code, e.message[:300])
            raise
        cost, cost_source = self._cost(target, result)
        content = result.extra.get("content")
        rec.update(
            served_model=result.model, is_mock=result.is_mock, parse_mode=result.parse_mode,
            stop_reason=result.stop_reason, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            latency_ms=result.latency_ms, wall_ms=int((time.perf_counter() - t0) * 1000),
            estimated_cost_usd=cost, cost_source=cost_source,
            response_text=content if isinstance(content, str) else json.dumps(result.output.model_dump()),
        )
        if strict_model and not _same_model(result.model, target.model):
            rec.update(status="error", error_code="MODEL_SWITCHED",
                       error_message=f"served '{result.model}' instead of requested '{target.model}'")
            raise LLMError("MODEL_SWITCHED", f"Provider served '{result.model}' instead of requested "
                           f"'{target.model}'. Result discarded to keep the evaluation controlled.")
        rec["status"] = "ok"
        return result
