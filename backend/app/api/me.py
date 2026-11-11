"""GET /api/me: what the backend makes of this browser's sign-in. Never returns the token, an email or a secret."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.identity import describe_identity
from app.state import AppState, get_state

router = APIRouter(prefix="/api")


class MeResponse(BaseModel):
    # False = this deployment has no sign-in (SUPABASE_URL not set): the website hides it.
    auth_enabled: bool
    # signed_in = a valid token for an invited person | anonymous = no token | not_invited = a valid Supabase account
    # whose email is not on the invite list | invalid_token = expired or not genuine | auth_unavailable = the backend
    # could not reach Supabase's signing keys just now | no_auth = sign-in is not configured here.
    status: Literal["no_auth", "anonymous", "invalid_token", "auth_unavailable", "not_invited", "signed_in"]
    role: Literal["resident", "staff"] | None = None
    persona_id: str | None = None  # the synthetic resident id a resident is linked to


@router.get("/me", response_model=MeResponse)
def me(request: Request, state: AppState = Depends(get_state)) -> MeResponse:
    status, identity = describe_identity(request, state)
    return MeResponse(auth_enabled=state.deps.settings.supabase_auth_enabled, status=status,
                      role=identity.role if identity else None, persona_id=identity.persona_id if identity else None)
