"""Who is signed in? Turns an `Authorization: Bearer <Supabase access token>` header into an invited person.

Two checks, both required (docs/security/SUPABASE_AUTH.md):
1. the token is genuine and current (app/supabase_auth.py), and
2. its email is on the invite list (`user_profiles`, managed with app/manage_users.py), not disabled, and belongs to the
   same Supabase account that first signed in as that email.
A valid token for an email that is not on the list is NOT signed in: it gets the same public, anonymous service as
everyone else. Message text, the model and the browser's persona selector never change who someone is.

Customer chat never refuses a request because of a bad or expired token (an emergency message must always be answered):
it treats the caller as anonymous. Staff and confirm/cancel routes use the same result and simply grant nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from app.auth import AuthError
from app.state import AppState

IdentityStatus = Literal["no_auth", "anonymous", "invalid_token", "auth_unavailable", "not_invited", "signed_in"]


@dataclass(frozen=True)
class Identity:
    email: str
    role: Literal["resident", "staff"]
    persona_id: str | None  # the ONE synthetic resident id a resident is linked to; None for staff
    user_id: str


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    value = value.strip()
    return value if scheme.lower() == "bearer" and value else None


def describe_identity(request: Request, state: AppState) -> tuple[IdentityStatus, Identity | None]:
    """The outcome for this request, with the reason. Never raises; never includes the token."""
    verifier = getattr(state, "verifier", None)
    if verifier is None:
        return "no_auth", None  # sign-in is not configured on this deployment
    token = bearer_token(request)
    if token is None:
        return "anonymous", None
    try:
        claims = verifier.verify(token)
    except AuthError as e:
        return ("auth_unavailable" if e.status == 503 else "invalid_token"), None
    profile = state.store.profile_for_email(claims.email)
    if profile is None or profile["disabled"]:
        return "not_invited", None
    if not state.store.claim_profile(claims.email, claims.user_id):
        return "not_invited", None  # a different Supabase account than the one first invited under this email
    if profile["role"] == "resident" and not profile["persona_id"]:
        return "not_invited", None  # a resident invite without a linked resident id grants nothing
    return "signed_in", Identity(email=claims.email, role=profile["role"], persona_id=profile["persona_id"],
                                 user_id=claims.user_id)


def resolve_identity(request: Request, state: AppState) -> Identity | None:
    """The signed-in, invited person for this request, or None (anonymous, invalid token, not on the list)."""
    return describe_identity(request, state)[1]
