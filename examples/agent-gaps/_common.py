"""Shared plumbing for the agent-gaps demos: the frozen "before" boundary, the live "after" boundary, and output.

The "before" side loads the frozen code in examples/agent-gaps/before/ (tag agents-before). Nothing in the platform
imports it. Its OPA policies and product files are frozen with it. The shared libraries it uses (identity, grants,
masking, lineage verification) are the live ones, which have not changed in a way that matters to these demos.
"""

import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BEFORE = HERE / "before"
for entry in (REPO, REPO / "platform", HERE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

# Demo-only value. Real runs set their own.
os.environ.setdefault("FINTECH_IRI_KEY", "demo-only-key-not-for-production")

from shared.governance.grants import MemoryGrantStore  # noqa: E402
from shared.identity.devtools import generate_rsa_keypair, issue_workload_cert, make_ca, mint_token  # noqa: E402
from shared.testing.harness import (AGENT_SPIFFE_ID, AUDIENCE, IDP_ISSUER, WORKLOADS, local_opa,  # noqa: E402
                                    open_proposal_stack)

# The demos run on the real clock: the IdP tokens are checked against it. Fixture scores are dated relative to it.
DEMO_NOW = datetime.now(timezone.utc).replace(microsecond=0)
ANALYST = "risk.analyst@chakra.fintech"
ANALYST_ROLES = ["risk_analyst"]
OWNER = "owner@risk-compliance.chakra.fintech"
OWNER_ROLES = ["data_owner"]
OWNER_DOMAINS = ["risk-compliance-domain"]
NOTEBOOK = WORKLOADS["notebook"]
AGENT = AGENT_SPIFFE_ID
RISK = "risk-compliance.risk-scores"
NOTES = "risk-compliance.risk-review-notes"


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def show(label: str, value) -> None:
    print(f"  {label:<26} {value}")


def ok(claim: str) -> None:
    print(f"  [ok] {claim}")


@contextmanager
def after_stack():
    """The live boundary, with the governed writer, over a temporary copy of the product state."""
    with tempfile.TemporaryDirectory(prefix="agent-gaps-after-") as tmp:
        with open_proposal_stack(Path(tmp)) as stack:
            stack.now = DEMO_NOW
            yield stack


class BeforeStack:
    """The frozen boundary, with the frozen OPA policies and product files, in-process."""

    def __init__(self, opa_url: str):
        from boundary_before_loader import load_before_main

        main = load_before_main()
        self.now = DEMO_NOW
        self.audit_records: List[dict] = []
        self.grants = MemoryGrantStore()
        self.private_pem, jwk = generate_rsa_keypair()
        self.kid = jwk["kid"]
        jwks = {"keys": [jwk]}

        async def fetch_jwks(url: str) -> dict:
            return jwks

        ca_key, ca_cert = make_ca()
        self._certs = {}
        for spiffe_id in WORKLOADS.values():
            _, cert_pem = issue_workload_cert(ca_key, ca_cert, spiffe_id)
            self._certs[spiffe_id] = quote(cert_pem.decode())

        os.environ["OPA_DECISION_URL"] = f"{opa_url}/v1/data/data_mesh/access"
        os.environ["OPA_MASKING_URL"] = f"{opa_url}/v1/data/data_mesh/access/masking_strategy"

        async def record(entry: dict) -> None:
            self.audit_records.append(entry)

        settings = main.Settings(
            domains_dir=BEFORE / "domains",
            fixtures_dir=BEFORE / "platform/boundary/fixtures",
            lineage_dir=BEFORE / "platform/lineage/attestations",
            lineage_trust_dir=BEFORE / "platform/lineage/trust-config",
            policy_root=BEFORE,
            idp_jwks_url=f"{IDP_ISSUER}/.well-known/jwks.json",
            idp_issuer=IDP_ISSUER,
            idp_audience=AUDIENCE,
            fuseki_endpoints={},
            grant_store="memory",
        )
        self.app = main.create_app(settings, grants=self.grants, audit=record, clock=lambda: self.now,
                                   jwks_fetch=fetch_jwks)

    def token(self, subject: str, roles: Iterable[str] = ()) -> str:
        return mint_token(self.private_pem, self.kid, issuer=IDP_ISSUER, audience=AUDIENCE,
                          subject=subject, roles=roles, now=self.now)

    def headers(self, token: str, workload: str = NOTEBOOK) -> dict:
        return {"Authorization": f"Bearer {token}", "X-Client-Cert": self._certs[workload]}

    def client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, raise_server_exceptions=False)


@contextmanager
def before_stack():
    base = BEFORE
    with local_opa([base / "platform/governance/opa-policies", base / "domains/risk-compliance/policy",
                    base / "domains/accounts/policy"]) as opa_url:
        yield BeforeStack(opa_url)
