"""Delegated identity: an agent acting for a person, as a token the agent's own sidecar issued, forwarded by the
boundary's sidecar. See verify.py for the full path and the claims."""

from .verify import (
    Delegation,
    DelegationError,
    GatewayTrust,
    JtiCache,
    load_gateway_trusts,
    mint_delegated_token,
    peek_issuer,
    verify_forwarded,
)

__all__ = [
    "Delegation",
    "DelegationError",
    "GatewayTrust",
    "JtiCache",
    "load_gateway_trusts",
    "mint_delegated_token",
    "peek_issuer",
    "verify_forwarded",
]
