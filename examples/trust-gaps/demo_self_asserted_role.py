"""G1: identity is a claim. Before, the request body says who you are. After, a verified token says it.

Before: a body claiming role risk_analyst for a sensitive product is approved, with no human involved.
After:  no token gets 401; a token for an analyst cannot claim risk_analyst in the body (400).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import before_policy_dir, line, load_before_discovery, section  # noqa: E402
from shared.governance.products import load_products  # noqa: E402
from shared.testing.harness import REPO, open_stack  # noqa: E402
from shared.testing.harness import local_opa  # noqa: E402

PRODUCT = "risk-compliance.risk-scores"


def before() -> None:
    from fastapi.testclient import TestClient

    with local_opa([before_policy_dir()]) as opa:
        os.environ["OPA_URL"] = f"{opa}/v1/data/data_mesh/access"
        discovery = load_before_discovery()
        discovery.data_products.update(load_products(REPO / "domains"))
        client = TestClient(discovery.app)
        r = client.post("/api/access-requests", json={
            "user_id": "anyone@example.com",
            "user_role": "risk_analyst",
            "data_product_id": PRODUCT,
            "action": "read",
            "justification": "I am a risk analyst",
        })
        print(f"POST /api/access-requests (body says user_role=risk_analyst) -> {r.status_code} {r.json()}")


def after() -> None:
    with open_stack() as stack:
        client = stack.discovery_client()
        analyst = stack.token("analyst@chakra.fintech", roles=["analyst"])
        body = {"data_product_id": PRODUCT, "action": "read", "justification": "fraud review",
                "requested_columns": ["fraud_score"]}

        r = client.post("/api/access-requests", json=body)
        print(f"no token                                  -> {r.status_code} {r.json()}")

        r = client.post("/api/access-requests", headers=stack.headers(analyst),
                        json={**body, "user_role": "risk_analyst"})
        print(f"analyst token, body claims risk_analyst   -> {r.status_code} {r.json()}")

        r = client.post("/api/access-requests", headers=stack.headers(analyst), json=body)
        print(f"analyst token, no identity in body        -> {r.status_code} status={r.json().get('status')}")
        print("(the decision uses the token's roles: analyst. It needs approval, so it is pending.)")


if __name__ == "__main__":
    line("G1 self-asserted role")
    section("BEFORE (frozen f949583)")
    before()
    section("AFTER (live code)")
    after()
