"""LIVE CHECK, run inside the agent's network namespace against the compose stack: a delegated token is bound to the
agent's certificate, so the boundary's sidecar refuses it when it is presented with another workload's certificate.

Run by `make agent-check` (it starts the agent in a sleeping mode so this process can share its namespace):
    docker exec -i chakra-agent python - < tools/dev-gateway/check_binding.py

The notebook's certificate is from the same dev CA, so it is a valid client certificate for the sidecar. The refusal
is the binding, not the certificate chain.
"""

import sys

import httpx

AGENT_CERT = ("/certs/risk-review-agent.pem", "/certs/risk-review-agent.key")
NOTEBOOK_CERT = ("/certs-notebook/notebook.pem", "/certs-notebook/notebook.key")
CA = "/certs/ca.pem"
BOUNDARY = "spiffe://chakracommerce.com/ns/boundary/sa/boundary"
PATH = "/products/risk-compliance.risk-scores/rows?columns=customer_iri&purpose=risk-review"


def delegated_token() -> str:
    idp = httpx.post("http://dev-idp:8090/token/risk-analyst", timeout=10).json()["access_token"]
    admin = httpx.Client(base_url="https://localhost:6443", cert=AGENT_CERT, verify=CA, timeout=10)
    minted = admin.post("/v1/svid/jwt-with-user", json={"user_credential": idp, "user_issuer": "http://dev-idp:8090"})
    minted.raise_for_status()
    exchanged = admin.post("/v1/token-exchange", json={"subject_token": minted.json()["token"], "audience": BOUNDARY})
    exchanged.raise_for_status()
    return exchanged.json()["access_token"]


def call(cert, token: str) -> httpx.Response:
    client = httpx.Client(base_url="https://boundary:8444", cert=cert, verify=CA, timeout=10)
    return client.get(PATH, headers={"X-SPIFFE-OBO-Token": token})


def main() -> int:
    token = delegated_token()
    other = call(NOTEBOOK_CERT, token)
    own = call(AGENT_CERT, token)
    print(f"token presented with the notebook's certificate: {other.status_code} {other.text[:120]}")
    print(f"same token with the agent's own certificate:    {own.status_code} {own.text[:120]}")
    if other.status_code == 200:
        print("FAIL: a token bound to the agent was served to the notebook")
        return 1
    if own.status_code == 200:
        print("PASS: refused for the other certificate, and served for the agent's")
        return 0
    if "binding" in other.text.lower() or "certificate" in other.text.lower():
        print("PASS: refused by the binding; the agent's own certificate did not get a grant-free read (see grants)")
        return 0
    print("CHECK: refused for the other certificate; the agent's own call was refused too (check grants)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
