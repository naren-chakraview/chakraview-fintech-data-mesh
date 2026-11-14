"""SPARQL side door: update forms never reach Fuseki, and PII predicates are masked on the way out."""

from datetime import timedelta

import httpx
import pytest

from shared.testing.harness import WORKLOADS, open_stack

RISK = "risk-compliance.risk-scores"
ENDPOINT = "http://fuseki.test/risk_compliance/sparql"
PREFIX = "PREFIX f: <http://jena.apache.org/fintech#>\n"
SUBJECT = "risk.analyst@chakra.fintech"
PURPOSE = "fraud-review"

RESULTS = {
    "head": {"vars": ["email", "score"]},
    "results": {"bindings": [
        {"email": {"type": "literal", "value": "john@acme.com"}, "score": {"type": "literal", "value": "0.91"}},
    ]},
}


@pytest.fixture
def sparql_stack():
    seen = []

    def handler(request):
        seen.append(request.content.decode())
        return httpx.Response(200, json=RESULTS)

    transport = httpx.MockTransport(handler)
    try:
        ctx = open_stack(fuseki_endpoints={"risk-compliance": ENDPOINT}, sparql_transport=transport)
        stack = ctx.__enter__()
    except Exception as exc:  # opa missing
        pytest.skip(f"trust stack unavailable: {exc}")
    try:
        yield stack, seen
    finally:
        ctx.__exit__(None, None, None)


def post(stack, query, extra=None):
    token = stack.token(SUBJECT, roles=["risk_analyst"])
    body = {"query": query, **(extra or {})}
    return stack.boundary().post(f"/products/{RISK}/sparql?purpose={PURPOSE}", json=body,
                                 headers=stack.headers(token))


@pytest.mark.parametrize("query", [
    PREFIX + 'INSERT DATA { <urn:x> f:customerEmail "a@b.c" }',
    PREFIX + "DELETE WHERE { ?s ?p ?o }",
    "LOAD <http://evil.example/x.ttl>",
    "CLEAR ALL",
    "DROP GRAPH <urn:g>",
    "CREATE GRAPH <urn:g>",
])
def test_update_forms_are_refused_before_fuseki(sparql_stack, query):
    stack, seen = sparql_stack
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=[], purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))

    r = post(stack, query)

    assert r.status_code == 400
    assert seen == []


def test_read_is_forwarded_and_pii_is_masked(sparql_stack):
    stack, seen = sparql_stack
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=["email", "score"], purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))

    r = post(stack, PREFIX + "SELECT ?email ?score WHERE { ?c f:customerEmail ?email . ?c f:fraudScore ?score }")

    assert r.status_code == 200
    assert len(seen) == 1
    binding = r.json()["results"]["bindings"][0]
    assert binding["email"]["value"] != "john@acme.com"
    assert binding["email"]["type"] == "literal"
    assert "@" not in binding["email"]["value"]


def test_identity_in_the_body_is_ignored(sparql_stack):
    stack, seen = sparql_stack

    r = post(stack, PREFIX + "SELECT ?email WHERE { ?c f:customerEmail ?email }",
             extra={"user_role": "fraud_analyst", "subject": "someone-else"})

    assert r.status_code == 403  # no grant; the body changed nothing
    assert seen == []
    assert stack.audit_records[-1]["roles"] == ["risk_analyst"]


def test_fuseki_outage_returns_503(sparql_stack):
    stack, seen = sparql_stack
    services = stack.boundary_app.state.services
    original = services.sparql_transport
    services.sparql_transport = httpx.MockTransport(lambda request: httpx.Response(500))
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=["email"], purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))
    try:
        r = post(stack, PREFIX + "SELECT ?email WHERE { ?c f:customerEmail ?email }")
    finally:
        services.sparql_transport = original

    assert r.status_code == 503
    assert "results" not in r.json()
