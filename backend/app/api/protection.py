"""Public-endpoint protection (Sprint 10, independent review P1): a request-size cap, per-client and per-session rate
limits, one turn at a time per conversation, and error bodies that never echo the request.

All in memory, for a single-instance demo (the free Render plan runs one instance). Nothing here is paid
infrastructure; a multi-instance deployment would need a shared store instead.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("mckinley.protection")


def error_body(code: str, message: str, retryable: bool = False) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "retryable": retryable}}).encode()


class BodyLimitMiddleware:
    """Refuse request bodies over `max_bytes` with 413 (checked on Content-Length and while streaming)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_bytes <= 0:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await _send_json(send, 413, error_body("REQUEST_TOO_LARGE", "That message is too long to send."))
            return
        seen = 0
        too_big = False

        async def limited() -> Message:
            nonlocal seen, too_big
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max_bytes:
                    too_big = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return msg

        started = False

        async def tracking_send(msg: Message) -> None:
            nonlocal started
            if too_big and not started:
                return  # the app saw an empty body; the 413 below replaces whatever it answered
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        await self.app(scope, limited, tracking_send)
        if too_big and not started:
            await _send_json(send, 413, error_body("REQUEST_TOO_LARGE", "That message is too long to send."))


class CatchAllMiddleware:
    """An unexpected error becomes the standard JSON error (inside CORS, so the browser can read it) instead of a
    bare text 500 that the website would show as 'cannot reach the backend'. Nothing about the error is returned."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(msg: Message) -> None:
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as e:  # noqa: BLE001 - the last line of defence for one request
            log.error("unhandled error on %s: %s", scope.get("path"), type(e).__name__)
            if not started:
                await _send_json(send, 500, error_body(
                    "SERVER_ERROR", "Something went wrong on our side. Please try again in a moment.", True))


async def _send_json(send: Send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class RateLimiter:
    """Sliding one-minute window per key. `limit <= 0` means off."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 20_000:  # bound memory: forget idle keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > window][:10_000]:
                    self._hits.pop(k, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = RateLimiter()


class SessionLocks:
    """One turn (or confirm/cancel) at a time per conversation: drafts are read early and saved late, so two
    concurrent requests in one session could otherwise overwrite each other."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                if len(self._locks) > 20_000:
                    for k in [k for k, v in self._locks.items() if not v.locked()][:10_000]:
                        self._locks.pop(k, None)
                lock = self._locks[key] = threading.Lock()
            return lock


SESSION_LOCKS = SessionLocks()


def client_key(request: Any, hosted: bool) -> str:
    """The caller's address. Behind Render's proxy the first X-Forwarded-For hop is the visitor (spoofable, which is
    why a per-session limit also applies)."""
    if hosted:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def rate_limited(request: Any, settings: Any, route: str, session_id: str | None) -> bool:
    """True when this request is over a limit. Limits apply on a hosted deployment unless set explicitly."""
    hosted = settings.app_env == "hosted"
    per_ip = settings.rate_limit_per_minute if settings.rate_limit_per_minute is not None else (30 if hosted else 0)
    per_session = settings.rate_limit_per_session_minute if settings.rate_limit_per_session_minute is not None \
        else (15 if hosted else 0)
    if not LIMITER.allow(f"{route}|ip|{client_key(request, hosted)}", per_ip):
        return True
    return bool(session_id) and not LIMITER.allow(f"{route}|s|{session_id}", per_session)


RouteHandler = Callable[..., Awaitable[Any]]
