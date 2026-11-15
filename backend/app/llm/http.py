"""Shared HTTP call with bounded retries and typed error mapping. Never logs request bodies or keys."""

import logging
import time
from typing import Any

import httpx

from app.llm.base import LLMError

log = logging.getLogger("mckinley.llm")

MAX_BACKOFF_SECONDS = 8.0


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    try:
        return min(float(resp.headers.get("retry-after", "")), MAX_BACKOFF_SECONDS)
    except ValueError:
        return min(1.0 * 2**attempt, MAX_BACKOFF_SECONDS)


def post_json(
    provider: str, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float,
    max_retries: int, client: httpx.Client | None = None,
) -> tuple[dict[str, Any], int]:
    """POST and return (json, latency_ms of the successful attempt). Retries 429/5xx/timeouts on the SAME model."""
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        for attempt in range(max_retries + 1):
            start = time.perf_counter()
            try:
                resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            except httpx.TimeoutException as e:
                if attempt < max_retries:
                    time.sleep(min(2**attempt, MAX_BACKOFF_SECONDS))
                    continue
                raise LLMError("MODEL_TIMEOUT", f"{provider} request timed out after {timeout:.0f}s.",
                               retryable=True, http_status=504) from e
            except httpx.ConnectError as e:
                raise LLMError("MODEL_CONNECTION_ERROR", f"Could not connect to {provider} at {url.split('/v1')[0]}.",
                               retryable=True, http_status=503) from e
            except httpx.HTTPError as e:
                raise LLMError("MODEL_CONNECTION_ERROR", f"{provider} transport error: {type(e).__name__}.",
                               retryable=True, http_status=503) from e
            latency_ms = int((time.perf_counter() - start) * 1000)
            status = resp.status_code
            if status == 200:
                try:
                    return resp.json(), latency_ms
                except ValueError as e:
                    raise LLMError("MODEL_BAD_RESPONSE", f"{provider} returned non-JSON content.") from e
            log.warning("llm http error provider=%s status=%d attempt=%d", provider, status, attempt)
            if (status == 429 or status >= 500) and attempt < max_retries:
                time.sleep(_retry_after(resp, attempt))
                continue
            raise _map_status(provider, status, resp)
        raise LLMError("MODEL_API_ERROR", f"{provider} request failed.")  # pragma: no cover
    finally:
        if own:
            client.close()


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error")
        msg = err.get("message") if isinstance(err, dict) else err
        return str(msg or "")[:200]
    except Exception:
        return ""


def _map_status(provider: str, status: int, resp: httpx.Response) -> LLMError:
    return map_status(provider, status, _error_message(resp))


def map_status(provider: str, status: int, detail: str = "") -> LLMError:
    """HTTP status -> gateway error code. Shared so an error reported inside a 200 body maps the same way."""
    suffix = f": {detail}" if detail else ""
    if status == 401:
        return LLMError("MODEL_AUTH_ERROR", f"{provider} rejected the API key (401){suffix}")
    if status == 402:
        return LLMError("MODEL_PAYMENT_REQUIRED", f"{provider} requires credits for this model (402){suffix}")
    if status == 403:
        return LLMError("MODEL_PERMISSION_DENIED", f"{provider} denied access (403){suffix}")
    if status == 404:
        return LLMError("MODEL_NOT_FOUND", f"{provider} model or endpoint not found (404){suffix}")
    if status == 429:
        return LLMError("MODEL_RATE_LIMITED", f"{provider} rate limit reached (429). Free tiers are limited; "
                        f"retry later{suffix}", retryable=True, http_status=503)
    if status == 400:
        return LLMError("MODEL_BAD_REQUEST", f"{provider} rejected the request (400){suffix}")
    return LLMError("MODEL_API_ERROR", f"{provider} API error ({status}){suffix}", retryable=status >= 500)
