"""Demo-only boundary for staff, evaluation and diagnostics routes. NOT authentication for real users.

- If STAFF_API_TOKEN is set, these routes need the header ``X-Staff-Token: <token>``.
- If it is not set (local demo default), they answer only requests from this machine (loopback). Behind a reverse
  proxy every request looks local, so any shared deployment MUST set a token (and real staff sign-in is still a
  deployment blocker; see docs/SPRINT_REVIEW_REPORT.md).
Customer routes (/api/chat, /api/personas, /api/actions/*) are not guarded here; the chat ``target`` override is.
"""

import hmac

from fastapi import Depends, HTTPException, Request

from app.state import AppState, get_state

_LOOPBACK = {"127.0.0.1", "::1", "testclient"}  # "testclient" = FastAPI's in-process test client only
# Any of these means the request came through a proxy or tunnel, so "loopback" says nothing about the real caller.
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "x-forwarded-host", "x-forwarded-proto", "via",
                  "x-client-ip", "cf-connecting-ip", "true-client-ip", "x-original-forwarded-for",
                  "x-forwarded-server", "x-proxyuser-ip", "x-cluster-client-ip", "fastly-client-ip")
# A browser page on another site can reach 127.0.0.1 via DNS rebinding; its Host header then names that site.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "testserver"}


def staff_allowed(request: Request, state: AppState) -> bool:
    token = state.deps.settings.staff_api_token
    if token is not None and token.get_secret_value():
        given = request.headers.get("x-staff-token", "")
        return hmac.compare_digest(given.encode(), token.get_secret_value().encode())
    if any(h in request.headers for h in _PROXY_HEADERS):
        return False  # without a token, proxied requests are never treated as local (even "XFF: 127.0.0.1")
    raw_host = request.headers.get("host") or ""
    host_header = raw_host.split("]")[0] + "]" if raw_host.startswith("[") else raw_host.rsplit(":", 1)[0]
    if host_header.lower() not in _LOCAL_HOSTS:
        return False
    host = request.client.host if request.client else ""
    return host in _LOOPBACK


def require_staff(request: Request, state: AppState = Depends(get_state)) -> None:
    if not staff_allowed(request, state):
        raise HTTPException(status_code=403, detail={"code": "STAFF_ONLY",
                                                     "message": "Staff and demo tools are only available locally "
                                                                "or with a staff token.", "retryable": False})
