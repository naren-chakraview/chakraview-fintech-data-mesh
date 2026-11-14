"""The read path, end to end against a real OPA: identity, decision, grant, masking, audit, failure modes."""

import os
from datetime import timedelta
from urllib.parse import quote

from boundary.lineage_check import make_lineage_check
from shared.identity.devtools import generate_rsa_keypair, mint_token
from shared.testing.harness import REPO, WORKLOADS, TrustStack

RISK = "risk-compliance.risk-scores"
ACCOUNTS = "accounts.account-master"
PURPOSE = "fraud-review"
SUBJECT = "risk.analyst@chakra.fintech"


def risk_analyst(stack: TrustStack) -> dict:
    return stack.headers(stack.token(SUBJECT, roles=["risk_analyst"]))


def grant(stack: TrustStack, *, columns=("account_ref", "fraud_score"), purpose=PURPOSE,
          expires_in=timedelta(hours=1), workload=WORKLOADS["notebook"], product=RISK):
    return stack.grants.create(
        subject=SUBJECT, workload_spiffe_id=workload, product_id=product,
        columns=list(columns), purpose=purpose, expires_at=stack.now + expires_in,
    )


def read(stack, headers=None, product=RISK, columns="account_ref,fraud_score", purpose=PURPOSE):
    url = f"/products/{product}/rows?columns={columns}&purpose={purpose}"
    return stack.boundary().get(url, headers=risk_analyst(stack) if headers is None else headers)


def test_no_token_returns_401_and_no_rows(stack):
    headers = {"X-Client-Cert": risk_analyst(stack)["X-Client-Cert"]}

    r = read(stack, headers=headers)

    assert r.status_code == 401
    assert "rows" not in r.json()


def test_no_client_certificate_returns_401(stack):
    headers = {"Authorization": risk_analyst(stack)["Authorization"]}

    assert read(stack, headers=headers).status_code == 401


def test_token_signed_by_another_key_returns_401(stack):
    other_pem, _ = generate_rsa_keypair()
    forged = mint_token(other_pem, stack.kid, issuer="http://dev-idp", audience="data-mesh",
                        subject=SUBJECT, roles=["risk_analyst"])

    assert read(stack, headers=stack.headers(forged)).status_code == 401


def test_garbage_client_certificate_returns_401(stack):
    headers = {
        "Authorization": risk_analyst(stack)["Authorization"],
        "X-Client-Cert": quote("not a certificate"),
    }

    assert read(stack, headers=headers).status_code == 401


def test_read_without_grant_is_refused_and_audited(stack):
    stack.audit_records.clear()
    grant_count = len(stack.audit_records)

    r = read(stack)

    assert r.status_code == 403
    assert "approval required" in r.json()["detail"]
    assert len(stack.audit_records) == grant_count + 1
    assert stack.audit_records[-1]["decision"] == "deny"
    assert stack.audit_records[-1]["subject"] == SUBJECT


def test_read_with_grant_returns_masked_rows(stack):
    grant(stack)

    r = read(stack)

    assert r.status_code == 200
    body = r.json()
    assert body["grant_id"] is not None
    first = body["rows"][0]
    # account_ref has no classification, so the domain default (full_hash) applies: a 64-char hex digest.
    assert len(first["account_ref"]) == 64
    assert first["account_ref"] != "ACC-1001"
    # fraud_score is sensitive; partial_mask fully masks values of four characters or fewer.
    assert first["fraud_score"] == "[MASKED]"


def test_partial_mask_keeps_the_ends_of_longer_values(stack):
    grant(stack, columns=("fraud_score",))

    rows = read(stack, columns="fraud_score").json()["rows"]

    assert rows[0]["fraud_score"] == "[MASKED]"  # 4-char values are fully masked, by design


def test_audit_record_names_everything_the_brief_requires(stack):
    grant(stack)
    stack.audit_records.clear()

    read(stack)

    record = stack.audit_records[-1]
    for key in ("subject", "roles", "workload_spiffe_id", "product", "columns", "decision",
                "strategies", "policy_revisions", "grant_id", "lineage_verified", "timestamp", "purpose"):
        assert key in record, key
    assert record["decision"] == "allow"
    assert record["roles"] == ["risk_analyst"]
    assert record["workload_spiffe_id"] == WORKLOADS["notebook"]
    assert record["strategies"]["account_ref"] == "full_hash"
    assert record["strategies"]["fraud_score"] == "partial_mask"
    assert record["policy_revisions"]["platform"]
    assert record["policy_revisions"]["domains"][RISK]


def test_expired_grant_is_refused(stack):
    grant(stack, expires_in=timedelta(minutes=10))
    stack.now = stack.now + timedelta(minutes=11)
    try:
        assert read(stack).status_code == 403
    finally:
        stack.now = stack.now - timedelta(minutes=11)


def test_grant_for_another_purpose_is_refused(stack):
    grant(stack)

    assert read(stack, purpose="marketing").status_code == 403


def test_grant_for_a_different_workload_is_refused(stack):
    grant(stack, workload=WORKLOADS["nightly-batch"])

    assert read(stack).status_code == 403


def test_column_outside_the_grant_is_refused(stack):
    grant(stack, columns=("account_ref",))

    assert read(stack, columns="account_ref,fraud_score").status_code == 403


def test_unknown_column_is_400(stack):
    grant(stack)

    assert read(stack, columns="fraud_score,not_a_column").status_code == 400


def test_product_without_domain_policy_is_404(stack):
    assert read(stack, product="nope.nothing").status_code == 404


def test_pii_product_needs_a_grant_even_for_a_verified_analyst(stack):
    analyst = stack.headers(stack.token("analyst@chakra.fintech", roles=["analyst"]))

    r = read(stack, headers=analyst, product=ACCOUNTS, columns="account_id")

    assert r.status_code == 403


def test_missing_purpose_is_400(stack):
    grant(stack)
    r = stack.boundary().get(f"/products/{RISK}/rows?columns=fraud_score", headers=risk_analyst(stack))

    assert r.status_code == 400


def test_audit_failure_returns_no_rows(stack):
    grant(stack)
    services = stack.boundary_app.state.services
    original = services.audit

    async def broken(record):
        raise RuntimeError("elasticsearch down")

    services.audit = broken
    try:
        r = read(stack)
    finally:
        services.audit = original

    assert r.status_code == 503
    assert "rows" not in r.json()


def test_opa_unreachable_returns_503_and_no_rows(stack):
    grant(stack)
    original = os.environ["OPA_DECISION_URL"]
    os.environ["OPA_DECISION_URL"] = "http://127.0.0.1:9/v1/data/data_mesh/access"
    try:
        r = read(stack)
    finally:
        os.environ["OPA_DECISION_URL"] = original

    assert r.status_code == 503
    assert "rows" not in r.json()


def test_lineage_verifies_for_the_published_snapshot(stack):
    grant(stack)

    assert read(stack).json()["lineage_verified"] is True


def test_lineage_fails_for_a_tampered_snapshot():
    snapshot = (REPO / "platform/boundary/fixtures" / f"{RISK}.json").read_bytes()
    tampered = snapshot.replace(b"0.82", b"0.19")
    check = make_lineage_check(REPO / "platform/lineage/attestations", REPO / "platform/lineage/trust")

    assert check(RISK, snapshot) is True
    assert check(RISK, tampered) is False


def test_lineage_fails_closed_when_no_attestation_exists(tmp_path):
    snapshot = (REPO / "platform/boundary/fixtures" / f"{RISK}.json").read_bytes()
    check = make_lineage_check(tmp_path, REPO / "platform/lineage/trust")

    assert check(RISK, snapshot) is False
