"""D1 and D5: before, an agent's read is recorded as the analyst's notebook. After, the audit names the person,
the agent and the chain, and the agent's read is attributable to both."""

from datetime import timedelta

from _common import (AGENT, ANALYST, ANALYST_ROLES, NOTEBOOK, RISK, after_stack, before_stack, ok, section, show)


def main() -> None:
    section("BEFORE (frozen): an agent acting for an analyst")
    with before_stack() as before:
        before.grants.create(subject=ANALYST, workload_spiffe_id=NOTEBOOK, product_id=RISK,
                             columns=["account_ref", "fraud_score"], purpose="risk-review",
                             expires_at=before.now + timedelta(hours=1))
        # Before delegation existed, the agent could only present the analyst's own token and its own certificate.
        headers = before.headers(before.token(ANALYST, ANALYST_ROLES), workload=NOTEBOOK)
        r = before.client().get(f"/products/{RISK}/rows?columns=account_ref&purpose=risk-review", headers=headers)
        record = before.audit_records[-1]
        show("read status", r.status_code)
        show("audit subject", record["subject"])
        show("audit workload", record["workload_spiffe_id"])
        show("names an agent?", "no field exists for one")
        assert r.status_code == 200 and record["workload_spiffe_id"] == NOTEBOOK
        assert "on_behalf_of" not in record and "actor_chain" not in record
        print("  The read is indistinguishable from the analyst's own notebook.")

    section("AFTER: the same read, delegated through the gateway")
    with after_stack() as after:
        after.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=RISK,
                            columns=["customer_iri", "risk_band", "scored_at"], purpose="risk-review",
                            expires_at=after.now + timedelta(hours=1))
        headers = after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT])
        r = after.boundary().get(
            f"/products/{RISK}/rows?columns=customer_iri,risk_band,scored_at&purpose=risk-review", headers=headers)
        record = after.audit_records[-1]
        show("read status", r.status_code)
        show("audit subject", record["subject"])
        show("audit workload (agent)", record["workload_spiffe_id"])
        show("on_behalf_of", record["on_behalf_of"])
        show("actor_chain", record["actor_chain"])
        show("snapshot_sha256", record["snapshot_sha256"][:16] + "...")
        assert r.status_code == 200
        assert record["workload_spiffe_id"] == AGENT and record["on_behalf_of"] == ANALYST
        assert record["actor_chain"] == [AGENT]
        ok("the audit names the person, the agent and the chain")
        ok("the record cites the snapshot the read returned, so a later proposal can be checked against it")


if __name__ == "__main__":
    main()
