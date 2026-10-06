"""Access-token verification.

The API verifies Supabase Auth access tokens itself — signature (asymmetric keys from JWKS), issuer, audience,
expiry and ``role`` — and never trusts a role, organisation or capability supplied by the caller. Symmetric
(HS256) tokens are rejected: the local stack and production both use asymmetric signing keys.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK

from pawguard_api.errors import ServiceUnavailable, Unauthenticated
from pawguard_api.settings import Settings

ALLOWED_ALGORITHMS = ("ES256", "RS256")


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_id: UUID | None
    email: str | None
    aal: str | None
    expires_at: int
    token: str  # kept only in memory for the duration of the request (needed for session checks)


class JwksCache:
    """Fetches and caches the JWKS. Refreshes on unknown ``kid`` (key rotation) at most once per 30 s."""

    def __init__(self, url: str, ttl_seconds: int = 600, static_jwks: dict[str, Any] | None = None) -> None:
        self._url = url
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0
        if static_jwks is not None:
            self._load(static_jwks)
            self._fetched_at = float("inf")

    def _load(self, jwks: dict[str, Any]) -> None:
        keys: dict[str, PyJWK] = {}
        for jwk in jwks.get("keys", []):
            if jwk.get("alg") in ALLOWED_ALGORITHMS and jwk.get("kid"):
                keys[jwk["kid"]] = PyJWK.from_dict(jwk)
        self._keys = keys

    def _fetch(self) -> None:
        try:
            resp = httpx.get(self._url, timeout=5.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("Authentication keys are unavailable.", code="auth_keys_unavailable") from exc
        self._load(resp.json())
        self._fetched_at = time.monotonic()

    def get(self, kid: str) -> PyJWK:
        with self._lock:
            now = time.monotonic()
            if now - self._fetched_at > self._ttl:
                self._fetch()
            key = self._keys.get(kid)
            if key is None and now - self._last_forced > 30 and self._fetched_at != float("inf"):
                self._last_forced = now
                self._fetch()
                key = self._keys.get(kid)
        if key is None:
            raise Unauthenticated("Unknown signing key.", code="invalid_token")
        return key

    def is_reachable(self) -> bool:
        try:
            with self._lock:
                if self._fetched_at == float("inf"):
                    return True
                self._fetch()
            return bool(self._keys)
        except ServiceUnavailable:
            return False


class TokenVerifier:
    def __init__(self, settings: Settings, jwks: JwksCache | None = None) -> None:
        assert settings.auth_jwks_url and settings.auth_issuer
        self._issuer = settings.auth_issuer
        self._audience = settings.auth_audience
        self._leeway = settings.auth_leeway_seconds
        self.jwks = jwks or JwksCache(settings.auth_jwks_url)

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise Unauthenticated("Malformed token.", code="invalid_token") from exc
        alg, kid = header.get("alg"), header.get("kid")
        if alg not in ALLOWED_ALGORITHMS or not kid:
            raise Unauthenticated("Unsupported token algorithm.", code="invalid_token")
        key = self.jwks.get(kid)
        try:
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise Unauthenticated("Session expired.", code="token_expired") from exc
        except jwt.PyJWTError as exc:
            raise Unauthenticated("Invalid token.", code="invalid_token") from exc
        if claims.get("role") != "authenticated":
            raise Unauthenticated("Token is not a user session.", code="invalid_token")
        try:
            user_id = UUID(claims["sub"])
            session_id = UUID(claims["session_id"]) if claims.get("session_id") else None
        except (ValueError, TypeError) as exc:
            raise Unauthenticated("Invalid token subject.", code="invalid_token") from exc
        return Principal(user_id=user_id, session_id=session_id, email=claims.get("email"),
                         aal=claims.get("aal"), expires_at=int(claims["exp"]), token=token)
