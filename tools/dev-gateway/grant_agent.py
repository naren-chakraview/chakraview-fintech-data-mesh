"""DEV ONLY: create the grants the risk-review agent needs, in the boundary's grant store (Postgres).

In production an owner approves an access request and the approval creates these grants. This script stands in for
that approval, for the compose demo. It grants the risk analyst's read of the risk scores, for the agent's workload
only, and the agent's propose on the review notes. Run inside the boundary container:

    docker compose exec boundary python /app/tools/dev-gateway/grant_agent.py
"""

from datetime import timedelta

from shared.governance.grants import PostgresGrantStore, utc_now

ANALYST = "risk.analyst@chakra.fintech"
AGENT = "spiffe://chakracommerce.com/ns/agents/sa/risk-review-agent"
HOURS = 8


def main() -> None:
    store = PostgresGrantStore()
    expires = utc_now() + timedelta(hours=HOURS)
    scores = store.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id="risk-compliance.risk-scores",
                          columns=["customer_iri", "risk_band", "scored_at"], purpose="risk-review",
                          expires_at=expires)
    notes = store.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id="risk-compliance.risk-review-notes",
                         columns=[], purpose="propose", expires_at=expires)
    print(f"read grant {scores.id} and propose grant {notes.id}, valid {HOURS}h, for the agent only")


if __name__ == "__main__":
    main()
