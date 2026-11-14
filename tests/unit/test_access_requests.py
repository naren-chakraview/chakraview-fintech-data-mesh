"""Discovery access requests: identity comes from the verified token, decisions from OPA (stubbed here).

The end-to-end path with a real OPA is in tests/trust/test_discovery.py.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "platform", REPO / "platform" / "discovery"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from backend import main as discovery  # noqa: E402
from backend.opa_client import OPAError, evaluate_access  # noqa: E402
from boundary.policy import Decision  # noqa: E402
from shared.governance.grants import MemoryGrantStore  # noqa: E402
from shared.governance.products import product_classification  # noqa: E402
from shared.identity import CallerVerifier, JWKSCache  # noqa: E402
from shared.identity.devtools import generate_rsa_keypair, mint_token  # noqa: E402

IDP = "http://dev-idp"
PRIVATE, JWK = generate_rsa_keypair()
WORKLOAD = "spiffe://chakracommerce.com/ns/analytics/sa/notebook"
CERT = "-----BEGIN CERTIFICATE-----\nnot-used-here\n-----END CERTIFICATE-----"


def product(product_id, owner, columns, approval=True, sla=4):
    domain, name = product_id.split(".", 1)
    return {
        "domain": domain, "name": name, "owner": owner, "access_policy": {
            "approval_required": approval, "approval_sla_hours": sla,
            "columns": [{"name": n, "classification": c} for n, c in columns],
        },
    }


PUBLIC = product("market-data.merchant-catalog", "market-data-domain", [("merchant_id", "public")], approval=False)
PII = product("accounts.account-master", "accounts-domain", [("account_id", "pii")], sla=4)
NO_COLUMNS = product("risk-compliance.no-columns", "risk-compliance-domain", [])


async def fetch_jwks(url):
    return {"keys": [JWK]}


def token(subject="analyst@chakra.fintech", roles=("analyst",), owns=(), issued=None):
    return mint_token(PRIVATE, JWK["kid"], issuer=IDP, audience="data-mesh", subject=subject,
                      roles=roles, owns=owns, now=issued)


@pytest.fixture
def client(monkeypatch):
    products = {p["domain"] + "." + p["name"]: p for p in (PUBLIC, PII, NO_COLUMNS)}
    monkeypatch.setattr(discovery, "data_products", products)
    monkeypatch.setattr(discovery, "access_requests", {})
    grants = MemoryGrantStore()
    monkeypatch.setattr(discovery, "grants", grants)
    monkeypatch.setattr(discovery, "verifier", CallerVerifier(
        jwks=JWKSCache("unused", fetch=fetch_jwks), issuer=IDP, audience="data-mesh"))
    monkeypatch.setattr(discovery, "clock", lambda: datetime.now(timezone.utc))
    return TestClient(discovery.app, raise_server_exceptions=False)


def headers(tok=None):
    tok = tok or token()
    return {"Authorization": f"Bearer {tok}", "X-Client-Cert": CERT_FOR_TESTS}


def stub_opa(monkeypatch, decision=None, exc=None):
    async def fake(caller, product, action, **kwargs):
        if exc is not None:
            raise exc
        return decision

    monkeypatch.setattr(discovery, "evaluate_access", fake)


def body(product_id, **extra):
    return {"data_product_id": product_id, "justification": "quarterly review",
            "requested_columns": ["merchant_id"], **extra}


CERT_FOR_TESTS = None


@pytest.fixture(autouse=True)
def workload_cert(monkeypatch):
    global CERT_FOR_TESTS
    from shared.identity.devtools import issue_workload_cert, make_ca
    from urllib.parse import quote
    ca_key, ca_cert = make_ca()
    _, cert_pem = issue_workload_cert(ca_key, ca_cert, WORKLOAD)
    CERT_FOR_TESTS = quote(cert_pem.decode())
    yield


def test_public_product_is_approved(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=False))

    r = client.post("/api/access-requests", json=body("market-data.merchant-catalog"), headers=headers())

    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_pii_product_is_pending_with_owner_and_sla(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=True))

    r = client.post("/api/access-requests", json=body("accounts.account-master"), headers=headers())

    body_json = r.json()
    assert body_json["status"] == "pending"
    assert body_json["routed_to"] == "accounts-domain"
    assert body_json["approval_sla_hours"] == 4


def test_user_id_in_body_is_rejected(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=False))

    r = client.post("/api/access-requests", json=body("market-data.merchant-catalog", user_id="x"), headers=headers())

    assert r.status_code == 400
    assert "user_id" in r.json()["detail"]


def test_user_role_in_body_is_rejected_even_for_risk_analyst(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=False))

    r = client.post("/api/access-requests", json=body("accounts.account-master", user_role="risk_analyst"),
                    headers=headers(token(roles=("analyst",))))

    assert r.status_code == 400


def test_missing_token_is_401(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=False))

    r = client.post("/api/access-requests", json=body("market-data.merchant-catalog"))

    assert r.status_code == 401


def test_opa_error_denies_request(client, monkeypatch):
    stub_opa(monkeypatch, exc=OPAError("down"))

    r = client.post("/api/access-requests", json=body("market-data.merchant-catalog"), headers=headers())

    assert r.status_code == 503
    assert discovery.access_requests["req_1"]["status"] == "denied"


def test_product_without_columns_is_classified_restricted():
    assert product_classification(NO_COLUMNS) == "restricted"


def test_owner_can_approve_and_grant_is_stored(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=True))
    created = client.post("/api/access-requests", json=body("accounts.account-master"), headers=headers())
    assert created.json()["status"] == "pending"

    owner = token("owner@accounts", roles=("data_owner",), owns=["accounts-domain"])
    r = client.post("/api/access-requests/req_1/approve", headers=headers(owner))

    assert r.status_code == 200
    grant = r.json()["grant"]
    assert grant["columns"] == ["merchant_id"]
    assert discovery.access_requests["req_1"]["status"] == "approved"


def test_non_owner_cannot_approve(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=True))
    client.post("/api/access-requests", json=body("accounts.account-master"), headers=headers())

    r = client.post("/api/access-requests/req_1/approve",
                    headers=headers(token("other@x", roles=("data_owner",), owns=["risk-compliance-domain"])))

    assert r.status_code == 403


def test_approval_after_sla_window_is_refused(client, monkeypatch):
    stub_opa(monkeypatch, Decision(allow=True, requires_approval=True))
    client.post("/api/access-requests", json=body("accounts.account-master"), headers=headers())
    later = datetime.now(timezone.utc) + timedelta(hours=5)
    monkeypatch.setattr(discovery, "clock", lambda: later)

    owner = token("owner@accounts", roles=("data_owner",), owns=["accounts-domain"])
    r = client.post("/api/access-requests/req_1/approve", headers=headers(owner))

    assert r.status_code == 409
    assert "window" in r.json()["detail"]


def test_evaluate_access_uses_verified_caller(monkeypatch):
    seen = {}

    async def fake_decide(policy_input, **kwargs):
        seen.update(policy_input)
        return Decision(allow=True, requires_approval=False)

    import backend.opa_client as client_module
    monkeypatch.setattr(client_module, "decide", fake_decide)
    from shared.identity import Caller
    from shared.identity.tokens import Principal

    caller = Caller(principal=Principal(subject="s", roles=frozenset({"analyst"})), spiffe_id=WORKLOAD)
    import asyncio
    asyncio.run(evaluate_access(caller, PII, "request_access"))

    assert seen["principal"] == {"subject": "s", "roles": ["analyst"]}
    assert seen["workload"] == {"spiffe_id": WORKLOAD}
    assert seen["product"]["id"] == "accounts.account-master"
