"""D2: before, an agent acting for an analyst has the analyst's whole view. After, the effective access is the
intersection: the person's grant, the agent's capability and the product's policy. A grant for the notebook does
not extend to the agent."""

from datetime import timedelta

from _common import AGENT, ANALYST, ANALYST_ROLES, NOTEBOOK, RISK, after_stack, before_stack, ok, section, show


def main() -> None:
    section("BEFORE (frozen): the agent gets the analyst's full view")
    with before_stack() as before:
        before.grants.create(subject=ANALYST, workload_spiffe_id=NOTEBOOK, product_id=RISK,
                             columns=["fraud_score", "kyc_verdict"], purpose="risk-review",
                             expires_at=before.now + timedelta(hours=1))
        headers = before.headers(before.token(ANALYST, ANALYST_ROLES), workload=NOTEBOOK)
        r = before.client().get(f"/products/{RISK}/rows?columns=fraud_score,kyc_verdict&purpose=risk-review",
                                headers=headers)
        show("agent reads kyc_verdict", r.status_code)
        assert r.status_code == 200
        print("  kyc_verdict is the analyst's column. An agent using the analyst's token reads it, because the")
        print("  boundary cannot tell an agent from the analyst's own notebook.")

    section("AFTER: effective access = person's grant AND agent capability AND product policy")
    with after_stack() as after:
        after.grants.create(subject=ANALYST, workload_spiffe_id=NOTEBOOK, product_id=RISK,
                            columns=["kyc_verdict"], purpose="risk-review",
                            expires_at=after.now + timedelta(hours=1))
        direct = after.boundary().get(f"/products/{RISK}/rows?columns=kyc_verdict&purpose=risk-review",
                                      headers=after.headers(after.token(ANALYST, ANALYST_ROLES),
                                                            workload=NOTEBOOK))
        show("analyst, own notebook", direct.status_code)
        assert direct.status_code == 200

        via_agent = after.boundary().get(f"/products/{RISK}/rows?columns=kyc_verdict&purpose=risk-review",
                                         headers=after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]))
        show("agent for analyst, kyc", via_agent.status_code)
        assert via_agent.status_code == 403

        notebook_grant_only = after.boundary().get(
            f"/products/{RISK}/rows?columns=customer_iri&purpose=risk-review",
            headers=after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]))
        show("agent, notebook grant only", notebook_grant_only.status_code)
        assert notebook_grant_only.status_code == 403

        after.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=RISK,
                            columns=["customer_iri", "risk_band"], purpose="risk-review",
                            expires_at=after.now + timedelta(hours=1))
        allowed = after.boundary().get(f"/products/{RISK}/rows?columns=customer_iri,risk_band&purpose=risk-review",
                                       headers=after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]))
        show("agent, its own grant", allowed.status_code)
        assert allowed.status_code == 200

        ok("the analyst reads kyc_verdict directly; the agent acting for them does not")
        ok("a grant for the notebook is not a grant for the agent")
        ok("the agent sees only the columns its domain lists for agents")


if __name__ == "__main__":
    main()
