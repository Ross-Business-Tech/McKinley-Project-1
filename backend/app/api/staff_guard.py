"""Demo-only boundary for staff, evaluation and diagnostics routes. NOT authentication for real users.

- A signed-in, invited STAFF member (Supabase sign-in, app/identity.py) is always allowed. This is the real staff
  sign-in; the browser console sends the access token as ``Authorization: Bearer <token>``.
- If STAFF_API_TOKEN is set, a request with the header ``X-Staff-Token: <token>`` is also allowed (operations,
  scripts).
- With no token and no staff sign-in (local demo default), they answer only requests from this machine (loopback).
  Behind a reverse proxy every request looks local, so a shared deployment MUST set a token.
Customer routes (/api/chat, /api/personas, /api/actions/*) are not guarded here; the chat ``target`` override is.
"""

import hmac

from fastapi import Depends, HTTPException, Request

from app.identity import resolve_identity
from app.state import AppState, get_state

_LOOPBACK = {"127.0.0.1", "::1", "testclient"}  # "testclient" = FastAPI's in-process test client only
# Any of these means the request came through a proxy or tunnel, so "loopback" says nothing about the real caller.
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "x-forwarded-host", "x-forwarded-proto", "via",
                  "x-client-ip", "cf-connecting-ip", "true-client-ip", "x-original-forwarded-for",
                  "x-forwarded-server", "x-proxyuser-ip", "x-cluster-client-ip", "fastly-client-ip")
# A browser page on another site can reach 127.0.0.1 via DNS rebinding; its Host header then names that site.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "testserver"}


def request_is_local(request: Request) -> bool:
    """True only for a request made straight from this machine: no proxy/tunnel header, a local Host header and a
    loopback peer. Anything else (a reverse proxy, a tunnel, a LAN address, DNS rebinding) is remote. Fail closed:
    used for the no-token staff guard, demo personas (app/auth.py) and server-issued sessions."""
    if any(h in request.headers for h in _PROXY_HEADERS):
        return False  # proxied requests are never treated as local (even "XFF: 127.0.0.1")
    raw_host = request.headers.get("host") or ""
    host_header = raw_host.split("]")[0] + "]" if raw_host.startswith("[") else raw_host.rsplit(":", 1)[0]
    if host_header.lower() not in _LOCAL_HOSTS:
        return False
    host = request.client.host if request.client else ""
    return host in _LOOPBACK


def staff_allowed(request: Request, state: AppState) -> bool:
    settings = state.deps.settings
    token = settings.staff_api_token
    has_token = token is not None and bool(token.get_secret_value())
    if has_token:
        given = request.headers.get("x-staff-token", "")
        if given and hmac.compare_digest(given.encode(), token.get_secret_value().encode()):
            return True
    identity = resolve_identity(request, state)  # a signed-in, invited staff member (needs a valid Supabase token)
    if identity is not None and identity.role == "staff":
        return True
    if has_token or settings.app_env == "hosted":
        return False  # a hosted backend never falls back to "loopback = staff" (startup also requires a token)
    return request_is_local(request)


def require_staff(request: Request, state: AppState = Depends(get_state)) -> None:
    if not staff_allowed(request, state):
        raise HTTPException(status_code=403, detail={"code": "STAFF_ONLY",
                                                     "message": "Staff and demo tools are only available to signed-in "
                                                                "staff, locally, or with a staff token.",
                                                     "retryable": False})
