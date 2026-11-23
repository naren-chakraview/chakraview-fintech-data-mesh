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
# Test-only value: customer IRIs are minted with it (shared/semantic/identity.py). Real runs set their own.
os.environ.setdefault("FINTECH_IRI_KEY", "demo-only-key-not-for-production")
for entry in (REPO, REPO / "platform", REPO / "platform" / "discovery"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from shared.governance.grants import MemoryGrantStore  # noqa: E402
from shared.governance.products import load_products  # noqa: E402
from shared.identity import CallerVerifier, JWKSCache  # noqa: E402
from shared.identity.devtools import generate_rsa_keypair, issue_workload_cert, make_ca, mint_token  # noqa: E402
from delegation import GatewayTrust, mint_delegated_token  # noqa: E402

PLATFORM_POLICY_DIR = REPO / "platform/governance/opa-policies"
DOMAIN_POLICY_DIRS = sorted((REPO / "domains").glob("*/policy"))
IDP_ISSUER = "http://dev-idp"
AUDIENCE = "data-mesh"

NOTES_PRODUCT = "risk-compliance.risk-review-notes"
GATEWAY_SPIFFE_ID = "spiffe://chakracommerce.com/ns/gateway/sa/zt-gateway"
GATEWAY_ISSUER = "http://zt-gateway"
AGENT_SPIFFE_ID = "spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"
BOUNDARY_SPIFFE_ID = "spiffe://chakracommerce.com/ns/boundary/sa/boundary"
LOOPBACK_PORT = 8080

WORKLOADS = {
    "notebook": "spiffe://chakracommerce.com/ns/analytics/sa/notebook",
    "nightly-batch": "spiffe://chakracommerce.com/ns/batch/sa/nightly",
    "risk-producer": "spiffe://chakracommerce.com/ns/risk/sa/producer",
    "risk-review-agent": AGENT_SPIFFE_ID,
    "zt-gateway": GATEWAY_SPIFFE_ID,
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


@contextmanager
def open_proposal_stack(root: Path, extra_intake_rego: str = ""):
    """A boundary with the governed writer for the review-notes product, over copies made under `root`.

    The repo's own fixtures, attestations and trust config are copied, never written, so a proposal or a
    rollback in a test or demo cannot change the repository. Yields a TrustStack with `.writer` and `.paths`.
    """
    from boundary.main import WRITER_KEYID, WRITER_SPIFFE_ID
    from boundary.proposals import Limits
    from proposals.writer import GovernedWriter

    root = Path(root)
    paths = {"fixtures": root / "fixtures", "lineage": root / "lineage", "trust": root / "trust",
             "state": root / "state"}
    shutil.copytree(REPO / "platform/boundary/fixtures", paths["fixtures"])
    shutil.copytree(REPO / "platform/lineage/attestations", paths["lineage"])
    shutil.copytree(REPO / "platform/lineage/trust-config", paths["trust"])

    holder: dict = {}
    writer = GovernedWriter(
        product_id=NOTES_PRODUCT, snapshot_dir=paths["fixtures"], attestation_dir=paths["lineage"],
        history_dir=paths["state"] / "history",
        private_key_pem=(REPO / "platform/lineage/keys/governed-writer.key").read_bytes(),
        keyid=WRITER_KEYID, producer_spiffe_id=WRITER_SPIFFE_ID, clock=lambda: holder["stack"].now,
    )
    limits = Limits()
    policy_dirs = platform_policy_dirs()
    if extra_intake_rego:
        # The accounts domain's policy with extra rules appended to the customer-intake file, for a test that changes a
        # domain's rule (for example, switching subject consent off). The repository's policy is not changed.
        overrides = root / "policy-overrides"
        shutil.copytree(REPO / "domains/accounts/policy", overrides)
        (overrides / "customer-intake.rego").write_text(
            (REPO / "domains/accounts/policy/customer-intake.rego").read_text() + "\n" + extra_intake_rego)
        policy_dirs = [PLATFORM_POLICY_DIR] + [d for d in DOMAIN_POLICY_DIRS
                                               if d.parent.name != "accounts"] + [overrides]
    with local_opa(policy_dirs) as opa_url:
        stack = TrustStack(opa_url, fixtures_dir=paths["fixtures"], lineage_dir=paths["lineage"],
                           lineage_trust_dir=paths["trust"], proposal_state_dir=paths["state"],
                           writer=writer, limits=limits)
        holder["stack"] = stack
        stack.limits = limits
        stack.paths = paths
        yield stack


class TrustStack:
    """Boundary and discovery in-process, against one OPA URL. Build with `open_stack`."""

    def __init__(self, opa_url: str, *, grants=None, fuseki_endpoints: Optional[Dict[str, str]] = None,
                 lineage_dir: Optional[Path] = None, lineage_trust_dir: Optional[Path] = None,
                 sparql_transport=None, fixtures_dir: Optional[Path] = None, writer=None,
                 proposal_state_dir: Optional[Path] = None, limits=None):
        from boundary.main import Settings, create_app
        import backend.main as discovery

        os.environ["OPA_DECISION_URL"] = f"{opa_url}/v1/data/data_mesh/access"
        os.environ["OPA_MASKING_URL"] = f"{opa_url}/v1/data/data_mesh/access/masking_strategy"
        os.environ["OPA_WRITE_URL"] = f"{opa_url}/v1/data/data_mesh/access/write_outcome"

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

        # The agent's sidecar signs the delegated tokens with its own key. The boundary trusts only its public half.
        self._gateway_key, gateway_jwk = generate_rsa_keypair()
        self.gateway_kid = gateway_jwk["kid"]
        self.gateway_trusts = [GatewayTrust(issuer=GATEWAY_ISSUER, jwks={"keys": [gateway_jwk]})]

        self.products = load_products(REPO / "domains")
        settings = Settings(
            domains_dir=REPO / "domains",
            fixtures_dir=Path(fixtures_dir) if fixtures_dir else REPO / "platform/boundary/fixtures",
            lineage_dir=Path(lineage_dir) if lineage_dir else REPO / "platform/lineage/attestations",
            lineage_trust_dir=Path(lineage_trust_dir) if lineage_trust_dir else REPO / "platform/lineage/trust-config",
            policy_root=REPO,
            idp_jwks_url=f"{IDP_ISSUER}/.well-known/jwks.json",
            idp_issuer=IDP_ISSUER,
            idp_audience=AUDIENCE,
            fuseki_endpoints=fuseki_endpoints or {},
            grant_store="memory",
            delegation_trust_dir=REPO / "platform/delegation/trust-config",
            proposal_state_dir=Path(proposal_state_dir) if proposal_state_dir else REPO / "platform/proposals/state",
            writer_key_path=REPO / "platform/lineage/keys/governed-writer.key",
            boundary_spiffe_id=BOUNDARY_SPIFFE_ID,
            loopback_port=LOOPBACK_PORT,
        )

        def record(entry: dict) -> None:
            self.audit_records.append(entry)

        self.writer = writer
        self.boundary_app = create_app(
            settings, grants=self.grants, audit=_async(record), clock=clock,
            sparql_transport=sparql_transport, jwks_fetch=fetch_jwks,
            gateway_trusts=self.gateway_trusts, writer=writer, limits=limits,
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
              ttl_seconds: int = 3600, issued_at: Optional[datetime] = None,
              attributes: Optional[dict] = None) -> str:
        """An IdP token. `attributes` are extra claims the credential carries (e.g. kyc_id)."""
        return mint_token(self.private_pem, self.kid, issuer=IDP_ISSUER, audience=AUDIENCE,
                          subject=subject, roles=roles, owns=owns, ttl_seconds=ttl_seconds,
                          now=issued_at, extra_claims=attributes)

    def headers(self, token: str, workload: str = WORKLOADS["notebook"]) -> dict:
        return {"Authorization": f"Bearer {token}", "X-Client-Cert": self._certs[workload]}

    def delegated_headers(self, user: str, roles: Iterable[str], chain: Iterable[str],
                          ttl_seconds: int = 60, issued_at: Optional[datetime] = None,
                          attributes: Optional[dict] = None) -> dict:
        """What the boundary's sidecar forwards on the loopback listener for a call the agent's sidecar issued.

        `chain` is originator first, current actor last. A fresh token each time: the replay check is single use.
        """
        chain = list(chain)
        # Issued on the stack's clock, the same clock the boundary reads, so the token is never "from the future".
        token = mint_delegated_token(
            self._gateway_key, self.gateway_kid, issuer=GATEWAY_ISSUER, audience=BOUNDARY_SPIFFE_ID,
            user=user, roles=roles, chain=chain, ttl_seconds=ttl_seconds, now=issued_at or self.now,
            attributes=attributes,
        )
        return {
            "X-ZT-Verified-Token": token,
            "X-ZT-Verified-User": user,
            "X-ZT-Verified-Caller": chain[-1],
            "X-ZT-Verified-Chain": ",".join(chain),
        }

    def boundary(self) -> "ListenerRouter":
        """Calls to the boundary, sent to the listener that matches the caller: loopback for a forwarded call (a
        request with X-ZT-Verified-Token), mTLS for everything else."""
        return ListenerRouter(self.boundary_app)

    def boundary_mtls(self) -> TestClient:
        return TestClient(self.boundary_app, base_url="https://boundary:8443", raise_server_exceptions=False)

    def discovery_client(self) -> TestClient:
        return TestClient(self.discovery.app, raise_server_exceptions=False)

    def client_cert_pem(self, workload: str = WORKLOADS["notebook"]) -> bytes:
        return self._keys[workload][1]


class ListenerRouter:
    """Sends each call to the boundary's listener that its caller would reach. See `TrustStack.boundary`."""

    def __init__(self, app):
        self.loopback = TestClient(app, base_url=f"http://127.0.0.1:{LOOPBACK_PORT}", raise_server_exceptions=False)
        self.mtls = TestClient(app, base_url="https://boundary:8443", raise_server_exceptions=False)

    def _pick(self, headers):
        forwarded = any(key.lower() == "x-zt-verified-token" for key in (headers or {}))
        return self.loopback if forwarded else self.mtls

    def get(self, url, headers=None, **kwargs):
        return self._pick(headers).get(url, headers=headers, **kwargs)

    def post(self, url, headers=None, **kwargs):
        return self._pick(headers).post(url, headers=headers, **kwargs)


def _async(fn):
    async def wrapper(entry):
        fn(entry)
    return wrapper


@contextmanager
def open_stack(policy_dirs: Optional[Iterable[Path]] = None, **kwargs):
    """Start OPA with the platform and domain policies and yield a TrustStack."""
    with local_opa(list(policy_dirs) if policy_dirs is not None else platform_policy_dirs()) as opa_url:
        yield TrustStack(opa_url, **kwargs)
