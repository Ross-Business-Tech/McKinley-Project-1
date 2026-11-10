"""Trusted principal model: WHO a request may read resident data as. Derived server-side only.

This prototype has NO real sign-in. A "demo persona" is a synthetic account the person picks from a list on a
deployment that allows it (APP_ENV=local, or DEMO_PERSONAS_ENABLED=true off a hosted backend). Picking one is NOT
authentication: anyone who can reach a demo-enabled backend can act as any synthetic persona. That is acceptable only
because every persona is synthetic. On a hosted backend demo personas are off (config.hosted_problems refuses to
start otherwise), so every customer request is anonymous and no resident data is reachable.

Rules (see docs/security/AUTHORIZATION_BOUNDARIES.md):
- anonymous by default; never derived from conversation text, the model, or audience classification.
- demo_persona only for a KNOWN demo persona id, only when the deployment allows demo personas.
- authenticated_resident is defined for the future and never produced (no real auth exists).
- staff only via the existing staff guard (loopback / STAFF_API_TOKEN), see app/api/staff_guard.py.
- data access (context, resident record, records, history, drafts) is allowed only by `may_access_persona`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.config import Settings

PrincipalKind = Literal["anonymous", "demo_persona", "authenticated_resident", "staff"]


@dataclass(frozen=True)
class Principal:
    kind: PrincipalKind
    session_id: str | None
    source: str  # how it was derived, for traces and docs ("default", "demo_persona_selector", "staff_guard", ...)
    persona_id: str | None = None
    can_read_resident_data: bool = False  # a resident record (fixture / workbook / database) may be read
    is_authenticated: bool = False  # True only for authenticated_resident, which is never produced

    @property
    def key(self) -> str:
        """The persona key used by the session store ("none" = anonymous)."""
        return self.persona_id or "none"


class AuthError(Exception):
    """A request the server refuses (mapped to HTTP 403 by the API layer). Messages are customer-safe."""

    def __init__(self, code: str, message: str, status: int = 403):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": False}


def demo_personas_enabled(settings: Settings) -> bool:
    return settings.demo_personas_allowed


def anonymous(session_id: str | None, source: str = "default") -> Principal:
    return Principal(kind="anonymous", session_id=session_id, source=source)


def _persona_kind(persona_id: str, workbook: Any) -> str | None:
    """'prospect' | 'unmatched_resident' | 'resident' for a known demo persona id, else None."""
    from app.personas import FICTIONAL_PROSPECTS, FIXTURE_RESIDENTS, UNMATCHED_RESIDENT_ID

    if persona_id in FICTIONAL_PROSPECTS:
        return "prospect"
    if persona_id == UNMATCHED_RESIDENT_ID:
        return "unmatched_resident"
    if persona_id in FIXTURE_RESIDENTS or (workbook is not None and persona_id in workbook.residents):
        return "resident"  # workbook rows loaded from the file OR the database: same check
    return None


def derive_principal(settings: Settings, persona_id: str | None, session_id: str | None, workbook: Any, *,
                     strict: bool = True) -> Principal:
    """The customer principal for one request. `persona_id` is the demo selector value the browser sent; it is
    honoured only when the deployment allows demo personas and the id is a known demo persona.

    strict=True (API requests): a persona id on a deployment without demo personas is refused (AuthError), so a
    caller learns it was not used. strict=False (offline tooling): it is silently dropped (anonymous)."""
    pid = (persona_id or "").strip() or None
    if pid is None:
        return anonymous(session_id)
    if not demo_personas_enabled(settings):
        if strict:
            raise AuthError("DEMO_PERSONAS_DISABLED", "Demo accounts are not available on this site. You can still "
                                                      "ask general questions or leave a note for the office.")
        return anonymous(session_id, "persona_ignored_demo_disabled")
    kind = _persona_kind(pid, workbook)
    if kind is None:
        return anonymous(session_id, "unknown_persona_ignored")
    return Principal(kind="demo_persona", session_id=session_id, source="demo_persona_selector", persona_id=pid,
                     can_read_resident_data=kind == "resident")


def staff_principal(session_id: str | None = None, persona_id: str | None = None,
                    source: str = "staff_guard") -> Principal:
    """Only for code paths already behind require_staff (or offline staff tooling such as eval runs)."""
    return Principal(kind="staff", session_id=session_id, source=source, persona_id=persona_id,
                     can_read_resident_data=True)


def may_access_persona(principal: Principal | None, persona_id: str | None) -> bool:
    """Deny by default. Staff may read any synthetic persona; a demo_persona only its own exact id."""
    if principal is None or not persona_id:
        return False
    if principal.kind == "staff":
        return True
    if principal.kind == "demo_persona":
        return principal.persona_id == persona_id
    return False  # anonymous; authenticated_resident is never produced


def session_bound_to(store: Any, principal: Principal) -> bool:
    """Bind the session to (principal kind, persona key) on first use; True if the session is this principal's."""
    if store is None or not principal.session_id or principal.kind == "staff":
        return True
    return store.bind_session(principal.session_id, principal.kind, principal.key) == (principal.kind, principal.key)


def check_session_binding(store: Any, principal: Principal) -> None:
    """For confirm/cancel: refuse a session that belongs to someone else (AuthError 403 SESSION_PERSONA_MISMATCH).
    Chat turns never get a 403 for this (an emergency message must always be answered): run_turn starts a new
    conversation with a fresh server-issued session id instead."""
    if not session_bound_to(store, principal):
        raise AuthError("SESSION_PERSONA_MISMATCH", "This conversation belongs to a different sign-in. Please start "
                                                    "a new conversation.")


# Offline / staff tooling (eval runs behind require_staff, gate evals, journey evals, the demo exporter, tests): a
# staff principal, because those runs read synthetic personas on purpose. Never used for a customer request.
TOOLING = staff_principal(source="offline_tooling")
