"""How the scripted agent reaches the boundary. Each call gets a fresh delegated credential.

StackChannel    the in-process demos and tests. The credential is minted by the test harness, in the shape the
                boundary's sidecar forwards.
HttpChannel     the compose stack. The agent's own sidecar (agent-zt, same network namespace) issues the credential:
                an edge mint of the analyst's IdP token, then an RFC 8693 exchange bound to the agent's certificate.
                The call goes to the boundary's sidecar (boundary-zt) over mTLS with that token.
"""

from typing import Iterable, Optional


class StackChannel:
    def __init__(self, stack, user: str, roles: Iterable[str], chain: Iterable[str], ttl_seconds: int = 60,
                 attributes: Optional[dict] = None):
        self.stack = stack
        self.user = user
        self.roles = list(roles)
        self.chain = list(chain)
        self.ttl_seconds = ttl_seconds
        self.attributes = attributes

    def _headers(self) -> dict:
        return self.stack.delegated_headers(self.user, self.roles, self.chain, ttl_seconds=self.ttl_seconds,
                                            attributes=self.attributes)

    def get(self, path: str):
        return self.stack.boundary().get(path, headers=self._headers())

    def post(self, path: str, json: Optional[dict] = None):
        return self.stack.boundary().post(path, json=json, headers=self._headers())


class HttpChannel:
    """Calls over the sidecars in compose. Built from the agent's own certificate and the dev CA."""

    def __init__(self, *, admin_url: str, boundary_url: str, idp_url: str, idp_issuer: str,
                 agent_spiffe_id: str, boundary_spiffe_id: str, cert: tuple, ca: str, user_token: str):
        import httpx
        self.admin = httpx.Client(base_url=admin_url, cert=cert, verify=ca, timeout=10)
        self.boundary = httpx.Client(base_url=boundary_url, cert=cert, verify=ca, timeout=10)
        self.idp_issuer = idp_issuer
        self.agent_spiffe_id = agent_spiffe_id
        self.boundary_spiffe_id = boundary_spiffe_id
        self.user_token = user_token

    def _delegated_token(self) -> str:
        """Edge mint, then exchange. Called for every request: a token is single use at the boundary."""
        minted = self.admin.post("/v1/svid/jwt-with-user",
                                 json={"user_credential": self.user_token, "user_issuer": self.idp_issuer})
        minted.raise_for_status()
        exchanged = self.admin.post("/v1/token-exchange",
                                    json={"subject_token": minted.json()["token"],
                                          "audience": self.boundary_spiffe_id})
        exchanged.raise_for_status()
        return exchanged.json()["access_token"]

    def get(self, path: str):
        return self.boundary.get(path, headers={"X-SPIFFE-OBO-Token": self._delegated_token()})

    def post(self, path: str, json: Optional[dict] = None):
        return self.boundary.post(path, json=json, headers={"X-SPIFFE-OBO-Token": self._delegated_token()})
