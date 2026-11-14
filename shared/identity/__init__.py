"""Verified identity for people (JWT) and workloads (SPIFFE IDs from client certificates)."""

from .tokens import AuthError, JWKSCache, Principal, verify_token
from .spiffe import IdentityError, spiffe_id_from_pem
from .callers import Caller, CallerVerifier

__all__ = [
    "AuthError",
    "Caller",
    "CallerVerifier",
    "IdentityError",
    "JWKSCache",
    "Principal",
    "spiffe_id_from_pem",
    "verify_token",
]
