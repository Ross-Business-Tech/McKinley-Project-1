"""Check a Supabase Auth access token (a signed JWT) on the backend. Nothing here talks to a person: it only answers
"is this token genuine, current and for a signed-in email?".

How a token is trusted (docs/security/SUPABASE_AUTH.md):
- Signature: new Supabase projects sign with an asymmetric key (ES256 / RS256) published at
  <SUPABASE_URL>/auth/v1/.well-known/jwks.json, so the backend needs no secret. Legacy projects sign with one shared
  secret (HS256): set SUPABASE_JWT_SECRET only for those. Any other algorithm, including "none", is refused.
- Claims: audience "authenticated", issuer <SUPABASE_URL>/auth/v1, not expired (10 s of clock leeway), a subject and a
  verified email, not an anonymous sign-in, and signed in by the email one-time code (the only method this app turns
  on). The public anon key and the service-role key are not user tokens and are refused.
- Being signed in is NOT enough: the email must also be on the invite list (app/identity.py).
The token and the secret are never logged or echoed.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.auth import AuthError
from app.config import Settings

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
ALLOWED_PROVIDERS = ("email",)  # the one-time email code; add a provider here only on purpose
JWKS_TTL_SECONDS = 600.0
JWKS_MIN_REFETCH_SECONDS = 30.0  # an unknown key id can't make this backend hammer Supabase
LEEWAY_SECONDS = 10

_INVALID = ("INVALID_TOKEN", "Your sign-in is not valid or has expired. Please sign in again.")


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    email: str


def _fetch_jwks(url: str) -> dict[str, Any]:
    res = httpx.get(url, timeout=5.0, headers={"Accept": "application/json"})
    res.raise_for_status()
    return res.json()


class SupabaseVerifier:
    def __init__(self, settings: Settings, fetch_jwks: Callable[[str], dict[str, Any]] = _fetch_jwks,
                 clock: Callable[[], float] = time.monotonic):
        origin = settings.supabase_origin
        if not origin:
            raise ValueError("SUPABASE_URL is not set")
        self._issuer = f"{origin}/auth/v1"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._secret = settings.supabase_jwt_secret.get_secret_value().strip() if settings.supabase_jwt_secret else ""
        self._fetch = fetch_jwks
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None

    # ---- signing keys ----
    def _refresh(self) -> None:
        """Fetch the published keys. A failed fetch keeps whatever keys we already have."""
        try:
            data = self._fetch(self._jwks_url)
            keys = {k["kid"]: jwt.PyJWK(k).key for k in data.get("keys", []) if k.get("kid") and k.get("alg") in
                    (*ASYMMETRIC_ALGORITHMS, None)}
        except Exception:  # network error, bad JSON, bad key: never include details (they may name internals)
            if not self._keys:
                raise AuthError("AUTH_UNAVAILABLE", "Sign-in is temporarily unavailable. Please try again in a "
                                                    "moment.", 503) from None
            self._fetched_at = self._clock()  # keep using the keys we have; don't retry on every request
            return
        self._keys, self._fetched_at = keys, self._clock()

    def _key_for(self, kid: str | None) -> Any:
        with self._lock:
            age = None if self._fetched_at is None else self._clock() - self._fetched_at
            if age is None or age > JWKS_TTL_SECONDS or (kid not in self._keys and age > JWKS_MIN_REFETCH_SECONDS):
                self._refresh()
            key = self._keys.get(kid or "")
        if key is None:
            raise AuthError(*_INVALID, 401)
        return key

    # ---- the check ----
    def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            if alg == "HS256" and self._secret:
                key: Any = self._secret
            elif alg in ASYMMETRIC_ALGORITHMS:
                key = self._key_for(header.get("kid"))
            else:
                raise AuthError(*_INVALID, 401)
            payload = jwt.decode(token, key, algorithms=[alg], audience="authenticated", issuer=self._issuer,
                                 leeway=LEEWAY_SECONDS, options={"require": ["exp", "sub", "aud", "iss"]})
        except AuthError:
            raise
        except jwt.PyJWTError:
            raise AuthError(*_INVALID, 401) from None
        meta = payload.get("app_metadata") or {}
        email = payload.get("email")
        if (payload.get("role") != "authenticated" or payload.get("is_anonymous") or meta.get("provider") not in
                ALLOWED_PROVIDERS or not isinstance(email, str) or "@" not in email or not payload.get("sub")):
            raise AuthError(*_INVALID, 401)
        return TokenClaims(user_id=str(payload["sub"]), email=email.strip().lower())
