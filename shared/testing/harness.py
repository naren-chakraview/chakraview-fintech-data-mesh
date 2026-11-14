"""Build the trust stack in-process for tests and demos.

Starts a real OPA server (needs the `opa` binary on PATH), generates a dev IdP key and a dev
workload CA in memory, and wires the boundary and discovery apps. Requests carry the same two
credentials the mTLS gateway would forward: a bearer token and the client certificate.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "platform", REPO / "platform" / "discovery"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from shared.governance.grants import MemoryGrantStore  # noqa: E402
from shared.governance.products import load_products  # noqa: E402
from shared.identity import CallerVerifier, JWKSCache  # noqa: E402
from shared.identity.devtools import generate_rsa_keypair, issue_workload_cert, make_ca, mint_token  # noqa: E402

PLATFORM_POLICY_DIR = REPO / "platform/governance/opa-policies"
DOMAIN_POLICY_DIRS = sorted((REPO / "domains").glob("*/policy"))
IDP_ISSUER = "http://dev-idp"
AUDIENCE = "data-mesh"

WORKLOADS = {
    "notebook": "spiffe://chakracommerce.com/ns/analytics/sa/notebook",
    "nightly-batch": "spiffe://chakracommerce.com/ns/batch/sa/nightly",
    "risk-producer": "spiffe://chakracommerce.com/ns/risk/sa/producer",
}


class OPANotAvailable(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def local_opa(policy_dirs: Iterable[Path]):
    """Run `opa run --server` on a free port with the given policy directories. Yields the base URL."""
    opa = shutil.which("opa")
    if opa is None:
        raise OPANotAvailable("the opa binary is not on PATH; install OPA 1.0.0 to run the trust tests and demos")
    port = free_port()
    dirs = [str(path) for path in policy_dirs]
    process = subprocess.Popen(
        [opa, "run", "--server", f"--addr=127.0.0.1:{port}", *dirs],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                raise OPANotAvailable(process.stderr.read().decode(errors="replace"))
            try:
                if httpx.get(f"{base}/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise OPANotAvailable("OPA did not become healthy")
            time.sleep(0.1)
        yield base
    finally:
        process.terminate()
        process.wait(timeout=5)


def platform_policy_dirs() -> List[Path]:
    return [PLATFORM_POLICY_DIR, *DOMAIN_POLICY_DIRS]


class TrustStack:
    """Boundary and discovery in-process, against one OPA URL. Build with `open_stack`."""

    def __init__(self, opa_url: str, *, grants=None, fuseki_endpoints: Optional[Dict[str, str]] = None,
                 lineage_dir: Optional[Path] = None, sparql_transport=None):
        from boundary.main import Settings, create_app
        import backend.main as discovery

        os.environ["OPA_DECISION_URL"] = f"{opa_url}/v1/data/data_mesh/access"
        os.environ["OPA_MASKING_URL"] = f"{opa_url}/v1/data/data_mesh/access/masking_strategy"

        # `now` is the stack's clock. Tests move it to exercise expiry and approval windows.
        self.now = datetime.now(timezone.utc)

        def clock() -> datetime:
            return self.now

        self.clock = clock
        self.audit_records: List[dict] = []
        self.grants = grants or MemoryGrantStore()
        self.private_pem, jwk = generate_rsa_keypair()
        self.kid = jwk["kid"]
        jwks = {"keys": [jwk]}

        async def fetch_jwks(url: str) -> dict:
            return jwks

        self.ca_key, self.ca_cert = make_ca()
        self._certs: Dict[str, str] = {}
        for name, spiffe_id in WORKLOADS.items():
            _, cert_pem = issue_workload_cert(self.ca_key, self.ca_cert, spiffe_id)
            self._certs[spiffe_id] = quote(cert_pem.decode())
        self._keys = {}
        for name, spiffe_id in WORKLOADS.items():
            key_pem, cert_pem = issue_workload_cert(self.ca_key, self.ca_cert, spiffe_id)
            self._keys[spiffe_id] = (key_pem, cert_pem)

        self.products = load_products(REPO / "domains")
        settings = Settings(
            domains_dir=REPO / "domains",
            fixtures_dir=REPO / "platform/boundary/fixtures",
            lineage_dir=Path(lineage_dir) if lineage_dir else REPO / "platform/lineage/attestations",
            policy_root=REPO,
            idp_jwks_url=f"{IDP_ISSUER}/.well-known/jwks.json",
            idp_issuer=IDP_ISSUER,
            idp_audience=AUDIENCE,
            fuseki_endpoints=fuseki_endpoints or {},
            grant_store="memory",
        )

        def record(entry: dict) -> None:
            self.audit_records.append(entry)

        self.boundary_app = create_app(
            settings, grants=self.grants, audit=_async(record), clock=clock,
            sparql_transport=sparql_transport, jwks_fetch=fetch_jwks,
        )
        discovery.configure(
            caller_verifier=CallerVerifier(
                jwks=JWKSCache(f"{IDP_ISSUER}/.well-known/jwks.json", fetch=fetch_jwks),
                issuer=IDP_ISSUER, audience=AUDIENCE,
            ),
            grant_store=self.grants,
        )
        discovery.clock = clock
        discovery.load_data_products()
        discovery.access_requests.clear()
        self.discovery = discovery

    def token(self, subject: str, roles: Iterable[str] = (), owns: Iterable[str] = (),
              ttl_seconds: int = 3600, issued_at: Optional[datetime] = None) -> str:
        return mint_token(self.private_pem, self.kid, issuer=IDP_ISSUER, audience=AUDIENCE,
                          subject=subject, roles=roles, owns=owns, ttl_seconds=ttl_seconds,
                          now=issued_at)

    def headers(self, token: str, workload: str = WORKLOADS["notebook"]) -> dict:
        return {"Authorization": f"Bearer {token}", "X-Client-Cert": self._certs[workload]}

    def boundary(self) -> TestClient:
        return TestClient(self.boundary_app, raise_server_exceptions=False)

    def discovery_client(self) -> TestClient:
        return TestClient(self.discovery.app, raise_server_exceptions=False)

    def client_cert_pem(self, workload: str = WORKLOADS["notebook"]) -> bytes:
        return self._keys[workload][1]


def _async(fn):
    async def wrapper(entry):
        fn(entry)
    return wrapper


@contextmanager
def open_stack(policy_dirs: Optional[Iterable[Path]] = None, **kwargs):
    """Start OPA with the platform and domain policies and yield a TrustStack."""
    with local_opa(list(policy_dirs) if policy_dirs is not None else platform_policy_dirs()) as opa_url:
        yield TrustStack(opa_url, **kwargs)
