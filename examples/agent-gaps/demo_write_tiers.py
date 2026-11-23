"""Write tiers (addendum W2 to W6): who decided the data decides whether a human gate applies.

One line per write: the caller, the kind of write, the classification of what was written, the outcome, and who
accepted it. Then the owner rolls one write back. Every write here runs through the same gates, in the same order, as
the boundary runs them for real; the writes are made against temporary copies of the product state.
"""

from datetime import timedelta

from _common import (AGENT, ANALYST, ANALYST_ROLES, DEMO_NOW, NOTEBOOK, OWNER, OWNER_DOMAINS, OWNER_ROLES, after_stack,
                     ok, section, show)
from agent import RiskReviewAgent, review_note_turtle
from channels import StackChannel
import json

from lineage.trust import load_trust
from lineage.verify import verify_envelope
from shared.semantic.identity import mint_customer_iri
from shared.testing.harness import WORKLOADS

INTAKE = "accounts.customer-intake"
SUMMARY = "risk-compliance.score-freshness-summary"
SCORES = "risk-compliance.risk-scores"
NOTES = "risk-compliance.risk-review-notes"
ONBOARD = "spiffe://chakracommerce.com/ns/agents/sa/onboarding-agent"
CUSTOMER = "ada@customer.test"
KYC = "K-1001"
OTHER_CUSTOMER = "grace@customer.test"
OTHER_KYC = "K-2002"
CANONICAL_ADDRESS = "1 ANALYTICAL WAY, LONDON"  # the deterministic stand-in standardizer (no external call)
COLUMNS = ["customer_iri", "legal_name", "ssn", "address"]
SUMMARY_COLUMNS = ["summary_id", "day", "risk_band", "stale_count", "customer_label"]


def line(caller: str, kind: str, classification: str, outcome: str, accepted_by: str) -> None:
    short = "policy:" + accepted_by.split(":", 1)[1][:12] if accepted_by.startswith("policy:") else accepted_by
    print(f"  {caller:<24} {kind:<9} {classification:<12} {outcome:<30} accepted_by={short}")


def write(stack, product: str, rows: list, headers: dict, derived=()):
    return stack.boundary().post(f"/products/{product}/writes", json={"rows": rows, "derived_from": list(derived)},
                                 headers=headers)


def grant(stack, subject, workload, product, columns, purpose="write"):
    stack.grants.create(subject=subject, workload_spiffe_id=workload, product_id=product, columns=list(columns),
                        purpose=purpose, expires_at=stack.now + timedelta(hours=2))


def main() -> None:
    with after_stack() as stack:
        section("THE WRITES")
        print("  caller                   kind      class      outcome                    accepted_by")

        # 1. captured: the customer's onboarding agent writes the customer's own intake, directly.
        grant(stack, CUSTOMER, ONBOARD, INTAKE, COLUMNS)
        intake = [{"customer_iri": mint_customer_iri(CUSTOMER, KYC), "legal_name": "Ada Lovelace",
                   "ssn": "123-45-6789", "address": "1 Analytical Way, London"}]
        r = write(stack, INTAKE, intake, stack.delegated_headers(CUSTOMER, ["customer"], [ONBOARD],
                                                                 attributes={"kyc_id": KYC}))
        assert r.status_code == 201, r.text
        line("onboarding agent", "captured", "pii", r.json()["outcome"], r.json()["accepted_by"])

        # 2. derived, internal: the risk agent writes the freshness summary directly, citing the scores it read.
        grant(stack, ANALYST, AGENT, SCORES, ["customer_iri", "risk_band", "scored_at"], purpose="risk-review")
        read = stack.boundary().get(f"/products/{SCORES}/rows?columns=customer_iri,risk_band,scored_at&purpose=risk-review",
                                    headers=stack.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]))
        assert read.status_code == 200, read.text
        digest = read.json()["snapshot_sha256"]
        grant(stack, ANALYST, AGENT, SUMMARY, SUMMARY_COLUMNS[:4])
        summary = [{"summary_id": "2026-11-21|high", "day": "2026-11-21", "risk_band": "high", "stale_count": 2}]
        r = write(stack, SUMMARY, summary, stack.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]), derived=[digest])
        assert r.status_code == 201, r.text
        line("risk agent", "derived", "internal", r.json()["outcome"], r.json()["accepted_by"])
        summary_snapshot = r.json()["snapshot_sha256"]

        # 3. derived, confidential: the risk agent's review note is a proposal; an owner accepts it.
        channel = StackChannel(stack, ANALYST, ANALYST_ROLES, [AGENT])
        grant(stack, ANALYST, AGENT, NOTES, [], purpose="propose")
        direct = write(stack, NOTES, [{"note_id": "RN-DEMO", "customer_iri": intake[0]["customer_iri"],
                                       "risk_band": "high", "reviewed_note": "Re-score."}],
                       stack.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]), derived=[digest])
        assert direct.status_code == 409, direct.text
        line("risk agent (direct)", "derived", "confidential", "requires_owner_review", "-")
        proposal = channel.post(f"/products/{NOTES}/proposals",
                                json={"format": "turtle", "derived_from": [digest],
                                      "payload": review_note_turtle("RN-DEMO", intake[0]["customer_iri"], "high",
                                                                    "2026-01-15", DEMO_NOW)})
        assert proposal.status_code == 201, proposal.text
        owner = stack.headers(stack.token(OWNER, OWNER_ROLES, owns=OWNER_DOMAINS), workload=NOTEBOOK)
        accepted = stack.boundary().post(f"/products/{NOTES}/proposals/{proposal.json()['id']}/accept", headers=owner)
        assert accepted.status_code == 200, accepted.text
        line("risk agent (proposal)", "derived", "confidential", "proposal", "owner")

        # 4. derived, personal: the risk agent tries to put a name into the summary. Refused.
        bad = write(stack, SUMMARY, [{**summary[0], "customer_label": "Ada Lovelace"}],
                    stack.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]), derived=[digest])
        assert bad.status_code == 422 and bad.json()["detail"] == "agent_cannot_create_pii", bad.text
        line("risk agent", "derived", "pii", "refused: agent_cannot_create_pii", "-")

        # 5. derived, sensitive: the scores service writes its output directly, as a listed producer.
        grant(stack, "producer@risk.chakra.fintech", WORKLOADS["risk-producer"], SCORES,
              ["account_ref", "fraud_score", "kyc_verdict", "customer_iri", "risk_band", "scored_at"])
        row = {"account_ref": "ACC-2001", "fraud_score": "0.55", "kyc_verdict": "clear",
               "customer_iri": intake[0]["customer_iri"], "risk_band": "medium", "scored_at": "2026-11-21T09:00:00Z"}
        r = write(stack, SCORES, [row], stack.headers(stack.token("producer@risk.chakra.fintech",
                                                                 roles=["risk_producer"]),
                                                     workload=WORKLOADS["risk-producer"]))
        assert r.status_code == 201, r.text
        line("scores service", "derived", "sensitive", r.json()["outcome"], r.json()["accepted_by"])

        section("SUBJECT CONSENT: THE CANONICAL ADDRESS IS HERS TO BLESS")
        # The agent reads its own record (its customer_iri) to cite the snapshot its derived address comes from.
        grant(stack, CUSTOMER, ONBOARD, INTAKE, ["customer_iri"], "intake-check")
        grant(stack, CUSTOMER, ONBOARD, INTAKE, COLUMNS, "propose")
        read = stack.boundary().get(f"/products/{INTAKE}/rows?columns=customer_iri&purpose=intake-check",
                                    headers=stack.delegated_headers(CUSTOMER, ["customer"], [ONBOARD],
                                                                    attributes={"kyc_id": KYC}))
        assert read.status_code == 200, read.text
        cited = read.json()["snapshot_sha256"]
        canonical = [{"customer_iri": intake[0]["customer_iri"], "legal_name": "Ada Lovelace",
                      "ssn": "123-45-6789", "address": CANONICAL_ADDRESS}]
        agent_headers = stack.delegated_headers(CUSTOMER, ["customer"], [ONBOARD], attributes={"kyc_id": KYC})
        derived_write = stack.boundary().post(f"/products/{INTAKE}/writes",
                                              json={"rows": canonical, "derived_from": [cited], "kind": "derived"},
                                              headers=agent_headers)
        assert derived_write.status_code == 409, derived_write.text
        line("onboarding agent (direct)", "derived", "pii", "requires_subject_consent", "-")

        proposal = stack.boundary().post(f"/products/{INTAKE}/consent-proposals",
                                         json={"rows": canonical, "derived_from": [cited]},
                                         headers=stack.delegated_headers(CUSTOMER, ["customer"], [ONBOARD],
                                                                         attributes={"kyc_id": KYC}))
        assert proposal.status_code == 201, proposal.text
        pid = proposal.json()["id"]
        line("onboarding agent (consent)", "derived", "pii", "proposal to the customer", "-")
        show("  replaces", proposal.json()["replaces"]["address"])
        show("  proposed", proposal.json()["proposed"]["address"])

        agent_accepts = stack.boundary().post(f"/products/{INTAKE}/consent-proposals/{pid}/accept",
                                              headers=stack.delegated_headers(CUSTOMER, ["customer"], [ONBOARD],
                                                                              attributes={"kyc_id": KYC}))
        assert agent_accepts.status_code == 403, agent_accepts.text
        line("the agent, for her", "accept", "pii", "refused: 403", "-")

        owner = stack.headers(stack.token("owner@accounts.chakra.fintech", OWNER_ROLES, owns=["accounts-domain"]), workload=NOTEBOOK)
        owner_accepts = stack.boundary().post(f"/products/{INTAKE}/consent-proposals/{pid}/accept", headers=owner)
        assert owner_accepts.status_code == 403, owner_accepts.text
        line("domain owner", "accept", "pii", "refused: 403", "-")

        other = stack.headers(stack.token(OTHER_CUSTOMER, ["customer"], attributes={"kyc_id": OTHER_KYC}),
                              workload=NOTEBOOK)
        other_accepts = stack.boundary().post(f"/products/{INTAKE}/consent-proposals/{pid}/accept", headers=other)
        assert other_accepts.status_code == 403, other_accepts.text
        line("another customer", "accept", "pii", "refused: 403", "-")

        hers = stack.headers(stack.token(CUSTOMER, ["customer"], attributes={"kyc_id": KYC}), workload=NOTEBOOK)
        accepted = stack.boundary().post(f"/products/{INTAKE}/consent-proposals/{pid}/accept", headers=hers)
        assert accepted.status_code == 200, accepted.text
        line("the customer herself", "accept", "pii", "accepted", "customer")

        envelope = json.loads((stack.paths["lineage"] / f"{INTAKE}.dsse.json").read_text())
        predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])[INTAKE].public_key)["predicate"]
        show("snapshot accepted_by", predicate["accepted_by"])
        show("snapshot consent", predicate["consent"])
        assert predicate["accepted_by"] == CUSTOMER and predicate["consent"] == "subject"

        # The risk agent's derived write naming several customers' personal data stays refused.
        risk = stack.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT])
        several = [{"customer_iri": intake[0]["customer_iri"], "legal_name": "Ada Lovelace", "ssn": "123-45-6789",
                    "address": "x"},
                   {"customer_iri": mint_customer_iri(OTHER_CUSTOMER, OTHER_KYC), "legal_name": "Grace Hopper",
                    "ssn": "987-65-4321", "address": "y"}]
        several_write = stack.boundary().post(f"/products/{INTAKE}/writes",
                                               json={"rows": several, "derived_from": [cited], "kind": "derived"},
                                               headers=risk)
        assert several_write.status_code == 422, several_write.text
        line("risk agent (several people)", "derived", "pii", "refused: agent_cannot_create_pii", "-")

        section("THE OWNER ROLLS ONE WRITE BACK")
        owner_summary = stack.headers(stack.token(OWNER, OWNER_ROLES, owns=OWNER_DOMAINS), workload=NOTEBOOK)
        rolled = stack.boundary().post(f"/products/{SUMMARY}/rollback", json={"reason": "wrong band"},
                                       headers=owner_summary)
        assert rolled.status_code == 200, rolled.text
        show("summary rolled back to", rolled.json()["current_digest"][:16] + "...")
        show("rolled back from", summary_snapshot[:16] + "...")
        assert rolled.json()["current_digest"] != summary_snapshot

        ok("the customer's own intake went in directly: the customer decided the values")
        ok("the agent's confidential note waited for the owner; the agent's personal write was refused")
        ok("the scores service wrote its sensitive output directly, as a listed producer")
        ok("the owner's rollback is signed and audited, like the write it reverses")
        ok("a personal value the agent derived was blessed by the one person it describes, and no one else could")


if __name__ == "__main__":
    main()
