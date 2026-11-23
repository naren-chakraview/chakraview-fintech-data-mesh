"""Subject consent (addendum 2, W7 and W8), through the boundary's gates against a real OPA.

An agent derived a personal value that describes one customer. It is not written: it is proposed to her. Only she can
accept or decline it, with her own identity; the agent that proposed it, another customer, and the domain owner cannot.
Each refusal leaves the customer's record unchanged."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from lineage.trust import load_trust
from lineage.verify import verify_envelope
from shared.semantic.identity import mint_customer_iri
from shared.testing.harness import WORKLOADS, open_proposal_stack

INTAKE = "accounts.customer-intake"
CUSTOMER = "ada@customer.test"
KYC = "K-1001"
OTHER = "grace@customer.test"
OTHER_KYC = "K-2002"
ONBOARD = "spiffe://chakracommerce.com/ns/agents/sa/onboarding-agent"
ANALYST = "risk.analyst@chakra.fintech"
OWNER = "owner@accounts.chakra.fintech"
COLUMNS = ["customer_iri", "legal_name", "ssn", "address"]
IRI = mint_customer_iri(CUSTOMER, KYC)
OTHER_IRI = mint_customer_iri(OTHER, OTHER_KYC)
TYPED = "1 Analytical Way, London"
CANONICAL = "1 ANALYTICAL WAY, LONDON"  # the deterministic stand-in standardizer's output (no external call)


def record(address, customer_iri=IRI):
    return {"customer_iri": customer_iri, "legal_name": "Ada Lovelace", "ssn": "123-45-6789", "address": address}


def agent(stack, customer=CUSTOMER, kyc=KYC):
    return stack.delegated_headers(customer, ["customer"], [ONBOARD], attributes={"kyc_id": kyc})


def customer_token(stack, email=CUSTOMER, kyc=KYC):
    return stack.headers(stack.token(email, roles=["customer"], attributes={"kyc_id": kyc}),
                         workload=WORKLOADS["notebook"])


def write(stack, rows, headers, derived=(), kind=None):
    body = {"rows": rows, "derived_from": list(derived)}
    if kind:
        body["kind"] = kind
    return stack.boundary().post(f"/products/{INTAKE}/writes", json=body, headers=headers)


def intake_rows(stack):
    path = stack.paths["state"] / "products" / f"{INTAKE}.json"
    return json.loads(path.read_text())["rows"] if path.exists() else []


def grant(stack, subject, workload, columns, purpose):
    stack.grants.create(subject=subject, workload_spiffe_id=workload, product_id=INTAKE, columns=list(columns),
                        purpose=purpose, expires_at=stack.now + timedelta(hours=2))


def setup_customer(stack):
    """The customer's typed address is written directly (captured), and the agent reads its own record (customer_iri)
    so it can cite the snapshot its derived value comes from."""
    grant(stack, CUSTOMER, ONBOARD, COLUMNS, "write")
    grant(stack, CUSTOMER, ONBOARD, COLUMNS, "propose")
    grant(stack, CUSTOMER, ONBOARD, ["customer_iri"], "intake-check")
    assert write(stack, [record(TYPED)], agent(stack)).status_code == 201
    read = stack.boundary().get(f"/products/{INTAKE}/rows?columns=customer_iri&purpose=intake-check",
                                headers=agent(stack))
    assert read.status_code == 200, read.text
    return read.json()["snapshot_sha256"]


def propose(stack, digest, address=CANONICAL):
    return stack.boundary().post(f"/products/{INTAKE}/consent-proposals",
                                 json={"rows": [record(address)], "derived_from": [digest]}, headers=agent(stack))


def decide(stack, proposal_id, action, headers, reason=""):
    return stack.boundary().post(f"/products/{INTAKE}/consent-proposals/{proposal_id}/{action}",
                                 json={"reason": reason}, headers=headers)


@pytest.fixture
def stack(tmp_path):
    with open_proposal_stack(tmp_path) as s:
        s.limits.agent.limit = 1000
        s.limits.person.limit = 1000
        yield s


# ---- the derived personal value is a proposal to the customer, not a write ----------------------------------

def test_the_canonical_address_is_not_written_and_the_agent_is_told_to_ask_the_customer(stack):
    digest = setup_customer(stack)

    r = write(stack, [record(CANONICAL)], agent(stack), derived=[digest], kind="derived")

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == f"requires_subject_consent: propose at /products/{INTAKE}/consent-proposals"
    assert intake_rows(stack)[0]["address"] == TYPED, "the record is unchanged by the refused write"


def test_a_consent_proposal_carries_the_value_replaced_and_the_value_proposed(stack):
    digest = setup_customer(stack)

    r = propose(stack, digest)

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending" and body["subject"] == IRI
    assert body["replaces"]["address"] == TYPED
    assert body["proposed"]["address"] == CANONICAL
    assert body["on_behalf_of"] == CUSTOMER and body["actor_chain"] == [ONBOARD]


def test_a_consent_proposal_is_refused_when_the_agent_did_not_read_what_it_cites(stack):
    setup_customer(stack)

    r = propose(stack, "0" * 64)

    assert r.status_code == 403


def test_a_consent_proposal_must_cite_what_it_was_derived_from(stack):
    setup_customer(stack)

    r = stack.boundary().post(f"/products/{INTAKE}/consent-proposals",
                              json={"rows": [record(CANONICAL)], "derived_from": []}, headers=agent(stack))

    assert r.status_code == 422


def test_only_an_agent_acting_for_the_customer_proposes_consent(stack):
    digest = setup_customer(stack)

    r = stack.boundary().post(f"/products/{INTAKE}/consent-proposals",
                              json={"rows": [record(CANONICAL)], "derived_from": [digest]},
                              headers=customer_token(stack))

    assert r.status_code == 403


def test_the_customer_sees_both_values_and_nobody_else_does(stack):
    digest = setup_customer(stack)
    proposal = propose(stack, digest).json()

    mine = stack.boundary().get(f"/products/{INTAKE}/consent-proposals/{proposal['id']}",
                                headers=customer_token(stack))
    theirs = stack.boundary().get(f"/products/{INTAKE}/consent-proposals/{proposal['id']}", headers=agent(stack))

    assert mine.status_code == 200 and mine.json()["replaces"]["address"] == TYPED
    assert theirs.status_code == 403


# ---- only the data subject accepts or declines ----------------------------------------------------------------

def test_the_agent_cannot_accept_its_own_proposal(stack):
    proposal = propose(stack, setup_customer(stack)).json()

    r = decide(stack, proposal["id"], "accept", agent(stack))

    assert r.status_code == 403
    assert intake_rows(stack)[0]["address"] == TYPED


def test_the_domain_owner_cannot_accept_for_the_customer(stack):
    proposal = propose(stack, setup_customer(stack)).json()
    owner = stack.headers(stack.token(OWNER, roles=["data_owner"], owns=["accounts-domain"]),
                          workload=WORKLOADS["notebook"])

    r = decide(stack, proposal["id"], "accept", owner)

    assert r.status_code == 403
    assert intake_rows(stack)[0]["address"] == TYPED


def test_another_customer_cannot_accept(stack):
    proposal = propose(stack, setup_customer(stack)).json()
    other = stack.headers(stack.token(OTHER, roles=["customer"], attributes={"kyc_id": OTHER_KYC}),
                          workload=WORKLOADS["notebook"])

    r = decide(stack, proposal["id"], "accept", other)

    assert r.status_code == 403
    assert intake_rows(stack)[0]["address"] == TYPED


def test_the_customer_accepts_and_the_snapshot_is_signed_with_her_as_acceptor(stack):
    proposal = propose(stack, setup_customer(stack)).json()

    r = decide(stack, proposal["id"], "accept", customer_token(stack))

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert intake_rows(stack)[0]["address"] == CANONICAL
    assert len(intake_rows(stack)) == 1, "the customer's one record is replaced, not duplicated"
    envelope = json.loads((stack.paths["lineage"] / f"{INTAKE}.dsse.json").read_text())
    predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])[INTAKE].public_key)["predicate"]
    assert predicate["action"] == "accept_consent"
    assert predicate["consent"] == "subject"
    assert predicate["accepted_by"] == CUSTOMER
    assert predicate["on_behalf_of"] == CUSTOMER
    assert predicate["actor_chain"] == [ONBOARD]
    assert predicate["write_kind"] == "captured"
    assert predicate["derived_from"]


def test_the_customer_declines_and_the_original_value_stays(stack):
    proposal = propose(stack, setup_customer(stack)).json()

    r = decide(stack, proposal["id"], "decline", customer_token(stack), reason="I prefer what I typed")

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected" and r.json()["reason"] == "I prefer what I typed"
    assert intake_rows(stack)[0]["address"] == TYPED
    assert any(a.get("action") == "reject" and a.get("consent_subject") == IRI for a in stack.audit_records)


def test_an_expired_consent_proposal_changes_nothing(stack):
    proposal = propose(stack, setup_customer(stack)).json()
    stack.now = stack.now + timedelta(days=3)

    r = decide(stack, proposal["id"], "accept", customer_token(stack))

    assert r.status_code == 409
    assert intake_rows(stack)[0]["address"] == TYPED


# ---- the gate's other outcomes -----------------------------------------------------------------------------------

def test_derived_personal_values_for_several_customers_are_still_refused(stack):
    digest = setup_customer(stack)
    risk = stack.delegated_headers(ANALYST, ["risk_analyst"], [WORKLOADS["risk-producer"]])
    rows = [record(CANONICAL), record("2 Other Street", customer_iri=OTHER_IRI)]

    r = write(stack, rows, risk, derived=[digest], kind="derived")

    assert r.status_code == 422
    assert r.json()["detail"] == "agent_cannot_create_pii"


def test_a_domain_that_switches_subject_consent_off_refuses_the_value(tmp_path):
    with open_proposal_stack(tmp_path / "consent-off", extra_intake_rego="subject_consent := false") as stack:
        digest = setup_customer(stack)

        direct = write(stack, [record(CANONICAL)], agent(stack), derived=[digest], kind="derived")
        proposal = propose(stack, digest)

    assert direct.status_code == 422 and direct.json()["detail"] == "agent_cannot_create_pii"
    assert proposal.status_code == 403, "the domain turned consent proposals off"
    assert intake_rows(stack)[0]["address"] == TYPED

