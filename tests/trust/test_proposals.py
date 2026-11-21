"""Governed writes, end to end against a real OPA: an agent proposes, the owner decides, and every change is a
signed snapshot. Each refusal is checked to leave the product unchanged."""

import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from lineage.trust import load_trust, verify_product
from lineage.verify import verify_envelope
from proposals import limits as limits_mod
from shared.testing.harness import AGENT_SPIFFE_ID, WORKLOADS, open_proposal_stack

RISK = "risk-compliance.risk-scores"
NOTES = "risk-compliance.risk-review-notes"
ACCOUNTS = "accounts.account-master"
ANALYST = "risk.analyst@chakra.fintech"
OWNER = "owner@risk-compliance.chakra.fintech"
CUSTOMER = "https://chakracommerce.com/customer#48b31b90c7a67e7c08b6ddbb4265d2987aef9c19dbbb1aa3171880347b282339"


def note(note_id="RN-1004", customer=CUSTOMER, band="high", text="Re-score before the next decision.",
         extra="", email=None):
    email_line = f'fintech:email "{email}" ;\n  ' if email else ""
    return f'''@prefix fintech: <https://chakracommerce.com/ontology/fintech/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<https://chakracommerce.com/ontology/fintech/review/{note_id}> a fintech:ReviewNote ;
  fintech:noteId "{note_id}" ;
  fintech:forCustomer <{customer}> ;
  fintech:riskBand "{band}" ;
  fintech:reviewedNote "{text}" ;
  {email_line}fintech:sourceSystem "{AGENT_SPIFFE_ID}" ;
  fintech:sourceIngestionTime "2026-11-20T10:00:00Z"^^xsd:dateTime .
{extra}
'''


@pytest.fixture
def stack(tmp_path):
    """A fresh boundary per test, so each test starts with its own product state."""
    if shutil.which("opa") is None:
        pytest.skip("the opa binary is not on PATH")
    with open_proposal_stack(tmp_path) as s:
        yield s


def agent_grant(stack, columns, purpose, product):
    return stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT_SPIFFE_ID, product_id=product,
                               columns=list(columns), purpose=purpose,
                               expires_at=stack.now + timedelta(hours=1))


def owner_headers(stack):
    return stack.headers(stack.token(OWNER, roles=["data_owner"], owns=["risk-compliance-domain"]))


def agent_headers(stack, chain=(AGENT_SPIFFE_ID,)):
    return stack.delegated_headers(ANALYST, ["risk_analyst"], list(chain))


def read_scores(stack):
    """The agent reads the risk scores through the boundary, which is what lets it cite the snapshot."""
    agent_grant(stack, ["customer_iri", "risk_band", "scored_at"], "risk-review", RISK)
    r = stack.boundary().get(f"/products/{RISK}/rows?columns=customer_iri,risk_band,scored_at&purpose=risk-review",
                             headers=agent_headers(stack))
    assert r.status_code == 200, r.text
    return r.json()["snapshot_sha256"]


def propose(stack, payload, derived, fmt="turtle", chain=(AGENT_SPIFFE_ID,)):
    return stack.boundary().post(f"/products/{NOTES}/proposals",
                                 json={"format": fmt, "payload": payload, "derived_from": derived},
                                 headers=agent_headers(stack, chain))


def with_propose_grant(stack):
    return stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT_SPIFFE_ID, product_id=NOTES,
                               columns=[], purpose="propose", expires_at=stack.now + timedelta(hours=2))


def decide(stack, proposal_id, action, body=None, headers=None):
    client = stack.boundary()
    url = f"/products/{NOTES}/proposals/{proposal_id}/{action}"
    return client.post(url, json=body or {}, headers=headers or owner_headers(stack))


def note_rows(stack, headers=None):
    agent_grant_needed = stack.grants.create(
        subject=ANALYST, workload_spiffe_id=WORKLOADS["notebook"], product_id=NOTES,
        columns=["note_id", "customer_iri", "risk_band", "reviewed_note"], purpose="review-read",
        expires_at=stack.now + timedelta(hours=1))
    assert agent_grant_needed
    return stack.boundary().get(
        f"/products/{NOTES}/rows?columns=note_id,customer_iri,risk_band,reviewed_note&purpose=review-read",
        headers=headers or stack.headers(stack.token(ANALYST, roles=["risk_analyst"])))


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---- the happy path ------------------------------------------------------------------------------------------

def test_agent_proposes_owner_accepts_and_the_signed_snapshot_names_the_chain(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)

    p = propose(stack, note(), [digest])
    assert p.status_code == 201, p.text
    proposal = p.json()
    assert proposal["status"] == "pending"
    assert proposal["on_behalf_of"] == ANALYST
    assert proposal["actor_chain"] == [AGENT_SPIFFE_ID]

    a = decide(stack, proposal["id"], "accept")
    assert a.status_code == 200, a.text
    assert a.json()["status"] == "accepted" and a.json()["decided_by"] == OWNER

    fixture = stack.paths["fixtures"] / f"{NOTES}.json"
    assert [row["note_id"] for row in json.loads(fixture.read_bytes())["rows"]] == ["RN-1004"]
    assert verify_product(NOTES, fixture.read_bytes(), stack.paths["lineage"], load_trust(stack.paths["trust"]))

    envelope = json.loads((stack.paths["lineage"] / f"{NOTES}.dsse.json").read_text())
    statement = verify_envelope(envelope, load_trust(stack.paths["trust"])[NOTES].public_key)
    predicate = statement["predicate"]
    assert predicate["action"] == "accept"
    assert predicate["on_behalf_of"] == ANALYST
    assert predicate["actor_chain"] == [AGENT_SPIFFE_ID]
    assert predicate["accepted_by"] == OWNER
    assert predicate["proposal_id"] == proposal["id"]
    assert predicate["derived_from"] == [{"sha256": digest}]


def test_accepted_note_is_readable_with_verified_lineage(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    decide(stack, proposal["id"], "accept")

    r = note_rows(stack)

    assert r.status_code == 200, r.text
    assert r.json()["lineage_verified"] is True
    assert [row["note_id"] for row in r.json()["rows"]] == ["RN-1004"]
    assert r.json()["rows"][0]["reviewed_note"] != "Re-score before the next decision."


def test_trace_answers_which_agent_for_whom_read_what_proposed_what_and_who_accepted(stack):
    from boundary.audit_trace import trace_proposal
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    decide(stack, proposal["id"], "accept")

    trace = trace_proposal(stack.audit_records, proposal["id"])

    assert trace["agent"] == AGENT_SPIFFE_ID
    assert trace["for_person"] == ANALYST
    assert trace["actor_chain"] == [AGENT_SPIFFE_ID]
    assert [r["snapshot_sha256"] for r in trace["read"]] == [digest]
    assert trace["proposed_rows"] == 1
    assert trace["accepted_by"] == OWNER
    assert trace_proposal(stack.audit_records, "prop_missing") is None


def test_audit_chains_proposal_and_acceptance(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    decide(stack, proposal["id"], "accept")

    propose_record = next(r for r in stack.audit_records if r.get("action") == "propose")
    accept_record = next(r for r in stack.audit_records if r.get("action") == "accept")
    assert propose_record["on_behalf_of"] == ANALYST
    assert propose_record["workload_spiffe_id"] == AGENT_SPIFFE_ID
    assert propose_record["derived_from"] == [digest]
    assert accept_record["accepted_by"] == OWNER
    assert accept_record["proposal_id"] == proposal["id"]
    assert accept_record["derived_from"] == [digest]


# ---- refusals: nothing changes ------------------------------------------------------------------------------

def assert_product_unchanged(stack, before_digest):
    assert stack.writer.current_digest() == before_digest
    assert json.loads((stack.paths["fixtures"] / f"{NOTES}.json").read_bytes())["rows"] == []


def test_citing_a_snapshot_the_agent_never_read_is_refused(stack):
    before = stack.writer.current_digest()
    with_propose_grant(stack)

    p = propose(stack, note(), ["0" * 64])

    assert p.status_code == 403
    assert stack.writer.proposals == {}
    assert_product_unchanged(stack, before)


def test_proposal_without_citations_is_refused(stack):
    with_propose_grant(stack)

    assert propose(stack, note(), []).status_code == 422


def test_unminted_customer_id_is_rejected_by_shacl(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)

    p = propose(stack, note(customer="https://chakracommerce.com/customer#3abeb7cf"), [digest])

    assert p.status_code == 422
    assert "forCustomer" in p.json()["detail"]


def test_deprecated_term_is_rejected_by_the_core_shapes(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)

    p = propose(stack, note(email="someone@example.test"), [digest])

    assert p.status_code == 422
    assert "deprecated" in p.json()["detail"]


def test_unparseable_payload_is_refused(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)

    assert propose(stack, "this is not turtle {{{", [digest]).status_code == 422


def test_oversized_payload_is_refused_before_parsing(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)

    assert propose(stack, "#" * (65 * 1024), [digest]).status_code == 413


def test_proposal_from_the_person_without_a_delegate_is_refused(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    person = stack.headers(stack.token(ANALYST, roles=["risk_analyst"]), workload=WORKLOADS["notebook"])

    p = stack.boundary().post(f"/products/{NOTES}/proposals",
                              json={"payload": note(), "derived_from": [digest]}, headers=person)

    assert p.status_code == 403


def test_an_agent_cannot_accept_its_own_proposal(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()

    delegated_owner = stack.delegated_headers(OWNER, ["data_owner"], [AGENT_SPIFFE_ID])
    a = decide(stack, proposal["id"], "accept", headers=delegated_owner)

    assert a.status_code == 403
    assert stack.writer.get(proposal["id"])["status"] == "pending"


def test_an_agent_cannot_reject_or_roll_back_either(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    delegated_owner = stack.delegated_headers(OWNER, ["data_owner"], [AGENT_SPIFFE_ID])

    assert decide(stack, proposal["id"], "reject", {"reason": "x"}, headers=delegated_owner).status_code == 403
    # A fresh token for each call: a forwarded token is single use, so reusing the first one is a replay.
    fresh_owner = stack.delegated_headers(OWNER, ["data_owner"], [AGENT_SPIFFE_ID])
    r = stack.boundary().post(f"/products/{NOTES}/rollback", json={"reason": "x"}, headers=fresh_owner)
    assert r.status_code == 403


def test_a_risk_analyst_is_not_an_owner(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    analyst = stack.headers(stack.token(ANALYST, roles=["risk_analyst"], owns=[]))

    assert decide(stack, proposal["id"], "accept", headers=analyst).status_code == 403


def test_an_owner_of_another_domain_cannot_accept(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    other = stack.headers(stack.token("owner@accounts.chakra.fintech", roles=["data_owner"],
                                      owns=["accounts-domain"]))

    assert decide(stack, proposal["id"], "accept", headers=other).status_code == 403


def test_a_decided_proposal_cannot_be_decided_again(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    assert decide(stack, proposal["id"], "accept").status_code == 200

    assert decide(stack, proposal["id"], "accept").status_code == 409
    assert decide(stack, proposal["id"], "reject", {"reason": "late"}).status_code == 409


def test_a_rejection_records_its_reason_and_writes_nothing(stack):
    before = stack.writer.current_digest()
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()

    r = decide(stack, proposal["id"], "reject", {"reason": "already covered by RN-0999"})

    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["reason"] == "already covered by RN-0999"
    assert_product_unchanged(stack, before)


def test_a_duplicate_note_id_cannot_be_accepted(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    first = propose(stack, note(), [digest]).json()
    second = propose(stack, note(text="Another note with the same id."), [digest]).json()
    assert decide(stack, first["id"], "accept").status_code == 200

    r = decide(stack, second["id"], "accept")

    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_an_expired_proposal_cannot_be_accepted(stack):
    before = stack.writer.current_digest()
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    stack.now = stack.now + timedelta(days=3)

    r = decide(stack, proposal["id"], "accept")

    assert r.status_code == 409
    assert stack.writer.get(proposal["id"])["status"] == "expired"
    assert_product_unchanged(stack, before)


def test_rate_limit_stops_an_agent_proposing_too_fast(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    stack.limits.agent.limit = 2
    assert propose(stack, note(note_id="RN-2001"), [digest]).status_code == 201
    assert propose(stack, note(note_id="RN-2002"), [digest]).status_code == 201

    r = propose(stack, note(note_id="RN-2003"), [digest])

    assert r.status_code == 429


def test_rollback_restores_the_previous_snapshot_and_is_signed(stack):
    original = stack.writer.current_digest()
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    decide(stack, proposal["id"], "accept")
    accepted = stack.writer.current_digest()
    assert accepted != original

    r = stack.boundary().post(f"/products/{NOTES}/rollback", json={"reason": "wrong customer"},
                              headers=owner_headers(stack))

    assert r.status_code == 200, r.text
    assert r.json()["current_digest"] == original
    assert_product_unchanged(stack, original)
    envelope = json.loads((stack.paths["lineage"] / f"{NOTES}.dsse.json").read_text())
    predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])[NOTES].public_key)["predicate"]
    assert predicate["action"] == "rollback"
    assert predicate["rolled_back_from"] == accepted
    assert predicate["reason"] == "wrong customer"
    assert verify_product(NOTES, (stack.paths["fixtures"] / f"{NOTES}.json").read_bytes(),
                          stack.paths["lineage"], load_trust(stack.paths["trust"]))


def test_rollback_with_nothing_earlier_is_refused(stack):
    r = stack.boundary().post(f"/products/{NOTES}/rollback", json={"reason": "x"}, headers=owner_headers(stack))

    assert r.status_code == 409


def test_a_proposal_that_cannot_be_audited_changes_nothing(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    services = stack.boundary_app.state.services
    original_audit = services.audit

    async def broken(record):
        if record.get("action") == "propose":
            raise RuntimeError("audit store down")
        await original_audit(record)

    services.audit = broken
    try:
        r = propose(stack, note(), [digest])
    finally:
        services.audit = original_audit

    assert r.status_code == 503
    assert stack.writer.proposals == {}


def test_only_the_person_or_the_owner_may_read_a_proposal(stack):
    digest = read_scores(stack)
    with_propose_grant(stack)
    proposal = propose(stack, note(), [digest]).json()
    stranger = stack.headers(stack.token("someone@chakra.fintech", roles=["analyst"]))

    assert stack.boundary().get(f"/products/{NOTES}/proposals/{proposal['id']}", headers=stranger).status_code == 403
    assert stack.boundary().get(f"/products/{NOTES}/proposals/{proposal['id']}",
                                headers=owner_headers(stack)).status_code == 200


def test_products_without_a_writer_take_no_proposals(stack):
    r = stack.boundary().post(f"/products/{RISK}/proposals", json={"payload": "x", "derived_from": ["0"]},
                              headers=agent_headers(stack))

    assert r.status_code == 404


# ---- ledger and limits -------------------------------------------------------------------------------------

def test_ledger_counts_only_allowed_reads_by_this_pair(stack):
    from boundary.ledger import ReadLedger
    ledger = ReadLedger()
    since = stack.now - timedelta(hours=1)
    base = {"action": "read", "decision": "allow", "product": RISK, "subject": ANALYST,
            "workload_spiffe_id": AGENT_SPIFFE_ID, "snapshot_sha256": "a" * 64,
            "timestamp": stack.now.isoformat()}
    ledger.observe(base)
    ledger.observe({**base, "snapshot_sha256": "b" * 64, "decision": "deny"})
    ledger.observe({**base, "snapshot_sha256": "c" * 64, "workload_spiffe_id": WORKLOADS["notebook"]})
    ledger.observe({**base, "snapshot_sha256": "d" * 64, "action": "propose"})

    assert ledger.unread(subject=ANALYST, actor=AGENT_SPIFFE_ID, digests=["a" * 64], since=since) == set()
    assert ledger.unread(subject=ANALYST, actor=AGENT_SPIFFE_ID, digests=["b" * 64, "c" * 64, "d" * 64],
                         since=since) == {"b" * 64, "c" * 64, "d" * 64}
    assert ledger.unread(subject=ANALYST, actor=AGENT_SPIFFE_ID, digests=["a" * 64], since=stack.now + timedelta(hours=1)) == {"a" * 64}


def test_rate_limiter_refuses_without_recording_the_refused_attempt():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    limiter = limits_mod.RateLimiter(2, timedelta(hours=1))
    limiter.take("a", now)
    limiter.take("a", now)
    with pytest.raises(limits_mod.RateLimited):
        limiter.take("a", now)
    limiter.take("a", now + timedelta(hours=2))


def test_payload_parsing_is_size_and_format_bounded():
    from proposals.payload import PayloadError, parse_payload
    with pytest.raises(PayloadError) as exc:
        parse_payload(b"x" * (65 * 1024), "turtle")
    assert exc.value.status == 413
    with pytest.raises(PayloadError) as exc:
        parse_payload(b"<a> <b> <c> .", "xml")
    assert exc.value.status == 400


def test_a_proposal_after_its_grant_expired_is_refused_though_the_agent_saw_the_grant(stack):
    """A9: nothing is remembered. The grant is re-resolved at the moment of the proposal, so one that has expired
    fails even though the agent read through it earlier in the same run and its token is still valid."""
    grant = stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT_SPIFFE_ID, product_id=RISK,
                                columns=["customer_iri", "risk_band", "scored_at"], purpose="risk-review",
                                expires_at=stack.now + timedelta(hours=1))
    stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT_SPIFFE_ID, product_id=NOTES, columns=[],
                        purpose="propose", expires_at=stack.now + timedelta(hours=3))
    read = stack.boundary().get(f"/products/{RISK}/rows?columns=customer_iri,risk_band,scored_at&purpose=risk-review",
                                headers=stack.delegated_headers(ANALYST, ["risk_analyst"], [AGENT_SPIFFE_ID], ttl_seconds=7200))
    assert read.status_code == 200, "the agent saw the grant and read through it"
    digest = read.json()["snapshot_sha256"]

    stack.now = stack.now + timedelta(minutes=90)  # the scores grant has expired; the token has not

    p = stack.boundary().post(f"/products/{NOTES}/proposals",
                              json={"format": "turtle", "payload": note(), "derived_from": [digest]},
                              headers=stack.delegated_headers(ANALYST, ["risk_analyst"], [AGENT_SPIFFE_ID], ttl_seconds=7200))
    assert p.status_code == 403, p.text
    assert grant.id  # the expired grant still exists; it is simply not valid any more
    assert stack.writer.proposals == {}
