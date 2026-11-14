"""require_provenance: a product whose contract requires verified lineage is refused when the snapshot does not verify."""

from datetime import timedelta

from boundary.reader import FixtureReader
from shared.testing.harness import REPO, WORKLOADS

ACCOUNTS = "accounts.account-master"
SUBJECT = "risk.analyst@chakra.fintech"
PURPOSE = "balance-review"


def grant_and_read(stack, product=ACCOUNTS):
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=product,
                        columns=["account_id"], purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))
    headers = stack.headers(stack.token(SUBJECT, roles=["risk_analyst"]))
    url = f"/products/{product}/rows?columns=account_id&purpose={PURPOSE}"
    return stack.boundary().get(url, headers=headers)


def test_verified_snapshot_is_readable_for_a_provenance_required_product(stack):
    r = grant_and_read(stack)

    assert r.status_code == 200
    assert r.json()["lineage_verified"] is True


def test_tampered_snapshot_is_refused_and_audited(stack, tmp_path):
    original = (REPO / "platform/boundary/fixtures" / f"{ACCOUNTS}.json").read_bytes()
    (tmp_path / f"{ACCOUNTS}.json").write_bytes(original.replace(b"ACC-1001", b"ACC-9999"))
    services = stack.boundary_app.state.services
    saved = services.reader
    services.reader = FixtureReader(tmp_path)
    try:
        r = grant_and_read(stack)
    finally:
        services.reader = saved

    assert r.status_code == 403
    assert "provenance required" in r.json()["detail"]
    assert "rows" not in r.json()
    record = stack.audit_records[-1]
    assert record["decision"] == "deny"
    assert record["reason"] == "provenance required: lineage did not verify"


def test_a_product_without_the_requirement_is_not_refused_on_lineage(stack, tmp_path):
    # risk-scores does not require provenance: a tampered snapshot is still reported, not refused.
    original = (REPO / "platform/boundary/fixtures/risk-compliance.risk-scores.json").read_bytes()
    (tmp_path / "risk-compliance.risk-scores.json").write_bytes(original.replace(b"0.82", b"0.19"))
    services = stack.boundary_app.state.services
    saved = services.reader
    services.reader = FixtureReader(tmp_path)
    try:
        stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"],
                            product_id="risk-compliance.risk-scores", columns=["fraud_score"],
                            purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))
        headers = stack.headers(stack.token(SUBJECT, roles=["risk_analyst"]))
        r = stack.boundary().get(f"/products/risk-compliance.risk-scores/rows?columns=fraud_score&purpose={PURPOSE}",
                                 headers=headers)
    finally:
        services.reader = saved

    assert r.status_code == 200
    assert r.json()["lineage_verified"] is False


def test_the_contract_flag_is_visible_in_the_policy_input():
    from shared.governance.products import load_products, product_policy_input

    products = load_products(REPO / "domains")

    assert product_policy_input(products[ACCOUNTS])["require_provenance"] is True
    assert product_policy_input(products["risk-compliance.risk-scores"])["require_provenance"] is False
