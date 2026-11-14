"""Access requests and approvals in discovery, and the grant they create, honoured by the boundary."""

from datetime import timedelta

import pytest

from shared.testing.harness import WORKLOADS

RISK = "risk-compliance.risk-scores"
ACCOUNTS = "accounts.account-master"
SUBJECT = "risk.analyst@chakra.fintech"
PURPOSE = "fraud-review"


@pytest.fixture
def portal(stack):
    """A discovery client plus the caller and owner tokens it needs."""
    client = stack.discovery_client()
    return client, stack


def submit(stack, client, product_id, columns, purpose=PURPOSE, roles=("risk_analyst",)):
    token = stack.token(SUBJECT, roles=roles)
    return client.post("/api/access-requests", headers=stack.headers(token), json={
        "data_product_id": product_id,
        "justification": "fraud review of flagged accounts",
        "purpose": purpose,
        "requested_columns": columns,
    })


def owner_headers(stack, owns):
    token = stack.token(f"owner@{owns}", roles=["data_owner"], owns=[owns])
    return stack.headers(token)


def test_risk_analyst_request_is_pending_on_a_sensitive_product(portal):
    client, stack = portal

    r = submit(stack, client, RISK, ["fraud_score"])

    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert r.json()["routed_to"] == "risk-compliance-domain"


def test_request_body_cannot_name_a_role(portal):
    client, stack = portal
    token = stack.token(SUBJECT, roles=["analyst"])

    r = client.post("/api/access-requests", headers=stack.headers(token), json={
        "data_product_id": RISK, "justification": "x", "requested_columns": ["fraud_score"],
        "user_role": "risk_analyst",
    })

    assert r.status_code == 400


def test_approval_by_the_owner_creates_a_grant_the_boundary_honours(portal):
    client, stack = portal
    created = submit(stack, client, RISK, ["fraud_score"])
    request_id = created.json()["id"]

    approved = client.post(f"/api/access-requests/{request_id}/approve",
                           headers=owner_headers(stack, "risk-compliance-domain"))
    assert approved.status_code == 200

    rows = stack.boundary().get(
        f"/products/{RISK}/rows?columns=fraud_score&purpose={PURPOSE}",
        headers=stack.headers(stack.token(SUBJECT, roles=["risk_analyst"])),
    )
    assert rows.status_code == 200
    assert rows.json()["grant_id"] == approved.json()["grant"]["id"]


def test_grant_expires_at_the_boundary(portal):
    client, stack = portal
    request_id = submit(stack, client, RISK, ["fraud_score"]).json()["id"]
    client.post(f"/api/access-requests/{request_id}/approve?ttl_days=1",
                headers=owner_headers(stack, "risk-compliance-domain"))
    headers = stack.headers(stack.token(SUBJECT, roles=["risk_analyst"]))
    url = f"/products/{RISK}/rows?columns=fraud_score&purpose={PURPOSE}"

    assert stack.boundary().get(url, headers=headers).status_code == 200

    stack.now = stack.now + timedelta(days=2)
    try:
        assert stack.boundary().get(url, headers=headers).status_code == 403
    finally:
        stack.now = stack.now - timedelta(days=2)


def test_grant_does_not_cover_other_columns_or_purposes(portal):
    client, stack = portal
    request_id = submit(stack, client, RISK, ["fraud_score"]).json()["id"]
    client.post(f"/api/access-requests/{request_id}/approve", headers=owner_headers(stack, "risk-compliance-domain"))
    headers = stack.headers(stack.token(SUBJECT, roles=["risk_analyst"]))

    other_column = stack.boundary().get(f"/products/{RISK}/rows?columns=kyc_verdict&purpose={PURPOSE}", headers=headers)
    other_purpose = stack.boundary().get(f"/products/{RISK}/rows?columns=fraud_score&purpose=marketing", headers=headers)

    assert other_column.status_code == 403
    assert other_purpose.status_code == 403


def test_a_non_owner_cannot_approve(portal):
    client, stack = portal
    request_id = submit(stack, client, RISK, ["fraud_score"]).json()["id"]

    r = client.post(f"/api/access-requests/{request_id}/approve",
                    headers=owner_headers(stack, "accounts-domain"))

    assert r.status_code == 403
    assert stack.grants.find_valid(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"],
                                   product_id=RISK, columns=["fraud_score"], purpose=PURPOSE,
                                   now=stack.now) is None


def test_approval_after_the_sla_window_is_refused(portal):
    client, stack = portal
    request_id = submit(stack, client, RISK, ["fraud_score"]).json()["id"]
    stack.now = stack.now + timedelta(hours=3)  # risk-scores approval_sla_hours is 2
    try:
        r = client.post(f"/api/access-requests/{request_id}/approve",
                        headers=owner_headers(stack, "risk-compliance-domain"))
    finally:
        stack.now = stack.now - timedelta(hours=3)

    assert r.status_code == 409


def test_accounts_product_routes_to_its_own_owner(portal):
    client, stack = portal

    r = submit(stack, client, ACCOUNTS, ["account_id"], roles=("analyst",))

    assert r.json()["routed_to"] == "accounts-domain"
    assert r.json()["approval_sla_hours"] == 4
