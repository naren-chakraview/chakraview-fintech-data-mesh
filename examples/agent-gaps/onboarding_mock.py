"""A deterministic mock onboarding agent, for the customer-intake path (addendum W3).

It is scripted, not an LLM, on purpose: the same inputs must give the same outcomes every run, so the test of the
identity rule is reproducible. It acts for one customer, who gave their own identity, and writes intake records:

  1. the customer's own record, as the customer's agent: direct, and it is signed                     -> 201
  2. the same record again: the key is already held (an intake is written once)                       -> 409
  3. another customer's record, as this customer's agent: a customer writes only their own record      -> 403

Run in-process by the test (through a StackChannel), or live through the sidecars (main below, via HttpChannel).
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from shared.semantic.identity import mint_customer_iri  # noqa: E402

INTAKE = "accounts.customer-intake"
ONBOARD = "spiffe://chakracommerce.com/ns/agents/sa/onboarding-agent"
CUSTOMER = "ada@customer.test"
KYC = "K-1001"
OTHER_CUSTOMER = "grace@customer.test"
OTHER_KYC = "K-2002"
RECORD = {"legal_name": "Ada Lovelace", "ssn": "123-45-6789", "address": "1 Analytical Way, London"}

# The steps, in order. Each one is decided first by identity, before anything about the database is assumed:
#   - a record whose customer_iri is not the acting customer's is refused (403), whatever the database holds;
#   - the acting customer's own record is written once: 201 if it is new, 409 if it is already held. Either is the
#     correct answer, and the check reports which one it saw, so it holds on a fresh boundary and on a used one.
OWN, OTHER = "own", "other"
STEPS = [
    ("own record", OWN, {201, 409}),
    ("same record again", OWN, {201, 409}),
    ("another customer's record", OTHER, {403}),
]


def owner_of(customer_iri: str, acting_iri: str) -> str:
    """Whose record a write is, decided from identity alone (no database)."""
    return OWN if customer_iri == acting_iri else OTHER


def intake(customer_iri: str) -> dict:
    return {"rows": [{"customer_iri": customer_iri, **RECORD}]}


def run(channel) -> List[Tuple[str, int, str]]:
    """The fixed script. Returns (step, status, outcome-or-detail) for each step, in order."""
    acting = mint_customer_iri(CUSTOMER, KYC)
    records = {OWN: acting, OTHER: mint_customer_iri(OTHER_CUSTOMER, OTHER_KYC)}
    results = []
    for step, which, _ in STEPS:
        record = records[which]
        if owner_of(record, acting) != which:  # the identity check comes before anything else
            raise AssertionError(f"{step}: the script's own record does not match the customer it acts for")
        response = channel.post(f"/products/{INTAKE}/writes", json=intake(record))
        detail = response.json().get("outcome") if response.status_code == 201 else response.text[:120]
        results.append((step, response.status_code, detail))
    return results


def check(results: List[Tuple[str, int, str]]) -> None:
    """Each step must give one of its allowed outcomes. Anything else names the step that differed."""
    if [step for step, _, _ in results] != [step for step, _, _ in STEPS]:
        raise AssertionError("the intake path did not run the steps in order")
    for (step, status, _), (_, _, allowed) in zip(results, STEPS):
        if status not in allowed:
            raise AssertionError(f"{step}: got {status}, expected one of {sorted(allowed)}")


def main() -> int:
    from channels import HttpChannel
    token = _fetch_customer_token(os.environ["IDP_TOKEN_URL"])
    channel = HttpChannel(
        admin_url=os.environ["ADMIN_URL"], boundary_url=os.environ["BOUNDARY_URL"],
        idp_url=os.environ["IDP_TOKEN_URL"], idp_issuer=os.environ["IDP_ISSUER"],
        agent_spiffe_id=os.environ["AGENT_SPIFFE_ID"], boundary_spiffe_id=os.environ["BOUNDARY_SPIFFE_ID"],
        cert=(os.environ["CLIENT_CERT"], os.environ["CLIENT_KEY"]), ca=os.environ["CA_CERT"], user_token=token,
    )
    _wait_for_sidecar(channel)
    results = run(channel)
    print(json.dumps([{"step": s, "status": st, "outcome": o} for s, st, o in results], indent=2))
    try:
        check(results)
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: the intake path behaved as scripted")
    return 0


def _fetch_customer_token(url: str) -> str:
    import httpx
    response = httpx.post(url, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def _wait_for_sidecar(channel, attempts: int = 60) -> None:
    last = None
    for _ in range(attempts):
        try:
            channel._delegated_token()
            return
        except Exception as exc:  # the sidecar is still starting
            last = exc
            time.sleep(1)
    raise SystemExit(f"the onboarding sidecar did not come up: {last}")


if __name__ == "__main__":
    sys.exit(main())
