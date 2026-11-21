"""Verify a delegated call that the delegation sidecar forwarded, and mint one (dev stand-in for tests and demos).

How a delegated call reaches the boundary:
  agent -> agent-zt (its own sidecar, same network namespace): edge mint (the analyst's IdP token becomes a token
           whose user is the analyst), then RFC 8693 exchange for the boundary, bound to the agent's certificate.
  agent -> boundary-zt (the boundary's sidecar, same network namespace): mTLS with the agent's certificate, the
           exchanged token in X-SPIFFE-OBO-Token. The sidecar checks the signature, issuer, audience, expiry,
           `jti` and the binding, then forwards to the boundary's LOOPBACK listener with:
             X-ZT-Verified-Token   the exact token it validated (forward_verified_token)
             X-ZT-Verified-Caller  the current actor
             X-ZT-Verified-User    the signed user
             X-ZT-Verified-Chain   the chain, chronological (originator first, current actor last), comma-joined
  The boundary accepts this only on its loopback listener. It checks the token against the gateways it trusts,
  and checks that the headers say what the token says. A forwarded token, or a header, on the mTLS listener is
  ignored.

Token claims (zero-trust-rs, `OboClaims`):
    iss    the gateway that signed it (spiffe://<trust-domain>/ns/zt-gateway/sa/<kid>)
    aud    the boundary's SPIFFE ID
    sub    the originator: the agent, for an edge-minted token
    user   the human the agent acts for, as the gateway verified them
    roles  the human's roles, from the IdP credential at the edge mint
    act    the delegation chain, nested newest-first: the outermost act.sub is the current actor
    cnf    binding to the agent's certificate (checked at the sidecar)
    jti    single-use identifier
"""

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Tuple

import jwt

SPIFFE_PREFIX = "spiffe://"
MAX_DEPTH = 2

HEADER_TOKEN = "x-zt-verified-token"
HEADER_CALLER = "x-zt-verified-caller"
HEADER_USER = "x-zt-verified-user"
HEADER_CHAIN = "x-zt-verified-chain"


class DelegationError(Exception):
    """The delegated call is refused. The caller must answer 401 and return no data."""


@dataclass(frozen=True)
class GatewayTrust:
    issuer: str
    jwks: dict = field(repr=False)


@dataclass(frozen=True)
class Delegation:
    user: str
    roles: frozenset
    actor: str
    chain: Tuple[str, ...]
    issued_at: dt.datetime
    expires_at: dt.datetime
    token_id: str
    # The human's attributes the gateway verified from their IdP credential (e.g. kyc_id), from the token's
    # user_attributes. Empty when none were configured.
    attributes: Mapping[str, str] = field(default_factory=dict)


def load_gateway_trusts(path: Path) -> List[GatewayTrust]:
    """The gateways this boundary trusts to forward delegated calls (gateways.json, written by make_config)."""
    document = json.loads(Path(path).read_text())
    return [GatewayTrust(issuer=entry["issuer"], jwks=entry["jwks"]) for entry in document["gateways"]]


def peek_issuer(token: str) -> Optional[str]:
    """The unverified iss claim, used only to choose which gateway's keys to check. Never trusted as identity."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    issuer = claims.get("iss")
    return issuer if isinstance(issuer, str) else None


def chronological_chain(claims: Mapping) -> List[str]:
    """Originator first, current actor last: the same order zero-trust-rs's `delegation_chain` produces."""
    hops: List[str] = []
    node = claims.get("act")
    while node is not None:
        if not isinstance(node, dict):
            raise DelegationError("act claim is malformed")
        sub = node.get("sub")
        if not isinstance(sub, str) or not sub.startswith(SPIFFE_PREFIX):
            raise DelegationError("act names a workload that is not a SPIFFE ID")
        hops.append(sub)
        if len(hops) > MAX_DEPTH:
            raise DelegationError("delegation chain is deeper than the cap")
        node = node.get("act")
    hops.reverse()
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.startswith(SPIFFE_PREFIX):
        raise DelegationError("sub is not a SPIFFE ID")
    chain = [sub] + hops
    if len(chain) > MAX_DEPTH:
        raise DelegationError("delegation chain is deeper than the cap")
    return chain


def verify_forwarded(token: str, trusts: Iterable[GatewayTrust], *, audience: str, now: dt.datetime,
                     headers: Mapping[str, str]) -> Delegation:
    """Return the verified delegation, or raise DelegationError. `headers` are the forwarded X-ZT-* headers."""
    if not token:
        raise DelegationError("no forwarded token")
    issuer = peek_issuer(token)
    trust = next((t for t in trusts if t.issuer == issuer), None)
    if trust is None:
        raise DelegationError("token is from a gateway this boundary does not trust")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise DelegationError("malformed token") from exc
    if header.get("alg") != "RS256":
        raise DelegationError("unsupported signing algorithm")
    key = next((k for k in trust.jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise DelegationError("unknown gateway signing key")
    try:
        # Time is checked below against `now`, the clock the boundary was given, not PyJWT's own wall clock.
        claims = jwt.decode(
            token, key=jwt.PyJWK(key).key, algorithms=["RS256"], audience=audience, issuer=trust.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"], "verify_exp": False,
                     "verify_iat": False, "verify_nbf": False},
        )
    except jwt.PyJWTError as exc:
        raise DelegationError(f"token rejected: {exc.__class__.__name__}") from exc

    now_ts = int(now.timestamp())
    if claims["iat"] > now_ts or claims.get("nbf", claims["iat"]) > now_ts:
        raise DelegationError("delegated token is not yet valid")
    expires = dt.datetime.fromtimestamp(claims["exp"], dt.timezone.utc)
    if expires <= now:
        raise DelegationError("delegated token has expired")
    user = claims.get("user")
    if not isinstance(user, str) or not user:
        raise DelegationError("delegated token names no user")
    roles = claims.get("roles", [])
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise DelegationError("roles claim is malformed")
    chain = chronological_chain(claims)
    actor = chain[-1]
    if actor == user:
        raise DelegationError("the actor cannot be the person it acts for")
    jti = claims.get("jti")
    if not isinstance(jti, str) or not jti:
        raise DelegationError("delegated token has no jti")
    attributes = claims.get("user_attributes", {})
    if not isinstance(attributes, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                   for k, v in attributes.items()):
        raise DelegationError("user_attributes claim is malformed")

    # The headers must say what the token says. A mismatch means something between the sidecar and here changed the
    # call, so it is refused, not reconciled.
    if headers.get(HEADER_USER) != user:
        raise DelegationError("X-ZT-Verified-User does not match the token")
    if headers.get(HEADER_CALLER) != actor:
        raise DelegationError("X-ZT-Verified-Caller does not match the token's current actor")
    if headers.get(HEADER_CHAIN) != ",".join(chain):
        raise DelegationError("X-ZT-Verified-Chain does not match the token's chain")

    return Delegation(
        user=user,
        roles=frozenset(roles),
        actor=actor,
        chain=tuple(chain),
        issued_at=dt.datetime.fromtimestamp(claims["iat"], dt.timezone.utc),
        expires_at=expires,
        token_id=jti,
        attributes=dict(attributes),
    )


class JtiCache:
    """Single use per token: the boundary's own replay check, on top of the sidecar's. In memory, one replica."""

    def __init__(self) -> None:
        self._seen: dict = {}

    def record(self, token_id: str, expires_at: dt.datetime, now: dt.datetime) -> None:
        self._seen = {jti: exp for jti, exp in self._seen.items() if exp > now}
        if token_id in self._seen:
            raise DelegationError("delegated token was already used")
        self._seen[token_id] = expires_at


def mint_delegated_token(
    private_pem: bytes,
    kid: str,
    *,
    issuer: str,
    audience: str,
    user: str,
    roles: Iterable[str],
    chain: Iterable[str],
    ttl_seconds: int = 60,
    now: Optional[dt.datetime] = None,
    attributes: Optional[Mapping[str, str]] = None,
) -> str:
    """Mint the token the sidecar would issue for `chain` (originator first, current actor last). Dev stand-in."""
    actors = list(chain)
    if not actors:
        raise ValueError("a delegated token needs at least one actor")
    act: Optional[dict] = None
    for sub in actors[1:]:
        act = {"sub": sub, **({"act": act} if act else {})}
    issued = now or dt.datetime.now(dt.timezone.utc)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": actors[0],
        "user": user,
        "roles": list(roles),
        "act": act,
        "iat": int(issued.timestamp()),
        "nbf": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if act is None:
        del claims["act"]
    if attributes:
        claims["user_attributes"] = dict(attributes)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})
