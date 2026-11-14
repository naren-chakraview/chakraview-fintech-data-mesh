"""A caller is a verified person (JWT) plus the verified workload (SPIFFE ID) they arrived through."""

from dataclasses import dataclass
from typing import Mapping

from .spiffe import IdentityError, spiffe_id_from_pem
from .tokens import AuthError, JWKSCache, Principal, verify_token

CLIENT_CERT_HEADER = "x-client-cert"


@dataclass(frozen=True)
class Caller:
    principal: Principal
    spiffe_id: str


class CallerVerifier:
    """Verifies both parties. The gateway verifies the certificate chain and forwards the cert in a header."""

    def __init__(self, *, jwks: JWKSCache, issuer: str, audience: str):
        self.jwks = jwks
        self.issuer = issuer
        self.audience = audience

    async def verify(self, headers: Mapping[str, str]) -> Caller:
        authorization = headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthError("missing bearer token")

        principal = verify_token(
            token.strip(), await self.jwks.get(), issuer=self.issuer, audience=self.audience
        )

        try:
            spiffe_id = spiffe_id_from_pem(headers.get(CLIENT_CERT_HEADER, ""))
        except IdentityError as exc:
            raise AuthError(f"workload identity: {exc}") from exc
        return Caller(principal=principal, spiffe_id=spiffe_id)
