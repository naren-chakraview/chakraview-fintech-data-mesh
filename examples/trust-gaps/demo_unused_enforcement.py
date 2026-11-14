"""G2 and G3: the masking code had no caller, and approvals changed nothing.

Before: the only path to product data is the snapshot itself, so anyone who can reach storage reads it
        in the clear. The approve step is not in the API (404), and the pending request changes nothing.
After:  reads go through the boundary: no token 401, no grant 403, with a grant masked (and audited),
        and after the grant expires 403 again.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import line, load_before_enforce, load_before_discovery, section  # noqa: E402
from shared.testing.harness import REPO, open_stack  # noqa: E402

PRODUCT = "accounts.account-master"
SNAPSHOT = REPO / "platform/boundary/fixtures" / f"{PRODUCT}.json"


def before() -> None:
    import json
    import os

    from fastapi.testclient import TestClient

    from _loader import before_policy_dir
    from shared.governance.products import load_products
    from shared.testing.harness import local_opa

    with local_opa([before_policy_dir()]) as opa:
        # The frozen modules read OPA_URL when they are first imported, so set it first.
        os.environ["OPA_URL"] = f"{opa}/v1/data/data_mesh/access"
        before_enforce = load_before_enforce()
        discovery = load_before_discovery()
        discovery.data_products.update(load_products(REPO / "domains"))

        print(f"mask_rows is defined in the frozen enforce.py: {hasattr(before_enforce, 'mask_rows')}")
        print("read routes in the frozen discovery API:",
              sorted(route.path for route in discovery.app.routes if "rows" in route.path) or "none")

        snapshot = json.loads(SNAPSHOT.read_text())
        print(f"direct read of the snapshot (no policy, no mask): {snapshot['rows'][0]}")

        client = TestClient(discovery.app)
        created = client.post("/api/access-requests", json={
            "user_id": "analyst@chakra.fintech", "user_role": "analyst",
            "data_product_id": PRODUCT, "action": "read", "justification": "balance review",
        })
        request_id = created.json()["id"]
        print(f"access request {request_id} -> {created.json()['status']}")
        approved = client.post(f"/api/access-requests/{request_id}/approve")
        print(f"approve {request_id} -> {approved.status_code} (no approve route in the frozen API)")
        status = client.get(f"/api/access-requests/{request_id}").json()["status"]
        print(f"request status after the approve attempt: {status}")
        print("reads: unchanged, the snapshot is still readable in the clear.")


def after() -> None:
    from datetime import timedelta as td

    with open_stack() as stack:
        client = stack.boundary()
        analyst_headers = stack.headers(stack.token("analyst@chakra.fintech", roles=["analyst"]))
        url = f"/products/{PRODUCT}/rows?columns=account_id,customer_name,balance&purpose=balance-review"

        r = client.get(url)
        print(f"no token                          -> {r.status_code}")

        r = client.get(url, headers=analyst_headers)
        print(f"verified analyst, no grant        -> {r.status_code} {r.json()['detail']}")

        owner = stack.headers(stack.token("owner@accounts.chakra.fintech", roles=["data_owner"],
                                          owns=["accounts-domain"]))
        discovery = stack.discovery_client()
        created = discovery.post("/api/access-requests", headers=analyst_headers, json={
            "data_product_id": PRODUCT, "justification": "balance review", "purpose": "balance-review",
            "requested_columns": ["account_id", "customer_name", "balance"], "action": "read",
        })
        request_id = created.json()["id"]
        approved = discovery.post(f"/api/access-requests/{request_id}/approve?ttl_days=1", headers=owner)
        print(f"owner approves {request_id}        -> {approved.status_code} grant {approved.json()['grant']['id']}")

        r = client.get(url, headers=analyst_headers)
        print(f"with the grant                    -> {r.status_code}")
        for row in r.json()["rows"][:2]:
            print(f"   masked row: {row}")
        record = stack.audit_records[-1]
        print(f"   audit: decision={record['decision']} grant_id={record['grant_id']} "
              f"strategies={record['strategies']}")

        stack.now = stack.now + td(days=2)
        r = client.get(url, headers=analyst_headers)
        print(f"two days later, grant expired     -> {r.status_code} {r.json()['detail']}")


if __name__ == "__main__":
    line("G2 unused enforcement, G3 grants that go nowhere")
    section("BEFORE (frozen f949583)")
    before()
    section("AFTER (live code)")
    after()
