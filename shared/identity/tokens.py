"""Verify a person's JWT: RS256 signature from the IdP's JWKS, plus iss, aud, sub, exp, nbf.

Roles and the subject come only from verified claims. Any failure raises AuthError.
"""

import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

import httpx
import jwt


class AuthError(Exception):
    """The caller could not be authenticated. Callers must return 401 and no data."""


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset
    claims: Dict = field(default_factory=dict, compare=False, hash=False)


def verify_token(token: str, jwks: dict, *, issuer: str, audience: str) -> Principal:
    """Verify a bearer token against a JWKS document and return the principal."""
    if not token:
        raise AuthError("no token")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError("malformed token") from exc

    if header.get("alg") != "RS256":
        raise AuthError("unsupported signing algorithm")

    key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise AuthError("unknown signing key")

    try:
        public_key = jwt.PyJWK(key).key
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"token rejected: {exc.__class__.__name__}") from exc

    roles = claims.get("roles", [])
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise AuthError("roles claim is malformed")
    return Principal(subject=claims["sub"], roles=frozenset(roles), claims=claims)


JWKSFetch = Callable[[str], Awaitable[dict]]


async def fetch_jwks(url: str) -> dict:
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(url)
    if response.status_code != 200:
        raise AuthError(f"JWKS endpoint returned HTTP {response.status_code}")
    try:
        document = response.json()
    except ValueError as exc:
        raise AuthError("JWKS is not JSON") from exc
    if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
        raise AuthError("JWKS has no keys")
    return document


class JWKSCache:
    """Caches a JWKS document for ttl_seconds. A fetch failure raises AuthError, never a stale key."""

    def __init__(self, url: str, ttl_seconds: int = 300, fetch: JWKSFetch = fetch_jwks):
        self.url = url
        self.ttl_seconds = ttl_seconds
        self._fetch = fetch
        self._document: Optional[dict] = None
        self._fetched_at = 0.0

    async def get(self) -> dict:
        if self._document is None or time.monotonic() - self._fetched_at > self.ttl_seconds:
            self._document = await self._fetch(self.url)
            self._fetched_at = time.monotonic()
        return self._document
