"""Trusted principal model: WHO a request may read resident data as. Derived server-side only.

This prototype has NO real sign-in. A "demo persona" is a synthetic account the person picks from a list on a
deployment that allows it (APP_ENV=local, or DEMO_PERSONAS_ENABLED=true off a hosted backend). Picking one is NOT
authentication: anyone who can reach a demo-enabled backend can act as any synthetic persona. That is acceptable only
because every persona is synthetic. On a hosted backend demo personas are off (config.hosted_problems refuses to
start otherwise), so every customer request is anonymous and no resident data is reachable.

Rules (see docs/security/AUTHORIZATION_BOUNDARIES.md):
- anonymous by default; never derived from conversation text, the model, or audience classification.
- demo_persona only for a KNOWN demo persona id, only when the deployment allows demo personas.
- authenticated_resident only for a request with a valid Supabase sign-in token whose email is on the invite list
  as a RESIDENT linked to one synthetic resident id (app/identity.py). The browser's persona selector is then ignored.
- staff via the staff guard (loopback / STAFF_API_TOKEN / a signed-in invited staff member), see app/api/staff_guard.py.
- data access (context, resident record, records, history, drafts) is allowed only by `may_access_persona`.
- fail closed (Sprint 7): demo personas are honoured only for requests that reach the backend directly from this
  machine (no proxy/tunnel headers, local Host), unless DEMO_PERSONAS_ENABLED=true is set explicitly on a local
  deployment. A shared backend that forgot APP_ENV=hosted therefore still serves no persona data.
- sessions: on a hosted backend, or for any non-local request, a session id the server has never bound is replaced
  by a fresh server-issued id (the website adopts it). A client cannot choose, guess-in-advance or squat a session.
- "not the account holder" is sticky at the DATA layer: the store persists the revocation for (session, persona)
  (app/db.py), so later turns and confirm/cancel get no account data even if the wording is not re-detected.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from app.config import Settings

if TYPE_CHECKING:  # only for type hints: app/identity.py imports this module
    from app.identity import Identity

PrincipalKind = Literal["anonymous", "demo_persona", "authenticated_resident", "staff"]


@dataclass(frozen=True)
class Principal:
    kind: PrincipalKind
    session_id: str | None
    source: str  # how it was derived, for traces and docs ("default", "demo_persona_selector", "staff_guard", ...)
    persona_id: str | None = None
    can_read_resident_data: bool = False  # a resident record (fixture / workbook / database) may be read
    is_authenticated: bool = False  # True only for authenticated_resident (a verified Supabase sign-in)
    # False once this (session, persona) said it is not the account holder (persisted, see app/db.py): the persona
    # context is then built with no account data. Never True again for that session.
    account_access: bool = True

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


def demo_personas_enabled(settings: Settings, local_request: bool = True) -> bool:
    """Demo personas for THIS request. Off on APP_ENV=hosted (always), off when switched off, and off for a request
    that did not come straight from this machine unless DEMO_PERSONAS_ENABLED=true was set on purpose (fail closed:
    a shared deployment that forgot APP_ENV=hosted is reached through a proxy, so it serves no persona data)."""
    if not settings.demo_personas_allowed:
        return False
    return local_request or settings.demo_personas_enabled is True


def server_issues_sessions(settings: Settings, local_request: bool) -> bool:
    """Whether a client-supplied session id must already be bound (server-issued) to be continued."""
    return settings.app_env == "hosted" or not local_request


def new_session_id() -> str:
    """122 random bits (uuid4), 32 lowercase hex characters. The session id is the bearer of a conversation."""
    return uuid.uuid4().hex


_ISSUED = re.compile(r"[0-9a-f]{32}")


def looks_server_issued(session_id: str | None) -> bool:
    """Shape of a server-issued id. A shorter / other-shaped id is never continued where sessions are server-issued
    (hosted, remote), even if some older row bound it."""
    return bool(session_id) and _ISSUED.fullmatch(session_id) is not None


def continues_session(store: Any, settings: Settings, local_request: bool, session_id: str | None) -> bool:
    """Whether a client-sent session id may be continued. Local direct requests: any id (developer machine).
    Hosted / remote: only an id the server issued and already bound (a guessed, chosen or squatted id is not)."""
    if not server_issues_sessions(settings, local_request):
        return True
    return looks_server_issued(session_id) and store is not None and store.session_binding(session_id) is not None


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
                     strict: bool = True, local_request: bool = True, identity: Identity | None = None) -> Principal:
    """The customer principal for one request. `persona_id` is the demo selector value the browser sent; it is
    honoured only when the deployment allows demo personas and the id is a known demo persona.

    `identity` is a signed-in, invited person (app/identity.py). A resident is the authenticated_resident for their ONE
    linked resident id, whatever persona the browser sent. Staff keep the normal customer path here (they use the
    staff tools for staff access), so a staff sign-in never lets chat act as a resident.

    strict=True (API requests): a persona id on a deployment without demo personas is refused (AuthError), so a
    caller learns it was not used. strict=False (offline tooling): it is silently dropped (anonymous)."""
    if identity is not None and identity.role == "resident":
        linked = (identity.persona_id or "").strip()
        if linked and _persona_kind(linked, workbook) == "resident":
            return Principal(kind="authenticated_resident", session_id=session_id, source="supabase_sign_in",
                             persona_id=linked, can_read_resident_data=True, is_authenticated=True)
        return anonymous(session_id, "signed_in_without_resident_record")  # nothing to read; never fall to a persona
    pid = (persona_id or "").strip() or None
    if pid is None:
        return anonymous(session_id)
    if not demo_personas_enabled(settings, local_request):
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
    """Deny by default. Staff may read any synthetic persona; a demo_persona or authenticated_resident only its own
    exact id."""
    if principal is None or not persona_id:
        return False
    if principal.kind == "staff":
        return True
    if principal.kind in ("demo_persona", "authenticated_resident"):
        return principal.persona_id == persona_id
    return False  # anonymous


def session_bound_to(store: Any, principal: Principal) -> bool:
    """Bind the session to (principal kind, persona key) on first use; True if the session is this principal's."""
    if store is None or not principal.session_id or principal.kind == "staff":
        return True
    return store.bind_session(principal.session_id, principal.kind, principal.key) == (principal.kind, principal.key)


def check_session_binding(store: Any, principal: Principal) -> None:
    """For confirm/cancel: refuse a session that belongs to someone else (AuthError 403 SESSION_PERSONA_MISMATCH).
    Read-only: confirm/cancel never CREATE a binding (only a chat turn does), so they cannot be used to squat a
    session id. An unbound session simply has no draft. Chat turns never get a 403 for this (an emergency message
    must always be answered): run_turn starts a new conversation with a fresh server-issued session id instead."""
    if store is None or not principal.session_id or principal.kind == "staff":
        return
    bound = store.session_binding(principal.session_id)
    if bound is not None and bound != (principal.kind, principal.key):
        raise AuthError("SESSION_PERSONA_MISMATCH", "This conversation belongs to a different sign-in. Please start "
                                                    "a new conversation.")


def with_session_state(store: Any, principal: Principal) -> Principal:
    """The principal with the persisted per-session facts applied (today: a revoked account access)."""
    if store is None or not principal.session_id or principal.kind == "staff":
        return principal
    revoked = getattr(store, "account_access_revoked", None)
    if revoked is not None and revoked(principal.session_id, principal.key):
        return replace(principal, account_access=False)
    return principal


# Offline / staff tooling (eval runs behind require_staff, gate evals, journey evals, the demo exporter, tests): a
# staff principal, because those runs read synthetic personas on purpose. Never used for a customer request.
TOOLING = staff_principal(source="offline_tooling")
