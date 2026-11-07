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

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def staff_allowed(request: Request, state: AppState) -> bool:
    token = state.deps.settings.staff_api_token
    if token is not None and token.get_secret_value():
        given = request.headers.get("x-staff-token", "")
        return hmac.compare_digest(given.encode(), token.get_secret_value().encode())
    host = request.client.host if request.client else ""
    return host in _LOOPBACK


def require_staff(request: Request, state: AppState = Depends(get_state)) -> None:
    if not staff_allowed(request, state):
        raise HTTPException(status_code=403, detail={"code": "STAFF_ONLY",
                                                     "message": "Staff and demo tools are only available locally "
                                                                "or with a staff token.", "retryable": False})
