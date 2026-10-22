import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

# The discovery backend is a package named `backend` inside platform/discovery.
# Importing it from there avoids the stdlib `platform` module shadowing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "discovery"))

from backend import main as discovery  # noqa: E402
from backend.opa_client import OPAError, evaluate_access, product_classification  # noqa: E402


def make_product(product_id, owner, columns):
    return {
        "id": product_id,
        "owner": owner,
        "access_policy": {
            "approval_sla_hours": 4,
            "columns": [{"name": name, "classification": cls} for name, cls in columns],
        },
    }


PUBLIC = make_product("merchant-catalog", "market-data-domain", [("merchant_id", "public")])
PII = make_product("account-master", "accounts-domain", [("account_id", "pii")])
NO_COLUMNS = make_product("no-columns", "risk-compliance-domain", [])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        discovery, "data_products", {p["id"]: p for p in (PUBLIC, PII, NO_COLUMNS)}
    )
    monkeypatch.setattr(discovery, "access_requests", {})
    return TestClient(discovery.app)


def request_body(product_id, role="analyst"):
    return {
        "user_id": "u-1",
        "user_role": role,
        "data_product_id": product_id,
        "action": "read",
        "justification": "quarterly review",
    }


def stub_opa(monkeypatch, result=None, exc=None, calls=None):
    async def fake(user_id, user_role, action, data_classification):
        if calls is not None:
            calls.append({"data_classification": data_classification})
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(discovery, "evaluate_access", fake)


def test_public_read_is_approved(client, monkeypatch):
    stub_opa(monkeypatch, result={"allow": True, "requires_approval": False})

    r = client.post("/api/access-requests", json=request_body("merchant-catalog"))

    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_pii_product_is_pending_with_owner_and_sla(client, monkeypatch):
    stub_opa(monkeypatch, result={"allow": False, "requires_approval": True})

    r = client.post("/api/access-requests", json=request_body("account-master"))

    body = r.json()
    assert body["status"] == "pending"
    assert body["routed_to"] == "accounts-domain"
    assert body["approval_sla_hours"] == 4


def test_opa_error_denies_request(client, monkeypatch):
    stub_opa(monkeypatch, exc=OPAError("connection refused"))

    r = client.post("/api/access-requests", json=request_body("account-master"))

    assert r.status_code == 503
    stored = list(discovery.access_requests.values())
    assert len(stored) == 1
    assert stored[0]["status"] == "denied"


def test_product_without_columns_is_classified_restricted(client, monkeypatch):
    calls = []
    stub_opa(monkeypatch, result={"allow": True, "requires_approval": True}, calls=calls)

    r = client.post("/api/access-requests", json=request_body("no-columns"))

    assert calls[0]["data_classification"] == "restricted"
    assert r.json()["status"] == "pending"


def test_unknown_product_returns_404(client, monkeypatch):
    stub_opa(monkeypatch, result={"allow": True, "requires_approval": False})

    r = client.post("/api/access-requests", json=request_body("does-not-exist"))

    assert r.status_code == 404


def test_product_classification_is_highest_column():
    product = make_product("p", "o", [("a", "public"), ("b", "pii"), ("c", "sensitive")])
    assert product_classification(product) == "pii"


def test_unknown_classification_value_is_restricted():
    product = make_product("p", "o", [("a", "PII")])
    assert product_classification(product) == "restricted"


def test_evaluate_access_returns_decision_and_sends_input():
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"result": {"allow": True, "requires_approval": False}})

    decision = asyncio.run(
        evaluate_access("u-1", "analyst", "read", "public", transport=httpx.MockTransport(handler))
    )

    assert decision == {"allow": True, "requires_approval": False}
    assert '"data_classification": "public"' in seen["body"]


def test_evaluate_access_raises_on_non_200():
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "boom"}))

    with pytest.raises(OPAError):
        asyncio.run(evaluate_access("u-1", "analyst", "read", "public", transport=transport))


def test_evaluate_access_raises_on_missing_result():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))

    with pytest.raises(OPAError):
        asyncio.run(evaluate_access("u-1", "analyst", "read", "public", transport=transport))
