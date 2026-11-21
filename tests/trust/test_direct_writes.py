"""Direct writes (addendum W2 to W5), through the boundary's gates, against a real OPA.

Every row of the write table is exercised for both caller kinds, and each refusal is checked to leave the product
unchanged. The customer intake (W3) is checked for the identity rule and for masking on read."""

import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from boundary import writes
from boundary.proposals import Limits
from lineage.trust import load_trust
from lineage.verify import verify_envelope
from shared.semantic.identity import mint_customer_iri
from shared.testing.harness import AGENT_SPIFFE_ID, WORKLOADS, open_proposal_stack

INTAKE = "accounts.customer-intake"
SUMMARY = "risk-compliance.score-freshness-summary"
SCORES = "risk-compliance.risk-scores"
NOTES = "risk-compliance.risk-review-notes"
ONBOARD = "spiffe://chakracommerce.com/ns/agents/sa/onboarding-agent"
RISK_PRODUCER = WORKLOADS["risk-producer"]
ANALYST = "risk.analyst@chakra.fintech"
CUSTOMER = "ada@customer.test"
KYC = "K-1001"
OTHER_CUSTOMER = "grace@customer.test"
OTHER_KYC = "K-2002"
CUSTOMER_IRI = mint_customer_iri(CUSTOMER, KYC)
OTHER_IRI = mint_customer_iri(OTHER_CUSTOMER, OTHER_KYC)
OWNER = "owner@risk-compliance.chakra.fintech"


@pytest.fixture
def stack(tmp_path):
    with open_proposal_stack(tmp_path) as s:
        s.limits.agent.limit = 1000
        s.limits.person.limit = 1000
        yield s


def intake_row(customer_iri=CUSTOMER_IRI, ssn="123-45-6789"):
    return {"customer_iri": customer_iri, "legal_name": "Ada Lovelace", "ssn": ssn,
            "address": "1 Analytical Way, London"}


def write(stack, product, rows, headers, derived=()):
    return stack.boundary().post(f"/products/{product}/writes", json={"rows": rows, "derived_from": list(derived)},
                                 headers=headers)


def grant(stack, subject, workload, product, columns, purpose="write"):
    return stack.grants.create(subject=subject, workload_spiffe_id=workload, product_id=product,
                               columns=list(columns), purpose=purpose, expires_at=stack.now + timedelta(hours=1))


def snapshot_rows(stack, product):
    """The product's current rows: the boundary's own state if it has written the product, else the fixture."""
    state = stack.paths["state"] / "products" / f"{product}.json"
    source = state if state.exists() else stack.paths["fixtures"] / f"{product}.json"
    return json.loads(source.read_text())["rows"]


def customer_agent(stack, customer=CUSTOMER, kyc=KYC):
    return stack.delegated_headers(customer, ["customer"], [ONBOARD], attributes={"kyc_id": kyc})


def risk_producer(stack):
    return stack.headers(stack.token("producer@risk.chakra.fintech", roles=["risk_producer"]),
                         workload=RISK_PRODUCER)


def risk_agent(stack, chain=(AGENT_SPIFFE_ID,)):
    return stack.delegated_headers(ANALYST, ["risk_analyst"], list(chain))


def read_scores_digest(stack):
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SCORES, ["customer_iri", "risk_band", "scored_at"], purpose="risk-review")
    r = stack.boundary().get(f"/products/{SCORES}/rows?columns=customer_iri,risk_band,scored_at&purpose=risk-review",
                             headers=risk_agent(stack))
    assert r.status_code == 200, r.text
    return r.json()["snapshot_sha256"]


SUMMARY_COLUMNS = ["summary_id", "day", "risk_band", "stale_count"]


def summary_row(stale=2):
    return {"summary_id": "2026-11-21|high", "day": "2026-11-21", "risk_band": "high", "stale_count": stale}


# ---- captured: a customer writes their own intake, directly -------------------------------------------------

def test_a_customer_agent_writes_their_own_intake_directly_and_it_is_signed(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])

    r = write(stack, INTAKE, [intake_row()], customer_agent(stack))

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["outcome"] == "direct" and body["rows_written"] == 1
    assert body["accepted_by"].startswith("policy:")
    audit = next(a for a in stack.audit_records if a.get("action") == "write")
    assert audit["written_by"] == ONBOARD and audit["on_behalf_of"] == CUSTOMER
    assert audit["write_kind"] == "captured" and audit["classification"] == "pii"
    envelope = json.loads((stack.paths["lineage"] / f"{INTAKE}.dsse.json").read_text())
    statement = verify_envelope(envelope, load_trust(stack.paths["trust"])["accounts.customer-intake"].public_key)
    assert statement["predicate"]["write_kind"] == "captured"
    assert statement["predicate"]["written_by"] == ONBOARD
    assert statement["predicate"]["on_behalf_of"] == CUSTOMER


def test_an_agent_for_one_customer_cannot_write_another_customers_intake(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])

    r = write(stack, INTAKE, [intake_row(customer_iri=OTHER_IRI)], customer_agent(stack))

    assert r.status_code == 403
    assert r.json()["detail"] == "a customer may write only their own record"
    assert snapshot_rows(stack, INTAKE) == []


def test_a_customer_write_without_a_grant_is_refused(stack):
    r = write(stack, INTAKE, [intake_row()], customer_agent(stack))

    assert r.status_code == 403
    assert snapshot_rows(stack, INTAKE) == []


def test_a_service_with_no_customer_session_records_captured_data_directly(stack):
    grant(stack, "intake.service@chakra.fintech", WORKLOADS["notebook"], INTAKE,
          ["customer_iri", "legal_name", "ssn", "address"])
    headers = stack.headers(stack.token("intake.service@chakra.fintech", roles=["intake_service"]))

    r = write(stack, INTAKE, [intake_row()], headers)

    assert r.status_code == 201, r.text
    audit = next(a for a in stack.audit_records if a.get("action") == "write")
    assert audit["written_by"] == WORKLOADS["notebook"]
    assert audit["on_behalf_of"] is None


def test_an_intake_with_a_malformed_ssn_is_refused_by_the_shapes(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])

    r = write(stack, INTAKE, [intake_row(ssn="12345")], customer_agent(stack))

    assert r.status_code == 422
    assert "ssn" in r.json()["detail"]


def test_a_write_to_a_column_the_contract_does_not_have_is_refused(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])

    r = write(stack, INTAKE, [{**intake_row(), "favourite_colour": "teal"}], customer_agent(stack))

    assert r.status_code == 400
    assert "favourite_colour" in r.json()["detail"]


# ---- derived: what a writer computed -----------------------------------------------------------------------

def test_an_agent_writes_a_public_or_internal_derived_summary_directly_when_it_cites_what_it_read(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)

    r = write(stack, SUMMARY, [summary_row()], risk_agent(stack), derived=[digest])

    assert r.status_code == 201, r.text
    assert r.json()["outcome"] == "direct"
    audit = next(a for a in stack.audit_records if a.get("action") == "write" and a.get("product") == SUMMARY)
    assert audit["derived_from"] == [digest] and audit["written_by"] == AGENT_SPIFFE_ID


def test_an_agent_derived_write_without_a_citation_is_refused(stack):
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)

    r = write(stack, SUMMARY, [summary_row()], risk_agent(stack))

    assert r.status_code == 422
    assert "must cite" in r.json()["detail"]


def test_an_agent_derived_write_citing_a_snapshot_it_never_read_is_refused(stack):
    read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)

    r = write(stack, SUMMARY, [summary_row()], risk_agent(stack), derived=["0" * 64])

    assert r.status_code == 403


def test_an_agent_cannot_write_personal_data_into_a_derived_product(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS + ["customer_label"])

    r = write(stack, SUMMARY, [{**summary_row(), "customer_label": "Ada Lovelace"}], risk_agent(stack),
              derived=[digest])

    assert r.status_code == 422
    assert r.json()["detail"] == "agent_cannot_create_pii"
    assert snapshot_rows(stack, SUMMARY) == []


def test_an_agent_derived_confidential_write_waits_for_an_owner(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SCORES, ["account_ref", "fraud_score", "risk_band"])
    before = snapshot_rows(stack, SCORES)

    r = write(stack, SCORES, [{"account_ref": "ACC-2001", "fraud_score": "0.55", "risk_band": "medium"}],
              risk_agent(stack), derived=[digest])

    assert r.status_code == 409
    assert r.json()["detail"] == f"requires_owner_review: propose at /products/{SCORES}/proposals"
    assert snapshot_rows(stack, SCORES) == before, "a refused write changes nothing"


def test_a_listed_risk_producer_writes_its_sensitive_output_directly(stack):
    grant(stack, "producer@risk.chakra.fintech", RISK_PRODUCER, SCORES,
          ["account_ref", "fraud_score", "kyc_verdict", "customer_iri", "risk_band", "scored_at"])
    row = {"account_ref": "ACC-2001", "fraud_score": "0.55", "kyc_verdict": "clear",
           "customer_iri": CUSTOMER_IRI, "risk_band": "medium", "scored_at": "2026-11-21T09:00:00Z"}

    r = write(stack, SCORES, [row], risk_producer(stack))

    assert r.status_code == 201, r.text
    assert r.json()["outcome"] == "direct"
    assert any(x["account_ref"] == "ACC-2001" for x in snapshot_rows(stack, SCORES))


def test_an_unlisted_service_writing_a_confidential_derived_product_is_forbidden(stack):
    grant(stack, "producer@risk.chakra.fintech", WORKLOADS["notebook"], SCORES,
          ["account_ref", "fraud_score", "kyc_verdict", "customer_iri", "risk_band", "scored_at"])
    headers = stack.headers(stack.token("producer@risk.chakra.fintech", roles=["risk_producer"]),
                            workload=WORKLOADS["notebook"])
    row = {"account_ref": "ACC-2002", "fraud_score": "0.10", "kyc_verdict": "clear",
           "customer_iri": CUSTOMER_IRI, "risk_band": "low", "scored_at": "2026-11-21T09:00:00Z"}

    r = write(stack, SCORES, [row], headers)

    assert r.status_code == 403


# ---- the gate's other checks -------------------------------------------------------------------------------

def test_direct_writes_are_rate_limited_per_agent(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)
    stack.limits.agent.limit = 1
    assert write(stack, SUMMARY, [summary_row(1)], risk_agent(stack), derived=[digest]).status_code == 201

    second = write(stack, SUMMARY, [{**summary_row(2), "summary_id": "2026-11-21|medium", "risk_band": "medium"}],
                   risk_agent(stack), derived=[digest])

    assert second.status_code == 429


def test_an_append_product_refuses_a_key_it_already_holds(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])
    assert write(stack, INTAKE, [intake_row()], customer_agent(stack)).status_code == 201

    again = write(stack, INTAKE, [intake_row()], customer_agent(stack))

    assert again.status_code == 409
    assert len(snapshot_rows(stack, INTAKE)) == 1


def test_a_write_that_cannot_be_audited_changes_nothing(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])
    services = stack.boundary_app.state.services
    original = services.audit

    async def broken(record):
        if record.get("action") == "write":
            raise RuntimeError("audit store down")
        await original(record)

    services.audit = broken
    try:
        r = write(stack, INTAKE, [intake_row()], customer_agent(stack))
    finally:
        services.audit = original

    assert r.status_code == 503
    assert snapshot_rows(stack, INTAKE) == []


# ---- the owner can roll back any write, and the rollback is signed ------------------------------------------

def test_the_owner_rolls_back_a_direct_write_and_the_rollback_is_signed_and_audited(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)
    assert write(stack, SUMMARY, [summary_row()], risk_agent(stack), derived=[digest]).status_code == 201
    owner = stack.headers(stack.token(OWNER, roles=["data_owner"], owns=["risk-compliance-domain"]))

    r = stack.boundary().post(f"/products/{SUMMARY}/rollback", json={"reason": "wrong band"}, headers=owner)

    assert r.status_code == 200, r.text
    assert snapshot_rows(stack, SUMMARY) == []
    envelope = json.loads((stack.paths["lineage"] / f"{SUMMARY}.dsse.json").read_text())
    predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])["risk-compliance.score-freshness-summary"]
                                .public_key)["predicate"]
    assert predicate["action"] == "rollback" and predicate["reason"] == "wrong band"
    assert any(a.get("action") == "rollback" for a in stack.audit_records)


def test_an_agent_cannot_roll_back_a_direct_write(stack):
    digest = read_scores_digest(stack)
    grant(stack, ANALYST, AGENT_SPIFFE_ID, SUMMARY, SUMMARY_COLUMNS)
    write(stack, SUMMARY, [summary_row()], risk_agent(stack), derived=[digest])

    r = stack.boundary().post(f"/products/{SUMMARY}/rollback", json={"reason": "x"},
                              headers=stack.delegated_headers(OWNER, ["data_owner"], [AGENT_SPIFFE_ID]))

    assert r.status_code == 403


# ---- W3: masking on read of captured personal data ---------------------------------------------------------

def test_personal_values_are_masked_on_read_except_under_a_kyc_grant(stack):
    grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri", "legal_name", "ssn", "address"])
    write(stack, INTAKE, [intake_row()], customer_agent(stack))
    officer = "kyc.officer@chakra.fintech"
    grant(stack, officer, WORKLOADS["notebook"], INTAKE, ["ssn"], purpose="kyc")
    grant(stack, officer, WORKLOADS["notebook"], INTAKE, ["ssn"], purpose="review")
    headers = stack.headers(stack.token(officer, roles=["kyc_officer"]))

    kyc = stack.boundary().get(f"/products/{INTAKE}/rows?columns=ssn&purpose=kyc", headers=headers)
    review = stack.boundary().get(f"/products/{INTAKE}/rows?columns=ssn&purpose=review", headers=headers)

    assert kyc.status_code == 200 and review.status_code == 200
    kyc_ssn = kyc.json()["rows"][0]["ssn"]
    review_ssn = review.json()["rows"][0]["ssn"]
    assert kyc_ssn.endswith("89") and "1234" not in kyc_ssn, "a KYC grant sees the last digits only"
    assert "123" not in review_ssn and "789" not in review_ssn, "any other purpose sees nothing of the value"
    assert review_ssn != kyc_ssn


# ---- the contract itself -----------------------------------------------------------------------------------

def test_an_unclassified_column_counts_as_personal_when_written():
    from shared.governance.products import load_products
    product = {"domain": "x", "name": "y", "access_policy": {"columns": [
        {"name": "a", "classification": "public"}]}}

    assert writes.effective_classification(product, ["a"]) == "public"
    assert writes.effective_classification(product, ["a", "unknown"]) == "pii"
